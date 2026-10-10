from fastapi import APIRouter, HTTPException
import re

router = APIRouter()

@router.get("/")
async def list_leads():
    return []

@router.get("/{lead_id}")
async def get_lead_detail(lead_id: str):
    return {"lead_id": lead_id}

@router.post("/")
async def create_lead(phone: str):
    if not re.match(r"^\+?[1-9]\d{1,14}$", phone):
        raise HTTPException(status_code=400, detail="Invalid E.164 phone number")
    return {"status": "created"}

@router.post("/bulk")
async def bulk_import_leads():
    return {"status": "imported"}

@router.patch("/{lead_id}")
async def update_lead(lead_id: str):
    return {"status": "updated"}

@router.delete("/{lead_id}")
async def delete_lead(lead_id: str):
    return {"status": "deleted"}

@router.post("/{lead_id}/dnc")
async def add_dnc(lead_id: str):
    return {"status": "added to dnc"}

@router.get("/health")
async def leads_health():
    return {"status": "ok"}
