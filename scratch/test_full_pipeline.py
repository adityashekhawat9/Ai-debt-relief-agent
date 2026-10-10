import asyncio
import sys
import time
import os
import wave

# Mock Settings and Logger to bypass FastAPI dependencies
class MockSettings:
    LLM_MODEL_PATH = r"C:\Users\RG0626\Desktop\Debt-relief-ai\ai-voice-platform\models\llm\qwen2.5-3b-instruct-q4_k_m.gguf"
    LLM_N_CTX = 2048
    LLM_THREADS = 6
    LLM_N_GPU_LAYERS = 0
    TTS_MODEL_PATH = r"C:\Users\RG0626\Desktop\Debt-relief-ai\ai-voice-platform\models\piper\en_US-ryan-medium.onnx"
    PIPER_EXEC_PATH = r"C:\Users\RG0626\Desktop\Debt-relief-ai\ai-voice-platform\models\piper\piper.exe"

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

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/backend'))

from types import ModuleType
core_config = ModuleType('core.config')
core_config.get_settings = MockConfig.get_settings
sys.modules['core.config'] = core_config

core_logging = ModuleType('core.logging')
core_logging.get_logger = MockCoreLogging.get_logger
sys.modules['core.logging'] = core_logging

from services.ai.llm_engine import LLMEngine
from services.ai.tts_engine import TTSEngine

async def generate_llm_stream(llm, prompt):
    messages = [
        {"role": "system", "content": "You are a helpful debt relief AI agent. Keep your response under 2 sentences."},
        {"role": "user", "content": prompt}
    ]
    print("\n[AI is thinking...]")
    async for token in llm.generate_stream(messages, max_tokens=150):
        print(token, end="", flush=True)
        yield token
    print("\n[Finished generating text]")

async def test_pipeline():
    print("Initializing Pipeline...")
    try:
        llm = LLMEngine()
        tts = TTSEngine()
    except Exception as e:
        print(f"Failed to load engines: {e}")
        return

    print("Pipeline Ready!\n")
    user_input = "Hi, I have about $15,000 in credit card debt and I'm struggling to make the minimum payments. Can you help me?"
    print(f"User (Simulated STT): '{user_input}'\n")

    # Wire LLM generator directly into TTS synthesizer
    token_stream = generate_llm_stream(llm, user_input)
    audio_stream = tts.synthesize_stream(token_stream)

    audio_bytes = b""
    start_time = time.time()
    first_audio_chunk = None

    print("[TTS is synthesizing audio chunks...]")
    
    async for chunk in audio_stream:
        if first_audio_chunk is None:
            first_audio_chunk = time.time() - start_time
            print(f"--> [First AUDIO chunk generated in {first_audio_chunk:.2f}s!]")
        audio_bytes += chunk

    print(f"\nTotal pipeline time: {time.time() - start_time:.2f}s")
    print(f"Generated {len(audio_bytes)} bytes of 8000Hz 16-bit PCM Audio.")

    # Save to a WAV file so the user can listen to it
    wav_path = "test_output.wav"
    with wave.open(wav_path, 'wb') as wav_file:
        wav_file.setnchannels(1)      # Mono
        wav_file.setsampwidth(2)      # 16-bit
        wav_file.setframerate(8000)   # 8kHz
        wav_file.writeframes(audio_bytes)
        
    print(f"\nSaved audio output to {os.path.abspath(wav_path)}!")
    print("Open this file to hear the AI speak!")

if __name__ == "__main__":
    asyncio.run(test_pipeline())
