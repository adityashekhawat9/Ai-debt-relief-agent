import asyncio
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Callable, Coroutine, Any

class AudioSocketKind(IntEnum):
    HANGUP = 0x00
    UUID   = 0x01
    AUDIO  = 0x10
    ERROR  = 0xFF

@dataclass
class AudioSocketSession:
    channel_uuid: str           # 36-char UUID from Asterisk
    call_id: str | None         # Our internal call_id (linked after UUID received)
    remote_addr: tuple[str, int]
    connected_at: datetime = field(default_factory=datetime.utcnow)
    bytes_received: int = 0
    bytes_sent: int = 0
    is_active: bool = True
    audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    # Thread-safe writing
    _writer_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _writer: asyncio.StreamWriter | None = None

class AudioSocketServer:
    """
    Async TCP server implementing the Asterisk AudioSocket protocol.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9092,
    ) -> None:
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._sessions: dict[str, AudioSocketSession] = {}
        self._on_session_start: Callable[[AudioSocketSession], Coroutine[Any, Any, None]] | None = None
        self._on_session_end: Callable[[AudioSocketSession], Coroutine[Any, Any, None]] | None = None

    async def start(self) -> None:
        """Start the TCP server. Runs asyncio.start_server()."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
    
    async def stop(self) -> None:
        """Stop the server, close all sessions."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        for session in list(self._sessions.values()):
            session.is_active = False
            if session._writer:
                session._writer.close()
        self._sessions.clear()
    
    def on_session_start(
        self,
        handler: Callable[[AudioSocketSession], Coroutine[Any, Any, None]],
    ) -> None:
        """Register callback for new AudioSocket sessions."""
        self._on_session_start = handler
    
    def on_session_end(
        self,
        handler: Callable[[AudioSocketSession], Coroutine[Any, Any, None]],
    ) -> None:
        """Register callback for session termination."""
        self._on_session_end = handler
    
    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle one Asterisk AudioSocket connection."""
        addr = writer.get_extra_info('peername')
        session: AudioSocketSession | None = None
        
        try:
            # 1. Read first packet — must be UUID (0x01)
            kind, payload = await self._read_packet(reader)
            if kind != AudioSocketKind.UUID or len(payload) != 16:
                raise ConnectionError("First packet must be UUID (16 bytes)")
            
            import uuid
            channel_uuid = str(uuid.UUID(bytes=payload))
            
            # 2. Create AudioSocketSession
            session = AudioSocketSession(
                channel_uuid=channel_uuid,
                call_id=None,
                remote_addr=addr,
                _writer=writer
            )
            self._sessions[channel_uuid] = session
            
            # 3. Fire on_session_start
            if self._on_session_start:
                await self._on_session_start(session)
                
            # 4. Enter read loop
            while session.is_active:
                kind, payload = await self._read_packet(reader)
                if kind == AudioSocketKind.HANGUP:
                    break
                elif kind == AudioSocketKind.AUDIO:
                    session.bytes_received += len(payload)
                    if not session.audio_queue.full():
                        await session.audio_queue.put(payload)
                elif kind == AudioSocketKind.ERROR:
                    break
                    
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            # 5. On HANGUP or disconnect: fire on_session_end, clean up
            if session:
                session.is_active = False
                if self._on_session_end:
                    await self._on_session_end(session)
                self._sessions.pop(session.channel_uuid, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
    
    async def _read_packet(
        self,
        reader: asyncio.StreamReader,
    ) -> tuple[AudioSocketKind, bytes]:
        """Read exactly one AudioSocket packet."""
        try:
            header = await reader.readexactly(3)
        except asyncio.IncompleteReadError as e:
            raise ConnectionError("EOF while reading header") from e
            
        kind = header[0]
        length = struct.unpack('>H', header[1:3])[0]
        
        try:
            payload = await reader.readexactly(length) if length > 0 else b''
        except asyncio.IncompleteReadError as e:
            raise ConnectionError("EOF while reading payload") from e
            
        try:
            return AudioSocketKind(kind), payload
        except ValueError:
            raise ConnectionError(f"Unknown packet kind: {kind}")
    
    async def send_audio(
        self,
        channel_uuid: str,
        pcm_data: bytes,
    ) -> None:
        """Send PCM audio to Asterisk for a specific channel."""
        session = self.get_session(channel_uuid)
        if not session or not session.is_active or not session._writer:
            from core.exceptions import AppException
            raise AppException(
                message=f"AudioSocket session {channel_uuid!r} not found or inactive",
                code="SESSION_NOT_FOUND",
                status_code=404,
            )
            
        chunk_size = 160
        async with session._writer_lock:
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i+chunk_size]
                header = struct.pack('>BH', AudioSocketKind.AUDIO.value, len(chunk))
                session._writer.write(header + chunk)
                session.bytes_sent += len(chunk)
            await session._writer.drain()
    
    async def send_hangup(self, channel_uuid: str) -> None:
        """Send HANGUP packet."""
        session = self.get_session(channel_uuid)
        if not session or not session.is_active or not session._writer:
            return
            
        async with session._writer_lock:
            header = struct.pack('>BH', AudioSocketKind.HANGUP.value, 0)
            session._writer.write(header)
            await session._writer.drain()
        session.is_active = False
    
    async def get_audio_chunk(
        self,
        channel_uuid: str,
        timeout: float = 5.0,
    ) -> bytes | None:
        """Get next audio chunk from session queue (blocking, with timeout)."""
        session = self.get_session(channel_uuid)
        if not session:
            return None
            
        try:
            return await asyncio.wait_for(session.audio_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    def get_session(self, channel_uuid: str) -> AudioSocketSession | None:
        """Get session by channel UUID."""
        return self._sessions.get(channel_uuid)
    
    def get_active_session_count(self) -> int:
        """Count of currently active AudioSocket sessions."""
        return len(self._sessions)
    
    async def echo_session(self, session: AudioSocketSession) -> None:
        """Echo all received audio back to the caller."""
        while session.is_active:
            try:
                chunk = await asyncio.wait_for(session.audio_queue.get(), timeout=1.0)
                await self.send_audio(session.channel_uuid, chunk)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
