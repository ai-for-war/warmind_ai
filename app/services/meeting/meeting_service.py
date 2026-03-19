"""Application service entry point for live meeting recording flows."""

from __future__ import annotations

from app.common.exceptions import (
    ActiveMeetingRecordConflictError,
    MeetingRecordOwnershipError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    UnsupportedMeetingLanguageError,
)
from app.config.settings import get_settings
from app.repo.meeting_record_repo import MeetingRecordRepository
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.services.meeting.session import (
    MeetingSession,
    MeetingSessionEvent,
    MeetingSessionEventKind,
)
from app.services.meeting.session_manager import MeetingSessionManager

MEETING_SUPPORTED_LANGUAGES = frozenset(get_settings().MEETING_SUPPORTED_LANGUAGES)


class MeetingService:
    """Application service entry point for live meeting recording flows."""

    def __init__(
        self,
        *,
        session_manager: MeetingSessionManager,
        meeting_record_repo: MeetingRecordRepository,
        organization_repo: OrganizationRepository,
        member_repo: OrganizationMemberRepository,
    ) -> None:
        self.session_manager = session_manager
        self.meeting_record_repo = meeting_record_repo
        self.organization_repo = organization_repo
        self.member_repo = member_repo

    def get_session(self, sid: str) -> MeetingSession | None:
        """Return the live meeting session for a socket, if any."""
        return self.session_manager.get_session(sid)

    def acknowledge_stop_emitted(self, sid: str) -> None:
        """Release pending provider events after STOPPING is emitted."""
        self.session_manager.acknowledge_stop_emitted(sid)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        organization_id: str,
        language: str | None,
    ) -> list[MeetingSessionEvent]:
        """Start one live meeting session."""
        existing = self.session_manager.get_session(sid)
        if existing is not None and existing.is_active:
            raise ActiveMeetingRecordConflictError()

        await self._validate_org_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        normalized_language = self._normalize_language(language)
        record = await self.meeting_record_repo.create(
            user_id=user_id,
            organization_id=organization_id,
            language=normalized_language,
            provider="deepgram",
        )

        try:
            return await self.session_manager.start_session(
                sid=sid,
                user_id=user_id,
                organization_id=organization_id,
                meeting_id=record.id,
                language=normalized_language,
            )
        except Exception as exc:
            await self.meeting_record_repo.mark_failed(
                meeting_id=record.id,
                organization_id=organization_id,
                error_message=str(exc),
            )
            raise

    async def push_audio(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
        chunk: bytes,
    ) -> list[MeetingSessionEvent]:
        """Push one audio chunk into the active meeting session."""
        session = self._require_owned_session(
            sid=sid,
            user_id=user_id,
            meeting_id=meeting_id,
        )
        events = await self.session_manager.push_audio(
            sid=sid,
            user_id=user_id,
            meeting_id=meeting_id,
            chunk=chunk,
        )
        await self._sync_record_state_from_events(session=session, events=events)
        return events

    async def stop_session(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> list[MeetingSessionEvent]:
        """Stop the active meeting session."""
        session = self._require_owned_session(
            sid=sid,
            user_id=user_id,
            meeting_id=meeting_id,
        )
        await self.meeting_record_repo.mark_stopping(
            meeting_id=meeting_id,
            organization_id=session.organization_id,
        )

        try:
            events = await self.session_manager.stop_session(
                sid=sid,
                user_id=user_id,
                meeting_id=meeting_id,
            )
        except Exception as exc:
            await self.meeting_record_repo.mark_failed(
                meeting_id=meeting_id,
                organization_id=session.organization_id,
                error_message=str(exc),
            )
            raise

        await self._sync_record_state_from_events(session=session, events=events)
        return events

    async def handle_disconnect(self, sid: str) -> list[MeetingSessionEvent]:
        """Clean up an active meeting session on socket disconnect."""
        session = self.session_manager.get_session(sid)
        if session is None:
            return []

        await self.meeting_record_repo.mark_stopping(
            meeting_id=session.meeting_id,
            organization_id=session.organization_id,
        )
        try:
            events = await self.session_manager.handle_disconnect(sid)
        except Exception as exc:
            self.session_manager.discard_session(sid)
            await self.meeting_record_repo.mark_failed(
                meeting_id=session.meeting_id,
                organization_id=session.organization_id,
                error_message=str(exc),
            )
            return [session.fail(str(exc))]

        await self._sync_record_state_from_events(session=session, events=events)
        return events

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        """Collect pending provider-driven meeting events."""
        session = self.session_manager.get_session(sid)
        if session is None:
            return []

        events = await self.session_manager.collect_session_events(
            sid=sid,
            wait_for_first=wait_for_first,
            timeout_seconds=timeout_seconds,
        )
        await self._sync_record_state_from_events(session=session, events=events)
        return events

    async def _validate_org_membership(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> None:
        organization = await self.organization_repo.find_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(
                f"Organization '{organization_id}' was not found"
            )

        membership = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if membership is None:
            raise PermissionDeniedError(
                "User is not an active member of this organization"
            )

    def _require_owned_session(
        self,
        *,
        sid: str,
        user_id: str,
        meeting_id: str,
    ) -> MeetingSession:
        session = self.session_manager.get_session(sid)
        if session is None:
            raise MeetingRecordOwnershipError()
        session.assert_owner(sid=sid, user_id=user_id, meeting_id=meeting_id)
        return session

    async def _sync_record_state_from_events(
        self,
        *,
        session: MeetingSession,
        events: list[MeetingSessionEvent],
    ) -> None:
        if not events:
            return

        for event in events:
            if event.kind == MeetingSessionEventKind.COMPLETED:
                await self.meeting_record_repo.mark_completed(
                    meeting_id=session.meeting_id,
                    organization_id=session.organization_id,
                )
                return
            if event.kind == MeetingSessionEventKind.ERROR:
                await self.meeting_record_repo.mark_failed(
                    meeting_id=session.meeting_id,
                    organization_id=session.organization_id,
                    error_message=event.payload.error_message,
                )
                return

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = (language or "en").strip().lower()
        if normalized not in MEETING_SUPPORTED_LANGUAGES:
            raise UnsupportedMeetingLanguageError(
                f"Unsupported language '{normalized}'"
            )
        return normalized
