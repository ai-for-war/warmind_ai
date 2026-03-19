"""Durable meeting transcript persistence and read service."""

from __future__ import annotations

import base64
import binascii

from app.common.exceptions import MeetingRecordNotFoundError
from app.domain.schemas.meeting_transcript import (
    MeetingTranscriptBlockPayload,
    MeetingTranscriptItemResponse,
    MeetingTranscriptPageResponse,
    MeetingTranscriptSegmentPayload,
)
from app.repo.meeting_record_repo import MeetingRecordRepository
from app.repo.meeting_transcript_repo import MeetingTranscriptRepository


class MeetingTranscriptService:
    """Persist and page stable transcript history for meeting review."""

    def __init__(
        self,
        *,
        meeting_record_repo: MeetingRecordRepository,
        meeting_transcript_repo: MeetingTranscriptRepository,
    ) -> None:
        self.meeting_record_repo = meeting_record_repo
        self.meeting_transcript_repo = meeting_transcript_repo

    async def append_closed_block(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        block_id: str,
        sequence: int,
        segments: list[MeetingTranscriptSegmentPayload],
    ) -> None:
        """Persist one finalized transcript block into durable storage."""
        finalized_segments = [
            segment
            for segment in segments
            if segment.is_final and segment.text.strip()
        ]
        if not finalized_segments:
            return

        await self.meeting_transcript_repo.upsert_block_segments(
            meeting_id=meeting_id,
            organization_id=organization_id,
            block_id=block_id,
            block_sequence=sequence,
            segments=finalized_segments,
        )

    async def append_closed_block_payload(
        self,
        payload: MeetingTranscriptBlockPayload,
        *,
        organization_id: str,
    ) -> None:
        """Persist one finalized public transcript block payload."""
        await self.append_closed_block(
            meeting_id=payload.meeting_id,
            organization_id=organization_id,
            block_id=payload.block_id,
            sequence=payload.sequence,
            segments=payload.segments,
        )

    async def get_transcript_page(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MeetingTranscriptPageResponse:
        """Return one oldest-first transcript page for active or completed meetings."""
        record = await self.meeting_record_repo.get_by_id(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        if record is None:
            raise MeetingRecordNotFoundError(
                f"Meeting '{meeting_id}' was not found"
            )

        normalized_limit = max(1, min(limit, 200))
        after = self._decode_cursor(cursor) if cursor else None
        items = await self.meeting_transcript_repo.list_by_meeting(
            meeting_id=meeting_id,
            organization_id=organization_id,
            after=after,
            limit=normalized_limit + 1,
        )

        has_more = len(items) > normalized_limit
        page_items = items[:normalized_limit]
        next_cursor = None
        if has_more and page_items:
            last_item = page_items[-1]
            next_cursor = self._encode_cursor(
                last_item.block_sequence,
                last_item.segment_index,
            )

        return MeetingTranscriptPageResponse(
            meeting_id=meeting_id,
            items=[
                MeetingTranscriptItemResponse(
                    block_id=item.block_id,
                    segment_id=item.segment_id,
                    block_sequence=item.block_sequence,
                    segment_index=item.segment_index,
                    speaker_label=item.speaker_label,
                    text=item.text,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                )
                for item in page_items
            ],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _encode_cursor(block_sequence: int, segment_index: int) -> str:
        raw = f"{block_sequence}:{segment_index}".encode("ascii")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[int, int]:
        try:
            padded = cursor + ("=" * (-len(cursor) % 4))
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
            block_sequence_raw, segment_index_raw = decoded.split(":", maxsplit=1)
            block_sequence = int(block_sequence_raw)
            segment_index = int(segment_index_raw)
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("Invalid transcript cursor") from exc

        if block_sequence < 0 or segment_index < 0:
            raise ValueError("Invalid transcript cursor")
        return block_sequence, segment_index
