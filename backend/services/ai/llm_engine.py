import asyncio
from typing import AsyncGenerator
import os

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import LLMError

logger = get_logger(__name__)

from anthropic import AsyncAnthropic

class CloudLLMEngine:
    """
    Cloud LLM Engine using Anthropic Claude 3.5 Haiku as primary.
    """
    
    def __init__(self):
        self.settings = get_settings()
        api_key = self.settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY is not set. CloudLLMEngine will fail if called.")
            
        try:
            self.client = AsyncAnthropic(
                api_key=api_key,
                max_retries=1,
                timeout=5.0
            )
            self.model = "claude-haiku-4-5-20251001"
            logger.info(f"Initialized CloudLLMEngine with Anthropic (Primary Model: {self.model})")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            raise LLMError(f"Failed to initialize CloudLLMEngine: {e}")

    async def generate_stream(
        self, 
        messages: list[dict[str, str]], 
        max_tokens: int = 150,
        temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
        chat_messages = [m for m in messages if m["role"] != "system"]
        
        try:
            # Enable prompt caching for the system prompt to drastically reduce TTFB and costs
            system_payload = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ] if system_prompt else None

            stream = await self.client.messages.create(
                messages=chat_messages,
                system=system_payload if system_payload else system_prompt,
                model=self.model,
                max_tokens=max_tokens,
                stream=True,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
            )
            async for chunk in stream:
                if chunk.type == "content_block_delta":
                    if hasattr(chunk.delta, "text") and chunk.delta.text:
                        yield chunk.delta.text
        except Exception as e:
            logger.warning(f"Anthropic streaming generation failed ({e}).")
            raise LLMError(f"Generation failed: {e}")

    async def _fallback_generate_stream(self, messages, max_tokens, temperature):
        # Kept for compatibility but not used right now
        yield ""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
        chat_messages = [m for m in messages if m["role"] != "system"]
        
        try:
            system_payload = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ] if system_prompt else None

            response = await self.client.messages.create(
                messages=chat_messages,
                system=system_payload if system_payload else system_prompt,
                model=self.model,
                max_tokens=150,
                stream=False,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Anthropic generation failed ({e}).")
            raise LLMError(f"Generation failed: {e}")

# ------------------------------------------------------------------
# LOCAL LLM ENGINE (llama-cpp-python)
# LOCAL LLM ENGINE (llama-cpp-python)
# ------------------------------------------------------------------

class LocalLLMEngine:
    """
    Local LLM Engine using llama-cpp-python.
    Runs a quantized GGUF model strictly on the CPU.
    """
    
    def __init__(self):
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("llama-cpp-python is not installed. Run 'pip install llama-cpp-python' to use local models.")

        settings = get_settings()
        try:
            self.llm = Llama(
                model_path=settings.LLM_MODEL_PATH,
                n_ctx=settings.LLM_N_CTX,
                n_threads=settings.LLM_THREADS,
                n_gpu_layers=settings.LLM_N_GPU_LAYERS,
                verbose=False
            )
            logger.info("Initialized LocalLLMEngine")
        except Exception as e:
            logger.error(f"Failed to initialize Llama model: {e}")
            raise LLMError(f"Failed to initialize Local LLMEngine: {e}")

    async def generate_stream(
        self, 
        messages: list[dict[str, str]], 
        max_tokens: int = 150,
        temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        def _generate():
            try:
                response = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )
                for chunk in response:
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta["content"])
            except Exception as e:
                logger.error(f"Error during streaming generation: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(_generate))
        
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise LLMError(f"Streaming generation failed: {item}")
                yield item
        finally:
            if not task.done():
                task.cancel()

    async def generate(self, messages: list[dict[str, str]]) -> str:
        try:
            def _gen():
                return self.llm.create_chat_completion(
                    messages=messages,
                    stream=False
                )
            response = await asyncio.to_thread(_gen)
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error during non-streaming generation: {e}")
            raise LLMError(f"Generation failed: {e}")

# ------------------------------------------------------------------
# LLM ENGINE FACTORY
# ------------------------------------------------------------------
class LLMEngine:
    """
    Factory interface that delegates to either CloudLLMEngine or LocalLLMEngine
    based on the USE_CLOUD_LLM setting.
    """
    def __init__(self):
        settings = get_settings()
        if settings.USE_CLOUD_LLM:
            self._engine = CloudLLMEngine()
        else:
            self._engine = LocalLLMEngine()

    async def generate_stream(self, messages: list[dict[str, str]], max_tokens: int = 150, temperature: float = 0.3) -> AsyncGenerator[str, None]:
        async for chunk in self._engine.generate_stream(messages, max_tokens, temperature):
            yield chunk

    async def generate(self, messages: list[dict[str, str]]) -> str:
        return await self._engine.generate(messages)
