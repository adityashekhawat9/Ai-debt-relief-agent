import asyncio
import numpy as np
from services.ai.vad_engine import VADEngine
from services.ai.stt_engine import STTEngine

async def audio_generator():
    # Simulate a stream of 8192 byte chunks (4096 samples of 16-bit PCM = 256ms of 16kHz)
    # Let's generate a sine wave so VAD might detect speech
    t = np.linspace(0, 0.256, 4096, endpoint=False)
    # 400 Hz tone, high amplitude
    audio = (np.sin(2 * np.pi * 400 * t) * 30000).astype(np.int16)
    
    for _ in range(20):
        yield audio.tobytes()
        await asyncio.sleep(0.01)

async def main():
    print("Initializing VAD Engine...")
    vad = VADEngine(sample_rate=16000)
    print("Initializing STT Engine...")
    stt = STTEngine()
    
    interruption_event = asyncio.Event()
    
    print("Processing stream...")
    try:
        async for speech_segment in vad.process_stream(audio_generator(), interruption_event):
            print(f"Got speech segment of {len(speech_segment)} bytes")
            print("Transcribing...")
            text = await stt.transcribe(speech_segment, sample_rate=16000)
            print(f"Transcription: {text}")
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
