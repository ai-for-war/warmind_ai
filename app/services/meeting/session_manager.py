"""Process-local meeting session manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from app.common.exceptions import (
    ActiveMeetingRecordConflictError,
    InvalidMeetingRecordStateError,
)
from app.infrastructure.deepgram.client import DeepgramLiveClient
from app.services.meeting.session import MeetingSession, MeetingSessionEvent


class MeetingSessionManager:
    """Owns per-socket meeting sessions, lifecycle control, and cleanup."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory
        self._sessions: dict[str, MeetingSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def create_provider_client(self) -> DeepgramLiveClient:
        """Create a provider wrapper for a new meeting session."""
        return self._deepgram_client_factory()

    def get_session(self, sid: str) -> MeetingSession | None:
        """Return the active meeting session for a socket, if any."""
        return self._sessions.get(sid)

    def discard_session(self, sid: str) -> None:
        """Drop a session from the process-local registry."""
        self._sessions.pop(sid, None)
        self._locks.pop(sid, None)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        organization_id: str,
        meeting_id: str,
        language: str,
    ) -> list[MeetingSessionEvent]:
        """Create and start one active meeting session for a socket."""
        existing = self._sessions.get(sid)
        if existing is not None and existing.is_active:
            existing.assert_can_accept_new_meeting(sid=sid, meeting_id=meeting_id)
            raise ActiveMeetingRecordConflictError()

        if existing is not None and not existing.is_active:
            self.discard_session(sid)

        session = MeetingSession(
            meeting_id=meeting_id,
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            language=language,
            provider_client=self.create_provider_client(),
        )
        self._sessions[sid] = session
        self._locks[sid] = asyncio.Lock()

        try:
            return await session.start()
        except Exception:
            self.discard_session(sid)
            raise

    async def push_audio(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
        chunk: bytes,
    ) -> list[MeetingSessionEvent]:
        """Push one binary audio chunk to the owning meeting session."""
        session = self._require_session(sid)
        async with self._locks[sid]:
            session = self._require_session(sid)
            await session.push_audio(
                sid=sid,
                user_id=user_id,
                meeting_id=meeting_id,
                chunk=chunk,
            )
        return []

    async def stop_session(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> list[MeetingSessionEvent]:
        """Stop the active meeting session."""
        self._require_session(sid)
        async with self._locks[sid]:
            session = self._require_session(sid)
            try:
                events = await session.stop(
                    sid=sid,
                    user_id=user_id,
                    meeting_id=meeting_id,
                )
            finally:
                self.discard_session(sid)
        return events

    async def handle_disconnect(self, sid: str) -> list[MeetingSessionEvent]:
        """Clean up an active meeting session on socket disconnect."""
        session = self._sessions.get(sid)
        if session is None:
            return []

        lock = self._locks.setdefault(sid, asyncio.Lock())
        async with lock:
            session = self._sessions.get(sid)
            if session is None:
                return []
            try:
                events = await session.stop_for_disconnect()
            finally:
                self.discard_session(sid)
        return events

    def _require_session(self, sid: str) -> MeetingSession:
        session = self._sessions.get(sid)
        if session is None:
            raise InvalidMeetingRecordStateError(
                "No active meeting record for this socket. Meeting sessions are "
                "process-local and require sticky-session routing."
            )
        return session
