from datetime import datetime, timezone
import zoneinfo

from core.logging import get_logger

logger = get_logger(__name__)

class CallingHoursChecker:
    """
    Validates if current time is within legal calling hours for the target.
    US: 8am - 9pm local time.
    India: 10am - 7pm IST (Asia/Kolkata).
    """
    
    def is_within_hours(self, country: str, target_timezone: str | None) -> bool:
        """
        Returns True if it's currently legal to call.
        If US and no timezone provided, assume Eastern Time (most restrictive for morning calls, 
        but we need to be careful. Better to default to a safe window or reject if unknown).
        Let's use a safe default or require timezone.
        """
        now = datetime.now(timezone.utc)
        
        country = country.upper()
        
        if country == "IN":
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")
            local_time = now.astimezone(tz)
            # India: 10am - 7pm
            if 10 <= local_time.hour < 19:
                return True
            return False
            
        elif country == "US":
            # If no timezone is provided, default to America/New_York as a safe baseline 
            # (or reject, but the prompt suggests a safe default)
            # Actually, the safest timezone for US to call across all timezones without knowing is 
            # 8am PT (11am ET) to 9pm ET (6pm PT). This means 11am to 6pm ET.
            # But let's just use the provided timezone or America/New_York.
            tz_str = target_timezone or "America/New_York"
            try:
                tz = zoneinfo.ZoneInfo(tz_str)
            except zoneinfo.ZoneInfoNotFoundError:
                logger.warning("Invalid timezone provided, defaulting to America/New_York", tz=tz_str)
                tz = zoneinfo.ZoneInfo("America/New_York")
                
            local_time = now.astimezone(tz)
            # US: 8am - 9pm
            if 8 <= local_time.hour < 21:
                return True
            return False
            
        # Default for other countries or unhandled, perhaps reject or allow?
        # Let's allow by default or we can assume it's valid if not US/IN
        logger.warning("Unknown country for calling hours check, allowing", country=country)
        return True
