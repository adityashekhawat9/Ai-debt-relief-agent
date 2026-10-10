import httpx
from enum import Enum

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import AppException

logger = get_logger(__name__)

class LeadStatus(str, Enum):
    NEW = "NEW"
    CALLED = "CALLED" 
    SALE = "SALE"
    DNC = "DNC"
    CALLBACK = "CALLBACK"

class AgentStatus(str, Enum):
    READY = "READY"
    PAUSED = "PAUSED"
    INCALL = "INCALL"
    DISPO = "DISPO"

class VICIdialAPI:
    """
    Async VICIdial non-agent REST API client.
    
    All calls go to: /vicidial/non_agent_api.php
    Authentication via source/user/pass query params.
    Responses are plain text: 'SUCCESS: ...' or 'ERROR: ...'
    """
    
    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        source: str = "api",
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.user = user
        self.password = password
        self.source = source
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def _call(
        self,
        function: str,
        params: dict[str, str],
    ) -> str:
        """
        Make a VICIdial API call. Returns the response text.
        Raises AppException if response starts with 'ERROR:'.
        """
        query = {
            "source": self.source,
            "user": self.user,
            "pass": self.password,
            "function": function
        }
        query.update(params)
        
        try:
            res = await self.client.get("/vicidial/non_agent_api.php", params=query)
            res.raise_for_status()
            text = res.text.strip()
            
            logger.debug("VICIdial API response", function=function, response=text)
            
            if text.startswith("ERROR:"):
                logger.error("VICIdial API Error", function=function, error=text)
                raise AppException(f"VICIdial API Error: {text}")
                
            return text
        except httpx.HTTPError as e:
            logger.error("VICIdial API HTTP Error", function=function, exc_info=e)
            raise AppException(f"VICIdial HTTP Error: {e}")

    # ── Lead Management ────────────────────────────────────────────────────
    
    async def add_lead(
        self,
        phone: str,
        first_name: str = "",
        last_name: str = "",
        email: str = "",
        state: str = "",
        list_id: str = "998",
        status: str = "NEW",
    ) -> str:
        """
        Add a lead to VICIdial.
        """
        params = {
            "phone_number": phone,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "state": state,
            "list_id": list_id,
            "status": status
        }
        return await self._call("add_lead", params)

    async def update_lead(
        self,
        lead_id: str,
        status: str | None = None,
        custom_fields: dict[str, str] | None = None,
    ) -> str:
        """
        Update lead status/fields.
        """
        params = {"lead_id": lead_id}
        if status:
            params["status"] = status
            
        if custom_fields:
            for k, v in custom_fields.items():
                params[k] = v
                
        return await self._call("update_lead", params)

    async def search_lead_by_phone(
        self,
        phone: str,
    ) -> dict[str, str] | None:
        """
        Look up a lead by phone number.
        """
        params = {"phone_number": phone}
        try:
            res = await self._call("search_lead_by_phone", params)
            return {"raw_response": res}
        except AppException as e:
            if "ERROR: no leads found" in str(e).lower():
                return None
            raise

    async def add_dnc(
        self, phone: str, list_id: str = "--ALL--"
    ) -> str:
        """
        Add phone to VICIdial DNC list.
        """
        params = {"phone_number": phone, "list_id": list_id}
        return await self._call("add_to_dnc", params)

    # ── Call/Agent Control ─────────────────────────────────────────────────
    
    async def get_agent_status(
        self, agent_user: str
    ) -> dict[str, str]:
        """
        Get current status of a VICIdial agent.
        """
        params = {"agent_user": agent_user}
        res = await self._call("agent_status", params)
        return {"raw_response": res}

    async def get_available_agents(
        self, campaign_id: str = ""
    ) -> list[dict[str, str]]:
        """
        List agents currently in READY status.
        """
        params = {}
        if campaign_id:
            params["campaign_id"] = campaign_id
        res = await self._call("get_agent_status", params)
        return [{"raw_response": res}]

    async def external_hangup(
        self, agent_user: str
    ) -> str:
        """Hang up current agent call."""
        params = {"agent_user": agent_user}
        return await self._call("external_hangup", params)

    async def get_campaign_stats(
        self, campaign_id: str
    ) -> dict[str, str]:
        """Get live campaign statistics."""
        params = {"campaign_id": campaign_id}
        res = await self._call("campaign_stats", params)
        return {"raw_response": res}

    async def health_check(self) -> bool:
        """
        Test connectivity to VICIdial.
        """
        try:
            # simple ping using version
            await self._call("version", {}) 
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the httpx client."""
        await self.client.aclose()


class VICIdialBotClient:
    """
    Client for Vicidial Bot Call Transfer & Hangup API (AmiHangup.php).
    
    Used by the bot/AI system to handle call hangup actions and transfer
    calls to real agents when required.
    """
    def __init__(
        self,
        endpoint_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        settings = get_settings()
        self.endpoint_url = endpoint_url or getattr(
            settings, "VICIDIAL_BOT_API_URL", "http://103.113.27.27/bot_api/AmiHangup.php"
        )
        self.api_key = api_key or getattr(
            settings, "VICIDIAL_BOT_API_KEY", "jbti89692vc60b2o9nu7647"
        )
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def _send_action(
        self,
        channel: str,
        unique_id: str,
        action: str,
        comment: str = "",
    ) -> dict:
        """
        Execute call action (TRANSFER or HANGUP) via AmiHangup.php.
        """
        params = {
            "key": self.api_key,
            "channel": channel,
        }
        payload = {
            "key": self.api_key,
            "UNIQUEID": str(unique_id),
            "Action": action.upper(),
            "Comment": comment,
        }

        logger.info(
            "Sending Vicidial bot action",
            action=action,
            channel=channel,
            unique_id=unique_id,
            comment=comment,
            endpoint=self.endpoint_url,
        )

        try:
            res = await self.client.post(
                self.endpoint_url,
                params=params,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            res.raise_for_status()

            try:
                data = res.json()
            except Exception:
                data = {"raw": res.text}

            logger.info(
                "Vicidial bot action response",
                action=action,
                status_code=res.status_code,
                response=data,
            )
            return {"status_code": res.status_code, "response": data}
        except httpx.HTTPError as e:
            logger.error(
                "Vicidial bot API error",
                action=action,
                channel=channel,
                exc_info=e,
            )
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            return {"status_code": status_code, "error": str(e)}

    async def transfer_call(
        self,
        channel: str,
        unique_id: str,
        comment: str = "Transferred to sales agent",
    ) -> dict:
        """
        Action: TRANSFER
        - AI agent call is hung up.
        - Customer call is transferred to in-group real agent for live handling.
        - Used when bot decides customer needs human assistance.
        """
        return await self._send_action(
            channel=channel,
            unique_id=unique_id,
            action="TRANSFER",
            comment=comment,
        )

    async def hangup_call(
        self,
        channel: str,
        unique_id: str,
        comment: str = "AI bot call completed",
    ) -> dict:
        """
        Action: HANGUP
        - Full call is disconnected.
        - AI agent and customer both hang up.
        - Used when bot completes conversation or customer hangs up.
        """
        return await self._send_action(
            channel=channel,
            unique_id=unique_id,
            action="HANGUP",
            comment=comment,
        )

    async def close(self) -> None:
        """Close the httpx client."""
        await self.client.aclose()

