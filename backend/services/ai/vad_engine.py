import asyncio
import numpy as np
# pyrefly: ignore [missing-import]
import torch
from typing import AsyncGenerator

from core.logging import get_logger
from core.exceptions import AIServiceError

logger = get_logger(__name__)

class VADEngine:
    """
    Silero VAD implementation for Voice Activity Detection.
    Detects when a user starts and stops speaking in a continuous audio stream.
    Optimized for CPU inference.
    """
    
    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        # Use torch.set_num_threads(1) to avoid CPU thrashing since VAD is lightweight.
        torch.set_num_threads(1)
        
        try:
            self.model, self.utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            self.get_speech_timestamps = self.utils[0]
        except Exception as e:
            logger.error(f"Failed to load Silero VAD model: {e}")
            raise AIServiceError(f"VAD model initialization failed: {e}")

    def _resample(self, pcm_data: bytes, orig_sr: int, target_sr: int) -> bytes:
        """Utility to resample raw PCM if needed using numpy basic interpolation."""
        if orig_sr == target_sr:
            return pcm_data
            
        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        
        # Simple nearest-neighbor/linear interpolation for resampling
        duration = len(audio_array) / orig_sr
        target_len = int(duration * target_sr)
        
        x_old = np.linspace(0, duration, len(audio_array))
        x_new = np.linspace(0, duration, target_len)
        
        resampled_array = np.interp(x_new, x_old, audio_array).astype(np.int16)
        return resampled_array.tobytes()

    async def process_stream(self, audio_chunk_stream: AsyncGenerator[bytes, None], interruption_event: asyncio.Event = None, on_speech_start = None) -> AsyncGenerator[bytes, None]:
        """
        Takes a stream of raw PCM chunks (16kHz).
        Buffers them into 512-sample (1024 byte) chunks for Silero VAD.
        Yields concatenated audio buffers containing only the segmented speech (when speech ends).
        """
        speech_started = False
        silence_chunks = 0
        MAX_SILENCE_CHUNKS = 5 # ~160ms of silence
        
        raw_buffer = bytearray()
        speech_buffer = bytearray()
        chunk_size_bytes = 1024 # 512 samples * 2 bytes/sample (int16)
        
        async for incoming_chunk in audio_chunk_stream:
            raw_buffer.extend(incoming_chunk)
            
            while len(raw_buffer) >= chunk_size_bytes:
                chunk = raw_buffer[:chunk_size_bytes]
                raw_buffer = raw_buffer[chunk_size_bytes:]
                
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                audio_tensor = torch.from_numpy(audio_float32)
                
                try:
                    speech_prob = self.model(audio_tensor, self.sample_rate).item()
                    
                    # Debug logging to terminal every second (roughly every 30 chunks of 512 samples)
                    if not hasattr(self, '_chunk_counter'):
                        self._chunk_counter = 0
                    self._chunk_counter += 1
                    if self._chunk_counter % 30 == 0:
                        vol = np.max(np.abs(audio_float32))
                        print(f"[VAD DEBUG] Received audio. Max Vol: {vol:.3f}, Speech Prob: {speech_prob:.3f}")
                except Exception as e:
                    logger.error(f"VAD inference error: {e}")
                    continue
                    
                if speech_prob > self.threshold:
                    if not speech_started:
                        speech_started = True
                        if interruption_event:
                            interruption_event.set()
                        if on_speech_start:
                            if asyncio.iscoroutinefunction(on_speech_start):
                                await on_speech_start()
                            else:
                                on_speech_start()
                    silence_chunks = 0
                    speech_buffer.extend(chunk)
                else:
                    if speech_started:
                        silence_chunks += 1
                        speech_buffer.extend(chunk)
                        if silence_chunks >= MAX_SILENCE_CHUNKS:
                            # Speech ended
                            speech_started = False
                            yield bytes(speech_buffer)
                            speech_buffer.clear()
                            silence_chunks = 0
