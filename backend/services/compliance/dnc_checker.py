import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import get_settings
from core.logging import get_logger
from conversation_engine.session_manager import SessionManager
from models.database.dnc import InternalDNC, DNCCheckLog

logger = get_logger(__name__)

class DNCChecker:
    """
    Checks if a phone number is on any Do Not Call list.
    1. Fast path: Redis DNC cache (SessionManager.is_dnc)
    2. Internal DB: internal_dnc table
    3. External API: Federal DNC (US) or TRAI DND (IN) based on country code
    """
    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager
        self.settings = get_settings()
    
    async def is_dnc(
        self,
        phone: str,
        country: str,
        db_session: AsyncSession
    ) -> bool:
        """
        Check all lists.
        If found on any list, logs to dnc_check_log as blocked and returns True.
        If clear, logs as passed and returns False.
        """
        # 1. Fast path: Redis DNC cache
        if await self.session_manager.is_dnc(phone):
            await self._log_check(db_session, phone, country, "redis_cache", True)
            return True

        # 2. Internal DB
        if await self._check_internal(phone, db_session):
            await self.session_manager.mark_dnc(phone)
            await self._log_check(db_session, phone, country, "internal_db", True)
            return True

        # 3. External API
        if await self._check_external(phone, country):
            await self.session_manager.mark_dnc(phone)
            await self._log_check(db_session, phone, country, "external_api", True)
            return True

        await self._log_check(db_session, phone, country, "all", False)
        return False
        
    async def _check_internal(self, phone: str, db_session: AsyncSession) -> bool:
        stmt = select(InternalDNC).where(InternalDNC.phone_number == phone)
        result = await db_session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _check_external(self, phone: str, country: str) -> bool:
        if country.upper() == "US" and self.settings.FEDERAL_DNC_API_URL:
            return await self._call_external_api(self.settings.FEDERAL_DNC_API_URL, phone)
        elif country.upper() == "IN" and self.settings.TRAI_DND_API_URL:
            return await self._call_external_api(self.settings.TRAI_DND_API_URL, phone)
        return False

    async def _call_external_api(self, url: str, phone: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}?phone={phone}")
                response.raise_for_status()
                data = response.json()
                return data.get("is_dnc", False)
        except Exception as e:
            logger.error("External DNC API check failed", phone=phone, error=str(e))
            # Fail open if external API is down? Or fail closed? Usually fail open (allow call) or raise exception.
            # Let's fail open (return False) to not block operations on third party failure, but log it.
            return False

    async def _log_check(self, db_session: AsyncSession, phone: str, country: str, source: str, is_blocked: bool) -> None:
        log_entry = DNCCheckLog(
            phone_number=phone,
            country_code=country,
            source=source,
            is_blocked=is_blocked
        )
        db_session.add(log_entry)
        await db_session.flush()

    async def trigger_external_dnc_webhook(self, phone: str) -> None:
        if not self.settings.EXTERNAL_DNC_WEBHOOK_URL:
            logger.info("No EXTERNAL_DNC_WEBHOOK_URL configured, skipping webhook.")
            return
            
        payload = {
            "phone": phone,
            "source": "ai_agent",
            "reason": "user_requested_or_hostile"
        }
        
        headers = {"Content-Type": "application/json"}
        if self.settings.EXTERNAL_DNC_API_KEY:
            headers["Authorization"] = f"Bearer {self.settings.EXTERNAL_DNC_API_KEY}"
            
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.settings.EXTERNAL_DNC_WEBHOOK_URL,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"Successfully triggered DNC webhook for {phone}")
        except Exception as e:
            logger.error(f"Failed to trigger DNC webhook for {phone}: {e}")

    async def trigger_external_dnc_webhook(self, phone: str) -> None:
        if not self.settings.EXTERNAL_DNC_WEBHOOK_URL:
            logger.info("No EXTERNAL_DNC_WEBHOOK_URL configured, skipping webhook.")
            return
            
        payload = {
            "phone": phone,
            "source": "ai_agent",
            "reason": "user_requested_or_hostile"
        }
        
        headers = {"Content-Type": "application/json"}
        if self.settings.EXTERNAL_DNC_API_KEY:
            headers["Authorization"] = f"Bearer {self.settings.EXTERNAL_DNC_API_KEY}"
            
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.settings.EXTERNAL_DNC_WEBHOOK_URL,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"Successfully triggered DNC webhook for {phone}")
        except Exception as e:
            logger.error(f"Failed to trigger DNC webhook for {phone}: {e}")

    async def trigger_external_dnc_webhook(self, phone: str) -> None:
        if not self.settings.EXTERNAL_DNC_WEBHOOK_URL:
            logger.info("No EXTERNAL_DNC_WEBHOOK_URL configured, skipping webhook.")
            return
            
        payload = {
            "phone": phone,
            "source": "ai_agent",
            "reason": "user_requested_or_hostile"
        }
        
        headers = {"Content-Type": "application/json"}
        if self.settings.EXTERNAL_DNC_API_KEY:
            headers["Authorization"] = f"Bearer {self.settings.EXTERNAL_DNC_API_KEY}"
            
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.settings.EXTERNAL_DNC_WEBHOOK_URL,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"Successfully triggered DNC webhook for {phone}")
        except Exception as e:
            logger.error(f"Failed to trigger DNC webhook for {phone}: {e}")
