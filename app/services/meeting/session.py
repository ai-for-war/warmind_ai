"""Stateful meeting recording session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.common.exceptions import (
    ActiveMeetingRecordConflictError,
    InvalidMeetingRecordStateError,
    MeetingRecordOwnershipError,
    STTProviderConnectionError,
)
from app.domain.schemas.meeting_record import (
    MeetingRecordCompletedPayload,
    MeetingRecordErrorPayload,
    MeetingRecordStartedPayload,
    MeetingRecordStoppingPayload,
)
from app.domain.schemas.meeting_transcript import (
    MeetingTranscriptBlockPayload,
    MeetingTranscriptSegmentPayload,
)
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
    ProviderTranscriptEvent,
    ProviderTranscriptWord,
)

PUNCTUATION_PREFIXES = (".", ",", "!", "?", ";", ":", ")", "]", "}", "%")
PUNCTUATION_SUFFIXES = ("(", "[", "{")


@dataclass(slots=True)
class MeetingTranscriptSegmentState:
    """Process-local transcript segment state."""

    segment_id: str
    speaker_key: int | None = None
    speaker_label: str = "speaker unknown"
    text: str = ""
    start_ms: int | None = None
    end_ms: int | None = None

    def to_payload(self, *, is_final: bool) -> MeetingTranscriptSegmentPayload:
        """Convert segment state into the public socket payload shape."""
        return MeetingTranscriptSegmentPayload(
            segment_id=self.segment_id,
            speaker_key=self.speaker_key,
            speaker_label=self.speaker_label,
            text=self.text,
            is_final=is_final,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
        )


@dataclass(slots=True)
class OpenMeetingTranscriptBlock:
    """Process-local transcript block returned to the frontend on each update."""

    block_id: str
    sequence: int
    segments: list[MeetingTranscriptSegmentState] = field(default_factory=list)
    draft_segments: list[MeetingTranscriptSegmentState] = field(default_factory=list)


class MeetingSessionState(str, Enum):
    """Explicit meeting recording lifecycle states."""

    STARTING = "starting"
    STREAMING = "streaming"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingSessionEventKind(str, Enum):
    """Normalized session outputs for the socket/service layer."""

    STARTED = "started"
    TRANSCRIPT = "transcript"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(slots=True)
class MeetingSessionEvent:
    """Normalized meeting session event with a typed payload."""

    kind: MeetingSessionEventKind
    payload: (
        MeetingRecordStartedPayload
        | MeetingTranscriptBlockPayload
        | MeetingRecordStoppingPayload
        | MeetingRecordCompletedPayload
        | MeetingRecordErrorPayload
    )


class MeetingSession:
    """Owns one live meeting recording session."""

    def __init__(
        self,
        *,
        meeting_id: str,
        sid: str,
        user_id: str,
        organization_id: str,
        language: str,
        provider_client: DeepgramLiveClient,
    ) -> None:
        self.meeting_id = meeting_id
        self.sid = sid
        self.user_id = user_id
        self.organization_id = organization_id
        self.language = language
        self.provider_client = provider_client
        self.state = MeetingSessionState.STARTING
        self.created_at = self._utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.failed_at: datetime | None = None
        self.finalize_requested_at: datetime | None = None
        self.last_audio_at: datetime | None = None
        self.last_provider_activity_at: datetime | None = None
        self.last_keepalive_at: datetime | None = None
        self._open_block: OpenMeetingTranscriptBlock | None = None
        self._next_block_sequence = 0
        self._awaiting_stop_emit = False

    @property
    def is_active(self) -> bool:
        """Return whether the meeting is still live."""
        return self.state not in {
            MeetingSessionState.COMPLETED,
            MeetingSessionState.FAILED,
        }

    @property
    def awaiting_stop_emit(self) -> bool:
        """Return whether provider events should wait for STOPPING emission."""
        return self._awaiting_stop_emit

    async def start(self) -> list[MeetingSessionEvent]:
        """Open the provider stream and transition into streaming state."""
        self._assert_can_start()
        try:
            await self.provider_client.open(language=self.language)
        except Exception as exc:
            self._fail()
            raise STTProviderConnectionError(
                "Failed to start meeting recording stream"
            ) from exc

        self.state = MeetingSessionState.STREAMING
        self.started_at = self._utcnow()
        self.last_provider_activity_at = self.started_at
        return [
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.STARTED,
                payload=MeetingRecordStartedPayload(
                    meeting_id=self.meeting_id,
                    organization_id=self.organization_id,
                    language=self.language,
                ),
            )
        ]

    async def push_audio(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
        chunk: bytes,
    ) -> None:
        """Forward audio to the provider after ownership/state checks."""
        self.assert_owner(sid=sid, user_id=user_id, meeting_id=meeting_id)
        self._assert_state({MeetingSessionState.STREAMING, MeetingSessionState.FINALIZING})
        if not chunk:
            return
        await self.provider_client.send_audio(chunk)
        self.last_audio_at = self._utcnow()

    async def send_keepalive(self) -> bool:
        """Send a provider keepalive while the session is still active."""
        self._assert_state({MeetingSessionState.STREAMING, MeetingSessionState.FINALIZING})
        sent = await self.provider_client.send_keepalive()
        if sent:
            self.last_keepalive_at = self._utcnow()
        return sent

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

    async def request_finalize(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> list[MeetingSessionEvent]:
        """Request provider finalization without marking completion early."""
        self.assert_owner(sid=sid, user_id=user_id, meeting_id=meeting_id)
        return await self._request_finalize_internal()

    async def request_finalize_for_disconnect(self) -> list[MeetingSessionEvent]:
        """Request provider finalization during disconnect cleanup."""
        if not self.is_active:
            return []
        return await self._request_finalize_internal()

    def acknowledge_stop_emitted(self) -> None:
        """Release provider event draining after STOPPING reaches the client."""
        self._awaiting_stop_emit = False

    def consume_provider_events(
        self,
        events: list[ProviderEvent],
    ) -> list[MeetingSessionEvent]:
        """Apply provider events to session state and emit normalized outputs."""
        emitted: list[MeetingSessionEvent] = []
        for event in events:
            self.last_provider_activity_at = self._utcnow()
            emitted.extend(self._consume_provider_event(event))
        return emitted

    def assert_owner(self, *, sid: str, user_id: str, meeting_id: str) -> None:
        """Ensure inbound socket/control actions belong to this meeting."""
        if sid != self.sid or user_id != self.user_id or meeting_id != self.meeting_id:
            raise MeetingRecordOwnershipError()

    def assert_can_accept_new_meeting(self, *, sid: str, meeting_id: str) -> None:
        """Reject a second active meeting on the same socket."""
        if self.is_active and sid == self.sid and meeting_id != self.meeting_id:
            raise ActiveMeetingRecordConflictError()

    def fail(
        self,
        error_message: str,
        *,
        error_code: str = "meeting_record_failed",
    ) -> MeetingSessionEvent:
        """Transition the session into a failed state and emit an error event."""
        return self._build_error_event(error_message, error_code=error_code)

    async def _request_finalize_internal(self) -> list[MeetingSessionEvent]:
        self._assert_state({MeetingSessionState.STREAMING, MeetingSessionState.FINALIZING})
        if self.state == MeetingSessionState.FINALIZING:
            return []

        self.state = MeetingSessionState.FINALIZING
        self.finalize_requested_at = self._utcnow()
        self._awaiting_stop_emit = True
        await self.provider_client.finalize()
        return [
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.STOPPING,
                payload=MeetingRecordStoppingPayload(meeting_id=self.meeting_id),
            )
        ]

    def _consume_provider_event(self, event: ProviderEvent) -> list[MeetingSessionEvent]:
        if event.kind == ProviderEventKind.OPEN:
            return []
        if event.kind == ProviderEventKind.ERROR:
            return [self._build_error_event(event.error_message or "Provider error")]
        if event.kind == ProviderEventKind.CLOSE:
            return self._handle_close_event(event)
        if event.kind == ProviderEventKind.SPEECH_STARTED:
            return []
        if event.kind == ProviderEventKind.UTTERANCE_END:
            return self._handle_close_block()
        if event.kind == ProviderEventKind.PROVIDER_FINALIZE:
            return self._handle_close_block()
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
    ) -> list[MeetingSessionEvent]:
        block = self._get_or_create_open_block()

        if not transcript.is_final:
            draft_segments = self._build_draft_segments(
                transcript,
                existing_segments=block.draft_segments,
            )
            if not draft_segments:
                return []
            block.draft_segments = draft_segments
            payload = self._build_block_event(block, is_final=False)
            return [] if payload is None else [payload]

        final_segments = self._build_final_segments(transcript)
        if not final_segments:
            return []

        block.segments.extend(final_segments)
        block.draft_segments = []
        payload = self._build_block_event(block, is_final=False)
        return [] if payload is None else [payload]

    def _handle_close_block(self) -> list[MeetingSessionEvent]:
        return self._close_open_block()

    def _handle_close_event(self, event: ProviderEvent) -> list[MeetingSessionEvent]:
        if self.state == MeetingSessionState.FINALIZING:
            emitted = self._close_open_block()
            self._awaiting_stop_emit = False
            self.state = MeetingSessionState.COMPLETED
            self.completed_at = self._utcnow()
            emitted.append(
                MeetingSessionEvent(
                    kind=MeetingSessionEventKind.COMPLETED,
                    payload=MeetingRecordCompletedPayload(meeting_id=self.meeting_id),
                )
            )
            return emitted

        message = "Provider closed before meeting transcript finalized"
        if event.close_code is not None:
            message = f"{message} (code {event.close_code})"
        return [self._build_error_event(message)]

    def _build_error_event(
        self,
        error_message: str,
        *,
        error_code: str = "meeting_record_failed",
    ) -> MeetingSessionEvent:
        self._fail()
        self._awaiting_stop_emit = False
        self._open_block = None
        return MeetingSessionEvent(
            kind=MeetingSessionEventKind.ERROR,
            payload=MeetingRecordErrorPayload(
                meeting_id=self.meeting_id,
                error_code=error_code,
                error_message=error_message,
            ),
        )

    def _assert_can_start(self) -> None:
        if self.state != MeetingSessionState.STARTING:
            raise InvalidMeetingRecordStateError("Meeting session has already started")

    def _assert_state(self, allowed_states: set[MeetingSessionState]) -> None:
        if self.state not in allowed_states:
            allowed = ", ".join(
                state.value for state in sorted(allowed_states, key=str)
            )
            raise InvalidMeetingRecordStateError(
                f"Meeting session is '{self.state.value}', expected one of: {allowed}"
            )

    def _fail(self) -> None:
        self.state = MeetingSessionState.FAILED
        self.failed_at = self._utcnow()

    def _get_or_create_open_block(self) -> OpenMeetingTranscriptBlock:
        block = self._open_block
        if block is not None:
            return block

        block = OpenMeetingTranscriptBlock(
            block_id=uuid4().hex,
            sequence=self._next_block_sequence,
        )
        self._open_block = block
        return block

    def _build_draft_segments(
        self,
        transcript: ProviderTranscriptEvent,
        *,
        existing_segments: list[MeetingTranscriptSegmentState],
    ) -> list[MeetingTranscriptSegmentState]:
        grouped_words = self._group_words_by_speaker(transcript.words)
        if not grouped_words:
            text = transcript.transcript.strip()
            if not text:
                return []
            return [
                MeetingTranscriptSegmentState(
                    segment_id=(
                        existing_segments[0].segment_id
                        if existing_segments
                        else uuid4().hex
                    ),
                    speaker_key=transcript.speaker,
                    speaker_label=self._speaker_label(transcript.speaker),
                    text=text,
                    start_ms=transcript.start_ms,
                    end_ms=transcript.end_ms,
                )
            ]

        draft_segments: list[MeetingTranscriptSegmentState] = []
        for index, (speaker_key, words) in enumerate(grouped_words):
            text = self._compose_word_text(words)
            if not text:
                continue
            draft_segments.append(
                MeetingTranscriptSegmentState(
                    segment_id=(
                        existing_segments[index].segment_id
                        if index < len(existing_segments)
                        else uuid4().hex
                    ),
                    speaker_key=speaker_key,
                    speaker_label=self._speaker_label(speaker_key),
                    text=text,
                    start_ms=words[0].start_ms,
                    end_ms=words[-1].end_ms,
                )
            )
        return draft_segments

    def _build_final_segments(
        self,
        transcript: ProviderTranscriptEvent,
    ) -> list[MeetingTranscriptSegmentState]:
        grouped_words = self._group_words_by_speaker(transcript.words)
        if not grouped_words:
            text = transcript.transcript.strip()
            if not text:
                return []
            return [
                MeetingTranscriptSegmentState(
                    segment_id=uuid4().hex,
                    speaker_key=transcript.speaker,
                    speaker_label=self._speaker_label(transcript.speaker),
                    text=text,
                    start_ms=transcript.start_ms,
                    end_ms=transcript.end_ms,
                )
            ]

        segments: list[MeetingTranscriptSegmentState] = []
        for speaker_key, words in grouped_words:
            text = self._compose_word_text(words)
            if not text:
                continue
            segments.append(
                MeetingTranscriptSegmentState(
                    segment_id=uuid4().hex,
                    speaker_key=speaker_key,
                    speaker_label=self._speaker_label(speaker_key),
                    text=text,
                    start_ms=words[0].start_ms,
                    end_ms=words[-1].end_ms,
                )
            )
        return segments

    def _group_words_by_speaker(
        self,
        words: list[ProviderTranscriptWord] | None,
    ) -> list[tuple[int | None, list[ProviderTranscriptWord]]]:
        if not words:
            return []

        groups: list[tuple[int | None, list[ProviderTranscriptWord]]] = []
        current_speaker = words[0].speaker
        current_group: list[ProviderTranscriptWord] = [words[0]]

        for word in words[1:]:
            if word.speaker == current_speaker:
                current_group.append(word)
                continue
            groups.append((current_speaker, current_group))
            current_speaker = word.speaker
            current_group = [word]

        groups.append((current_speaker, current_group))
        return groups

    def _build_block_event(
        self,
        block: OpenMeetingTranscriptBlock,
        *,
        is_final: bool,
    ) -> MeetingSessionEvent | None:
        if not block.segments and not block.draft_segments:
            return None

        start_ms, end_ms = self._derive_block_window(block)
        return MeetingSessionEvent(
            kind=MeetingSessionEventKind.TRANSCRIPT,
            payload=MeetingTranscriptBlockPayload(
                meeting_id=self.meeting_id,
                block_id=block.block_id,
                sequence=block.sequence,
                segments=[
                    segment.to_payload(is_final=True)
                    for segment in block.segments
                ],
                draft_segments=[
                    segment.to_payload(is_final=False)
                    for segment in block.draft_segments
                ],
                is_final=is_final,
                start_ms=start_ms,
                end_ms=end_ms,
            ),
        )

    def _close_open_block(
        self,
    ) -> list[MeetingSessionEvent]:
        block = self._open_block
        if block is None:
            return []

        payload = self._build_block_event(block, is_final=True)
        self._open_block = None
        self._next_block_sequence = block.sequence + 1
        return [] if payload is None else [payload]

    def _derive_block_window(
        self,
        block: OpenMeetingTranscriptBlock,
    ) -> tuple[int | None, int | None]:
        start_candidates: list[int] = []
        end_candidates: list[int] = []

        for segment in block.segments:
            if segment.start_ms is not None:
                start_candidates.append(segment.start_ms)
            if segment.end_ms is not None:
                end_candidates.append(segment.end_ms)

        for segment in block.draft_segments:
            if segment.start_ms is not None:
                start_candidates.append(segment.start_ms)
            if segment.end_ms is not None:
                end_candidates.append(segment.end_ms)

        start_ms = min(start_candidates) if start_candidates else None
        end_ms = max(end_candidates) if end_candidates else None
        return start_ms, end_ms

    def _compose_word_text(self, words: list[ProviderTranscriptWord]) -> str:
        parts: list[str] = []
        for word in words:
            token = word.text.strip()
            if not token:
                continue
            if not parts:
                parts.append(token)
                continue
            if token.startswith(PUNCTUATION_PREFIXES):
                parts[-1] = f"{parts[-1]}{token}"
                continue
            if parts[-1].endswith(PUNCTUATION_SUFFIXES):
                parts[-1] = f"{parts[-1]}{token}"
                continue
            parts.append(token)
        return " ".join(parts).strip()

    @staticmethod
    def _speaker_label(speaker_key: int | None) -> str:
        if speaker_key is None:
            return "speaker unknown"
        return f"speaker {speaker_key + 1}"

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
