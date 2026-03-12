"""Process-local STT session manager.

This manager keeps live STT sessions in process memory and keys them by socket
ID. Horizontal scale therefore requires sticky sessions so inbound socket audio
and control messages always hit the same app instance that owns the session.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    InvalidSTTStreamStateError,
)
from app.domain.schemas.stt import STTErrorPayload
from app.infrastructure.deepgram.client import DeepgramLiveClient
from app.services.stt.session import (
    STTSession,
    STTSessionEvent,
    STTSessionEventKind,
    STTSessionState,
)


class STTSessionManager:
    """Owns per-socket STT sessions, lifecycle control, and cleanup."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
        max_pending_audio_chunks: int = 32,
        startup_idle_timeout_seconds: int = 15,
        stream_idle_timeout_seconds: int = 45,
        finalize_grace_timeout_seconds: int = 10,
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory
        self._max_pending_audio_chunks = max_pending_audio_chunks
        self._startup_idle_timeout_seconds = startup_idle_timeout_seconds
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds
        self._finalize_grace_timeout_seconds = finalize_grace_timeout_seconds
        self._sessions: dict[str, STTSession] = {}
        self._audio_locks: dict[str, asyncio.Lock] = {}
        self._pending_audio_chunks: dict[str, int] = {}

    def create_provider_client(self) -> DeepgramLiveClient:
        """Create a provider wrapper for a new STT session."""
        return self._deepgram_client_factory()

    def get_session(self, sid: str) -> STTSession | None:
        """Return the active session for a socket, if any."""
        return self._sessions.get(sid)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        stream_id: str,
        organization_id: str | None,
        language: str | None,
    ) -> list[STTSessionEvent]:
        """Create and start one active STT session for a socket."""
        existing = self._sessions.get(sid)
        if existing is not None and existing.is_active:
            existing.assert_can_accept_new_stream(sid=sid, stream_id=stream_id)
            raise ActiveSTTStreamConflictError()

        if existing is not None and not existing.is_active:
            self._remove_session(sid)

        session = STTSession(
            sid=sid,
            user_id=user_id,
            stream_id=stream_id,
            organization_id=organization_id,
            language=language,
            provider_client=self.create_provider_client(),
        )
        self._sessions[sid] = session
        self._audio_locks[sid] = asyncio.Lock()
        self._pending_audio_chunks[sid] = 0

        emitted = await session.start()
        emitted.extend(await self._collect_session_events(session, wait_for_first=False))
        if not session.is_active:
            self._remove_session(sid)
        return emitted

    async def push_audio(
        self,
        *,
        sid: str,
        stream_id: str,
        chunk: bytes,
    ) -> list[STTSessionEvent]:
        """Push one binary audio chunk to the owning session with backpressure."""
        session = self._require_session(sid)
        session.assert_owner(sid=sid, stream_id=stream_id)
        self._guard_audio_backlog(sid)

        self._pending_audio_chunks[sid] += 1
        try:
            async with self._audio_locks[sid]:
                session = self._require_session(sid)
                await session.push_audio(sid=sid, stream_id=stream_id, chunk=chunk)
        finally:
            self._pending_audio_chunks[sid] = max(
                0, self._pending_audio_chunks.get(sid, 1) - 1
            )

        emitted = await self._collect_session_events(session, wait_for_first=False)
        if not session.is_active:
            self._remove_session(sid)
        return emitted

    async def finalize_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[STTSessionEvent]:
        """Request provider finalize for the owning session."""
        session = self._require_session(sid)
        await session.request_finalize(sid=sid, stream_id=stream_id)
        emitted = await self._collect_session_events(session, wait_for_first=False)
        if not session.is_active:
            self._remove_session(sid)
        return emitted

    async def stop_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[STTSessionEvent]:
        """Stop the active session and eagerly clean up manager state."""
        session = self._require_session(sid)
        await session.stop(sid=sid, stream_id=stream_id)
        emitted = await self._collect_session_events(
            session,
            wait_for_first=True,
            timeout_seconds=1.0,
        )
        self._remove_session(sid)
        return emitted

    async def handle_disconnect(self, sid: str) -> list[STTSessionEvent]:
        """Always close and remove the active session on socket disconnect."""
        session = self._sessions.get(sid)
        if session is None:
            return []

        emitted: list[STTSessionEvent] = []
        if session.is_active:
            await session.provider_client.close()
            emitted.extend(
                await self._collect_session_events(
                    session,
                    wait_for_first=True,
                    timeout_seconds=1.0,
                )
            )

        self._remove_session(sid)
        return emitted

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[STTSessionEvent]:
        """Collect normalized provider-driven events for a live session."""
        session = self._require_session(sid)
        emitted = await self._collect_session_events(
            session,
            wait_for_first=wait_for_first,
            timeout_seconds=timeout_seconds,
        )
        if not session.is_active:
            self._remove_session(sid)
        return emitted

    async def reap_inactive_sessions(self) -> list[STTSessionEvent]:
        """Apply inactivity policy to all live sessions.

        Policy:
        - If a session starts and never receives audio before the startup timeout,
          hard-close it immediately.
        - If a streaming session received audio and then goes idle too long,
          auto-finalize first.
        - If a finalizing session remains idle past the grace timeout, hard-close it.
        """

        emitted: list[STTSessionEvent] = []
        now = self._utcnow()

        for sid, session in list(self._sessions.items()):
            if not session.is_active:
                self._remove_session(sid)
                continue

            age_seconds = (now - session.created_at).total_seconds()
            provider_idle = session.seconds_since_provider_activity(at=now)
            audio_idle = session.seconds_since_audio(at=now)

            if session.last_audio_at is None and age_seconds >= self._startup_idle_timeout_seconds:
                await session.provider_client.close()
                emitted.append(self._build_timeout_event(session, "Session timed out before any audio arrived"))
                self._remove_session(sid)
                continue

            if (
                session.state == STTSessionState.STREAMING
                and audio_idle is not None
                and audio_idle >= self._stream_idle_timeout_seconds
            ):
                await session.request_finalize(sid=session.sid, stream_id=session.stream_id)
                emitted.extend(await self._collect_session_events(session, wait_for_first=False))
                if not session.is_active:
                    self._remove_session(sid)
                continue

            if (
                session.state == STTSessionState.FINALIZING
                and provider_idle is not None
                and provider_idle >= self._finalize_grace_timeout_seconds
            ):
                await session.provider_client.close()
                emitted.extend(
                    await self._collect_session_events(
                        session,
                        wait_for_first=False,
                    )
                )
                self._remove_session(sid)

        return emitted

    async def _collect_session_events(
        self,
        session: STTSession,
        *,
        wait_for_first: bool,
        timeout_seconds: float | None = None,
    ) -> list[STTSessionEvent]:
        provider_events = session.provider_client.drain_pending_events()
        if not provider_events and wait_for_first:
            try:
                if timeout_seconds is None:
                    provider_events.append(await session.provider_client.next_event())
                else:
                    provider_events.append(
                        await asyncio.wait_for(
                            session.provider_client.next_event(),
                            timeout=timeout_seconds,
                        )
                    )
            except asyncio.TimeoutError:
                return []

        provider_events.extend(session.provider_client.drain_pending_events())
        if not provider_events:
            return []
        return session.consume_provider_events(provider_events)

    def _require_session(self, sid: str) -> STTSession:
        session = self._sessions.get(sid)
        if session is None:
            raise InvalidSTTStreamStateError("No active STT session for this socket")
        return session

    def _guard_audio_backlog(self, sid: str) -> None:
        pending = self._pending_audio_chunks.get(sid, 0)
        if pending >= self._max_pending_audio_chunks:
            raise InvalidSTTStreamStateError(
                "Audio queue overflow for active STT session"
            )

    def _remove_session(self, sid: str) -> None:
        self._sessions.pop(sid, None)
        self._audio_locks.pop(sid, None)
        self._pending_audio_chunks.pop(sid, None)

    @staticmethod
    def _build_timeout_event(session: STTSession, message: str) -> STTSessionEvent:
        return STTSessionEvent(
            kind=STTSessionEventKind.ERROR,
            payload=STTErrorPayload(
                stream_id=session.stream_id,
                error_code="stt_session_timeout",
                error_message=message,
            ),
        )

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
