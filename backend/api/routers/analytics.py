from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard():
    return {}

@router.get("/calls/daily")
async def get_daily_stats():
    return []

@router.get("/calls/outcomes")
async def get_outcomes():
    return {}

@router.get("/latency")
async def get_latency():
    return {}

@router.get("/compliance")
async def get_compliance():
    return {}

@router.get("/health")
async def analytics_health():
    return {"status": "ok"}
