"""Meeting summary enqueue orchestration and durable state access."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.common.exceptions import AppException, MeetingRecordNotFoundError
from app.config.settings import get_settings
from app.domain.models.meeting_summary import MeetingSummary, MeetingSummaryStatus
from app.domain.models.meeting_summary_job import (
    MeetingSummaryJob,
    MeetingSummaryJobKind,
    MeetingSummaryJobStatus,
)
from app.infrastructure.llm.factory import get_chat_openai_legacy
from app.infrastructure.redis.redis_queue import RedisQueue
from app.prompts.system.meeting_summary import (
    MEETING_SUMMARY_SYSTEM_PROMPT,
    build_meeting_summary_user_prompt,
)
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
    ) -> MeetingSummary:
        """Execute one claimed summary job and persist the latest summary."""
        record = await self.meeting_record_repo.get_by_id(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
        )
        if record is None:
            raise MeetingRecordNotFoundError(
                f"Meeting '{job.meeting_id}' was not found"
            )

        latest_summary = await self.meeting_summary_repo.get_latest_by_meeting(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
        )
        covered_summary = self._get_covered_summary_for_job(
            job=job,
            latest_summary=latest_summary,
        )
        if covered_summary is not None:
            if (
                job.job_kind == MeetingSummaryJobKind.FINALIZE
                and covered_summary.bullets
                and not covered_summary.is_final
            ):
                return await self.meeting_summary_repo.upsert_latest_summary(
                    meeting_id=job.meeting_id,
                    organization_id=job.organization_id,
                    language=covered_summary.language,
                    status="final_ready",
                    bullets=covered_summary.bullets,
                    is_final=True,
                    source_block_sequence=covered_summary.source_block_sequence,
                    error_message=None,
                )
            return covered_summary

        return await self.generate_summary_for_job(
            job=job,
            language=record.language,
            latest_summary=latest_summary,
        )

    async def generate_summary_for_job(
        self,
        *,
        job: MeetingSummaryJob,
        language: str,
        latest_summary: MeetingSummary | None = None,
    ) -> MeetingSummary:
        """Generate and persist one live or final short summary."""
        min_block_sequence_exclusive = self._get_previous_summary_sequence(
            latest_summary=latest_summary,
        )
        transcript_segments = (
            await self.meeting_transcript_repo.list_up_to_block_sequence(
                meeting_id=job.meeting_id,
                organization_id=job.organization_id,
                max_block_sequence=job.target_block_sequence,
                limit=self.settings.MEETING_SUMMARY_MAX_INPUT_SEGMENTS,
                min_block_sequence_exclusive=min_block_sequence_exclusive,
            )
        )
        if not transcript_segments:
            return await self._persist_existing_summary(
                job=job,
                language=language,
                latest_summary=latest_summary,
            )

        transcript_text = self._build_transcript_text(transcript_segments)
        if not transcript_text:
            return await self._persist_existing_summary(
                job=job,
                language=language,
                latest_summary=latest_summary,
            )

        llm = get_chat_openai_legacy(
            model=self.settings.MEETING_SUMMARY_MODEL,
            temperature=0.2,
            streaming=False,
            max_tokens=self.settings.MEETING_SUMMARY_MAX_TOKENS,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=MEETING_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(
                    content=build_meeting_summary_user_prompt(
                        language=language,
                        transcript_text=transcript_text,
                        existing_bullets=(
                            list(latest_summary.bullets[-10:])
                            if latest_summary is not None and latest_summary.bullets
                            else None
                        ),
                    )
                ),
            ]
        )
        should_update, bullets = self._parse_summary_result(
            self._extract_message_text(response.content)
        )
        if not should_update:
            return await self._persist_existing_summary(
                job=job,
                language=language,
                latest_summary=latest_summary,
            )
        # Live jobs persist status="ready"; finalize jobs persist status="final_ready".
        status = (
            "final_ready" if job.job_kind == MeetingSummaryJobKind.FINALIZE else "ready"
        )
        is_final = job.job_kind == MeetingSummaryJobKind.FINALIZE

        return await self.meeting_summary_repo.upsert_latest_summary(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
            language=language,
            status=status,
            bullets=bullets,
            is_final=is_final,
            source_block_sequence=job.target_block_sequence,
            error_message=None,
        )

    async def get_summary_language(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        latest_summary: MeetingSummary | None = None,
    ) -> str:
        """Resolve the authoritative summary language for one meeting."""
        if latest_summary is not None and latest_summary.language:
            return latest_summary.language

        record = await self.meeting_record_repo.get_by_id(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        if record is not None and record.language:
            return record.language
        return "en"

    async def mark_job_failed(
        self,
        *,
        job: MeetingSummaryJob,
        error_message: str,
        latest_summary: MeetingSummary | None = None,
    ) -> MeetingSummary:
        """Persist failed summary lifecycle state without discarding last good bullets."""
        language = await self.get_summary_language(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
            latest_summary=latest_summary,
        )
        source_block_sequence = (
            latest_summary.source_block_sequence
            if latest_summary is not None
            else job.target_block_sequence
        )
        bullets = latest_summary.bullets if latest_summary is not None else []

        return await self.meeting_summary_repo.mark_status(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
            language=language,
            status=MeetingSummaryStatus.FAILED,
            source_block_sequence=source_block_sequence,
            is_final=False,
            error_message=error_message,
            bullets=bullets,
        )

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
            raise MeetingRecordNotFoundError(f"Meeting '{meeting_id}' was not found")

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

    @staticmethod
    def _build_transcript_text(transcript_segments: Sequence[Any]) -> str:
        lines: list[str] = []
        for segment in transcript_segments:
            text = segment.text.strip()
            if not text:
                continue
            speaker_label = (segment.speaker_label or "speaker").strip()
            lines.append(f"{speaker_label}: {text}")
        return "\n".join(lines)

    @staticmethod
    def _extract_message_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                        continue
                    parts.append(str(item.get("content", "")))
                    continue
                parts.append(str(item))
            return "".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _parse_summary_result(raw_response: str) -> tuple[bool, list[str]]:
        normalized = raw_response.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                normalized = "\n".join(lines[1:-1]).strip()

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise AppException("Meeting summary model returned invalid JSON") from exc

        if not isinstance(parsed, dict):
            raise AppException("Meeting summary model must return a JSON object")

        should_update = parsed.get("should_update")
        if not isinstance(should_update, bool):
            raise AppException(
                'Meeting summary JSON must contain a boolean "should_update" field'
            )

        bullets = parsed.get("bullets")
        if not isinstance(bullets, list):
            raise AppException('Meeting summary JSON must contain a "bullets" array')

        normalized_bullets = [
            bullet.strip()
            for bullet in bullets
            if isinstance(bullet, str) and bullet.strip()
        ]
        if not should_update:
            if normalized_bullets:
                raise AppException(
                    'Meeting summary JSON with "should_update": false must return an empty "bullets" array'
                )
            return False, []

        if len(normalized_bullets) not in {2, 3}:
            raise AppException(
                "Meeting summary model must return exactly 2 or 3 bullet strings"
            )
        return True, normalized_bullets

    @staticmethod
    def _get_covered_summary_for_job(
        *,
        job: MeetingSummaryJob,
        latest_summary: MeetingSummary | None,
    ) -> MeetingSummary | None:
        if latest_summary is None:
            return None
        if latest_summary.source_block_sequence < job.target_block_sequence:
            return None
        if latest_summary.status not in {
            MeetingSummaryStatus.READY,
            MeetingSummaryStatus.FINAL_READY,
        }:
            return None
        return latest_summary

    @staticmethod
    def _get_previous_summary_sequence(
        *,
        latest_summary: MeetingSummary | None,
    ) -> int | None:
        if latest_summary is None:
            return None
        if latest_summary.status not in {
            MeetingSummaryStatus.READY,
            MeetingSummaryStatus.FINAL_READY,
        }:
            return None
        return latest_summary.source_block_sequence

    async def _persist_existing_summary(
        self,
        *,
        job: MeetingSummaryJob,
        language: str,
        latest_summary: MeetingSummary | None,
    ) -> MeetingSummary:
        if latest_summary is None or not latest_summary.bullets:
            raise AppException(
                "No previous summary is available to carry forward for this job"
            )

        status = (
            "final_ready" if job.job_kind == MeetingSummaryJobKind.FINALIZE else "ready"
        )
        is_final = job.job_kind == MeetingSummaryJobKind.FINALIZE
        resolved_language = latest_summary.language or language

        return await self.meeting_summary_repo.upsert_latest_summary(
            meeting_id=job.meeting_id,
            organization_id=job.organization_id,
            language=resolved_language,
            status=status,
            bullets=list(latest_summary.bullets),
            is_final=is_final,
            source_block_sequence=job.target_block_sequence,
            error_message=None,
        )
