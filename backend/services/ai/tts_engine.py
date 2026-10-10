import asyncio
import re
try:
    import audioop
except ImportError:
    import audioop_lts as audioop
import subprocess
from typing import AsyncGenerator
import os
import hashlib

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import TTSError

import numpy as np

logger = get_logger(__name__)

async def handle_ssml_and_synthesize(text: str, synthesize_func) -> bytes:
    """Parses <break> tags and strips other SSML tags, synthesizing chunks with silent pauses."""
    
    # Only honor explicit <break> tags written by the LLM.
    # Do NOT auto-inject breaks on commas or ellipses — that causes unnatural robotic pacing.
    break_pattern = re.compile(r'(<break\s+time=["\']?\d+(?:\.\d+)?(?:s|ms)["\']?\s*/?>)')
    parts = break_pattern.split(text)
    
    final_audio = bytearray()
    
    for part in parts:
        if not part:
            continue
            
        part_clean = part.strip().lower()
        if part_clean.startswith('<break'):
            time_match = re.search(r'time=["\']?(\d+(?:\.\d+)?)(s|ms)["\']?', part_clean)
            if time_match:
                time_val = float(time_match.group(1))
                unit = time_match.group(2)
                duration_seconds = time_val if unit == 's' else time_val / 1000.0
                
                # 8000 Hz, 16-bit PCM (2 bytes per sample)
                num_samples = int(8000 * duration_seconds)
                num_bytes = num_samples * 2
                final_audio.extend(b'\x00' * num_bytes)
        else:
            clean_text = re.sub(r'<[^>]+>', '', part).strip()
            if clean_text:
                audio_bytes = await synthesize_func(clean_text)
                final_audio.extend(audio_bytes)
                
    return bytes(final_audio)

async def handle_ssml_and_synthesize_stream(text: str, synthesize_func_stream) -> AsyncGenerator[bytes, None]:
    """Parses <break> tags and strips other SSML tags, yielding chunks with silent pauses."""
    
    break_pattern = re.compile(r'(<break\s+time=["\']?\d+(?:\.\d+)?(?:s|ms)["\']?\s*/?>)')
    parts = break_pattern.split(text)
    
    for part in parts:
        if not part:
            continue
            
        part_clean = part.strip().lower()
        if part_clean.startswith('<break'):
            time_match = re.search(r'time=["\']?(\d+(?:\.\d+)?)(s|ms)["\']?', part_clean)
            if time_match:
                time_val = float(time_match.group(1))
                unit = time_match.group(2)
                duration_seconds = time_val if unit == 's' else time_val / 1000.0
                
                # 8000 Hz, 16-bit PCM (2 bytes per sample)
                num_samples = int(8000 * duration_seconds)
                num_bytes = num_samples * 2
                
                # Yield silence in chunks of 1024 bytes
                chunk_size = 1024
                for i in range(0, num_bytes, chunk_size):
                    yield b'\x00' * min(chunk_size, num_bytes - i)
        else:
            clean_text = re.sub(r'<[^>]+>', '', part).strip()
            if clean_text:
                async for chunk in synthesize_func_stream(clean_text):
                    yield chunk

# ------------------------------------------------------------------
# CLOUD TTS ENGINE (DEEPGRAM AURA)
# Uncomment to use Cloud APIs.
# ------------------------------------------------------------------
import httpx
def normalize_tts_text(text: str) -> str:
    text = re.sub(r'>\s*(\d+)', r'more than \1', text)
    text = re.sub(r'<\s*(\d+)', r'less than \1', text)
    return text

