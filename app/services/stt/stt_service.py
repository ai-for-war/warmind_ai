"""STT service scaffolding."""

from __future__ import annotations

from app.services.stt.session import STTSession, STTSessionEvent
from app.services.stt.session_manager import STTSessionManager


class STTService:
    """Application service entry point for live speech-to-text flows."""

    def __init__(self, *, session_manager: STTSessionManager) -> None:
        self.session_manager = session_manager

    def get_session(self, sid: str) -> STTSession | None:
        """Return the live STT session for a socket, if any."""
        return self.session_manager.get_session(sid)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        stream_id: str,
        organization_id: str | None,
        language: str | None,
    ) -> list[STTSessionEvent]:
        """Start one live STT session."""
        return await self.session_manager.start_session(
            sid=sid,
            user_id=user_id,
            stream_id=stream_id,
            organization_id=organization_id,
            language=language,
        )

    async def push_audio(
        self,
        *,
        sid: str,
        stream_id: str,
        chunk: bytes,
    ) -> list[STTSessionEvent]:
        """Push one audio chunk into the active session."""
        return await self.session_manager.push_audio(
            sid=sid,
            stream_id=stream_id,
            chunk=chunk,
        )

    async def finalize_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[STTSessionEvent]:
        """Finalize the active session."""
        return await self.session_manager.finalize_session(
            sid=sid,
            stream_id=stream_id,
        )

    async def stop_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[STTSessionEvent]:
        """Stop the active session."""
        return await self.session_manager.stop_session(
            sid=sid,
            stream_id=stream_id,
        )

    async def handle_disconnect(self, sid: str) -> list[STTSessionEvent]:
        """Clean up an active STT session on socket disconnect."""
        return await self.session_manager.handle_disconnect(sid)

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[STTSessionEvent]:
        """Collect pending provider-driven session events."""
        return await self.session_manager.collect_session_events(
            sid=sid,
            wait_for_first=wait_for_first,
            timeout_seconds=timeout_seconds,
        )

    async def reap_session(self, sid: str) -> list[STTSessionEvent]:
        """Apply inactivity policy to one session."""
        return await self.session_manager.reap_session(sid)
