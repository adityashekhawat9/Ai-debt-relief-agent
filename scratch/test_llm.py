import asyncio
import sys
import time

# Mock Settings and Logger to bypass FastAPI dependencies
class MockSettings:
    LLM_MODEL_PATH = r"C:\Users\RG0626\Desktop\Debt-relief-ai\ai-voice-platform\models\llm\qwen2.5-3b-instruct-q4_k_m.gguf"
    LLM_N_CTX = 2048
    LLM_THREADS = 6
    LLM_N_GPU_LAYERS = 0

class MockConfig:
    @staticmethod
    def get_settings(): return MockSettings()

class MockLogger:
    def info(self, *args, **kwargs): print("[INFO]", *args)
    def warning(self, *args, **kwargs): print("[WARN]", *args)
    def error(self, *args, **kwargs): print("[ERROR]", *args)
    def debug(self, *args, **kwargs): pass

class MockCoreLogging:
    @staticmethod
    def get_logger(name): return MockLogger()

import sys
from types import ModuleType
core_config = ModuleType('core.config')
core_config.get_settings = MockConfig.get_settings
sys.modules['core.config'] = core_config

core_logging = ModuleType('core.logging')
core_logging.get_logger = MockCoreLogging.get_logger
sys.modules['core.logging'] = core_logging

# Now import the actual LLMEngine we built
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/backend'))
from services.ai.llm_engine import LLMEngine

async def test_llm():
    print("Loading 2.1GB Qwen LLM into memory... (This may take a few seconds)")
    try:
        engine = LLMEngine()
    except Exception as e:
        print(f"Failed to load LLM: {e}")
        return

    print("Model loaded successfully!")
    print("\n--- Test Prompt ---")
    prompt = "You are an outbound AI agent for a debt relief company. The user just answered the phone and said 'Hello?'. How do you respond?"
    print(f"User: {prompt}\n")
    
    print("--- AI Response ---")
    messages = [
        {"role": "system", "content": "You are a helpful debt relief AI agent. Keep your response under 2 sentences."},
        {"role": "user", "content": prompt}
    ]
    
    start_time = time.time()
    first_token_time = None
    
    # Test the async streaming generator we built
    async for token in engine.generate_stream(messages, max_tokens=100):
        if first_token_time is None:
            first_token_time = time.time() - start_time
            print(f"[First token latency: {first_token_time:.2f}s]")
            
        print(token, end="", flush=True)
        
    total_time = time.time() - start_time
    print(f"\n\n[Total generation time: {total_time:.2f}s]")

if __name__ == "__main__":
    asyncio.run(test_llm())
