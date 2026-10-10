import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.ai.tts_engine import TTSEngine

async def main():
    print("Testing TTS Engine...")
    tts = TTSEngine()
    try:
        audio = await tts._synthesize_sentence("Hello, this is a test.")
        print(f"Success! Generated {len(audio)} bytes of audio.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
