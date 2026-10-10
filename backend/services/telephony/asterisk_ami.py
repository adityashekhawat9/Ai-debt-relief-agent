import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import TransferError, AppException

logger = get_logger(__name__)

@dataclass
class AMIEvent:
    event: str
    headers: dict[str, str]
    received_at: datetime = field(default_factory=datetime.utcnow)

@dataclass  
class AMIResponse:
    response: str  # 'Success' | 'Error'
    message: str
    headers: dict[str, str]
    action_id: str | None

class AsteriskAMI:
    """
    Async Asterisk Manager Interface client.
    
    Maintains a persistent TCP connection to Asterisk AMI.
    Handles login, action dispatch, event routing, and auto-reconnect.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        reconnect_interval: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.reconnect_interval = reconnect_interval
        
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._read_task: asyncio.Task | None = None
        self._pending_actions: dict[str, asyncio.Future[AMIResponse]] = {}
        self._event_handlers: dict[str, list[Callable[[AMIEvent], Coroutine[Any, Any, None]]]] = {}

    async def connect(self) -> None:
        """Open TCP connection and login to AMI."""
        while not self._connected:
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                logger.info("Connected to AMI TCP stream", host=self.host, port=self.port)
                
                if self.reader:
                    await self.reader.readline()
                
                await self._login()
                self._connected = True
                logger.info("Successfully logged into AMI")
                
                self._read_task = asyncio.create_task(self._read_loop())
                break
            except Exception as e:
                logger.error("Failed to connect/login to AMI", exc_info=e)
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                await asyncio.sleep(self.reconnect_interval)

    async def disconnect(self) -> None:
        """Send Logoff action and close connection."""
        self._connected = False
        if self._read_task:
            self._read_task.cancel()
        
        try:
            if self.writer:
                logoff_action = "Action: Logoff\r\n\r\n"
                self.writer.write(logoff_action.encode('utf-8'))
                await self.writer.drain()
                self.writer.close()
                await self.writer.wait_closed()
        except Exception as e:
            logger.error("Error during AMI disconnect", exc_info=e)
            
        for future in self._pending_actions.values():
            if not future.done():
                future.set_exception(TransferError("Disconnected from AMI"))
        self._pending_actions.clear()
        logger.info("Disconnected from AMI")

    async def _login(self) -> None:
        """Send Login action and wait for Success response."""
        action_id = str(uuid.uuid4())
        lines = [
            "Action: Login",
            f"ActionID: {action_id}",
            f"Username: {self.username}",
            f"Secret: {self.password}",
            "",
            ""
        ]
        if self.writer:
            self.writer.write("\r\n".join(lines).encode('utf-8'))
            await self.writer.drain()
            logger.debug("Sent AMI Login action", action_id=action_id)

        block = ""
        while True:
            if not self.reader:
                raise AppException("No reader available for login")
            line_bytes = await self.reader.readline()
            if not line_bytes:
                raise AppException("Connection closed during login")
            line = line_bytes.decode('utf-8')
            block += line
            if block.endswith("\r\n\r\n"):
                break
        
        headers = await self._parse_block(block)
        if headers.get("Response") != "Success":
            raise AppException(f"AMI login failed: {headers.get('Message')}")

    async def _read_loop(self) -> None:
        """
        Continuously read AMI blocks from the TCP stream.
        Dispatch events to registered handlers.
        Route responses to waiting action futures.
        Reconnect on connection loss.
        """
        block = ""
        while self._connected:
            try:
                if not self.reader:
                    break
                line_bytes = await self.reader.readline()
                if not line_bytes:
                    raise ConnectionError("EOF from AMI stream")
                
                line = line_bytes.decode('utf-8')
                block += line
                
                if block.endswith("\r\n\r\n"):
                    headers = await self._parse_block(block)
                    block = ""
                    
                    if "Event" in headers:
                        event_name = headers["Event"]
                        event = AMIEvent(event=event_name, headers=headers)
                        logger.debug("Received AMI Event", event_name=event_name, headers=headers)
                        
                        handlers = self._event_handlers.get(event_name, [])
                        for handler in handlers:
                            asyncio.create_task(handler(event))
                    elif "Response" in headers:
                        action_id = headers.get("ActionID")
                        response = AMIResponse(
                            response=headers["Response"],
                            message=headers.get("Message", ""),
                            headers=headers,
                            action_id=action_id
                        )
                        logger.debug("Received AMI Response", response=response.response, action_id=action_id)
                        
                        if action_id and action_id in self._pending_actions:
                            future = self._pending_actions.pop(action_id)
                            if not future.done():
                                future.set_result(response)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in AMI read loop", exc_info=e)
                self._connected = False
                asyncio.create_task(self.connect())
                break

    async def _parse_block(self, block: str) -> dict[str, str]:
        """Parse a raw AMI text block into a key-value dict."""
        headers = {}
        for line in block.split("\r\n"):
            if not line.strip():
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        return headers

    async def send_action(
        self,
        action: str,
        headers: dict[str, str],
        timeout: float = 10.0,
    ) -> AMIResponse:
        """
        Send an AMI action and await the response.
        """
        if not self._connected or not self.writer:
            raise TransferError("AMI not connected")

        action_id = str(uuid.uuid4())
        headers_to_send = {"Action": action, "ActionID": action_id}
        headers_to_send.update(headers)
        
        lines = []
        for k, v in headers_to_send.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("")
        
        action_data = "\r\n".join(lines).encode('utf-8')
        
        future = asyncio.get_event_loop().create_future()
        self._pending_actions[action_id] = future
        
        logger.debug("Sending AMI action", action=action, action_id=action_id, headers=headers)
        try:
            self.writer.write(action_data)
            await self.writer.drain()
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_actions.pop(action_id, None)
            raise TransferError(f"AMI action {action} timed out")
        except Exception as e:
            self._pending_actions.pop(action_id, None)
            raise TransferError(f"Failed to send AMI action {action}: {e}")

    def on_event(
        self,
        event_name: str,
        handler: Callable[[AMIEvent], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an async callback for a specific AMI event type."""
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

    def off_event(self, event_name: str) -> None:
        """Unregister event handler."""
        if event_name in self._event_handlers:
            del self._event_handlers[event_name]

    # ── Convenience action methods ─────────────────────────────────────────
    
    async def originate(
        self,
        channel: str,
        context: str,
        exten: str,
        priority: int = 1,
        caller_id: str = "",
        timeout: int = 30000,
        variables: dict[str, str] | None = None,
        async_: bool = True,
    ) -> AMIResponse:
        headers = {
            "Channel": channel,
            "Context": context,
            "Exten": exten,
            "Priority": str(priority),
            "Timeout": str(timeout),
            "Async": "true" if async_ else "false"
        }
        if caller_id:
            headers["CallerID"] = caller_id
            
        if variables:
            var_str = ",".join([f"{k}={v}" for k, v in variables.items()])
            headers["Variable"] = var_str
            
        return await self.send_action("Originate", headers)

    async def redirect(
        self,
        channel: str,
        context: str,
        exten: str,
        priority: int = 1,
    ) -> AMIResponse:
        headers = {
            "Channel": channel,
            "Context": context,
            "Exten": exten,
            "Priority": str(priority)
        }
        return await self.send_action("Redirect", headers)

    async def hangup(
        self,
        channel: str,
        cause: int = 16,
    ) -> AMIResponse:
        headers = {
            "Channel": channel,
            "Cause": str(cause)
        }
        return await self.send_action("Hangup", headers)

    async def get_channel_variable(
        self,
        channel: str,
        variable: str,
    ) -> str:
        headers = {
            "Channel": channel,
            "Variable": variable
        }
        res = await self.send_action("Getvar", headers)
        return res.headers.get("Value", "")

    async def set_channel_variable(
        self,
        channel: str,
        variable: str,
        value: str,
    ) -> AMIResponse:
        headers = {
            "Channel": channel,
            "Variable": variable,
            "Value": value
        }
        return await self.send_action("Setvar", headers)

    async def monitor_channel(
        self,
        channel: str,
        file_path: str,
        format_: str = 'wav',
        mix: bool = True,
    ) -> AMIResponse:
        headers = {
            "Channel": channel,
            "File": file_path,
            "Format": format_,
            "Mix": "true" if mix else "false"
        }
        return await self.send_action("Monitor", headers)

    async def stop_monitor(self, channel: str) -> AMIResponse:
        headers = {
            "Channel": channel
        }
        return await self.send_action("StopMonitor", headers)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def ping(self) -> bool:
        try:
            res = await self.send_action("Ping", {})
            return res.response == "Success"
        except Exception:
            return False

    async def get_active_channels(self) -> list[dict[str, str]]:
        # Using simple Status action implementation or CoreShowChannels
        try:
            res = await self.send_action("CoreShowChannels", {})
            # This is a stub for complex multi-event response grouping
            return []
        except Exception:
            return []
