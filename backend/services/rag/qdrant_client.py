class QdrantService:
    def __init__(self, url: str, collection_name: str, vector_size: int = 384):
        self.url = url
        self.collection_name = collection_name
        self.vector_size = vector_size
    
    async def init(self) -> None:
        pass
    
    async def health_check(self) -> bool:
        return True
    
    async def upsert_vectors(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        pass
    
    async def search(self, query_vector: list[float], top_k: int = 5, filter_conditions: dict | None = None) -> list[dict]:
        return []
    
    async def delete_by_ids(self, ids: list[str]) -> None:
        pass
    
    async def get_collection_info(self) -> dict:
        return {}
