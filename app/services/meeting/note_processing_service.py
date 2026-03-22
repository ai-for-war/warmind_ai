"""Worker-side processing for queued meeting note tasks."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.domain.models.meeting import MeetingStatus
from app.domain.models.meeting_note_chunk import MeetingNoteChunk
from app.domain.models.meeting_utterance import MeetingUtterance
from app.domain.schemas.meeting import (
    MeetingGeneratedNoteBatch,
    MeetingNoteState,
    MeetingNoteTask,
    MeetingNoteTerminalTask,
    MeetingNoteUtteranceClosedTask,
    MeetingPendingUtterancePayload,
)
from app.repo.meeting_note_chunk_repo import MeetingNoteChunkRepository
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.services.meeting.note_generation_service import MeetingNoteGenerationService
from app.services.meeting.note_state_store import RedisMeetingNoteStateStore

logger = logging.getLogger(__name__)

MeetingNoteChunkCallback = Callable[[MeetingNoteChunk, MeetingNoteState], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class MeetingNoteBatch:
    """One contiguous meeting utterance batch selected for summarization."""

    meeting_id: str
    organization_id: str
    created_by_user_id: str
    status: MeetingStatus
    final_sequence: int | None
    sequences: tuple[int, ...]
    utterances: tuple[MeetingPendingUtterancePayload, ...]

    @property
    def from_sequence(self) -> int:
        return self.sequences[0]

    @property
    def to_sequence(self) -> int:
        return self.sequences[-1]


@dataclass(slots=True, frozen=True)
class MeetingNoteProcessingResult:
    """Outcome of processing one queued meeting note task."""

    created_chunks: tuple[MeetingNoteChunk, ...] = ()
    summary_deferred: bool = False


class MeetingNoteProcessingService:
    """Persist queued utterances and generate structured incremental notes."""

    BATCH_SIZE = 7

    def __init__(
        self,
        *,
        note_state_store: RedisMeetingNoteStateStore,
        utterance_repo: MeetingUtteranceRepository,
        note_chunk_repo: MeetingNoteChunkRepository,
        note_generation_service: MeetingNoteGenerationService,
        note_chunk_created_callback: MeetingNoteChunkCallback | None = None,
    ) -> None:
        self.note_state_store = note_state_store
        self.utterance_repo = utterance_repo
        self.note_chunk_repo = note_chunk_repo
        self.note_generation_service = note_generation_service
        self.note_chunk_created_callback = note_chunk_created_callback

    async def process_task(
        self,
        task: MeetingNoteTask,
    ) -> MeetingNoteProcessingResult:
        """Process one queued meeting note task end to end."""
        if isinstance(task, MeetingNoteUtteranceClosedTask):
            await self._persist_and_stage_utterance(task)
        elif isinstance(task, MeetingNoteTerminalTask):
            await self.note_state_store.mark_terminal_state(
                meeting_id=task.meeting_id,
                organization_id=task.organization_id,
                created_by_user_id=task.created_by_user_id,
                status=task.status,
                final_sequence=task.final_sequence,
            )
        else:  # pragma: no cover - discriminated union guards this at parse time
            raise TypeError(f"Unsupported meeting note task type: {type(task)!r}")

        return await self._drain_available_batches(meeting_id=task.meeting_id)

    @classmethod
    def select_batch_sequences(
        cls,
        *,
        state: MeetingNoteState,
        pending_sequences: Sequence[int],
    ) -> tuple[int, ...]:
        """Choose the next eligible contiguous sequence batch for one meeting."""
        expected_sequence = state.last_summarized_sequence + 1
        contiguous: list[int] = []

        for sequence in sorted(set(pending_sequences)):
            if sequence < expected_sequence:
                continue
            if sequence != expected_sequence:
                break
            contiguous.append(sequence)
            expected_sequence += 1

        if len(contiguous) >= cls.BATCH_SIZE:
            return tuple(contiguous[: cls.BATCH_SIZE])

        if state.status == MeetingStatus.STREAMING:
            return ()

        if state.final_sequence is None:
            return ()

        if not contiguous or contiguous[-1] < state.final_sequence:
            return ()

        return tuple(contiguous)

    async def select_next_batch(
        self,
        *,
        meeting_id: str,
    ) -> MeetingNoteBatch | None:
        """Load the next eligible contiguous batch from Redis hot state."""
        state = await self.note_state_store.get_note_state(meeting_id=meeting_id)
        if state is None:
            return None

        sequences = self.select_batch_sequences(
            state=state,
            pending_sequences=await self.note_state_store.get_pending_sequence_numbers(
                meeting_id=meeting_id
            ),
        )
        if not sequences:
            return None

        utterances = tuple(
            await self.note_state_store.list_pending_utterances(
                meeting_id=meeting_id,
                sequences=sequences,
            )
        )
        if tuple(utterance.sequence for utterance in utterances) != sequences:
            raise ValueError(
                "Redis pending utterance payloads do not match selected sequences"
            )

        return MeetingNoteBatch(
            meeting_id=meeting_id,
            organization_id=state.organization_id,
            created_by_user_id=state.created_by_user_id,
            status=state.status,
            final_sequence=state.final_sequence,
            sequences=sequences,
            utterances=utterances,
        )

    async def _persist_and_stage_utterance(
        self,
        task: MeetingNoteUtteranceClosedTask,
    ) -> MeetingUtterance:
        persisted = await self.utterance_repo.append(
            meeting_id=task.meeting_id,
            sequence=task.sequence,
            messages=task.messages,
            utterance_id=task.utterance_id,
            created_at=task.created_at,
        )

        state = await self.note_state_store.get_note_state(meeting_id=task.meeting_id)
        if state is not None and persisted.sequence <= state.last_summarized_sequence:
            logger.debug(
                "Skip Redis restage for already summarized meeting utterance %s:%s",
                task.meeting_id,
                persisted.sequence,
            )
            return persisted

        await self.note_state_store.stage_pending_utterance(
            meeting_id=task.meeting_id,
            organization_id=task.organization_id,
            created_by_user_id=task.created_by_user_id,
            utterance_id=persisted.id,
            sequence=persisted.sequence,
            messages=persisted.messages,
            created_at=persisted.created_at,
        )
        return persisted

    async def _drain_available_batches(
        self,
        *,
        meeting_id: str,
    ) -> MeetingNoteProcessingResult:
        token = await self.note_state_store.acquire_summary_lock(meeting_id=meeting_id)
        if token is None:
            logger.debug(
                "Meeting note summary lock already held for meeting %s",
                meeting_id,
            )
            return MeetingNoteProcessingResult(summary_deferred=True)

        created_chunks: list[MeetingNoteChunk] = []
        try:
            while True:
                batch = await self.select_next_batch(meeting_id=meeting_id)
                if batch is None:
                    return MeetingNoteProcessingResult(
                        created_chunks=tuple(created_chunks)
                    )

                generated = await self.note_generation_service.generate_notes(
                    utterances=batch.utterances
                )
                chunk = await self._finalize_batch(batch=batch, generated=generated)
                if chunk is not None:
                    created_chunks.append(chunk)
        finally:
            await self.note_state_store.release_summary_lock(
                meeting_id=meeting_id,
                token=token,
            )

    async def _finalize_batch(
        self,
        *,
        batch: MeetingNoteBatch,
        generated: MeetingGeneratedNoteBatch,
    ) -> MeetingNoteChunk | None:
        if generated.is_empty:
            logger.debug(
                "Skipping empty meeting note batch %s:%s-%s",
                batch.meeting_id,
                batch.from_sequence,
                batch.to_sequence,
            )
            await self.note_state_store.remove_pending_utterances(
                meeting_id=batch.meeting_id,
                sequences=batch.sequences,
                last_summarized_sequence=batch.to_sequence,
            )
            return None

        chunk = await self.note_chunk_repo.append(
            meeting_id=batch.meeting_id,
            from_sequence=batch.from_sequence,
            to_sequence=batch.to_sequence,
            key_points=generated.key_points,
            decisions=generated.decisions,
            action_items=[
                item.model_dump(mode="python") for item in generated.action_items
            ],
        )
        await self.note_state_store.remove_pending_utterances(
            meeting_id=batch.meeting_id,
            sequences=batch.sequences,
            last_summarized_sequence=batch.to_sequence,
        )
        await self._emit_created_chunk_if_configured(
            meeting_id=batch.meeting_id,
            chunk=chunk,
        )
        return chunk

    async def _emit_created_chunk_if_configured(
        self,
        *,
        meeting_id: str,
        chunk: MeetingNoteChunk,
    ) -> None:
        if self.note_chunk_created_callback is None:
            return

        state = await self.note_state_store.get_note_state(meeting_id=meeting_id)
        if state is None:
            return
        await self.note_chunk_created_callback(chunk, state)
