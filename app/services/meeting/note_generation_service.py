"""AI generation for structured incremental meeting note batches."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.schemas.meeting import (
    MeetingGeneratedNoteBatch,
    MeetingPendingUtterancePayload,
)
from app.infrastructure.llm.factory import get_chat_azure_openai_legacy
from app.prompts.system.meeting_note_chunk import (
    MEETING_NOTE_CHUNK_SYSTEM_PROMPT,
)


class MeetingNoteGenerationService:
    """Generate structured notes from one contiguous meeting utterance batch."""

    def __init__(
        self,
        *,
        llm_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._llm_factory = llm_factory or self._default_llm_factory
        self._structured_llm: Any | None = None

    async def generate_notes(
        self,
        *,
        utterances: Sequence[MeetingPendingUtterancePayload],
    ) -> MeetingGeneratedNoteBatch:
        """Generate structured notes for one contiguous utterance batch."""
        if not utterances:
            raise ValueError("utterances must not be empty")

        result = await self._get_structured_llm().ainvoke(
            [
                SystemMessage(content=MEETING_NOTE_CHUNK_SYSTEM_PROMPT),
                HumanMessage(content=self._build_user_prompt(utterances)),
            ]
        )
        return MeetingGeneratedNoteBatch.model_validate(result)

    def _get_structured_llm(self) -> Any:
        if self._structured_llm is None:
            self._structured_llm = self._llm_factory().with_structured_output(
                MeetingGeneratedNoteBatch
            )
        return self._structured_llm

    @staticmethod
    def _build_user_prompt(
        utterances: Sequence[MeetingPendingUtterancePayload],
    ) -> str:
        first_sequence = utterances[0].sequence
        last_sequence = utterances[-1].sequence
        transcript_blocks: list[str] = []
        for utterance in utterances:
            transcript_blocks.append(
                f"[sequence {utterance.sequence}]\n{utterance.flat_text}"
            )

        transcript = "\n\n".join(transcript_blocks)
        return (
            "Extract structured notes for exactly one contiguous meeting batch.\n"
            "Use only the transcript between <transcript_batch> tags.\n"
            "If the batch is not note-worthy, return empty lists.\n\n"
            "<sequence_range>\n"
            f"{first_sequence}-{last_sequence}\n"
            "</sequence_range>\n\n"
            "<transcript_batch>\n"
            f"{transcript}\n"
            "</transcript_batch>"
        )

    @staticmethod
    def _default_llm_factory() -> Any:
        return get_chat_azure_openai_legacy(
            model="gpt-4.1",
            temperature=0.2,
            streaming=False,
            max_tokens=1024,
        )
