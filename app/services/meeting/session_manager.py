"""Process-local meeting session manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from app.common.exceptions import (
    ActiveMeetingRecordConflictError,
    InvalidMeetingRecordStateError,
    STTProviderConnectionError,
)
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
)
from app.services.meeting.session import (
    MeetingSession,
    MeetingSessionEvent,
    MeetingSessionState,
)


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
        self._held_provider_events: dict[str, list[ProviderEvent]] = {}

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
        self._held_provider_events.pop(sid, None)

    def acknowledge_stop_emitted(self, sid: str) -> None:
        """Release provider event draining after STOPPING is emitted."""
        session = self._sessions.get(sid)
        if session is not None:
            session.acknowledge_stop_emitted()

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
            try:
                await session.push_audio(
                    sid=sid,
                    user_id=user_id,
                    meeting_id=meeting_id,
                    chunk=chunk,
                )
            except STTProviderConnectionError as exc:
                failed_event = await self._fail_live_session(
                    session=session,
                    message=str(exc),
                    error_code="meeting_record_provider_connection_failed",
                )
                return [failed_event]
        return []

    async def stop_session(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> list[MeetingSessionEvent]:
        """Request finalize for the active meeting session."""
        self._require_session(sid)
        async with self._locks[sid]:
            session = self._require_session(sid)
            try:
                return await session.request_finalize(
                    sid=sid,
                    user_id=user_id,
                    meeting_id=meeting_id,
                )
            except STTProviderConnectionError as exc:
                failed_event = await self._fail_live_session(
                    session=session,
                    message=str(exc),
                    error_code="meeting_record_provider_connection_failed",
                )
                return [failed_event]

    async def handle_disconnect(self, sid: str) -> list[MeetingSessionEvent]:
        """Finalize an active meeting session during socket disconnect cleanup."""
        session = self._sessions.get(sid)
        if session is None:
            return []

        lock = self._locks.setdefault(sid, asyncio.Lock())
        async with lock:
            session = self._sessions.get(sid)
            if session is None:
                return []
            try:
                return await session.request_finalize_for_disconnect()
            except STTProviderConnectionError as exc:
                failed_event = await self._fail_live_session(
                    session=session,
                    message=str(exc),
                    error_code="meeting_record_provider_connection_failed",
                )
                return [failed_event]

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        """Collect normalized provider-driven events for a live meeting session."""
        session = self._require_session(sid)
        emitted = await self._collect_session_events(
            session,
            wait_for_first=wait_for_first,
            timeout_seconds=timeout_seconds,
        )
        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def _collect_session_events(
        self,
        session: MeetingSession,
        *,
        wait_for_first: bool,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        provider_events = self._held_provider_events.pop(session.sid, [])
        if session.awaiting_stop_emit:
            if provider_events:
                self._hold_provider_events(session.sid, provider_events)
            return []

        if not provider_events:
            provider_events = session.provider_client.drain_pending_events()
        if not provider_events and wait_for_first:
            try:
                if timeout_seconds is None:
                    next_event = await session.provider_client.next_event()
                else:
                    next_event = await asyncio.wait_for(
                        session.provider_client.next_event(),
                        timeout=timeout_seconds,
                    )
                if session.awaiting_stop_emit:
                    held_events = [next_event]
                    held_events.extend(session.provider_client.drain_pending_events())
                    self._hold_provider_events(session.sid, held_events)
                    return []
                provider_events.append(next_event)
            except asyncio.TimeoutError:
                return await self._handle_idle_session(session)

        provider_events.extend(session.provider_client.drain_pending_events())
        if session.awaiting_stop_emit:
            if provider_events:
                self._hold_provider_events(session.sid, provider_events)
            return []
        if not provider_events:
            return await self._handle_idle_session(session)

        should_close_after_finalize = (
            session.state == MeetingSessionState.FINALIZING
            and any(
                event.kind == ProviderEventKind.PROVIDER_FINALIZE
                or (
                    event.transcript is not None
                    and event.transcript.from_finalize
                )
                for event in provider_events
            )
        )
        emitted = session.consume_provider_events(provider_events)
        if should_close_after_finalize and session.is_active:
            emitted.extend(await self._close_finalized_session(session))
        return emitted

    async def _handle_idle_session(
        self,
        session: MeetingSession,
    ) -> list[MeetingSessionEvent]:
        if (
            session.state == MeetingSessionState.FINALIZING
            and session.finalize_requested_at is not None
            and (
                datetime.now(timezone.utc) - session.finalize_requested_at
            ).total_seconds()
            >= 1.0
        ):
            return await self._close_finalized_session(session)

        if not session.should_send_keepalive():
            return []

        try:
            await session.send_keepalive()
        except Exception as exc:
            failed_event = await self._fail_live_session(
                session=session,
                message=str(exc),
                error_code="meeting_record_keepalive_failed",
            )
            return [failed_event]

        return []

    async def _close_finalized_session(
        self,
        session: MeetingSession,
    ) -> list[MeetingSessionEvent]:
        await session.provider_client.close()

        close_events = session.provider_client.drain_pending_events()
        if not close_events:
            try:
                close_events.append(
                    await asyncio.wait_for(
                        session.provider_client.next_event(),
                        timeout=1.0,
                    )
                )
            except asyncio.TimeoutError:
                pass

        close_events.extend(session.provider_client.drain_pending_events())
        if not close_events:
            close_events = [ProviderEvent(kind=ProviderEventKind.CLOSE)]
        elif not any(event.kind == ProviderEventKind.CLOSE for event in close_events):
            close_events.append(ProviderEvent(kind=ProviderEventKind.CLOSE))

        return session.consume_provider_events(close_events)

    def _require_session(self, sid: str) -> MeetingSession:
        session = self._sessions.get(sid)
        if session is None:
            raise InvalidMeetingRecordStateError(
                "No active meeting record for this socket. Meeting sessions are "
                "process-local and require sticky-session routing."
            )
        return session

    async def _fail_live_session(
        self,
        *,
        session: MeetingSession,
        message: str,
        error_code: str,
    ) -> MeetingSessionEvent:
        try:
            await session.provider_client.close()
        except Exception:
            pass

        failed_event = session.fail(message, error_code=error_code)
        self.discard_session(session.sid)
        return failed_event

    def _hold_provider_events(self, sid: str, events: list[ProviderEvent]) -> None:
        if not events:
            return
        self._held_provider_events.setdefault(sid, []).extend(events)
