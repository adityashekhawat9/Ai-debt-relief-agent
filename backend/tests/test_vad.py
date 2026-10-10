import asyncio
import numpy as np
from services.ai.vad_engine import VADEngine

async def dummy_audio_stream():
    # Simulate a stream of 8192 byte chunks (4096 samples of 16-bit PCM = 256ms of 16kHz)
    dummy_chunk = np.zeros(4096, dtype=np.int16).tobytes()
    for _ in range(5):
        yield dummy_chunk
        await asyncio.sleep(0.1)

async def main():
    print("Initializing VAD Engine...")
    vad = VADEngine()
    print("VAD Engine Initialized.")
    
    interruption_event = asyncio.Event()
    
    print("Processing stream...")
    try:
        async for segment in vad.process_stream(dummy_audio_stream(), interruption_event):
            print(f"Got speech segment of {len(segment)} bytes")
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
