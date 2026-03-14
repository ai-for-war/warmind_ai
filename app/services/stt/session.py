"""Stateful STT session and transcript assembly logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    InvalidChannelMappingError,
    InvalidSTTStreamStateError,
    STTProviderConnectionError,
    STTStreamOwnershipError,
)
from app.config.settings import get_settings
from app.domain.schemas.stt import (
    InterviewAnswerPayload,
    STTChannelMap,
    STTChannelIndex,
    STTCompletedPayload,
    STTErrorPayload,
    STTFinalPayload,
    STTPartialPayload,
    STTSpeakerRole,
    STTStartedPayload,
    STTUtteranceClosedPayload,
)
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
    ProviderTranscriptEvent,
)


@dataclass(slots=True)
class StableTranscriptSegment:
    """Stable finalized transcript segment assigned to one interview channel."""

    text: str
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(slots=True)
class OpenInterviewUtterance:
    """Process-local open utterance state for one interview speaker channel."""

    utterance_id: str
    source: STTSpeakerRole
    channel: STTChannelIndex
    started_at: datetime
    stable_segments: list[StableTranscriptSegment] = field(default_factory=list)
    preview_text: str = ""
    ended_at: datetime | None = None
    last_activity_at: datetime | None = None

    @property
    def stable_text(self) -> str:
        """Return merged finalized text for the open utterance."""
        merged = ""
        for segment in self.stable_segments:
            merged = STTSession._compose_transcript(merged, segment.text)
        return merged

    @property
    def preview_transcript(self) -> str:
        """Return UI preview text combining stable and volatile transcript state."""
        return STTSession._compose_transcript(self.stable_text, self.preview_text)

    @property
    def has_stable_text(self) -> bool:
        """Return whether this utterance has any finalized transcript content."""
        return bool(self.stable_text)


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
    UTTERANCE_CLOSED = "utterance_closed"
    INTERVIEW_ANSWER = "interview_answer"
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
        | STTUtteranceClosedPayload
        | InterviewAnswerPayload
        | STTCompletedPayload
        | STTErrorPayload
    )


class STTSession:
    """Owns one multichannel interview STT stream and per-channel utterance state."""

    def __init__(
        self,
        *,
        sid: str,
        user_id: str,
        stream_id: str,
        conversation_id: str,
        organization_id: str | None,
        language: str | None,
        channel_map: STTChannelMap,
        provider_client: DeepgramLiveClient,
    ) -> None:
        self.sid = sid
        self.user_id = user_id
        self.stream_id = stream_id
        self.conversation_id = conversation_id
        self.organization_id = organization_id
        self.language = language or "en"
        self.channel_map = channel_map
        self.provider_client = provider_client
        self.turn_close_grace_ms = get_settings().INTERVIEW_TURN_CLOSE_GRACE_MS
        self.state = STTSessionState.STARTING
        self.created_at = self._utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.failed_at: datetime | None = None
        self.finalize_requested_at: datetime | None = None
        self.last_audio_at: datetime | None = None
        self.last_provider_activity_at: datetime | None = None
        self.last_keepalive_at: datetime | None = None
        self._open_utterances: dict[STTChannelIndex, OpenInterviewUtterance | None] = {
            0: None,
            1: None,
        }
        self._turn_close_deadlines: dict[STTChannelIndex, datetime | None] = {
            0: None,
            1: None,
        }

    @property
    def is_active(self) -> bool:
        """Return whether the session is still live."""
        return self.state not in {STTSessionState.COMPLETED, STTSessionState.FAILED}

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
                    conversation_id=self.conversation_id,
                    language=self.language,
                    channel_map=self.channel_map,
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
            try:
                emitted.extend(self._consume_provider_event(event))
            except InvalidChannelMappingError as exc:
                emitted.append(self._build_error_event(str(exc)))
            emitted.extend(
                self.consume_due_turn_closures(at=self.last_provider_activity_at)
            )
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

    def seconds_until_next_turn_close(self, *, at: datetime | None = None) -> float | None:
        """Return seconds until the next pending turn-close deadline, if any."""
        now = at or self._utcnow()
        deadlines = [
            deadline
            for deadline in self._turn_close_deadlines.values()
            if deadline is not None
        ]
        if not deadlines:
            return None
        earliest = min(deadlines)
        return max((earliest - now).total_seconds(), 0.0)

    def consume_due_turn_closures(
        self,
        *,
        at: datetime | None = None,
    ) -> list[STTSessionEvent]:
        """Emit utterance-closed events for any expired per-channel grace timer."""
        if not self.is_active:
            return []

        now = at or self._utcnow()
        emitted: list[STTSessionEvent] = []
        for channel in (0, 1):
            deadline = self._turn_close_deadlines[channel]
            if deadline is None or deadline > now:
                continue

            self._turn_close_deadlines[channel] = None
            utterance = self._open_utterances[channel]
            if utterance is None:
                continue

            if utterance.has_stable_text:
                ended_at = utterance.ended_at or utterance.last_activity_at or now
                emitted.append(
                    STTSessionEvent(
                        kind=STTSessionEventKind.UTTERANCE_CLOSED,
                        payload=STTUtteranceClosedPayload(
                            conversation_id=self.conversation_id,
                            utterance_id=utterance.utterance_id,
                            source=utterance.source,
                            channel=utterance.channel,
                            text=utterance.stable_text,
                            started_at=utterance.started_at,
                            ended_at=ended_at,
                            turn_closed_at=now,
                        ),
                    )
                )

            self._open_utterances[channel] = None

        return emitted

    def _consume_provider_event(self, event: ProviderEvent) -> list[STTSessionEvent]:
        if event.kind == ProviderEventKind.OPEN:
            return []
        if event.kind == ProviderEventKind.ERROR:
            return [self._build_error_event(event.error_message or "Provider error")]
        if event.kind == ProviderEventKind.CLOSE:
            return self._handle_close_event(event)
        if event.kind == ProviderEventKind.SPEECH_STARTED:
            return self._handle_speech_started(event)
        if event.kind == ProviderEventKind.UTTERANCE_END:
            return self._handle_utterance_end(event)
        if event.kind == ProviderEventKind.PROVIDER_FINALIZE:
            return self._handle_provider_finalize()
        if (
            event.kind
            in {
                ProviderEventKind.TRANSCRIPT_PARTIAL,
                ProviderEventKind.TRANSCRIPT_FINAL_FRAGMENT,
            }
            and event.transcript is not None
        ):
            return self._handle_transcript_event(event.transcript)
        return []

    def _handle_transcript_event(
        self,
        transcript: ProviderTranscriptEvent,
    ) -> list[STTSessionEvent]:
        channel = self._resolve_channel_index(transcript.channel_index)
        self._cancel_pending_turn_close(channel)
        utterance = self._get_or_create_open_utterance(channel=channel)
        utterance.last_activity_at = self._utcnow()

        if not transcript.is_final:
            utterance.preview_text = transcript.transcript
            return [
                STTSessionEvent(
                    kind=STTSessionEventKind.PARTIAL,
                    payload=STTPartialPayload(
                        stream_id=self.stream_id,
                        conversation_id=self.conversation_id,
                        source=utterance.source,
                        channel=channel,
                        transcript=utterance.preview_transcript,
                    ),
                )
            ]

        utterance.preview_text = ""
        self._append_stable_segment(utterance, transcript)
        utterance.ended_at = utterance.last_activity_at
        return [
            STTSessionEvent(
                kind=STTSessionEventKind.FINAL,
                payload=STTFinalPayload(
                    stream_id=self.stream_id,
                    conversation_id=self.conversation_id,
                    source=utterance.source,
                    channel=channel,
                    confidence=transcript.confidence,
                    transcript=transcript.transcript,
                    start_ms=transcript.start_ms,
                    end_ms=transcript.end_ms,
                ),
            )
        ]

    def _handle_speech_started(self, event: ProviderEvent) -> list[STTSessionEvent]:
        channel = self._resolve_channel_index(event.channel_index)
        self._cancel_pending_turn_close(channel)
        utterance = self._open_utterances[channel]
        if utterance is not None:
            utterance.last_activity_at = self._utcnow()
        return []

    def _handle_utterance_end(self, event: ProviderEvent) -> list[STTSessionEvent]:
        channel = self._resolve_channel_index(event.channel_index)
        utterance = self._open_utterances[channel]
        if utterance is None or not utterance.has_stable_text:
            return []

        self._turn_close_deadlines[channel] = self._utcnow() + self._grace_delta()
        return []

    def _handle_provider_finalize(self) -> list[STTSessionEvent]:
        return []

    def _handle_close_event(self, event: ProviderEvent) -> list[STTSessionEvent]:
        emitted: list[STTSessionEvent] = []
        self._clear_pending_turn_closures()

        if self.state == STTSessionState.FINALIZING:
            self.state = STTSessionState.COMPLETED
            self.completed_at = self._utcnow()
            self._discard_open_utterances()
            emitted.append(
                STTSessionEvent(
                    kind=STTSessionEventKind.COMPLETED,
                    payload=STTCompletedPayload(
                        stream_id=self.stream_id,
                        conversation_id=self.conversation_id,
                    ),
                )
            )
            return emitted

        message = "Provider closed before stream finalized"
        if event.close_code is not None:
            message = f"{message} (code {event.close_code})"
        emitted.append(self._build_error_event(message))
        return emitted

    def _build_error_event(self, error_message: str) -> STTSessionEvent:
        self._fail()
        self._clear_pending_turn_closures()
        self._discard_open_utterances()
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
            allowed = ", ".join(
                state.value for state in sorted(allowed_states, key=str)
            )
            raise InvalidSTTStreamStateError(
                f"STT session is '{self.state.value}', expected one of: {allowed}"
            )

    def _fail(self) -> None:
        self.state = STTSessionState.FAILED
        self.failed_at = self._utcnow()

    def _get_or_create_open_utterance(
        self,
        *,
        channel: STTChannelIndex,
    ) -> OpenInterviewUtterance:
        utterance = self._open_utterances[channel]
        if utterance is not None:
            return utterance

        now = self._utcnow()
        utterance = OpenInterviewUtterance(
            utterance_id=uuid4().hex,
            source=self.channel_map.role_for_channel(channel),
            channel=channel,
            started_at=now,
            last_activity_at=now,
        )
        self._open_utterances[channel] = utterance
        return utterance

    def _append_stable_segment(
        self,
        utterance: OpenInterviewUtterance,
        transcript: ProviderTranscriptEvent,
    ) -> None:
        normalized_text = transcript.transcript.strip()
        if not normalized_text:
            return

        current_text = utterance.stable_text
        merged_text = self._compose_transcript(current_text, normalized_text)
        if merged_text == current_text:
            return

        utterance.stable_segments.append(
            StableTranscriptSegment(
                text=normalized_text,
                confidence=transcript.confidence,
                start_ms=transcript.start_ms,
                end_ms=transcript.end_ms,
            )
        )

    def _cancel_pending_turn_close(self, channel: STTChannelIndex) -> None:
        self._turn_close_deadlines[channel] = None

    def _clear_pending_turn_closures(self) -> None:
        for channel in (0, 1):
            self._turn_close_deadlines[channel] = None

    def _discard_open_utterances(self) -> None:
        for channel in (0, 1):
            self._open_utterances[channel] = None

    def _resolve_channel_index(self, channel_index: int | None) -> STTChannelIndex:
        if channel_index not in (0, 1):
            raise InvalidChannelMappingError(
                "Provider event is missing a valid interview channel index"
            )
        return channel_index

    def _grace_delta(self) -> timedelta:
        return timedelta(milliseconds=self.turn_close_grace_ms)

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

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
