"""Schemas for meeting transcript records and realtime payloads."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.domain.models.meeting import MeetingArchiveScope, MeetingStatus

PHASE1_MEETING_ENCODING = "linear16"
PHASE1_MEETING_SAMPLE_RATE = 16000
PHASE1_MEETING_CHANNELS = 1
DEFAULT_MEETING_PAGE_LIMIT = 20
MAX_MEETING_PAGE_LIMIT = 100
TMeetingItem = TypeVar("TMeetingItem")


class MeetingSchemaBase(BaseModel):
    """Base schema for meeting-related durable payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
    )


def _normalize_non_empty_text_list(
    value: Sequence[str] | None,
    *,
    field_name: str,
) -> list[str]:
    """Normalize persisted note text lists for meeting schemas."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain only strings")
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"{field_name} entries must not be blank")
        normalized.append(stripped)
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    """Collapse blank optional strings to null for stable transport."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class MeetingRecord(MeetingSchemaBase):
    """Schema representing one durable meeting session."""

    id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    created_by: str = Field(..., min_length=1)
    title: str | None = None
    source: str = Field(default="google_meet", min_length=1)
    status: MeetingStatus = MeetingStatus.STREAMING
    language: str | None = None
    stream_id: str = Field(..., min_length=1, max_length=128)
    started_at: datetime
    ended_at: datetime | None = None
    error_message: str | None = None
    archived_at: datetime | None = None
    archived_by: str | None = None

    @field_validator("title", "error_message", "archived_by", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional fields to null."""
        return _normalize_optional_text(value)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Normalize persisted language values for stable transport."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> str:
        """Normalize persisted source values while preserving the default."""
        if value is None:
            return "google_meet"
        normalized = value.strip().lower()
        return normalized or "google_meet"


class MeetingUtteranceMessageRecord(MeetingSchemaBase):
    """Schema representing one speaker-grouped transcript message."""

    speaker_index: int = Field(..., ge=0)
    speaker_label: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_label(self) -> "MeetingUtteranceMessageRecord":
        """Require the label to remain aligned with the speaker index."""
        expected = f"speaker_{self.speaker_index + 1}"
        if self.speaker_label != expected:
            raise ValueError(
                f"speaker_label must match speaker_index as '{expected}'"
            )
        return self


class MeetingUtteranceRecord(MeetingSchemaBase):
    """Schema representing one durable canonical meeting utterance."""

    id: str = Field(..., min_length=1)
    meeting_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    created_at: datetime


class MeetingNoteActionItemRecord(MeetingSchemaBase):
    """Schema representing one structured meeting note action item."""

    text: str = Field(..., min_length=1)
    owner_text: str | None = None
    due_text: str | None = None

    @field_validator("owner_text", "due_text", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional values to null for stable transport."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MeetingNoteChunkRecord(MeetingSchemaBase):
    """Schema representing one durable structured meeting note chunk."""

    id: str = Field(..., min_length=1)
    meeting_id: str = Field(..., min_length=1)
    from_sequence: int = Field(..., ge=1)
    to_sequence: int = Field(..., ge=1)
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[MeetingNoteActionItemRecord] = Field(default_factory=list)
    created_at: datetime

    @field_validator("key_points", mode="before")
    @classmethod
    def normalize_key_points(cls, value: Sequence[str] | None) -> list[str]:
        """Normalize note key points for transport and persistence."""
        return _normalize_non_empty_text_list(value, field_name="key_points")

    @field_validator("decisions", mode="before")
    @classmethod
    def normalize_decisions(cls, value: Sequence[str] | None) -> list[str]:
        """Normalize note decisions for transport and persistence."""
        return _normalize_non_empty_text_list(value, field_name="decisions")

    @model_validator(mode="after")
    def validate_range_and_content(self) -> "MeetingNoteChunkRecord":
        """Require a valid note range and at least one visible note item."""
        if self.from_sequence > self.to_sequence:
            raise ValueError("from_sequence must be less than or equal to to_sequence")
        if not self.key_points and not self.decisions and not self.action_items:
            raise ValueError(
                "meeting note chunk must include at least one note item"
            )
        return self


class MeetingSummaryRecord(MeetingSchemaBase):
    """Summary schema returned by meeting management APIs."""

    id: str = Field(..., min_length=1)
    title: str | None = None
    source: str = Field(default="google_meet", min_length=1)
    status: MeetingStatus = MeetingStatus.STREAMING
    started_at: datetime
    ended_at: datetime | None = None
    archived_at: datetime | None = None
    archived_by: str | None = None

    @field_validator("title", "archived_by", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional fields to null."""
        return _normalize_optional_text(value)

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> str:
        """Normalize source values while preserving the default."""
        if value is None:
            return "google_meet"
        normalized = value.strip().lower()
        return normalized or "google_meet"


class MeetingPaginationParams(MeetingSchemaBase):
    """Shared pagination parameters for meeting management endpoints."""

    skip: int = Field(default=0, ge=0)
    limit: int = Field(
        default=DEFAULT_MEETING_PAGE_LIMIT,
        ge=1,
        le=MAX_MEETING_PAGE_LIMIT,
    )


class MeetingListQuery(MeetingPaginationParams):
    """Query schema for creator-scoped meeting listing."""

    scope: MeetingArchiveScope = MeetingArchiveScope.ACTIVE
    status: MeetingStatus | None = None
    started_at_from: datetime | None = None
    started_at_to: datetime | None = None
    q: str | None = None

    @field_validator("q", mode="before")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        """Treat blank title-search input as absent."""
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_started_at_range(self) -> "MeetingListQuery":
        """Require a coherent started-at range when both bounds are present."""
        if (
            self.started_at_from is not None
            and self.started_at_to is not None
            and self.started_at_from > self.started_at_to
        ):
            raise ValueError(
                "started_at_from must be less than or equal to started_at_to"
            )
        return self


class MeetingPaginationEnvelope(MeetingSchemaBase, Generic[TMeetingItem]):
    """Shared pagination envelope for meeting management list responses."""

    items: list[TMeetingItem]
    total: int = Field(..., ge=0)
    skip: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    has_more: bool | None = None

    @model_validator(mode="after")
    def populate_has_more(self) -> "MeetingPaginationEnvelope[TMeetingItem]":
        """Infer whether another page exists when omitted by the caller."""
        if len(self.items) > self.limit:
            raise ValueError("items length must not exceed limit")
        if self.has_more is None:
            self.has_more = self.skip + len(self.items) < self.total
        return self


class MeetingListResponse(MeetingPaginationEnvelope[MeetingSummaryRecord]):
    """Paginated meeting-list response."""


class MeetingUtteranceListResponse(
    MeetingPaginationEnvelope[MeetingUtteranceRecord]
):
    """Paginated meeting utterance response."""


class MeetingNoteChunkListResponse(
    MeetingPaginationEnvelope[MeetingNoteChunkRecord]
):
    """Paginated meeting note chunk response."""


class MeetingUpdateRequest(MeetingSchemaBase):
    """PATCH request schema for meeting metadata and archive updates."""

    title: str | None = None
    source: str | None = None
    archived: bool | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        """Require non-blank replacement titles when provided."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        """Require non-blank replacement source values when provided."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("source must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_mutation_fields(self) -> "MeetingUpdateRequest":
        """Require at least one non-null mutable field in a PATCH request."""
        mutable_fields = {"title", "source", "archived"}
        provided_fields = mutable_fields & self.model_fields_set
        if not provided_fields:
            raise ValueError(
                "At least one of title, source, or archived must be provided"
            )

        null_fields = [
            field_name
            for field_name in provided_fields
            if getattr(self, field_name) is None
        ]
        if null_fields:
            formatted = ", ".join(sorted(null_fields))
            raise ValueError(f"{formatted} must not be null")
        return self


class MeetingUpdateResponse(MeetingSchemaBase):
    """PATCH response schema for one updated meeting."""

    meeting: MeetingSummaryRecord


class MeetingNoteCreatedPayload(MeetingNoteChunkRecord):
    """Payload emitted when one structured meeting note chunk is created."""


class MeetingGeneratedNoteBatch(MeetingSchemaBase):
    """Structured AI output for one processed meeting note batch."""

    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[MeetingNoteActionItemRecord] = Field(default_factory=list)

    @field_validator("key_points", mode="before")
    @classmethod
    def normalize_key_points(cls, value: Sequence[str] | None) -> list[str]:
        """Normalize generated key points for stable downstream handling."""
        return _normalize_non_empty_text_list(value, field_name="key_points")

    @field_validator("decisions", mode="before")
    @classmethod
    def normalize_decisions(cls, value: Sequence[str] | None) -> list[str]:
        """Normalize generated decisions for stable downstream handling."""
        return _normalize_non_empty_text_list(value, field_name="decisions")

    @property
    def is_empty(self) -> bool:
        """Return whether AI produced no note-worthy content for the batch."""
        return not self.key_points and not self.decisions and not self.action_items


class MeetingStartRequest(MeetingSchemaBase):
    """Payload for `meeting:start` requests."""

    organization_id: str = Field(..., min_length=1, max_length=128)
    stream_id: str = Field(..., min_length=1, max_length=128)
    title: str | None = None
    language: str | None = Field(default=None, min_length=2, max_length=32)
    source: str = Field(default="google_meet", min_length=1, max_length=64)
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Normalize language values before provider-level validation."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str | None) -> str:
        """Allow arbitrary source values while preserving the default."""
        if value is None:
            return "google_meet"
        normalized = value.strip().lower()
        return normalized or "google_meet"


class MeetingAudioMetadata(MeetingSchemaBase):
    """Metadata accompanying a binary `meeting:audio` payload."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS
    sequence: int = Field(
        ...,
        ge=0,
        description="Client-maintained monotonic frame sequence per stream.",
    )
    timestamp_ms: int | None = Field(
        default=None,
        ge=0,
        description="Optional client capture timestamp in milliseconds.",
    )


class MeetingFinalizeRequest(MeetingSchemaBase):
    """Payload for `meeting:finalize` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class MeetingStopRequest(MeetingSchemaBase):
    """Payload for `meeting:stop` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class MeetingStartedPayload(MeetingSchemaBase):
    """Payload emitted when a live meeting transcript session starts."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    language: str = Field(default="en", min_length=2, max_length=32)
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS
    status: Literal["streaming"] = "streaming"


class MeetingFinalPayload(MeetingSchemaBase):
    """Payload emitted for one finalized realtime transcript fragment."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    utterance_id: str = Field(..., min_length=1, max_length=128)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    is_final: Literal[True] = True


class MeetingUtteranceClosedPayload(MeetingSchemaBase):
    """Payload emitted when one canonical meeting utterance closes."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    utterance_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    created_at: datetime


class MeetingPendingUtterancePayload(MeetingSchemaBase):
    """Canonical pending utterance payload stored in Redis hot note state."""

    utterance_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    flat_text: str = Field(..., min_length=1)
    created_at: datetime

    @field_validator("flat_text", mode="before")
    @classmethod
    def normalize_flat_text(cls, value: str) -> str:
        """Require flattened prompt text to remain non-blank."""
        if not isinstance(value, str):
            raise TypeError("flat_text must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("flat_text must not be blank")
        return normalized


class MeetingNoteState(MeetingSchemaBase):
    """Per-meeting Redis summary state for incremental note generation."""

    meeting_id: str = Field(..., min_length=1, max_length=128)
    organization_id: str = Field(..., min_length=1, max_length=128)
    created_by_user_id: str = Field(..., min_length=1, max_length=128)
    status: MeetingStatus = MeetingStatus.STREAMING
    last_summarized_sequence: int = Field(default=0, ge=0)
    final_sequence: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_sequence_bounds(self) -> "MeetingNoteState":
        """Keep the terminal sequence aligned with the summarized watermark."""
        if (
            self.final_sequence is not None
            and self.final_sequence < self.last_summarized_sequence
        ):
            raise ValueError(
                "final_sequence must be greater than or equal to "
                "last_summarized_sequence"
            )
        return self


class MeetingNoteUtteranceClosedTask(MeetingUtteranceClosedPayload):
    """Queue contract for one closed meeting utterance task."""

    kind: Literal["utterance_closed"] = "utterance_closed"
    organization_id: str = Field(..., min_length=1, max_length=128)
    created_by_user_id: str = Field(..., min_length=1, max_length=128)
    retry_count: int = Field(default=0, ge=0)
    queued_at: datetime | None = None


class MeetingNoteTerminalTask(MeetingSchemaBase):
    """Queue contract for one meeting terminal tail-flush task."""

    kind: Literal["meeting_terminal"] = "meeting_terminal"
    organization_id: str = Field(..., min_length=1, max_length=128)
    created_by_user_id: str = Field(..., min_length=1, max_length=128)
    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["completed", "interrupted"]
    final_sequence: int = Field(..., ge=0)
    retry_count: int = Field(default=0, ge=0)
    queued_at: datetime | None = None


class MeetingCompletedPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session completes cleanly."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["completed"] = "completed"


class MeetingInterruptedPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session ends in interrupted state."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["interrupted"] = "interrupted"


class MeetingErrorPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session cannot continue."""

    stream_id: str | None = Field(default=None, min_length=1, max_length=128)
    meeting_id: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=500)
    retryable: bool = False


MeetingNoteTask = Annotated[
    MeetingNoteUtteranceClosedTask | MeetingNoteTerminalTask,
    Field(discriminator="kind"),
]

_MEETING_NOTE_TASK_ADAPTER = TypeAdapter(MeetingNoteTask)


def parse_meeting_note_task(value: object) -> MeetingNoteTask:
    """Parse one queued meeting note task into its typed contract."""
    return _MEETING_NOTE_TASK_ADAPTER.validate_python(value)
