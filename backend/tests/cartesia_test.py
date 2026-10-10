import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.config import get_settings
from services.ai.tts_engine import CloudTTSEngine

async def test_cartesia():
    print("Testing Cartesia...")
    tts = CloudTTSEngine()
    print(f"API Key loaded: {tts.api_key[:10]}...")
    print(f"Voice ID: {tts.voice}")
    
    # Try streaming
    chunks = []
    try:
        async def mock_llm_stream():
            yield "Hello. "
            yield "This is a test of Cartesia."
            
        async for chunk in tts.synthesize_stream(mock_llm_stream()):
            chunks.append(chunk)
            print(f"Received chunk of {len(chunk)} bytes")
            
        print(f"Success! Received {len(chunks)} chunks.")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_cartesia())
