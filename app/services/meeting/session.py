"""Stateful meeting transcription session and canonical utterance assembly."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.common.exceptions import (
    ActiveSTTStreamConflictError,
    InvalidSTTStreamStateError,
    STTProviderConnectionError,
    STTStreamOwnershipError,
)
from app.domain.models.meeting import MeetingStatus
from app.domain.schemas.meeting import (
    MeetingCompletedPayload,
    MeetingErrorPayload,
    MeetingFinalPayload,
    MeetingInterruptedPayload,
    MeetingStartedPayload,
    MeetingUtteranceClosedPayload,
    MeetingUtteranceMessageRecord,
)
from app.infrastructure.deepgram.client import (
    DeepgramLiveClient,
    ProviderEvent,
    ProviderEventKind,
    ProviderTranscriptEvent,
    ProviderTranscriptWord,
)
from app.repo.meeting_repo import MeetingRepository

_NO_LEADING_SPACE_PATTERN = re.compile(r"^[,.;:!?%)\]\}]+$")
_ATTACHED_SUFFIX_TOKENS = {"'s", "'re", "'ve", "'m", "'d", "'ll", "n't"}


@dataclass(slots=True, frozen=True)
class BufferedMeetingWord:
    """One finalized word kept in memory until the utterance closes."""

    text: str
    speaker_index: int
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(slots=True)
class OpenMeetingUtterance:
    """Process-local finalized-word buffer for the current meeting utterance."""

    utterance_id: str
    started_at: datetime
    final_words: list[BufferedMeetingWord] = field(default_factory=list)
    last_activity_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def has_final_words(self) -> bool:
        """Return whether the utterance has buffered final words."""
        return bool(self.final_words)


class MeetingSessionEventKind(str, Enum):
    """Normalized session outputs for meeting socket/service layers."""

    STARTED = "started"
    FINAL = "final"
    UTTERANCE_CLOSED = "utterance_closed"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass(slots=True)
class MeetingSessionEvent:
    """Normalized meeting session event with a typed payload."""

    kind: MeetingSessionEventKind
    payload: (
        MeetingStartedPayload
        | MeetingFinalPayload
        | MeetingUtteranceClosedPayload
        | MeetingCompletedPayload
        | MeetingInterruptedPayload
        | MeetingErrorPayload
    )


class MeetingSession:
    """Own one live meeting transcription stream and its canonical utterances."""

    def __init__(
        self,
        *,
        sid: str,
        user_id: str,
        organization_id: str,
        stream_id: str,
        provider_client: DeepgramLiveClient,
        meeting_repo: MeetingRepository,
        meeting_id: str | None = None,
        title: str | None = None,
        language: str | None = None,
        source: str = "google_meet",
    ) -> None:
        self.sid = sid
        self.user_id = user_id
        self.organization_id = organization_id
        self.stream_id = stream_id
        self.provider_client = provider_client
        self.meeting_repo = meeting_repo
        self.meeting_id = meeting_id
        self.title = title
        self.language = (language or "en").strip().lower() or "en"
        self.source = source
        self.state = MeetingStatus.STREAMING
        self.created_at = self._utcnow()
        self.started_at: datetime | None = None
        self.finalize_requested_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.interrupted_at: datetime | None = None
        self.failed_at: datetime | None = None
        self.last_audio_at: datetime | None = None
        self.last_provider_activity_at: datetime | None = None
        self.last_keepalive_at: datetime | None = None
        self._next_sequence = 1
        self._open_utterance: OpenMeetingUtterance | None = None
        self._terminal_state_on_close = MeetingStatus.COMPLETED

    @property
    def is_active(self) -> bool:
        """Return whether the meeting session can still accept work."""
        return self.state not in {
            MeetingStatus.COMPLETED,
            MeetingStatus.INTERRUPTED,
            MeetingStatus.FAILED,
        }

    @property
    def last_allocated_sequence(self) -> int:
        """Return the highest meeting-local utterance sequence assigned so far."""
        return max(self._next_sequence - 1, 0)

    async def start(self) -> list[MeetingSessionEvent]:
        """Create the durable meeting record and open the provider stream."""
        if self.started_at is not None:
            raise InvalidSTTStreamStateError("Meeting session has already started")

        await self._ensure_meeting_record()
        try:
            await self.provider_client.open(language=self.language)
        except Exception as exc:
            await self._transition_terminal_state(
                MeetingStatus.FAILED,
                error_message="Failed to start meeting transcription stream",
            )
            raise STTProviderConnectionError(
                "Failed to start meeting transcription stream"
            ) from exc

        now = self._utcnow()
        self.started_at = now
        self.last_provider_activity_at = now
        return [
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.STARTED,
                payload=MeetingStartedPayload(
                    stream_id=self.stream_id,
                    meeting_id=self._require_meeting_id(),
                    language=self.language,
                ),
            )
        ]

    async def push_audio(self, *, sid: str, stream_id: str, chunk: bytes) -> None:
        """Forward a binary PCM chunk to the provider after ownership checks."""
        self.assert_owner(sid=sid, stream_id=stream_id)
        self._assert_state({MeetingStatus.STREAMING, MeetingStatus.FINALIZING})
        if not chunk:
            return

        await self.provider_client.send_audio(chunk)
        self.last_audio_at = self._utcnow()

    async def send_keepalive(self) -> bool:
        """Send a provider keepalive while the session is still active."""
        self._assert_state({MeetingStatus.STREAMING, MeetingStatus.FINALIZING})
        sent = await self.provider_client.send_keepalive()
        if sent:
            self.last_keepalive_at = self._utcnow()
        return sent

    async def request_finalize(self, *, sid: str, stream_id: str) -> None:
        """Ask the provider to flush final results before completing cleanly."""
        await self._request_terminal_transition(
            sid=sid,
            stream_id=stream_id,
            terminal_state=MeetingStatus.COMPLETED,
        )

    async def request_interrupt(self, *, sid: str, stream_id: str) -> None:
        """Ask the provider to flush final results before interrupting the meeting."""
        await self._request_terminal_transition(
            sid=sid,
            stream_id=stream_id,
            terminal_state=MeetingStatus.INTERRUPTED,
        )

    async def close_provider(self) -> bool:
        """Close the provider stream explicitly."""
        return await self.provider_client.close()

    async def consume_next_provider_events(self) -> list[MeetingSessionEvent]:
        """Consume one awaited provider event plus any already buffered events."""
        events = [await self.provider_client.next_event()]
        events.extend(self.provider_client.drain_pending_events())
        return await self.consume_provider_events(events)

    async def consume_provider_events(
        self,
        events: list[ProviderEvent],
    ) -> list[MeetingSessionEvent]:
        """Apply provider events to session state and emit normalized outputs."""
        emitted: list[MeetingSessionEvent] = []
        for event in events:
            self.last_provider_activity_at = self._utcnow()
            try:
                emitted.extend(await self._consume_provider_event(event))
            except Exception as exc:
                emitted.append(
                    await self.fail(
                        str(exc),
                        error_code="meeting_session_failed",
                    )
                )
                break
        return emitted

    def assert_owner(self, *, sid: str, stream_id: str) -> None:
        """Ensure inbound audio/control actions belong to this session."""
        if sid != self.sid or stream_id != self.stream_id:
            raise STTStreamOwnershipError()

    def assert_can_accept_new_stream(self, *, sid: str, stream_id: str) -> None:
        """Reject a second active meeting stream on the same socket."""
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

    async def fail(
        self,
        error_message: str,
        *,
        error_code: str = "meeting_session_failed",
    ) -> MeetingSessionEvent:
        """Transition the meeting into failed state and emit an error event."""
        await self._transition_terminal_state(
            MeetingStatus.FAILED,
            error_message=error_message,
        )
        with contextlib.suppress(Exception):
            await self.provider_client.close()
        return MeetingSessionEvent(
            kind=MeetingSessionEventKind.ERROR,
            payload=MeetingErrorPayload(
                stream_id=self.stream_id,
                meeting_id=self.meeting_id,
                error_code=error_code,
                error_message=error_message,
            ),
        )

    async def _request_terminal_transition(
        self,
        *,
        sid: str,
        stream_id: str,
        terminal_state: MeetingStatus,
    ) -> None:
        self.assert_owner(sid=sid, stream_id=stream_id)
        self._assert_state({MeetingStatus.STREAMING, MeetingStatus.FINALIZING})
        self.state = MeetingStatus.FINALIZING
        self.finalize_requested_at = self._utcnow()
        self._terminal_state_on_close = terminal_state
        await self._update_durable_status(MeetingStatus.FINALIZING)
        await self.provider_client.finalize()

    async def _consume_provider_event(
        self,
        event: ProviderEvent,
    ) -> list[MeetingSessionEvent]:
        if event.kind == ProviderEventKind.OPEN:
            return []
        if event.kind == ProviderEventKind.ERROR:
            return [
                await self.fail(
                    event.error_message or "Meeting transcription provider error",
                    error_code="meeting_provider_error",
                )
            ]
        if event.kind == ProviderEventKind.CLOSE:
            return await self._handle_close_event(event)
        if event.kind == ProviderEventKind.SPEECH_STARTED:
            return self._handle_speech_started()
        if event.kind == ProviderEventKind.UTTERANCE_END:
            return await self._handle_utterance_end()
        if event.kind == ProviderEventKind.PROVIDER_FINALIZE:
            return []
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

    def _handle_speech_started(self) -> list[MeetingSessionEvent]:
        utterance = self._open_utterance
        if utterance is not None:
            utterance.last_activity_at = self._utcnow()
        return []

    def _handle_transcript_event(
        self,
        transcript: ProviderTranscriptEvent,
    ) -> list[MeetingSessionEvent]:
        if not transcript.is_final:
            return []

        utterance = self._get_or_create_open_utterance()
        new_words = self._extract_new_final_words(
            existing_words=utterance.final_words,
            transcript=transcript,
        )
        if not new_words:
            return []

        now = self._utcnow()
        utterance.final_words.extend(new_words)
        utterance.last_activity_at = now
        utterance.ended_at = now

        messages = self._group_words_by_speaker(new_words)
        if not messages:
            return []

        return [
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.FINAL,
                payload=MeetingFinalPayload(
                    stream_id=self.stream_id,
                    meeting_id=self._require_meeting_id(),
                    utterance_id=utterance.utterance_id,
                    messages=messages,
                ),
            )
        ]

    async def _handle_utterance_end(self) -> list[MeetingSessionEvent]:
        utterance = self._open_utterance
        if utterance is None:
            return []

        self._open_utterance = None
        if not utterance.has_final_words:
            return []

        return [self._close_utterance(utterance)]

    async def flush_open_utterance(self) -> list[MeetingSessionEvent]:
        """Close any remaining finalized words before terminal cleanup."""
        utterance = self._open_utterance
        if utterance is None or not utterance.has_final_words:
            return []

        self._open_utterance = None
        return [self._close_utterance(utterance)]

    async def _handle_close_event(
        self,
        event: ProviderEvent,
    ) -> list[MeetingSessionEvent]:
        if self.state == MeetingStatus.FINALIZING:
            emitted = await self.flush_open_utterance()
            terminal_state = self._terminal_state_on_close
            await self._transition_terminal_state(terminal_state)
            if terminal_state == MeetingStatus.INTERRUPTED:
                emitted.append(
                    MeetingSessionEvent(
                        kind=MeetingSessionEventKind.INTERRUPTED,
                        payload=MeetingInterruptedPayload(
                            stream_id=self.stream_id,
                            meeting_id=self._require_meeting_id(),
                        ),
                    )
                )
                return emitted
            emitted.append(
                MeetingSessionEvent(
                    kind=MeetingSessionEventKind.COMPLETED,
                    payload=MeetingCompletedPayload(
                        stream_id=self.stream_id,
                        meeting_id=self._require_meeting_id(),
                    ),
                )
            )
            return emitted

        if self.state in {
            MeetingStatus.COMPLETED,
            MeetingStatus.INTERRUPTED,
            MeetingStatus.FAILED,
        }:
            return []

        message = "Provider closed before meeting stream finalized"
        if event.close_code is not None:
            message = f"{message} (code {event.close_code})"
        return [
            await self.fail(
                message,
                error_code="meeting_provider_closed",
            )
        ]

    def _close_utterance(
        self,
        utterance: OpenMeetingUtterance,
    ) -> MeetingSessionEvent:
        messages = self._group_words_by_speaker(utterance.final_words)
        if not messages:
            raise ValueError("Meeting utterance has no canonical speaker messages")

        sequence = self._next_sequence
        self._next_sequence += 1
        closed_at = self._utcnow()
        utterance.ended_at = closed_at
        return MeetingSessionEvent(
            kind=MeetingSessionEventKind.UTTERANCE_CLOSED,
            payload=MeetingUtteranceClosedPayload(
                stream_id=self.stream_id,
                meeting_id=self._require_meeting_id(),
                utterance_id=utterance.utterance_id,
                sequence=sequence,
                messages=messages,
                created_at=closed_at,
            ),
        )

    def _get_or_create_open_utterance(self) -> OpenMeetingUtterance:
        utterance = self._open_utterance
        if utterance is not None:
            return utterance

        now = self._utcnow()
        utterance = OpenMeetingUtterance(
            utterance_id=uuid4().hex,
            started_at=now,
            last_activity_at=now,
        )
        self._open_utterance = utterance
        return utterance

    def _extract_new_final_words(
        self,
        *,
        existing_words: Sequence[BufferedMeetingWord],
        transcript: ProviderTranscriptEvent,
    ) -> list[BufferedMeetingWord]:
        fallback_speaker = existing_words[-1].speaker_index if existing_words else None
        incoming_words = self._normalize_provider_words(
            transcript.words,
            fallback_speaker_index=fallback_speaker,
        )
        if not incoming_words:
            raise ValueError(
                "Meeting final transcript fragment is missing word-level speaker data"
            )

        return list(incoming_words)

    @staticmethod
    def _normalize_provider_words(
        words: Sequence[ProviderTranscriptWord],
        *,
        fallback_speaker_index: int | None,
    ) -> tuple[BufferedMeetingWord, ...]:
        normalized_words: list[BufferedMeetingWord] = []
        current_speaker = fallback_speaker_index
        for word in words:
            text = word.text.strip()
            if not text:
                continue

            speaker_index = word.speaker_index
            if speaker_index is None:
                speaker_index = 0 if current_speaker is None else current_speaker
            current_speaker = speaker_index

            normalized_words.append(
                BufferedMeetingWord(
                    text=text,
                    speaker_index=speaker_index,
                    confidence=word.confidence,
                    start_ms=word.start_ms,
                    end_ms=word.end_ms,
                )
            )

        return tuple(normalized_words)

    @classmethod
    def _group_words_by_speaker(
        cls,
        words: Sequence[BufferedMeetingWord],
    ) -> list[MeetingUtteranceMessageRecord]:
        messages: list[MeetingUtteranceMessageRecord] = []
        current_speaker: int | None = None
        current_tokens: list[str] = []

        for word in words:
            text = word.text.strip()
            if not text:
                continue

            if current_speaker is None:
                current_speaker = word.speaker_index
                current_tokens = [text]
                continue

            if word.speaker_index == current_speaker:
                current_tokens.append(text)
                continue

            messages.append(
                cls._build_message(
                    speaker_index=current_speaker,
                    tokens=current_tokens,
                )
            )
            current_speaker = word.speaker_index
            current_tokens = [text]

        if current_speaker is not None and current_tokens:
            messages.append(
                cls._build_message(
                    speaker_index=current_speaker,
                    tokens=current_tokens,
                )
            )

        return messages

    @classmethod
    def _build_message(
        cls,
        *,
        speaker_index: int,
        tokens: Sequence[str],
    ) -> MeetingUtteranceMessageRecord:
        return MeetingUtteranceMessageRecord(
            speaker_index=speaker_index,
            speaker_label=f"speaker_{speaker_index + 1}",
            text=cls._compose_tokens(tokens),
        )

    @staticmethod
    def _compose_tokens(tokens: Sequence[str]) -> str:
        transcript = ""
        for token in tokens:
            normalized = token.strip()
            if not normalized:
                continue
            if not transcript:
                transcript = normalized
                continue
            if (
                normalized.startswith("'")
                or normalized in _ATTACHED_SUFFIX_TOKENS
                or _NO_LEADING_SPACE_PATTERN.match(normalized)
            ):
                transcript = f"{transcript}{normalized}"
                continue
            transcript = f"{transcript} {normalized}"
        return transcript

    async def _ensure_meeting_record(self) -> None:
        meeting = await self.meeting_repo.create(
            organization_id=self.organization_id,
            created_by=self.user_id,
            stream_id=self.stream_id,
            title=self.title,
            source=self.source,
            status=self.state,
            language=self.language,
            meeting_id=self.meeting_id,
            started_at=self.created_at,
        )
        self.meeting_id = meeting.id

    async def _update_durable_status(
        self,
        status: MeetingStatus,
        *,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        if self.meeting_id is None:
            return
        await self.meeting_repo.update_status(
            meeting_id=self.meeting_id,
            status=status,
            ended_at=ended_at,
            error_message=error_message,
        )

    async def _transition_terminal_state(
        self,
        status: MeetingStatus,
        *,
        error_message: str | None = None,
    ) -> None:
        now = self._utcnow()
        self.state = status
        if status == MeetingStatus.COMPLETED:
            self.completed_at = now
        elif status == MeetingStatus.INTERRUPTED:
            self.interrupted_at = now
        elif status == MeetingStatus.FAILED:
            self.failed_at = now

        self._open_utterance = None
        await self._update_durable_status(
            status,
            ended_at=now,
            error_message=error_message,
        )

    def _assert_state(self, allowed_states: set[MeetingStatus]) -> None:
        if self.state not in allowed_states:
            allowed = ", ".join(
                state.value for state in sorted(allowed_states, key=lambda item: item.value)
            )
            raise InvalidSTTStreamStateError(
                f"Meeting session is '{self.state.value}', expected one of: {allowed}"
            )

    def _require_meeting_id(self) -> str:
        if self.meeting_id is None:
            raise InvalidSTTStreamStateError("Meeting session has no durable meeting id")
        return self.meeting_id

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
