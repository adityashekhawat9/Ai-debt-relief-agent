import asyncio
import json
import base64
from urllib.parse import urlparse
from typing import Any, Callable, Coroutine

import httpx
import websockets

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import AppException

logger = get_logger(__name__)

class AsteriskARI:
    """
    Async Asterisk REST Interface client.
    
    Provides HTTP REST calls for channel operations and
    a WebSocket event stream for real-time ARI events.
    """
    
    def __init__(
        self,
        base_url: str,       # http://asterisk:8088
        username: str,
        password: str,
        app_name: str = "ai-voice-platform",
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.app_name = app_name
        
        self.client: httpx.AsyncClient | None = None
        self._ws_task: asyncio.Task | None = None
        self._event_handlers: dict[str, list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]]] = {}
        self._connected = False

    async def connect(self) -> None:
        """Initialize httpx client. Start WebSocket event stream as background task."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(self.username, self.password),
            timeout=10.0
        )
        self._connected = True
        self._ws_task = asyncio.create_task(self._ws_event_loop())
        logger.info("Asterisk ARI client connected")

    async def disconnect(self) -> None:
        """Close httpx client and cancel WebSocket task."""
        self._connected = False
        if self._ws_task:
            self._ws_task.cancel()
        if self.client:
            await self.client.aclose()
        logger.info("Asterisk ARI client disconnected")

    async def _handle_response(self, response: httpx.Response) -> Any:
        if response.is_error:
            try:
                error_body = response.json()
            except ValueError:
                error_body = response.text
            logger.error("ARI HTTP error", status_code=response.status_code, error=error_body)
            raise AppException(f"ARI error {response.status_code}: {error_body}")
        
        if response.status_code != 204:
            try:
                return response.json()
            except ValueError:
                return response.text
        return None

    # ── REST Channel operations ────────────────────────────────────────────
    
    async def get_channels(self) -> list[dict[str, Any]]:
        """GET /channels — list all active channels."""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.get("/ari/channels")
        return await self._handle_response(res)

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        """GET /channels/{channelId}"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.get(f"/ari/channels/{channel_id}")
        return await self._handle_response(res)

    async def hangup_channel(self, channel_id: str, reason: str = "normal") -> None:
        """DELETE /channels/{channelId}"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.delete(f"/ari/channels/{channel_id}", params={"reason": reason})
        await self._handle_response(res)

    async def answer_channel(self, channel_id: str) -> None:
        """POST /channels/{channelId}/answer"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.post(f"/ari/channels/{channel_id}/answer")
        await self._handle_response(res)

    async def mute_channel(
        self, channel_id: str, direction: str = "both"
    ) -> None:
        """POST /channels/{channelId}/mute"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.post(f"/ari/channels/{channel_id}/mute", params={"direction": direction})
        await self._handle_response(res)

    async def redirect_channel(self, channel_id: str, endpoint: str) -> None:
        """POST /channels/{channelId}/redirect"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.post(f"/ari/channels/{channel_id}/redirect", params={"endpoint": endpoint})
        await self._handle_response(res)

    async def play_sound(
        self,
        channel_id: str,
        media: str,
        lang: str = "en",
    ) -> dict[str, Any]:
        """POST /channels/{channelId}/play — returns Playback object."""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.post(
            f"/ari/channels/{channel_id}/play",
            params={"media": media, "lang": lang}
        )
        return await self._handle_response(res)

    async def stop_playback(self, playback_id: str) -> None:
        """DELETE /playbacks/{playbackId}"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.delete(f"/ari/playbacks/{playback_id}")
        await self._handle_response(res)

    # ── Bridge operations (for transfers) ─────────────────────────────────
    
    async def create_bridge(
        self, type_: str = "mixing", name: str = ""
    ) -> dict[str, Any]:
        """POST /bridges"""
        if not self.client:
            raise AppException("ARI client not connected")
        params = {"type": type_}
        if name:
            params["name"] = name
        res = await self.client.post("/ari/bridges", params=params)
        return await self._handle_response(res)

    async def add_channel_to_bridge(
        self, bridge_id: str, channel_id: str
    ) -> None:
        """POST /bridges/{bridgeId}/addChannel"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.post(f"/ari/bridges/{bridge_id}/addChannel", params={"channel": channel_id})
        await self._handle_response(res)

    async def destroy_bridge(self, bridge_id: str) -> None:
        """DELETE /bridges/{bridgeId}"""
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.delete(f"/ari/bridges/{bridge_id}")
        await self._handle_response(res)

    # ── WebSocket event stream ─────────────────────────────────────────────
    
    async def _ws_event_loop(self) -> None:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{scheme}://{parsed.netloc}/ari/events?app={self.app_name}"
        
        auth_bytes = f"{self.username}:{self.password}".encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        headers = {"Authorization": f"Basic {auth_b64}"}
        
        while self._connected:
            try:
                async with websockets.connect(ws_url, extra_headers=headers) as ws:
                    logger.info("Connected to ARI WebSocket stream", url=ws_url)
                    async for message in ws:
                        if not self._connected:
                            break
                        try:
                            event = json.loads(message)
                            await self._dispatch_event(event)
                        except json.JSONDecodeError:
                            logger.error("Failed to parse ARI event", message=message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ARI WebSocket error, reconnecting", exc_info=e)
                if self._connected:
                    await asyncio.sleep(5.0)

    def on_event(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _dispatch_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if not event_type:
            return
            
        logger.debug("Received ARI Event", type=event_type)
        handlers = self._event_handlers.get(event_type, [])
        if not handlers:
            logger.debug("No handlers for ARI event", type=event_type)
            return
            
        for handler in handlers:
            asyncio.create_task(handler(event))

    async def health_check(self) -> bool:
        if not self.client:
            return False
        try:
            res = await self.client.get("/ari/asterisk/info")
            return res.status_code == 200
        except Exception:
            return False

    async def get_asterisk_info(self) -> dict[str, Any]:
        if not self.client:
            raise AppException("ARI client not connected")
        res = await self.client.get("/ari/asterisk/info")
        return await self._handle_response(res)
