"""Process-local meeting session manager.

This manager keeps live meeting transcription sessions in process memory and
keys them by socket ID. Horizontal scale therefore requires sticky sessions so
inbound socket audio and control messages always hit the same app instance that
owns the session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    InvalidSTTStreamStateError,
    STTProviderConnectionError,
    STTStreamOwnershipError,
)
from app.domain.models.meeting import MeetingStatus
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
)
from app.repo.meeting_repo import MeetingRepository
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.services.meeting.session import MeetingSession, MeetingSessionEvent

logger = logging.getLogger(__name__)


class MeetingSessionManager:
    """Owns per-socket meeting sessions, lifecycle control, and cleanup."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
        meeting_repo: MeetingRepository,
        utterance_repo: MeetingUtteranceRepository,
        max_pending_audio_chunks: int = 32,
        finalize_grace_timeout_seconds: float = 10.0,
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory
        self._meeting_repo = meeting_repo
        self._utterance_repo = utterance_repo
        self._max_pending_audio_chunks = max(max_pending_audio_chunks, 1)
        self._finalize_grace_timeout_seconds = max(
            finalize_grace_timeout_seconds,
            0.0,
        )
        self._sessions: dict[str, MeetingSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending_audio_chunks: dict[str, int] = {}
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
        self._pending_audio_chunks.pop(sid, None)
        self._held_provider_events.pop(sid, None)

    def acknowledge_stop_emitted(self, sid: str) -> None:
        """Release any retained provider events after terminal emit handling."""
        self._held_provider_events.pop(sid, None)
        session = self._sessions.get(sid)
        if session is not None and not session.is_active:
            self.discard_session(sid)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        organization_id: str,
        stream_id: str,
        title: str | None = None,
        language: str | None = None,
        meeting_id: str | None = None,
        source: str = "google_meet",
    ) -> list[MeetingSessionEvent]:
        """Create and start one active meeting session for a socket."""
        owner = self._find_active_session_by_stream_id(stream_id)
        if owner is not None and owner.sid != sid:
            raise STTStreamOwnershipError(
                "Another socket already owns this meeting stream"
            )

        existing = self._sessions.get(sid)
        if existing is not None and existing.is_active:
            existing.assert_can_accept_new_stream(sid=sid, stream_id=stream_id)
            raise ActiveSTTStreamConflictError()

        if existing is not None and not existing.is_active:
            self.discard_session(sid)

        session = MeetingSession(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            provider_client=self.create_provider_client(),
            meeting_repo=self._meeting_repo,
            utterance_repo=self._utterance_repo,
            meeting_id=meeting_id,
            title=title,
            language=language,
            source=source,
        )
        self._sessions[sid] = session
        self._locks[sid] = asyncio.Lock()
        self._pending_audio_chunks[sid] = 0

        try:
            emitted = await session.start()
            emitted.extend(
                await self._collect_session_events(session, wait_for_first=False)
            )
        except Exception:
            self.discard_session(sid)
            raise

        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def push_audio(
        self,
        *,
        sid: str,
        stream_id: str,
        chunk: bytes,
    ) -> list[MeetingSessionEvent]:
        """Push one binary audio chunk to the owning session."""
        session = self._require_session(sid, stream_id=stream_id)
        self._guard_audio_backlog(sid)

        lock = self._locks[sid]
        self._pending_audio_chunks[sid] = self._pending_audio_chunks.get(sid, 0) + 1
        try:
            async with lock:
                session = self._require_session(sid, stream_id=stream_id)
                await session.push_audio(
                    sid=sid,
                    stream_id=stream_id,
                    chunk=chunk,
                )
                emitted = await self._collect_session_events(
                    session,
                    wait_for_first=False,
                )
        except STTProviderConnectionError as exc:
            failed_event = await self._fail_live_session(
                session=session,
                message=str(exc),
                error_code="meeting_provider_connection_failed",
            )
            return [failed_event]
        finally:
            self._pending_audio_chunks[sid] = max(
                0,
                self._pending_audio_chunks.get(sid, 1) - 1,
            )

        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def finalize_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[MeetingSessionEvent]:
        """Finalize the active meeting session and close it cleanly."""
        return await self._finish_session(
            sid=sid,
            stream_id=stream_id,
            disconnect=False,
        )

    async def stop_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[MeetingSessionEvent]:
        """Stop the active meeting session through the same clean flush path."""
        return await self._finish_session(
            sid=sid,
            stream_id=stream_id,
            disconnect=False,
        )

    async def handle_disconnect(self, sid: str) -> list[MeetingSessionEvent]:
        """Flush and interrupt the active meeting session on socket disconnect."""
        session = self._sessions.get(sid)
        if session is None:
            return []

        lock = self._locks.setdefault(sid, asyncio.Lock())
        async with lock:
            session = self._sessions.get(sid)
            if session is None:
                return []
            if not session.is_active:
                self.discard_session(sid)
                return []

            try:
                await session.request_interrupt(
                    sid=sid,
                    stream_id=session.stream_id,
                )
                emitted = await self._finalize_active_session(session)
            except STTProviderConnectionError as exc:
                failed_event = await self._fail_live_session(
                    session=session,
                    message=str(exc),
                    error_code="meeting_provider_connection_failed",
                )
                return [failed_event]

        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        """Collect normalized provider-driven events for a live meeting session."""
        session = self._require_session(sid)
        lock = self._locks[sid]
        async with lock:
            session = self._require_session(sid)
            emitted = await self._collect_session_events(
                session,
                wait_for_first=wait_for_first,
                timeout_seconds=timeout_seconds,
            )
        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def _finish_session(
        self,
        *,
        sid: str,
        stream_id: str,
        disconnect: bool,
    ) -> list[MeetingSessionEvent]:
        session = self._require_session(sid, stream_id=stream_id)
        lock = self._locks[sid]

        async with lock:
            session = self._require_session(sid, stream_id=stream_id)
            try:
                if disconnect:
                    await session.request_interrupt(
                        sid=sid,
                        stream_id=stream_id,
                    )
                else:
                    await session.request_finalize(
                        sid=sid,
                        stream_id=stream_id,
                    )
                emitted = await self._finalize_active_session(session)
            except STTProviderConnectionError as exc:
                failed_event = await self._fail_live_session(
                    session=session,
                    message=str(exc),
                    error_code="meeting_provider_connection_failed",
                )
                return [failed_event]

        if not session.is_active:
            self.discard_session(sid)
        return emitted

    async def _finalize_active_session(
        self,
        session: MeetingSession,
    ) -> list[MeetingSessionEvent]:
        emitted = await self._collect_session_events(session, wait_for_first=False)
        if session.state == MeetingStatus.FINALIZING and session.is_active:
            emitted.extend(
                await self._drain_finalizing_session(
                    session,
                    timeout_seconds=self._finalize_grace_timeout_seconds,
                )
            )
        return emitted

    async def _drain_finalizing_session(
        self,
        session: MeetingSession,
        *,
        timeout_seconds: float | None,
    ) -> list[MeetingSessionEvent]:
        emitted: list[MeetingSessionEvent] = []
        loop = asyncio.get_running_loop()
        deadline = None if timeout_seconds is None else loop.time() + timeout_seconds

        while session.is_active and session.state == MeetingStatus.FINALIZING:
            remaining = None if deadline is None else max(0.0, deadline - loop.time())
            if remaining is not None and remaining <= 0:
                break

            batch = await self._collect_session_events(
                session,
                wait_for_first=True,
                timeout_seconds=remaining,
            )
            if batch:
                emitted.extend(batch)
                continue
            if deadline is not None and loop.time() >= deadline:
                break

        if session.is_active and session.state == MeetingStatus.FINALIZING:
            emitted.extend(await session.flush_open_utterance())
            emitted.extend(await self._close_finalized_session(session))
        return emitted

    async def _collect_session_events(
        self,
        session: MeetingSession,
        *,
        wait_for_first: bool,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        provider_events = self._held_provider_events.pop(session.sid, [])
        provider_events.extend(session.provider_client.drain_pending_events())

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
                return await self._handle_idle_session(session)

        provider_events.extend(session.provider_client.drain_pending_events())
        if not provider_events:
            return await self._handle_idle_session(session)

        should_close_after_finalize = (
            session.state == MeetingStatus.FINALIZING
            and any(
                event.kind == ProviderEventKind.PROVIDER_FINALIZE
                for event in provider_events
            )
        )

        emitted = await session.consume_provider_events(provider_events)
        if should_close_after_finalize and session.is_active:
            emitted.extend(await session.flush_open_utterance())
            emitted.extend(await self._close_finalized_session(session))
        return emitted

    async def _handle_idle_session(
        self,
        session: MeetingSession,
    ) -> list[MeetingSessionEvent]:
        if session.state == MeetingStatus.FINALIZING:
            return []

        if not session.should_send_keepalive():
            return []

        try:
            await session.send_keepalive()
        except Exception as exc:
            keepalive_error = await self._fail_live_session(
                session=session,
                message=str(exc),
                error_code="meeting_keepalive_failed",
            )
            return [keepalive_error]
        return []

    async def _close_finalized_session(
        self,
        session: MeetingSession,
    ) -> list[MeetingSessionEvent]:
        await session.close_provider()

        close_events = session.provider_client.drain_pending_events()
        if not any(event.kind == ProviderEventKind.CLOSE for event in close_events):
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
        if not any(event.kind == ProviderEventKind.CLOSE for event in close_events):
            close_events.append(ProviderEvent(kind=ProviderEventKind.CLOSE))

        return await session.consume_provider_events(close_events)

    def _require_session(
        self,
        sid: str,
        *,
        stream_id: str | None = None,
    ) -> MeetingSession:
        session = self._sessions.get(sid)
        if session is not None:
            return session

        if stream_id is not None:
            owner = self._find_active_session_by_stream_id(stream_id)
            if owner is not None and owner.sid != sid:
                raise STTStreamOwnershipError()

        raise InvalidSTTStreamStateError(
            "No active meeting session for this socket. Meeting sessions are "
            "process-local and require sticky-session routing."
        )

    def _find_active_session_by_stream_id(self, stream_id: str) -> MeetingSession | None:
        for session in self._sessions.values():
            if session.stream_id == stream_id and session.is_active:
                return session
        return None

    def _guard_audio_backlog(self, sid: str) -> None:
        pending = self._pending_audio_chunks.get(sid, 0)
        if pending >= self._max_pending_audio_chunks:
            raise InvalidSTTStreamStateError(
                "Audio queue overflow for active meeting session"
            )

    async def _fail_live_session(
        self,
        *,
        session: MeetingSession,
        message: str,
        error_code: str,
    ) -> MeetingSessionEvent:
        try:
            await session.close_provider()
        except Exception:
            logger.debug(
                "Provider close during failure handling raised for %s",
                session.stream_id,
                exc_info=True,
            )

        failed_event = await session.fail(message, error_code=error_code)
        self.discard_session(session.sid)
        return failed_event
