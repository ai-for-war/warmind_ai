"""Shared payload builders for meeting note socket events."""

from app.domain.models.meeting_note_chunk import MeetingNoteChunk
from app.domain.schemas.meeting import MeetingNoteCreatedPayload


def build_meeting_note_created_payload(*, chunk: MeetingNoteChunk) -> dict:
    """Return the normalized realtime payload for one created note chunk."""
    payload = MeetingNoteCreatedPayload.model_validate(
        chunk.model_dump(mode="python")
    )
    return payload.model_dump(mode="json")
