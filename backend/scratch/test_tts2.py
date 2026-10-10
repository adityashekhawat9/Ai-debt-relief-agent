import asyncio
import os
from services.ai.tts_engine import TTSEngine

async def main():
    os.environ["USE_CLOUD_LLM"] = "False"
    tts = TTSEngine()
    text = "Awesome. Okay, Great! We have multiple payment options for 12 to 36 months."
    print(f"Testing text: {text}")
    try:
        audio = await tts._synthesize_sentence(text)
        print(f"Audio bytes length: {len(audio)}")
        
        # Test with one sentence
        audio2 = await tts._synthesize_sentence("Awesome.")
        print(f"Audio bytes length single sentence: {len(audio2)}")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
