import asyncio
import os
import wave
from services.ai.tts_engine import TTSEngine
from conversation_engine.langgraph_dialogue import SCRIPT_TEXTS

async def main():
    os.environ["USE_CLOUD_LLM"] = "False"
    tts = TTSEngine()
    text = "Awesome. " + SCRIPT_TEXTS["1"]
    print(f"Testing text: {text}")
    try:
        audio = await tts._synthesize_sentence(text)
        print(f"Audio bytes length: {len(audio)}")
        # Save to file to manually verify if it's truncated
        with wave.open("scratch/test_out.wav", 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(8000)
            wav_file.writeframes(audio)
        print("Saved to scratch/test_out.wav")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
