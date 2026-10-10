import asyncio
import wave
from services.ai.tts_engine import TTSEngine

async def mock_token_stream():
    words = ["Hello, ", "this ", "is ", "Kokoro ", "TTS. ", "I ", "sound ", "incredibly ", "human!"]
    for w in words:
        yield w
        await asyncio.sleep(0.01)

async def test_kokoro():
    print("Initializing Kokoro TTS...")
    engine = TTSEngine()
    
    with wave.open("kokoro_test.wav", "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(8000)
        
        print("Synthesizing stream...")
        async for chunk in engine.synthesize_stream(mock_token_stream()):
            wf.writeframes(chunk)
            print(".", end="", flush=True)
            
    print("\nSuccessfully generated kokoro_test.wav")

if __name__ == "__main__":
    asyncio.run(test_kokoro())
