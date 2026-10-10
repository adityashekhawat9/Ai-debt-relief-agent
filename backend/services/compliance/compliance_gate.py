from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.exceptions import DNCError, CallingHoursError
from services.compliance.dnc_checker import DNCChecker
from services.compliance.calling_hours import CallingHoursChecker
from conversation_engine.session_manager import SessionManager

logger = get_logger(__name__)

class ComplianceGate:
    def __init__(self, session_manager: SessionManager):
        self.dnc = DNCChecker(session_manager)
        self.hours = CallingHoursChecker()

    async def verify_can_call(
        self,
        phone: str,
        country: str,
        target_timezone: str | None,
        db_session: AsyncSession
    ) -> None:
        """
        Raises CallingHoursError if outside hours.
        Raises DNCError if on DNC list.
        """
        # 1. Check Calling Hours First (synchronous and fast)
        if not self.hours.is_within_hours(country, target_timezone):
            logger.warning("Calling hours validation failed", phone=phone, country=country, tz=target_timezone)
            raise CallingHoursError(f"Cannot call {phone} in {country} at this time due to calling hours restrictions.")
            
        # 2. Check DNC List
        if await self.dnc.is_dnc(phone, country, db_session):
            logger.warning("DNC validation failed", phone=phone, country=country)
            raise DNCError(f"Phone number {phone} is on a Do Not Call list.")
            
        logger.info("Compliance checks passed", phone=phone, country=country)
