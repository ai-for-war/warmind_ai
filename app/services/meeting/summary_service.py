"""Meeting summary enqueue orchestration and durable state access."""

from __future__ import annotations

from app.common.exceptions import AppException, MeetingRecordNotFoundError
from app.config.settings import get_settings
from app.domain.models.meeting_summary import MeetingSummary, MeetingSummaryStatus
from app.domain.models.meeting_summary_job import (
    MeetingSummaryJob,
    MeetingSummaryJobKind,
    MeetingSummaryJobStatus,
)
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.meeting_record_repo import MeetingRecordRepository
from app.repo.meeting_summary_job_repo import MeetingSummaryJobRepository
from app.repo.meeting_summary_repo import MeetingSummaryRepository
from app.repo.meeting_transcript_repo import MeetingTranscriptRepository


class MeetingSummaryService:
    """Coordinates durable live/final meeting summary job orchestration."""

    def __init__(
        self,
        *,
        meeting_summary_repo: MeetingSummaryRepository,
        meeting_summary_job_repo: MeetingSummaryJobRepository,
        meeting_transcript_repo: MeetingTranscriptRepository,
        meeting_record_repo: MeetingRecordRepository,
        redis_queue: RedisQueue,
    ) -> None:
        self.meeting_summary_repo = meeting_summary_repo
        self.meeting_summary_job_repo = meeting_summary_job_repo
        self.meeting_transcript_repo = meeting_transcript_repo
        self.meeting_record_repo = meeting_record_repo
        self.redis_queue = redis_queue
        self.settings = get_settings()

    async def maybe_enqueue_live_summary(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        language: str,
        target_block_sequence: int,
    ) -> MeetingSummaryJob | None:
        """Enqueue one live summary job only after the debounce thresholds are met."""
        if (
            target_block_sequence + 1
            < self.settings.MEETING_SUMMARY_MIN_BLOCKS_FOR_LIVE
        ):
            return None

        latest_summary = await self.meeting_summary_repo.get_latest_by_meeting(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        latest_job = await self.meeting_summary_job_repo.get_latest_job(
            meeting_id=meeting_id,
            organization_id=organization_id,
            job_kind=MeetingSummaryJobKind.LIVE,
        )
        latest_live_sequence = self._get_latest_live_sequence(
            latest_summary=latest_summary,
            latest_job=latest_job,
        )
        if latest_live_sequence is not None and (
            target_block_sequence - latest_live_sequence
            < self.settings.MEETING_SUMMARY_MIN_NEW_BLOCKS
        ):
            return None

        return await self._create_and_enqueue_job(
            meeting_id=meeting_id,
            organization_id=organization_id,
            language=language,
            target_block_sequence=target_block_sequence,
            job_kind=MeetingSummaryJobKind.LIVE,
        )

    async def enqueue_final_summary(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        language: str,
        target_block_sequence: int,
    ) -> MeetingSummaryJob:
        """Create or reuse the durable final-summary job for the latest transcript batch."""
        return await self._create_and_enqueue_job(
            meeting_id=meeting_id,
            organization_id=organization_id,
            language=language,
            target_block_sequence=target_block_sequence,
            job_kind=MeetingSummaryJobKind.FINALIZE,
        )

    async def get_latest_summary(
        self,
        *,
        meeting_id: str,
        organization_id: str,
    ) -> MeetingSummary | None:
        """Return the latest durable summary state for one meeting."""
        return await self.meeting_summary_repo.get_latest_by_meeting(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )

    async def process_job(
        self,
        *,
        job: MeetingSummaryJob,
    ) -> MeetingSummaryJob:
        """Execute one claimed summary job.

        Phase 03-01 only establishes the durable queue lane. Actual transcript-to-summary
        generation lands in Phase 03-02, so this entrypoint currently validates
        prerequisites and closes the job cleanly.
        """
        record = await self.meeting_record_repo.get_by_id(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
        )
        if record is None:
            raise MeetingRecordNotFoundError(
                f"Meeting '{job.meeting_id}' was not found"
            )

        transcript_segment_count = await self.meeting_transcript_repo.count_by_meeting(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
        )
        if transcript_segment_count <= 0:
            raise AppException(
                f"No persisted transcript segments found for meeting '{job.meeting_id}'"
            )

        completed = await self.meeting_summary_job_repo.mark_completed(job.id)
        if completed is None:
            raise AppException(
                f"Failed to mark summary job '{job.id}' as completed"
            )
        return completed

    async def _create_and_enqueue_job(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        language: str,
        target_block_sequence: int,
        job_kind: MeetingSummaryJobKind,
    ) -> MeetingSummaryJob:
        record = await self.meeting_record_repo.get_by_id(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        if record is None:
            raise MeetingRecordNotFoundError(
                f"Meeting '{meeting_id}' was not found"
            )

        await self.meeting_summary_repo.mark_status(
            meeting_id=meeting_id,
            organization_id=organization_id,
            language=language or record.language,
            status=MeetingSummaryStatus.PENDING,
            is_final=False,
            source_block_sequence=target_block_sequence,
            error_message=None,
        )
        job = await self.meeting_summary_job_repo.create_or_get_pending_job(
            meeting_id=meeting_id,
            organization_id=organization_id,
            user_id=record.user_id,
            job_kind=job_kind,
            target_block_sequence=target_block_sequence,
        )
        if job.status != MeetingSummaryJobStatus.PENDING:
            return job

        enqueued = await self.redis_queue.enqueue(
            queue_name=self.settings.MEETING_SUMMARY_QUEUE_NAME,
            data={
                "job_id": job.id,
                "meeting_id": meeting_id,
                "organization_id": organization_id,
                "user_id": record.user_id,
                "job_kind": job.job_kind.value,
                "target_block_sequence": target_block_sequence,
            },
        )
        if not enqueued:
            raise AppException("Failed to enqueue meeting summary job")
        return job

    @staticmethod
    def _get_latest_live_sequence(
        *,
        latest_summary: MeetingSummary | None,
        latest_job: MeetingSummaryJob | None,
    ) -> int | None:
        candidates: list[int] = []
        if (
            latest_summary is not None
            and not latest_summary.is_final
            and latest_summary.status == MeetingSummaryStatus.READY
        ):
            candidates.append(latest_summary.source_block_sequence)
        if latest_job is not None:
            candidates.append(latest_job.target_block_sequence)
        if not candidates:
            return None
        return max(candidates)