class CloudTTSEngine:
    """
    Cloud TTS Engine using ElevenLabs API for ultra-low latency human voices.
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.ELEVENLABS_API_KEY or os.getenv("ELEVENLABS_API_KEY", "")
        self.voice = "uYXf8XasLslADfZ2MB4u"
        
        self.target_sample_rate = 24000
        self.url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice}/stream?output_format=pcm_24000"
        self.chunk_size = 4096
        self.sentence_regex = re.compile(r'([.!?;:\n,]+)')
        
        # Setup local disk cache for TTS sentences
        self.cache_dir = os.path.join(os.getcwd(), ".cache", "tts_eleven")
        os.makedirs(self.cache_dir, exist_ok=True)

    async def synthesize_stream(self, token_stream: AsyncGenerator[str, None], interruption_event: asyncio.Event = None) -> AsyncGenerator[bytes, None]:
        buffer = ""
        try:
            async for token in token_stream:
                buffer += token
                if self.sentence_regex.search(buffer):
                    parts = self.sentence_regex.split(buffer)
                    complete_sentences = ""
                    new_buffer = ""
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i] + parts[i+1]
                        complete_sentences += sentence
                    if len(parts) % 2 != 0:
                        new_buffer = parts[-1]
                    if complete_sentences.strip():
                        audio_data = await self._synthesize_sentence(complete_sentences.strip())
                        for i in range(0, len(audio_data), self.chunk_size):
                            if interruption_event and interruption_event.is_set():
                                return
                            chunk = audio_data[i:i + self.chunk_size]
                            if len(chunk) == self.chunk_size:
                                yield chunk
                            else:
                                yield chunk + b'\x00' * (self.chunk_size - len(chunk))
                    buffer = new_buffer
            if buffer.strip() and not (interruption_event and interruption_event.is_set()):
                audio_data = await self._synthesize_sentence(buffer.strip())
                for i in range(0, len(audio_data), self.chunk_size):
                    if interruption_event and interruption_event.is_set():
                        break
                    chunk = audio_data[i:i + self.chunk_size]
                    if len(chunk) == self.chunk_size:
                        yield chunk
                    else:
                        yield chunk + b'\x00' * (self.chunk_size - len(chunk))
        except Exception as e:
            logger.error(f"ElevenLabs TTS streaming failed: {e}")

    async def _synthesize_sentence(self, text: str) -> bytes:
        async def _do_synth(t):
            t = normalize_tts_text(t)
            t_hash = hashlib.sha256((t.lower().strip() + self.voice).encode('utf-8')).hexdigest()
            cache_path = os.path.join(self.cache_dir, f"{t_hash}.pcm")
            
            if os.path.exists(cache_path):
                logger.info(f"[TTS Cache Hit] '{t}'")
                with open(cache_path, "rb") as f:
                    return f.read()
                    
            logger.info(f"[TTS Cache Miss] Synthesizing: '{t}'")
            headers = {
                "xi-api-key": f"{self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "text": t,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.35,
                    "similarity_boost": 0.70,
                    "use_speaker_boost": True
                }
            }
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.url, headers=headers, json=payload, timeout=10.0)
                if response.status_code != 200:
                    raise TTSError(f"ElevenLabs TTS failed: {response.text}")
                
                audio_bytes = response.content
                if audio_bytes:
                    with open(cache_path, "wb") as f:
                        f.write(audio_bytes)
                return audio_bytes
            except Exception as e:
                logger.error(f"ElevenLabs Synthesis error: {e}")
                return b""
                
        return await handle_ssml_and_synthesize(text, _do_synth)

    async def _synthesize_sentence_stream(self, text: str, use_cache: bool = True) -> AsyncGenerator[bytes, None]:
        async def _do_synth_stream(t):
            t = normalize_tts_text(t)
            t_hash = hashlib.sha256((t.lower().strip() + self.voice).encode('utf-8')).hexdigest()
            cache_path = os.path.join(self.cache_dir, f"{t_hash}.pcm")
            
            if use_cache and os.path.exists(cache_path):
                logger.info(f"[TTS Stream Cache Hit] '{t}'")
                with open(cache_path, "rb") as f:
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        yield chunk
                return
                
            logger.info(f"[{'TTS Stream Cache Miss' if use_cache else 'TTS Synthesizing'}] '{t}'")
            headers = {
                "xi-api-key": f"{self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "text": t,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.55,
                    "similarity_boost": 0.80,
                    "use_speaker_boost": True
                }
            }
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", self.url, headers=headers, json=payload, timeout=10.0) as response:
                        if response.status_code != 200:
                            err = await response.aread()
                            raise TTSError(f"ElevenLabs TTS failed: {err}")
                        
                        if use_cache:
                            with open(cache_path, "wb") as f:
                                async for chunk in response.aiter_bytes(chunk_size=4096):
                                    f.write(chunk)
                                    yield chunk
                        else:
                            async for chunk in response.aiter_bytes(chunk_size=4096):
                                yield chunk
            except Exception as e:
                logger.error(f"ElevenLabs Stream Synthesis error: {e}")
                
        async for chunk in handle_ssml_and_synthesize_stream(text, _do_synth_stream):
            yield chunk


# ------------------------------------------------------------------
# LOCAL TTS ENGINE (Kokoro-ONNX)
# Currently Active.
# ------------------------------------------------------------------
class LocalTTSEngine:
    """
    Kokoro-ONNX implementation for Text-to-Speech.
    High-quality, CPU-friendly alternative to Piper.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.kokoro_dir = os.path.join(os.getcwd(), "models", "kokoro")
        self.model_path = os.path.join(self.kokoro_dir, "kokoro-v1.0.onnx")
        self.voices_path = os.path.join(self.kokoro_dir, "voices-v1.0.bin")
        self.source_sample_rate = 24000  # Kokoro native
        self.target_sample_rate = 16000   # Standardized PCM target
        self.chunk_size = 160
        self.sentence_regex = re.compile(r'([.!?;:\n]+)')
        self.voice_name = "am_michael" # Male American voice
        
        self.kokoro = None

    def _init_model(self):
        if not self.kokoro:
            # pyrefly: ignore [missing-import]
            from kokoro_onnx import Kokoro
            logger.info("Initializing Kokoro ONNX TTS model...")
            if not os.path.exists(self.model_path):
                raise TTSError(f"Kokoro model not found at {self.model_path}. Run download_kokoro.py first.")
            self.kokoro = Kokoro(self.model_path, self.voices_path)

    async def synthesize_stream(self, token_stream: AsyncGenerator[str, None], interruption_event: asyncio.Event = None) -> AsyncGenerator[bytes, None]:
        self._init_model()
        buffer = ""
        try:
            async for token in token_stream:
                buffer += token
                if self.sentence_regex.search(buffer):
                    parts = self.sentence_regex.split(buffer)
                    new_buffer = ""
                    
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i] + parts[i+1]
                        
                        if sentence.strip():
                            audio_data = await self._synthesize_sentence(sentence.strip())
                            for j in range(0, len(audio_data), self.chunk_size):
                                if interruption_event and interruption_event.is_set():
                                    logger.info("TTS Stream Interrupted by VAD Barge-in.")
                                    return
                                chunk = audio_data[j:j + self.chunk_size]
                                if len(chunk) == self.chunk_size:
                                    yield chunk
                                else:
                                    yield chunk + b'\x00' * (self.chunk_size - len(chunk))
                        
                    if len(parts) % 2 != 0:
                        new_buffer = parts[-1]
                                
                    buffer = new_buffer
                    
            if buffer.strip() and not (interruption_event and interruption_event.is_set()):
                audio_data = await self._synthesize_sentence(buffer.strip())
                for i in range(0, len(audio_data), self.chunk_size):
                    if interruption_event and interruption_event.is_set():
                        break
                    chunk = audio_data[i:i + self.chunk_size]
                    if len(chunk) == self.chunk_size:
                        yield chunk
                    else:
                        yield chunk + b'\x00' * (self.chunk_size - len(chunk))
                        
        except Exception as e:
            logger.error(f"Error in TTS synthesis stream: {str(e)}")
            raise TTSError(f"TTS streaming failed: {str(e)}") from e

    def _clean_text_for_tts(self, text: str) -> str:
        # Minimal cleaning needed for Kokoro compared to Piper
        text = text.replace(" / ", " or ")
        text = text.replace("/", " or ")
        text = text.replace("&", " and ")
        text = text.replace("Sir/Mam", "Sir or Ma'am")
        text = text.replace("Mr/Ms", "Mister or Missus")
        
        # Clean up double spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    async def _synthesize_sentence(self, text: str) -> bytes:
        self._init_model()
        
        async def _do_synth(t):
            clean_text = self._clean_text_for_tts(t)
            try:
                logger.debug(f"Running Kokoro TTS for text: {clean_text}")
                
                def _run_kokoro():
                    # generate samples (numpy array of floats)
                    samples, _ = self.kokoro.create(clean_text, voice=self.voice_name, speed=1.15, lang="en-us")
                    return samples
                    
                samples = await asyncio.to_thread(_run_kokoro)
                
                if samples is None or len(samples) == 0:
                    return b""
                    
                # Convert float32 array (-1.0 to 1.0) to 16-bit PCM bytes
                pcm_16 = (samples * 32767).astype(np.int16).tobytes()
                
                # Resample from 24000Hz down to 8000Hz for Asterisk
                resampled_data, _ = audioop.ratecv(
                    pcm_16, 2, 1, self.source_sample_rate, self.target_sample_rate, None
                )
                return resampled_data
                    
            except Exception as e:
                import traceback
                err_trace = traceback.format_exc()
                logger.error(f"Exception during Kokoro TTS synthesis: {err_trace}")
                raise TTSError(f"Synthesis error: {str(e)}") from e

        return await handle_ssml_and_synthesize(text, _do_synth)

    async def _synthesize_sentence_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        # Local Kokoro processes the full sentence at once anyway.
        # We just yield the resulting bytes in chunks to mimic a stream.
        async def _do_synth_stream(t):
            full_audio = await self._synthesize_sentence(t)
            if full_audio:
                chunk_size = 1024
                for i in range(0, len(full_audio), chunk_size):
                    yield full_audio[i:i+chunk_size]
                    await asyncio.sleep(0.001) # Yield to event loop
                    
        async for chunk in handle_ssml_and_synthesize_stream(text, _do_synth_stream):
            yield chunk

class TTSEngine:
    """
    Factory interface that delegates to either CloudTTSEngine or LocalTTSEngine
    based on the USE_CLOUD_LLM setting.
    """
    def __init__(self):
        settings = get_settings()
        if settings.USE_CLOUD_TTS:
            self._engine = CloudTTSEngine()
        else:
            self._engine = LocalTTSEngine()

    async def synthesize_stream(self, token_stream: AsyncGenerator[str, None], interruption_event: asyncio.Event = None) -> AsyncGenerator[bytes, None]:
        async for chunk in self._engine.synthesize_stream(token_stream, interruption_event):
            yield chunk

    async def _synthesize_sentence(self, text: str) -> bytes:
        return await self._engine._synthesize_sentence(text)

    async def _synthesize_sentence_stream(self, text: str, use_cache: bool = True) -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in self._engine._synthesize_sentence_stream(text, use_cache=use_cache):
                yield chunk
        except TypeError:
            async for chunk in self._engine._synthesize_sentence_stream(text):
                yield chunk
