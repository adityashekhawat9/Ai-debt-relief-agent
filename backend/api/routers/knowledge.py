import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from api.dependencies import get_db, require_supervisor
from services.rag.qdrant_client import QdrantService
from services.rag.embedder import EmbedderService
from core.logging import get_logger
from core.config import get_settings

logger = get_logger(__name__)
router = APIRouter()

# Instantiate global instances (normally injected or via lifespan)
settings = get_settings()
embedder_service = EmbedderService()
qdrant_service = QdrantService(
    url=getattr(settings, "QDRANT_URL", "http://localhost:6333"),
    collection_name=getattr(settings, "QDRANT_COLLECTION", "knowledge_base")
)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Basic word or character chunker."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = words[i:i + chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap
    return chunks

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_supervisor)
):
    """
    1. Read text file content (assume basic txt or markdown for now).
    2. Chunk the text.
    3. Generate embeddings for all chunks via EmbedderService.
    4. Store chunks and embeddings in Qdrant via QdrantService.upsert.
    5. Save a record in the postgres database `knowledge_documents` table.
    """
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(status_code=400, detail="Invalid file encoding. Only UTF-8 text is supported.")
    
    chunks = chunk_text(content, chunk_size=500, overlap=50)
    if not chunks:
        raise HTTPException(status_code=400, detail="Empty document.")
        
    doc_id = str(uuid.uuid4())
    filename = file.filename or "unknown"
    
    try:
        embeddings = await embedder_service.embed_texts(chunks)
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise HTTPException(status_code=500, detail="Error generating embeddings.")
        
    ids = []
    payloads = []
    for i, chunk in enumerate(chunks):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{i}"))
        ids.append(point_id)
        payloads.append({
            "doc_id": doc_id,
            "filename": filename,
            "chunk_index": i,
            "text": chunk
        })
        
    try:
        await qdrant_service.upsert_vectors(ids=ids, vectors=embeddings, payloads=payloads)
    except Exception as e:
        logger.error(f"Failed to upsert to Qdrant: {e}")
        raise HTTPException(status_code=500, detail="Error saving to vector database.")
        
    if db:
        try:
            await db.execute(
                text("""
                    INSERT INTO knowledge_documents (id, filename, uploaded_by, status)
                    VALUES (:id, :filename, :uploaded_by, :status)
                """),
                {
                    "id": doc_id,
                    "filename": filename,
                    "uploaded_by": getattr(user, 'username', 'supervisor'),
                    "status": "processed"
                }
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Error saving document metadata.")

    return {"status": "success", "doc_id": doc_id, "chunks_processed": len(chunks)}


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    """List all documents."""
    if not db:
        return []
    result = await db.execute(text("SELECT id, filename, uploaded_by, status, created_at FROM knowledge_documents"))
    docs = result.fetchall()
    return [{"id": d[0], "filename": d[1], "uploaded_by": d[2], "status": d[3], "created_at": d[4]} for d in docs]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_supervisor)):
    """Delete a document and its chunks."""
    if db:
        try:
            await db.execute(
                text("DELETE FROM knowledge_documents WHERE id = :id"),
                {"id": doc_id}
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Error deleting document metadata.")
        
    return {"status": "deleted", "doc_id": doc_id}

@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    return {"doc_id": doc_id}

@router.post("/search")
async def search_documents(query: str):
    try:
        embedding = await embedder_service.embed_query(query)
        results = await qdrant_service.search(query_vector=embedding, top_k=5)
        return results
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Error searching documents.")

@router.get("/health")
async def knowledge_health():
    return {"status": "ok"}
