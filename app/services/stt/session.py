"""Stateful STT session and transcript assembly logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    InvalidSTTStreamStateError,
    STTProviderConnectionError,
    STTStreamOwnershipError,
)
from app.domain.schemas.stt import (
    STTCompletedPayload,
    STTErrorPayload,
    STTFinalPayload,
    STTPartialPayload,
    STTStartedPayload,
)
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
    ProviderTranscriptEvent,
)


class STTSessionState(str, Enum):
    """Explicit STT session lifecycle states."""

    STARTING = "starting"
    STREAMING = "streaming"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class STTSessionEventKind(str, Enum):
    """Normalized session outputs for the socket/service layer."""

    STARTED = "started"
    PARTIAL = "partial"
    FINAL = "final"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(slots=True)
class STTSessionEvent:
    """Normalized STT session event with a typed payload."""

    kind: STTSessionEventKind
    payload: (
        STTStartedPayload
        | STTPartialPayload
        | STTFinalPayload
        | STTCompletedPayload
        | STTErrorPayload
    )


class STTSession:
    """Owns one live STT stream, provider connection, and transcript state."""

    def __init__(
        self,
        *,
        sid: str,
        user_id: str,
        stream_id: str,
        organization_id: str | None,
        language: str | None,
        provider_client: DeepgramLiveClient,
    ) -> None:
        self.sid = sid
        self.user_id = user_id
        self.stream_id = stream_id
        self.organization_id = organization_id
        self.language = language or "en"
        self.provider_client = provider_client
        self.state = STTSessionState.STARTING
        self.created_at = self._utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.failed_at: datetime | None = None
        self.finalize_requested_at: datetime | None = None
        self.last_audio_at: datetime | None = None
        self.last_provider_activity_at: datetime | None = None
        self.last_keepalive_at: datetime | None = None
        self._pending_final_fragments: list[ProviderTranscriptEvent] = []

    @property
    def is_active(self) -> bool:
        """Return whether the session is still live."""
        return self.state not in {STTSessionState.COMPLETED, STTSessionState.FAILED}

    @property
    def pending_final_text(self) -> str:
        """Return the buffered final fragment text."""
        return self._merge_transcript_text(self._pending_final_fragments)

    async def start(self) -> list[STTSessionEvent]:
        """Open the provider stream and transition into streaming state."""
        self._assert_can_start()
        try:
            await self.provider_client.open(language=self.language)
        except Exception as exc:
            self._fail()
            raise STTProviderConnectionError(
                "Failed to start speech-to-text stream"
            ) from exc

        self.state = STTSessionState.STREAMING
        self.started_at = self._utcnow()
        self.last_provider_activity_at = self.started_at
        return [
            STTSessionEvent(
                kind=STTSessionEventKind.STARTED,
                payload=STTStartedPayload(
                    stream_id=self.stream_id,
                    language=self.language,
                ),
            )
        ]

    async def push_audio(self, *, sid: str, stream_id: str, chunk: bytes) -> None:
        """Forward audio to the provider after ownership/state checks."""
        self.assert_owner(sid=sid, stream_id=stream_id)
        self._assert_state({STTSessionState.STREAMING, STTSessionState.FINALIZING})
        if not chunk:
            return

        await self.provider_client.send_audio(chunk)
        self.last_audio_at = self._utcnow()

    async def send_keepalive(self) -> bool:
        """Send a provider keepalive while the session is still active."""
        self._assert_state({STTSessionState.STREAMING, STTSessionState.FINALIZING})
        sent = await self.provider_client.send_keepalive()
        if sent:
            self.last_keepalive_at = self._utcnow()
        return sent

    async def request_finalize(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> None:
        """Request provider finalization without marking completion early."""
        self.assert_owner(sid=sid, stream_id=stream_id)
        self._assert_state({STTSessionState.STREAMING, STTSessionState.FINALIZING})
        self.state = STTSessionState.FINALIZING
        self.finalize_requested_at = self._utcnow()
        await self.provider_client.finalize()

    async def stop(self, *, sid: str, stream_id: str) -> None:
        """Close the provider stream for the owning socket."""
        self.assert_owner(sid=sid, stream_id=stream_id)
        if not self.is_active:
            return
        self.state = STTSessionState.FINALIZING
        await self.provider_client.close()

    async def consume_next_provider_events(self) -> list[STTSessionEvent]:
        """Consume one awaited provider event plus any already buffered events."""
        events = [await self.provider_client.next_event()]
        events.extend(self.provider_client.drain_pending_events())
        return self.consume_provider_events(events)

    def consume_provider_events(
        self,
        events: list[ProviderEvent],
    ) -> list[STTSessionEvent]:
        """Apply provider events to session state and emit normalized outputs."""
        emitted: list[STTSessionEvent] = []
        for event in events:
            self.last_provider_activity_at = self._utcnow()
            emitted.extend(self._consume_provider_event(event))
        return emitted

    def assert_owner(self, *, sid: str, stream_id: str) -> None:
        """Ensure inbound socket/control actions belong to this session."""
        if sid != self.sid or stream_id != self.stream_id:
            raise STTStreamOwnershipError()

    def assert_can_accept_new_stream(self, *, sid: str, stream_id: str) -> None:
        """Reject a second active stream on the same socket before provider open."""
        if self.is_active and sid == self.sid and stream_id != self.stream_id:
            raise ActiveSTTStreamConflictError()

    def should_send_keepalive(self, *, at: datetime | None = None) -> bool:
        """Return whether keepalive is currently due for this session."""
        if not self.is_active:
            return False
        now = at or self._utcnow()
        reference_candidates = [
            candidate
            for candidate in (
                self.last_audio_at,
                self.last_provider_activity_at,
                self.last_keepalive_at,
                self.started_at,
                self.created_at,
            )
            if candidate is not None
        ]
        if not reference_candidates:
            return False
        reference = max(reference_candidates)
        elapsed = (now - reference).total_seconds()
        return elapsed >= self.provider_client.keepalive_interval_seconds

    def seconds_since_audio(self, *, at: datetime | None = None) -> float | None:
        """Return idle time since the last audio packet."""
        if self.last_audio_at is None:
            return None
        now = at or self._utcnow()
        return (now - self.last_audio_at).total_seconds()

    def seconds_since_provider_activity(
        self,
        *,
        at: datetime | None = None,
    ) -> float | None:
        """Return idle time since the last provider event."""
        if self.last_provider_activity_at is None:
            return None
        now = at or self._utcnow()
        return (now - self.last_provider_activity_at).total_seconds()

    def _consume_provider_event(self, event: ProviderEvent) -> list[STTSessionEvent]:
        if event.kind == ProviderEventKind.OPEN:
            return []
        if event.kind == ProviderEventKind.ERROR:
            return [self._build_error_event(event.error_message or "Provider error")]
        if event.kind == ProviderEventKind.CLOSE:
            return self._handle_close_event(event)
        if event.kind == ProviderEventKind.UTTERANCE_END:
            return self._handle_utterance_end()
        if event.kind == ProviderEventKind.PROVIDER_FINALIZE:
            return self._handle_provider_finalize()
        if event.kind in {
            ProviderEventKind.TRANSCRIPT_PARTIAL,
            ProviderEventKind.TRANSCRIPT_FINAL_FRAGMENT,
        } and event.transcript is not None:
            return self._handle_transcript_event(event.transcript)
        return []

    def _handle_transcript_event(
        self,
        transcript: ProviderTranscriptEvent,
    ) -> list[STTSessionEvent]:
        if not transcript.is_final:
            return [
                STTSessionEvent(
                    kind=STTSessionEventKind.PARTIAL,
                    payload=STTPartialPayload(
                        stream_id=self.stream_id,
                        transcript=self._compose_transcript_with_buffer(
                            transcript.transcript
                        ),
                    ),
                )
            ]

        self._pending_final_fragments.append(transcript)
        if transcript.speech_final or (
            transcript.from_finalize and self.state == STTSessionState.FINALIZING
        ):
            return [self._flush_pending_final_fragments()]
        return []

    def _handle_utterance_end(self) -> list[STTSessionEvent]:
        if (
            self.state == STTSessionState.FINALIZING
            and self._pending_final_fragments
        ):
            return [self._flush_pending_final_fragments()]
        return []

    def _handle_provider_finalize(self) -> list[STTSessionEvent]:
        if self._pending_final_fragments:
            return [self._flush_pending_final_fragments()]
        return []

    def _handle_close_event(self, event: ProviderEvent) -> list[STTSessionEvent]:
        emitted: list[STTSessionEvent] = []
        if self._pending_final_fragments:
            emitted.append(self._flush_pending_final_fragments())

        if self.state == STTSessionState.FINALIZING:
            self.state = STTSessionState.COMPLETED
            self.completed_at = self._utcnow()
            emitted.append(
                STTSessionEvent(
                    kind=STTSessionEventKind.COMPLETED,
                    payload=STTCompletedPayload(stream_id=self.stream_id),
                )
            )
            return emitted

        message = "Provider closed before stream finalized"
        if event.close_code is not None:
            message = f"{message} (code {event.close_code})"
        emitted.append(self._build_error_event(message))
        return emitted

    def _flush_pending_final_fragments(self) -> STTSessionEvent:
        if not self._pending_final_fragments:
            raise InvalidSTTStreamStateError("No final transcript fragments to flush")

        fragments = list(self._pending_final_fragments)
        self._pending_final_fragments.clear()
        return STTSessionEvent(
            kind=STTSessionEventKind.FINAL,
            payload=STTFinalPayload(
                stream_id=self.stream_id,
                transcript=self._merge_transcript_text(fragments),
                confidence=self._merge_confidence(fragments),
                start_ms=self._merge_start_ms(fragments),
                end_ms=self._merge_end_ms(fragments),
            ),
        )

    def _build_error_event(self, error_message: str) -> STTSessionEvent:
        self._fail()
        return STTSessionEvent(
            kind=STTSessionEventKind.ERROR,
            payload=STTErrorPayload(
                stream_id=self.stream_id,
                error_code="stt_session_failed",
                error_message=error_message,
            ),
        )

    def _assert_can_start(self) -> None:
        if self.state != STTSessionState.STARTING:
            raise InvalidSTTStreamStateError("STT session has already started")

    def _assert_state(self, allowed_states: set[STTSessionState]) -> None:
        if self.state not in allowed_states:
            allowed = ", ".join(state.value for state in sorted(allowed_states, key=str))
            raise InvalidSTTStreamStateError(
                f"STT session is '{self.state.value}', expected one of: {allowed}"
            )

    def _fail(self) -> None:
        self.state = STTSessionState.FAILED
        self.failed_at = self._utcnow()

    @staticmethod
    def _compose_transcript(base: str, addition: str) -> str:
        base = base.strip()
        addition = addition.strip()
        if not base:
            return addition
        if not addition:
            return base
        if addition == base or addition.startswith(base):
            return addition
        if base.endswith(addition):
            return base
        return f"{base} {addition}"

    def _compose_transcript_with_buffer(self, transcript: str) -> str:
        return self._compose_transcript(self.pending_final_text, transcript)

    def _merge_transcript_text(
        self,
        fragments: list[ProviderTranscriptEvent],
    ) -> str:
        merged = ""
        for fragment in fragments:
            merged = self._compose_transcript(merged, fragment.transcript)
        return merged

    @staticmethod
    def _merge_confidence(fragments: list[ProviderTranscriptEvent]) -> float | None:
        values = [
            fragment.confidence
            for fragment in fragments
            if fragment.confidence is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _merge_start_ms(fragments: list[ProviderTranscriptEvent]) -> int | None:
        values = [
            fragment.start_ms for fragment in fragments if fragment.start_ms is not None
        ]
        return min(values) if values else None

    @staticmethod
    def _merge_end_ms(fragments: list[ProviderTranscriptEvent]) -> int | None:
        values = [fragment.end_ms for fragment in fragments if fragment.end_ms is not None]
        return max(values) if values else None

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
