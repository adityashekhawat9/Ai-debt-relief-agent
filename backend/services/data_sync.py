import asyncio
import logging
import httpx
from sqlalchemy.future import select

from core.config import get_settings
from database.session import get_session_factory
from models.database.lead import Lead
from models.database.call import Call
from models.database.qualification import QualificationAnswer

logger = logging.getLogger("data_sync")
logging.basicConfig(level=logging.INFO)

async def sync_call_data(vicidial_lead_id: str, phone: str, answers_dict: dict, ai_disposition: str):
    """
    Saves collected AI qualification answers to the database and posts them to a webhook.
    """
    settings = get_settings()
    
    # 1. Fire webhook (non-blocking)
    if settings.DATA_WEBHOOK_URL:
        payload = {
            "vicidial_lead_id": vicidial_lead_id,
            "phone": phone,
            "ai_disposition": ai_disposition,
            "collected_data": answers_dict
        }
        asyncio.create_task(_post_webhook(settings.DATA_WEBHOOK_URL, payload))
    else:
        logger.info("DATA_WEBHOOK_URL not configured, skipping external webhook sync.")

    # 2. Save to database
    # We need a session
    SessionLocal = get_session_factory()
    if not SessionLocal:
        logger.warning("Database not initialized, skipping DB save.")
        return

    async with SessionLocal() as session:
        try:
            # Check if we have a matching lead, if not, create a dummy one
            # Because vicidial_lead_id might not exist yet if Vicidial is driving the calls
            if vicidial_lead_id:
                stmt = select(Lead).where(Lead.vicidial_lead_id == str(vicidial_lead_id))
                result = await session.execute(stmt)
                lead = result.scalars().first()
                
                if not lead:
                    # Create a dummy lead to satisfy foreign key constraints
                    import uuid
                    import time
                    dummy_phone = phone if phone and phone != 'unknown' else f"dummy_{vicidial_lead_id}_{int(time.time())}"
                    lead = Lead(vicidial_lead_id=str(vicidial_lead_id), phone=dummy_phone, status=ai_disposition)
                    session.add(lead)
                    await session.flush() # flush to get the UUID

                # Create a dummy call to attach the answers to
                call = Call(lead_id=lead.id, vicidial_call_id=str(vicidial_lead_id), status=ai_disposition)
                session.add(call)
                await session.flush()

                # Insert answers
                for key, val in answers_dict.items():
                    answer_rec = QualificationAnswer(
                        call_id=call.id,
                        lead_id=lead.id,
                        question_key=key,
                        answer_text=str(val) if val is not None else None,
                    )
                    session.add(answer_rec)
                    
                await session.commit()
                logger.info(f"Successfully saved qualification data to DB for lead {vicidial_lead_id}")
            else:
                logger.warning("No vicidial_lead_id provided, skipping DB save.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save qualification data to DB: {e}")

async def _post_webhook(url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in [200, 201, 202, 204]:
                logger.info(f"Webhook sync successful: {resp.status_code}")
            else:
                logger.warning(f"Webhook sync returned non-200: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Webhook POST failed: {e}")
