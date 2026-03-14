"""Process-local STT session manager.

This manager keeps live STT sessions in process memory and keys them by socket
ID. Horizontal scale therefore requires sticky sessions so inbound socket audio
and control messages always hit the same app instance that owns the session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    AsyncUtterancePersistenceError,
    InterviewAITriggerError,
    InvalidSTTStreamStateError,
    RedisContextWriteError,
)
from app.domain.schemas.stt import STTChannelMap, STTErrorPayload
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
)
from app.repo.interview_utterance_repo import InterviewUtteranceRepository
from app.services.interview.answer_service import InterviewAnswerService
from app.services.stt.session import (
    STTSession,
    STTSessionEvent,
    STTSessionEventKind,
    STTSessionState,
)
from app.services.stt.context_store import (
    RedisInterviewContextStore,
    StableInterviewContextUtterance,
)

logger = logging.getLogger(__name__)


class STTSessionManager:
    """Owns per-socket STT sessions, lifecycle control, and cleanup."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
        context_store: RedisInterviewContextStore | None = None,
        utterance_repo: InterviewUtteranceRepository | None = None,
        answer_service: InterviewAnswerService | None = None,
        async_persist_retry_attempts: int = 3,
        async_persist_retry_delay_seconds: float = 0.5,
        max_pending_audio_chunks: int = 32,
        startup_idle_timeout_seconds: int = 15,
        stream_idle_timeout_seconds: int = 45,
        finalize_grace_timeout_seconds: int = 10,
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory
        self._context_store = context_store
        self._utterance_repo = utterance_repo
        self._answer_service = answer_service
        self._async_persist_retry_attempts = max(async_persist_retry_attempts, 1)
        self._async_persist_retry_delay_seconds = max(
            async_persist_retry_delay_seconds,
            0.0,
        )
        self._max_pending_audio_chunks = max_pending_audio_chunks
        self._startup_idle_timeout_seconds = startup_idle_timeout_seconds
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds
        self._finalize_grace_timeout_seconds = finalize_grace_timeout_seconds
        self._sessions: dict[str, STTSession] = {}
        self._audio_locks: dict[str, asyncio.Lock] = {}
        self._pending_audio_chunks: dict[str, int] = {}
        self._deferred_events: dict[str, list[STTSessionEvent]] = {}
        self._persistence_tasks: set[asyncio.Task[None]] = set()
        self._answer_tasks: dict[str, set[asyncio.Task[None]]] = {}

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
        conversation_id: str,
        organization_id: str | None,
        language: str | None,
        channel_map: STTChannelMap,
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
            conversation_id=conversation_id,
            organization_id=organization_id,
            language=language,
            channel_map=channel_map,
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

        for sid in list(self._sessions):
            emitted.extend(await self.reap_session(sid))

        return emitted

    async def reap_session(self, sid: str) -> list[STTSessionEvent]:
        """Apply inactivity policy to one live session."""
        session = self._sessions.get(sid)
        if session is None:
            return []
        if not session.is_active:
            self._remove_session(sid)
            return []

        now = self._utcnow()
        age_seconds = (now - session.created_at).total_seconds()
        provider_idle = session.seconds_since_provider_activity(at=now)
        audio_idle = session.seconds_since_audio(at=now)

        if session.last_audio_at is None and age_seconds >= self._startup_idle_timeout_seconds:
            await session.provider_client.close()
            self._remove_session(sid)
            return [
                self._build_timeout_event(
                    session,
                    "Session timed out before any audio arrived",
                )
            ]

        if (
            session.state == STTSessionState.STREAMING
            and audio_idle is not None
            and audio_idle >= self._stream_idle_timeout_seconds
        ):
            await session.request_finalize(sid=session.sid, stream_id=session.stream_id)
            emitted = await self._collect_session_events(session, wait_for_first=False)
            if not session.is_active:
                self._remove_session(sid)
            return emitted

        if (
            session.state == STTSessionState.FINALIZING
            and provider_idle is not None
            and provider_idle >= self._finalize_grace_timeout_seconds
        ):
            await session.provider_client.close()
            emitted = await self._collect_session_events(session, wait_for_first=False)
            self._remove_session(sid)
            return emitted

        return []

    async def _collect_session_events(
        self,
        session: STTSession,
        *,
        wait_for_first: bool,
        timeout_seconds: float | None = None,
    ) -> list[STTSessionEvent]:
        deferred_events = self._drain_deferred_events(session.sid)
        if deferred_events:
            return deferred_events

        due_events = session.consume_due_turn_closures()
        if due_events:
            return await self._persist_context_events(session, due_events)

        provider_events = session.provider_client.drain_pending_events()
        if not provider_events and wait_for_first:
            wait_timeout = timeout_seconds
            turn_close_timeout = session.seconds_until_next_turn_close()
            if turn_close_timeout is not None:
                wait_timeout = (
                    turn_close_timeout
                    if wait_timeout is None
                    else min(wait_timeout, turn_close_timeout)
                )
            try:
                if wait_timeout is None:
                    provider_events.append(await session.provider_client.next_event())
                else:
                    provider_events.append(
                        await asyncio.wait_for(
                            session.provider_client.next_event(),
                            timeout=wait_timeout,
                        )
                    )
            except asyncio.TimeoutError:
                return await self._handle_idle_session(session)

        provider_events.extend(session.provider_client.drain_pending_events())
        if not provider_events:
            return await self._handle_idle_session(session)

        should_close_after_finalize = (
            session.state == STTSessionState.FINALIZING
            and any(
                event.kind == ProviderEventKind.PROVIDER_FINALIZE
                for event in provider_events
            )
        )
        emitted = session.consume_provider_events(provider_events)
        emitted.extend(session.consume_due_turn_closures())
        emitted = await self._persist_context_events(session, emitted)
        if should_close_after_finalize and session.is_active:
            emitted.extend(await self._close_finalized_session(session))
        return emitted

    async def _handle_idle_session(self, session: STTSession) -> list[STTSessionEvent]:
        due_events = session.consume_due_turn_closures()
        if due_events:
            return await self._persist_context_events(session, due_events)

        if not session.should_send_keepalive():
            return []

        try:
            await session.send_keepalive()
        except Exception as exc:
            return [
                STTSessionEvent(
                    kind=STTSessionEventKind.ERROR,
                    payload=STTErrorPayload(
                        stream_id=session.stream_id,
                        error_code="stt_keepalive_failed",
                        error_message=str(exc),
                    ),
                )
            ]
        return []

    async def _close_finalized_session(
        self,
        session: STTSession,
    ) -> list[STTSessionEvent]:
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

        return session.consume_provider_events(close_events)

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
        self._deferred_events.pop(sid, None)
        self._cancel_answer_tasks(sid)

    async def _persist_context_events(
        self,
        session: STTSession,
        events: list[STTSessionEvent],
    ) -> list[STTSessionEvent]:
        if not events or self._context_store is None:
            return events

        emitted: list[STTSessionEvent] = []
        for event in events:
            emitted.append(event)
            if event.kind != STTSessionEventKind.UTTERANCE_CLOSED:
                continue

            payload = event.payload
            stable_utterance = StableInterviewContextUtterance(
                utterance_id=payload.utterance_id,
                conversation_id=payload.conversation_id,
                source=payload.source,
                channel=payload.channel,
                text=payload.text,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                turn_closed_at=payload.turn_closed_at,
            )
            try:
                await self._context_store.append_closed_utterance(
                    stable_utterance,
                    channel_map=session.channel_map,
                )
            except RedisContextWriteError as exc:
                emitted.append(
                    STTSessionEvent(
                        kind=STTSessionEventKind.ERROR,
                        payload=STTErrorPayload(
                            stream_id=session.stream_id,
                            error_code="redis_context_write_failed",
                            error_message=str(exc),
                        ),
                    )
                )
                continue

            self._schedule_interview_answer_stream(
                session=session,
                stable_utterance=stable_utterance,
            )

            self._schedule_async_utterance_persistence(
                sid=session.sid,
                stream_id=session.stream_id,
                stable_utterance=stable_utterance,
            )

        return emitted

    def _schedule_interview_answer_stream(
        self,
        *,
        session: STTSession,
        stable_utterance: StableInterviewContextUtterance,
    ) -> None:
        if self._answer_service is None or stable_utterance.source != "interviewer":
            return

        task = asyncio.create_task(
            self._stream_interview_answer(
                session=session,
                stable_utterance=stable_utterance,
            )
        )
        self._answer_tasks.setdefault(session.sid, set()).add(task)
        task.add_done_callback(
            lambda completed_task, session_id=session.sid: self._discard_answer_task(
                session_id,
                completed_task,
            )
        )

    async def _stream_interview_answer(
        self,
        *,
        session: STTSession,
        stable_utterance: StableInterviewContextUtterance,
    ) -> None:
        if self._answer_service is None or stable_utterance.source != "interviewer":
            return

        try:
            await self._answer_service.stream_for_closed_utterance(
                user_id=session.user_id,
                organization_id=session.organization_id,
                closed_utterance=stable_utterance,
            )
        except InterviewAITriggerError as exc:
            logger.warning(
                "Interview AI streaming failed for conversation %s",
                stable_utterance.conversation_id,
                exc_info=exc,
            )
        except Exception:
            logger.exception(
                "Unexpected interview AI streaming failure for conversation %s",
                stable_utterance.conversation_id,
            )

    def _cancel_answer_tasks(self, sid: str) -> None:
        tasks = self._answer_tasks.pop(sid, set())
        for task in tasks:
            task.cancel()

    def _discard_answer_task(
        self,
        sid: str,
        task: asyncio.Task[None],
    ) -> None:
        tasks = self._answer_tasks.get(sid)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            self._answer_tasks.pop(sid, None)

    def _schedule_async_utterance_persistence(
        self,
        *,
        sid: str,
        stream_id: str,
        stable_utterance: StableInterviewContextUtterance,
    ) -> None:
        if self._utterance_repo is None:
            return

        task = asyncio.create_task(
            self._persist_closed_utterance_in_background(
                sid=sid,
                stream_id=stream_id,
                stable_utterance=stable_utterance,
            )
        )
        self._persistence_tasks.add(task)
        task.add_done_callback(self._persistence_tasks.discard)

    async def _persist_closed_utterance_in_background(
        self,
        *,
        sid: str,
        stream_id: str,
        stable_utterance: StableInterviewContextUtterance,
    ) -> None:
        if self._utterance_repo is None:
            return

        last_error: Exception | None = None
        for attempt in range(1, self._async_persist_retry_attempts + 1):
            try:
                await self._utterance_repo.append_stable(
                    conversation_id=stable_utterance.conversation_id,
                    source=stable_utterance.source,
                    channel=stable_utterance.channel,
                    text=stable_utterance.text,
                    started_at=stable_utterance.started_at,
                    ended_at=stable_utterance.ended_at,
                    turn_closed_at=stable_utterance.turn_closed_at,
                    utterance_id=stable_utterance.utterance_id,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Async interview utterance persistence attempt %s/%s failed for %s",
                    attempt,
                    self._async_persist_retry_attempts,
                    stable_utterance.utterance_id,
                    exc_info=True,
                )
                if attempt < self._async_persist_retry_attempts:
                    await asyncio.sleep(
                        self._async_persist_retry_delay_seconds * attempt
                    )

        error = AsyncUtterancePersistenceError(
            "Failed to persist stable interview utterance after Redis write"
        )
        logger.error(
            "Async interview utterance persistence exhausted retries for %s",
            stable_utterance.utterance_id,
            exc_info=last_error,
        )
        self._queue_deferred_event(
            sid=sid,
            stream_id=stream_id,
            event=STTSessionEvent(
                kind=STTSessionEventKind.ERROR,
                payload=STTErrorPayload(
                    stream_id=stream_id,
                    error_code="async_utterance_persistence_failed",
                    error_message=str(error),
                ),
            ),
        )

    def _queue_deferred_event(
        self,
        *,
        sid: str,
        stream_id: str,
        event: STTSessionEvent,
    ) -> None:
        session = self._sessions.get(sid)
        if session is None or session.stream_id != stream_id:
            logger.warning(
                "Dropping deferred STT event for stale session %s/%s",
                sid,
                stream_id,
            )
            return
        self._deferred_events.setdefault(sid, []).append(event)

    def _drain_deferred_events(self, sid: str) -> list[STTSessionEvent]:
        events = self._deferred_events.pop(sid, [])
        if not events:
            return []
        return events

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
