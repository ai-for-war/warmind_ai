"""Application service entry point for live meeting transcription flows."""

from __future__ import annotations

from app.common.exceptions import PermissionDeniedError
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.services.meeting.session import MeetingSession, MeetingSessionEvent
from app.services.meeting.session_manager import MeetingSessionManager


class MeetingService:
    """Coordinate meeting session lifecycle with authenticated org access."""

    def __init__(
        self,
        *,
        session_manager: MeetingSessionManager,
        member_repo: OrganizationMemberRepository,
    ) -> None:
        self.session_manager = session_manager
        self.member_repo = member_repo

    def get_session(self, sid: str) -> MeetingSession | None:
        """Return the live meeting session for a socket, if any."""
        return self.session_manager.get_session(sid)

    async def start_session(
        self,
        *,
        sid: str,
        user_id: str,
        organization_id: str,
        stream_id: str,
        title: str | None,
        language: str | None,
        source: str = "google_meet",
    ) -> list[MeetingSessionEvent]:
        """Start one live meeting session for an authenticated organization."""
        await self._ensure_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        return await self.session_manager.start_session(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            title=title,
            language=language,
            source=source,
        )

    async def push_audio(
        self,
        *,
        sid: str,
        stream_id: str,
        chunk: bytes,
    ) -> list[MeetingSessionEvent]:
        """Push one audio chunk into the active meeting session."""
        return await self.session_manager.push_audio(
            sid=sid,
            stream_id=stream_id,
            chunk=chunk,
        )

    async def finalize_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[MeetingSessionEvent]:
        """Finalize the active meeting session."""
        return await self.session_manager.finalize_session(
            sid=sid,
            stream_id=stream_id,
        )

    async def stop_session(
        self,
        *,
        sid: str,
        stream_id: str,
    ) -> list[MeetingSessionEvent]:
        """Stop the active meeting session via the clean finalize path."""
        return await self.session_manager.stop_session(
            sid=sid,
            stream_id=stream_id,
        )

    async def handle_disconnect(self, sid: str) -> list[MeetingSessionEvent]:
        """Clean up an active meeting session on socket disconnect."""
        return await self.session_manager.handle_disconnect(sid)

    async def collect_session_events(
        self,
        *,
        sid: str,
        wait_for_first: bool = False,
        timeout_seconds: float | None = None,
    ) -> list[MeetingSessionEvent]:
        """Collect pending provider-driven meeting session events."""
        return await self.session_manager.collect_session_events(
            sid=sid,
            wait_for_first=wait_for_first,
            timeout_seconds=timeout_seconds,
        )

    async def _ensure_active_membership(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> None:
        membership = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if membership is None:
            raise PermissionDeniedError(
                "Meeting transcription requires an active membership in the requested organization"
            )
