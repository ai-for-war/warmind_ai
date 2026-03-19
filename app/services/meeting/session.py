"""Stateful meeting recording session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

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
from app.infrastructure.deepgram.client import DeepgramLiveClient


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
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(slots=True)
class MeetingSessionEvent:
    """Normalized meeting session event with a typed payload."""

    kind: MeetingSessionEventKind
    payload: (
        MeetingRecordStartedPayload
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

    @property
    def is_active(self) -> bool:
        """Return whether the meeting is still live."""
        return self.state not in {
            MeetingSessionState.COMPLETED,
            MeetingSessionState.FAILED,
        }

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

    async def stop(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> list[MeetingSessionEvent]:
        """Finalize and close the provider stream for the owning socket."""
        self.assert_owner(sid=sid, user_id=user_id, meeting_id=meeting_id)
        return await self._stop_internal()

    async def stop_for_disconnect(self) -> list[MeetingSessionEvent]:
        """Finalize and close the provider stream during disconnect cleanup."""
        if not self.is_active:
            return []
        return await self._stop_internal()

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
        self._fail()
        return MeetingSessionEvent(
            kind=MeetingSessionEventKind.ERROR,
            payload=MeetingRecordErrorPayload(
                meeting_id=self.meeting_id,
                error_code=error_code,
                error_message=error_message,
            ),
        )

    async def _stop_internal(self) -> list[MeetingSessionEvent]:
        self._assert_state({MeetingSessionState.STREAMING, MeetingSessionState.FINALIZING})
        self.state = MeetingSessionState.FINALIZING
        await self.provider_client.finalize()
        await self.provider_client.close()
        self.state = MeetingSessionState.COMPLETED
        self.completed_at = self._utcnow()
        return [
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.STOPPING,
                payload=MeetingRecordStoppingPayload(meeting_id=self.meeting_id),
            ),
            MeetingSessionEvent(
                kind=MeetingSessionEventKind.COMPLETED,
                payload=MeetingRecordCompletedPayload(meeting_id=self.meeting_id),
            ),
        ]

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

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
