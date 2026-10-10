import asyncio
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import httpx
import numpy as np
# pyrefly: ignore [missing-import]
from faster_whisper import WhisperModel
import websockets
import json

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import STTError

logger = get_logger(__name__)

# ------------------------------------------------------------------
# CLOUD STT ENGINE (DEEPGRAM NOVA-2)
# Uncomment to use Cloud APIs.
# ------------------------------------------------------------------
class CloudSTTEngine:
    """
    Cloud STT Engine using Deepgram Nova-2.
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.DEEPGRAM_API_KEY or os.getenv("DEEPGRAM_API_KEY")
        self.model = "nova-2"

    async def transcribe(self, pcm_audio: bytes, sample_rate: int = 8000) -> str:
        if not pcm_audio:
            return ""
            
        url = f"https://api.deepgram.com/v1/listen?model={self.model}&smart_format=true&encoding=linear16&sample_rate={sample_rate}&channels=1"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/x-raw"
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, content=pcm_audio, timeout=10.0)
            if response.status_code != 200:
                raise STTError(f"Deepgram STT failed: {response.text}")
            data = response.json()
            transcript = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            return transcript.strip()
        except Exception as e:
            logger.error(f"Deepgram STT error: {e}")
            return ""

class DeepgramStreamingClient:
    """
    Manages a continuous WebSocket connection to Deepgram for real-time streaming STT.
    """
    def __init__(self, sample_rate: int = 16000, encoding: str = None):
        self.settings = get_settings()
        self.api_key = self.settings.DEEPGRAM_API_KEY or os.getenv("DEEPGRAM_API_KEY")
        self.sample_rate = sample_rate
        # Browser MediaRecorder sends audio/webm;codecs=opus blobs.
        # Deepgram streaming auto-detects webm from the EBML header in the first chunk.
        # Do NOT use encoding= — that tells Deepgram to expect raw codec frames, not a container.
        # endpointing=300 gives snappy 300ms VAD silence detection.
        # utterance_end_ms=1000 acts as a reliable fallback word-gap boundary detector when ambient noise prevents VAD silence.
        self.url = (
            "wss://api.deepgram.com/v1/listen"
            "?model=nova-2"
            "&channels=1"
            "&vad_events=true"
            "&endpointing=300"
            "&utterance_end_ms=1000"
            "&interim_results=true"
            "&smart_format=true"
            "&keepalive=true"
        )
        if encoding:
            self.url += f"&encoding={encoding}&sample_rate={sample_rate}"
            
        self.ws = None
        self._closed = False

    async def connect(self):
        if not self.api_key:
            raise STTError("DEEPGRAM_API_KEY is not set for streaming STT.")
        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            try:
                self.ws = await websockets.connect(self.url, additional_headers=headers)
            except TypeError:
                self.ws = await websockets.connect(self.url, extra_headers=headers)
            logger.info(f"Deepgram Streaming WebSocket connected. URL: {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram streaming WS: {e}")
            raise STTError(f"WebSocket connection failed: {e}")

    @property
    def is_connected(self) -> bool:
        return self.ws is not None and not self._closed

    async def keepalive(self):
        """Send Deepgram KeepAlive to prevent idle timeout (~10s)."""
        if self.ws and not self._closed:
            try:
                await self.ws.send(json.dumps({"type": "KeepAlive"}))
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Deepgram WS closed during keepalive.")
                self.ws = None
                self._closed = True

    async def send_audio(self, pcm_data: bytes):
        if self.ws and not self._closed:
            try:
                await self.ws.send(pcm_data)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Deepgram WS closed while sending — marking connection as dead.")
                self.ws = None
                self._closed = True
                
    async def receive_results(self):
        if not self.ws:
            logger.warning("[Deepgram] receive_results called but self.ws is None — returning immediately.")
            return
        logger.info("[Deepgram] receive_results: starting WebSocket read loop.")
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning(f"[Deepgram] Non-JSON message: {message[:100]}")
                    continue

                msg_type = data.get("type", "unknown")

                if msg_type == "Results":
                    is_final = data.get("is_final", False)
                    speech_final = data.get("speech_final", False)
                    channels = data.get("channel", {})
                    alternatives = channels.get("alternatives", [{}])
                    transcript = alternatives[0].get("transcript", "")
                    words = alternatives[0].get("words", [])
                    
                    wpm = None
                    if is_final and words and len(words) >= 3:
                        try:
                            start_time = words[0].get("start", 0)
                            end_time = words[-1].get("end", 0)
                            duration_secs = end_time - start_time
                            if duration_secs > 0:
                                wpm = (len(words) / duration_secs) * 60.0
                        except Exception:
                            pass

                    if transcript:
                        logger.info(f"[Deepgram] Transcript: '{transcript}' | wpm={wpm} | speech_final={speech_final}")
                    else:
                        logger.debug(f"[Deepgram] Empty result | is_final={is_final} speech_final={speech_final}")

                    yield {
                        "text": transcript.strip(),
                        "is_final": is_final,
                        "speech_final": speech_final,
                        "wpm": wpm
                    }

                elif msg_type == "Metadata":
                    logger.info(f"[Deepgram] Metadata: {data}")

                elif msg_type == "Error":
                    logger.error(f"[Deepgram] ERROR: {data}")
                    self._closed = True
                    self.ws = None
                    break

                elif msg_type == "SpeechStarted":
                    logger.info("[Deepgram] SpeechStarted — user is speaking.")

                elif msg_type == "UtteranceEnd":
                    logger.info("[Deepgram] UtteranceEnd — treating as speech_final for accumulated text.")
                    # Yield a speech_final=True signal so _stt_receiver_task flushes its buffer
                    yield {
                        "text": "",
                        "is_final": True,
                        "speech_final": True,
                        "utterance_end": True
                    }

                else:
                    logger.info(f"[Deepgram] Unknown message type='{msg_type}': {str(data)[:200]}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"[Deepgram] WS closed. Code={getattr(e, 'code', '?')} Reason={getattr(e, 'reason', '?')}")
            self._closed = True
            self.ws = None
        except Exception as e:
            logger.error(f"[Deepgram] Error receiving: {e}")
            self._closed = True
            self.ws = None

    async def close(self):
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Could not cleanly close Deepgram WS: {e}")
            self.ws = None
            logger.info("Deepgram Streaming WebSocket closed.")


# ------------------------------------------------------------------
# LOCAL STT ENGINE (faster-whisper)
# Currently Active.
# ------------------------------------------------------------------
class LocalSTTEngine:
    """
    Faster-Whisper implementation for Speech-to-Text.
    Strictly configured for CPU (int8 compute type).
    """
    
    def __init__(self):
        try:
            settings = get_settings()
            stt_model = getattr(settings, 'STT_MODEL', "small.en")
            stt_device = getattr(settings, 'STT_DEVICE', "cpu")
            stt_compute_type = getattr(settings, 'STT_COMPUTE_TYPE', "int8")
            stt_cpu_threads = getattr(settings, 'STT_CPU_THREADS', 4)
            
            self.model = WhisperModel(
                model_size_or_path=stt_model,
                device=stt_device,
                compute_type=stt_compute_type,
                cpu_threads=stt_cpu_threads
            )
        except Exception as e:
            logger.error(f"Failed to initialize STTEngine: {e}")
            raise STTError(f"STT Model initialization failed: {e}")

    def _resample(self, audio_array: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        if orig_sr == target_sr:
            return audio_array
            
        duration = len(audio_array) / orig_sr
        target_len = int(duration * target_sr)
        
        x_old = np.linspace(0, duration, len(audio_array))
        x_new = np.linspace(0, duration, target_len)
        
        resampled_array = np.interp(x_new, x_old, audio_array)
        return resampled_array
        
    def _transcribe_sync(self, audio_float32: np.ndarray) -> str:
        try:
            segments, info = self.model.transcribe(audio_float32, beam_size=5)
            text = " ".join([segment.text for segment in segments])
            return text.strip()
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise STTError(f"Transcription error: {e}")

    async def transcribe(self, pcm_audio: bytes, sample_rate: int = 8000) -> str:
        if not pcm_audio:
            return ""
            
        try:
            audio_int16 = np.frombuffer(pcm_audio, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            
            if sample_rate != 16000:
                audio_float32 = self._resample(audio_float32, orig_sr=sample_rate, target_sr=16000)
            
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._transcribe_sync, audio_float32)
            
            return text
        except Exception as e:
            logger.error(f"Error processing audio for STT: {e}")
            raise STTError(f"STT processing failed: {e}")

class STTEngine:
    """
    Factory interface that delegates to either CloudSTTEngine or LocalSTTEngine
    based on the USE_CLOUD_LLM setting.
    """
    def __init__(self):
        settings = get_settings()
        if settings.USE_CLOUD_STT:
            self._engine = CloudSTTEngine()
        else:
            self._engine = LocalSTTEngine()

    async def transcribe(self, pcm_audio: bytes, sample_rate: int = 8000) -> str:
        return await self._engine.transcribe(pcm_audio, sample_rate)
