"""Redis-backed hot state helpers for incremental meeting note processing."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError
from redis.asyncio import Redis

from app.domain.models.meeting import MeetingStatus
from app.domain.schemas.meeting import (
    MeetingNoteState,
    MeetingPendingUtterancePayload,
    MeetingUtteranceMessageRecord,
)

_RELEASE_SUMMARY_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
""".strip()


class RedisMeetingNoteStateStore:
    """Wrap Redis access for meeting note hot state and summary locking."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        state_ttl_seconds: int = 86400,
        summary_lock_ttl_seconds: int = 120,
    ) -> None:
        self.redis = redis_client
        self.state_ttl_seconds = max(state_ttl_seconds, 1)
        self.summary_lock_ttl_seconds = max(summary_lock_ttl_seconds, 1)

    async def get_note_state(self, *, meeting_id: str) -> MeetingNoteState | None:
        """Load one meeting's Redis note state, if it exists."""
        raw_state = await self.redis.hgetall(self.note_state_key(meeting_id))
        if not raw_state:
            return None
        return self._parse_note_state(meeting_id=meeting_id, raw_state=raw_state)

    async def stage_pending_utterance(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by_user_id: str,
        utterance_id: str,
        sequence: int,
        messages: Sequence[MeetingUtteranceMessageRecord | dict[str, object]],
        created_at: datetime,
    ) -> MeetingPendingUtterancePayload:
        """Store one closed canonical utterance in Redis hot note state."""
        normalized_messages = self._normalize_messages(messages)
        payload = MeetingPendingUtterancePayload(
            utterance_id=utterance_id,
            meeting_id=meeting_id,
            sequence=sequence,
            messages=[
                message.model_dump(mode="python") for message in normalized_messages
            ],
            flat_text=self.flatten_messages(normalized_messages),
            created_at=created_at,
        )
        sequence_field = str(payload.sequence)
        note_state_key = self.note_state_key(meeting_id)
        pending_sequences_key = self.pending_sequences_key(meeting_id)
        pending_utterances_key = self.pending_utterances_key(meeting_id)

        pipeline = self.redis.pipeline(transaction=True)
        pipeline.hsetnx(note_state_key, "organization_id", organization_id)
        pipeline.hsetnx(note_state_key, "created_by_user_id", created_by_user_id)
        pipeline.hsetnx(note_state_key, "status", MeetingStatus.STREAMING.value)
        pipeline.hsetnx(note_state_key, "last_summarized_sequence", 0)
        pipeline.hset(
            pending_utterances_key,
            sequence_field,
            payload.model_dump_json(),
        )
        pipeline.zadd(pending_sequences_key, {sequence_field: payload.sequence})
        pipeline.expire(note_state_key, self.state_ttl_seconds)
        pipeline.expire(pending_sequences_key, self.state_ttl_seconds)
        pipeline.expire(pending_utterances_key, self.state_ttl_seconds)
        await pipeline.execute()

        return payload

    async def mark_terminal_state(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by_user_id: str,
        status: MeetingStatus | str,
        final_sequence: int,
    ) -> MeetingNoteState:
        """Persist the terminal flush boundary for one meeting."""
        resolved_status = MeetingStatus(status)
        if resolved_status not in {
            MeetingStatus.COMPLETED,
            MeetingStatus.INTERRUPTED,
            MeetingStatus.FAILED,
        }:
            raise ValueError("status must be a terminal meeting status")

        existing_state = await self.get_note_state(meeting_id=meeting_id)
        validated_state = MeetingNoteState(
            meeting_id=meeting_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            status=resolved_status,
            last_summarized_sequence=(
                existing_state.last_summarized_sequence
                if existing_state is not None
                else 0
            ),
            final_sequence=final_sequence,
        )
        note_state_key = self.note_state_key(meeting_id)
        pipeline = self.redis.pipeline(transaction=True)
        pipeline.hset(
            note_state_key,
            mapping={
                "organization_id": validated_state.organization_id,
                "created_by_user_id": validated_state.created_by_user_id,
                "status": str(validated_state.status),
                "final_sequence": validated_state.final_sequence,
                "last_summarized_sequence": validated_state.last_summarized_sequence,
            },
        )
        pipeline.expire(note_state_key, self.state_ttl_seconds)
        await pipeline.execute()

        state = await self.get_note_state(meeting_id=meeting_id)
        if state is None:
            raise ValueError("meeting note state must exist after terminal update")
        return state

    async def set_last_summarized_sequence(
        self,
        *,
        meeting_id: str,
        sequence: int,
    ) -> None:
        """Advance the summarized watermark for one meeting."""
        existing_state = await self.get_note_state(meeting_id=meeting_id)
        if existing_state is None:
            raise ValueError("meeting note state must exist before advancing it")

        validated_state = MeetingNoteState(
            meeting_id=meeting_id,
            organization_id=existing_state.organization_id,
            created_by_user_id=existing_state.created_by_user_id,
            status=existing_state.status,
            last_summarized_sequence=sequence,
            final_sequence=existing_state.final_sequence,
        )
        pipeline = self.redis.pipeline(transaction=True)
        pipeline.hset(
            self.note_state_key(meeting_id),
            mapping={
                "last_summarized_sequence": validated_state.last_summarized_sequence,
            },
        )
        pipeline.expire(self.note_state_key(meeting_id), self.state_ttl_seconds)
        await pipeline.execute()

    async def get_pending_sequence_numbers(self, *, meeting_id: str) -> list[int]:
        """Return pending utterance sequences in ascending order."""
        values = await self.redis.zrange(self.pending_sequences_key(meeting_id), 0, -1)
        return [int(value) for value in values]

    async def get_pending_utterance(
        self,
        *,
        meeting_id: str,
        sequence: int,
    ) -> MeetingPendingUtterancePayload | None:
        """Load one pending utterance payload from Redis, if present."""
        raw_value = await self.redis.hget(
            self.pending_utterances_key(meeting_id),
            str(sequence),
        )
        if raw_value is None:
            return None
        return self._parse_pending_utterance(raw_value)

    async def list_pending_utterances(
        self,
        *,
        meeting_id: str,
        sequences: Sequence[int] | None = None,
    ) -> list[MeetingPendingUtterancePayload]:
        """Load pending utterance payloads in ascending sequence order."""
        ordered_sequences = (
            list(sequences)
            if sequences is not None
            else await self.get_pending_sequence_numbers(meeting_id=meeting_id)
        )
        if not ordered_sequences:
            return []

        raw_values = await self.redis.hmget(
            self.pending_utterances_key(meeting_id),
            [str(sequence) for sequence in ordered_sequences],
        )
        utterances = [
            self._parse_pending_utterance(raw_value)
            for raw_value in raw_values
            if raw_value is not None
        ]
        utterances.sort(key=lambda utterance: utterance.sequence)
        return utterances

    async def remove_pending_utterances(
        self,
        *,
        meeting_id: str,
        sequences: Sequence[int],
        last_summarized_sequence: int | None = None,
    ) -> None:
        """Remove consumed pending utterances and optionally advance the watermark."""
        ordered_fields = [str(sequence) for sequence in sorted({*sequences})]
        if not ordered_fields and last_summarized_sequence is None:
            return

        note_state_key = self.note_state_key(meeting_id)
        pending_sequences_key = self.pending_sequences_key(meeting_id)
        pending_utterances_key = self.pending_utterances_key(meeting_id)
        pipeline = self.redis.pipeline(transaction=True)

        if ordered_fields:
            pipeline.hdel(pending_utterances_key, *ordered_fields)
            pipeline.zrem(pending_sequences_key, *ordered_fields)
            pipeline.expire(pending_sequences_key, self.state_ttl_seconds)
            pipeline.expire(pending_utterances_key, self.state_ttl_seconds)

        if last_summarized_sequence is not None:
            existing_state = await self.get_note_state(meeting_id=meeting_id)
            if existing_state is None:
                raise ValueError("meeting note state must exist before advancing it")
            validated_state = MeetingNoteState(
                meeting_id=meeting_id,
                organization_id=existing_state.organization_id,
                created_by_user_id=existing_state.created_by_user_id,
                status=existing_state.status,
                last_summarized_sequence=last_summarized_sequence,
                final_sequence=existing_state.final_sequence,
            )
            pipeline.hset(
                note_state_key,
                mapping={
                    "last_summarized_sequence": validated_state.last_summarized_sequence,
                },
            )
            pipeline.expire(note_state_key, self.state_ttl_seconds)

        await pipeline.execute()

    async def acquire_summary_lock(
        self,
        *,
        meeting_id: str,
        token: str | None = None,
        ttl_seconds: int | None = None,
    ) -> str | None:
        """Acquire the per-meeting summary lock and return its token."""
        resolved_token = token.strip() if token is not None else uuid4().hex
        if not resolved_token:
            raise ValueError("token must not be blank")

        acquired = await self.redis.set(
            self.summary_lock_key(meeting_id),
            resolved_token,
            ex=max(ttl_seconds or self.summary_lock_ttl_seconds, 1),
            nx=True,
        )
        if not acquired:
            return None
        return resolved_token

    async def release_summary_lock(
        self,
        *,
        meeting_id: str,
        token: str,
    ) -> bool:
        """Release the per-meeting summary lock only if the token matches."""
        if not token.strip():
            raise ValueError("token must not be blank")

        released = await self.redis.eval(
            _RELEASE_SUMMARY_LOCK_SCRIPT,
            1,
            self.summary_lock_key(meeting_id),
            token,
        )
        return bool(released)

    @staticmethod
    def note_state_key(meeting_id: str) -> str:
        """Build the Redis key for one meeting's note summary state."""
        return f"meeting:{meeting_id}:note_state"

    @staticmethod
    def pending_sequences_key(meeting_id: str) -> str:
        """Build the Redis key for pending meeting note sequence markers."""
        return f"meeting:{meeting_id}:pending_sequences"

    @staticmethod
    def pending_utterances_key(meeting_id: str) -> str:
        """Build the Redis key for pending meeting note utterance payloads."""
        return f"meeting:{meeting_id}:pending_utterances"

    @staticmethod
    def summary_lock_key(meeting_id: str) -> str:
        """Build the Redis key for one meeting's summary ownership lock."""
        return f"lock:meeting:{meeting_id}:note_summary"

    @staticmethod
    def flatten_messages(
        messages: Sequence[MeetingUtteranceMessageRecord | dict[str, object]],
    ) -> str:
        """Collapse canonical speaker messages into prompt-ready transcript text."""
        normalized_messages = RedisMeetingNoteStateStore._normalize_messages(messages)
        return "\n".join(
            f"{message.speaker_label}: {message.text}"
            for message in normalized_messages
        )

    @staticmethod
    def _normalize_messages(
        messages: Sequence[MeetingUtteranceMessageRecord | dict[str, object]],
    ) -> list[MeetingUtteranceMessageRecord]:
        return [
            (
                message
                if isinstance(message, MeetingUtteranceMessageRecord)
                else MeetingUtteranceMessageRecord.model_validate(message)
            )
            for message in messages
        ]

    @staticmethod
    def _parse_pending_utterance(raw_value: str) -> MeetingPendingUtterancePayload:
        try:
            payload = json.loads(raw_value)
            return MeetingPendingUtterancePayload.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(
                "Redis stored meeting pending utterance state in an invalid format"
            ) from exc

    @staticmethod
    def _parse_note_state(
        *,
        meeting_id: str,
        raw_state: dict[str, str],
    ) -> MeetingNoteState:
        try:
            return MeetingNoteState.model_validate(
                {"meeting_id": meeting_id, **raw_state}
            )
        except ValidationError as exc:
            raise ValueError(
                "Redis stored meeting note state in an invalid format"
            ) from exc
