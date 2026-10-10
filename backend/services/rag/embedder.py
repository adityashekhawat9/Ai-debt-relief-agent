import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastembed import TextEmbedding

from core.logging import get_logger
from core.config import get_settings

logger = get_logger(__name__)

class EmbedderService:
    """
    Generates text embeddings using FastEmbed (ONNX optimized for CPU).
    Default model: BAAI/bge-small-en-v1.5 (384 dimensions)
    """
    
    def __init__(self):
        settings = get_settings()
        self.model_name = getattr(settings, "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        logger.info(f"Initializing EmbedderService with model {self.model_name}")
        # Initialize FastEmbed
        # Note: threads=2 or 4 to avoid thrashing with the LLM
        self.embedding_model = TextEmbedding(model_name=self.model_name, threads=2)
        self.executor = ThreadPoolExecutor(max_workers=2)
        
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of text strings into vectors asynchronously using run_in_executor.
        """
        if not texts:
            return []
            
        loop = asyncio.get_running_loop()
        def _embed() -> list[list[float]]:
            embeddings_gen = self.embedding_model.embed(texts)
            return [vec.tolist() for vec in embeddings_gen]
            
        embeddings = await loop.run_in_executor(self.executor, _embed)
        return embeddings
        
    async def embed_query(self, query: str) -> list[float]:
        """
        Embeds a single query string for searching.
        Usually BGE models require a prefix like "Represent this sentence for searching relevant passages: " 
        or fastembed handles it under the hood (fastembed handles query prefixes if configured, otherwise we just embed).
        """
        loop = asyncio.get_running_loop()
        def _embed_query() -> list[float]:
            embeddings_gen = self.embedding_model.query_embed(query)
            return list(embeddings_gen)[0].tolist()
            
        embedding = await loop.run_in_executor(self.executor, _embed_query)
        return embedding
