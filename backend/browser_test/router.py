from fastapi import APIRouter, WebSocket, Depends
from browser_test.orchestrator import BrowserTestOrchestrator
from services.ai.llm_engine import LLMEngine
from core.logging import get_logger

# We need the LLM engine and Qdrant injected. For now, we instantiate or pull from app state.
# In a real app, these are dependency injected. We will import the global instances if possible,
# or create stubs for the test.

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["Testing"])

@router.websocket("/test-chat")
async def websocket_test_endpoint(websocket: WebSocket):
    # Retrieve dependencies from app state or similar
    # Initialize the real LLMEngine using the 3GB Qwen model
    try:
        llm_engine = LLMEngine()
    except Exception as e:
        logger.error(f"LLM Engine failed to load: {e}")
        llm_engine = None
        
    qdrant = getattr(websocket.app.state, "qdrant", None)
    embedder = getattr(websocket.app.state, "embedder", None)
    
    orchestrator = BrowserTestOrchestrator(
        websocket=websocket,
        llm_engine=llm_engine,
        qdrant_service=qdrant,
        embedder_service=embedder
    )
    
    await orchestrator.run()
