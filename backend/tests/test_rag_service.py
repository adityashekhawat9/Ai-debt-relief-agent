import sys
import os
import asyncio

from services.ai.rag_service import RAGService

async def test():
    rag = RAGService()
    res = await rag.get_rebuttal("Not interested.")
    print("REBUTTAL:", res)

if __name__ == "__main__":
    asyncio.run(test())
