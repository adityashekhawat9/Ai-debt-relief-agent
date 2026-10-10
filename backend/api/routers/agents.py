from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_agents():
    return []

@router.get("/status")
async def get_agent_status():
    return {"status": "available"}

@router.get("/health")
async def agents_health():
    return {"status": "ok"}
