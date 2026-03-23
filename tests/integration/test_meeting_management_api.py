from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_active_user
from app.api.v1.meetings.router import router as meetings_router
from app.common.exceptions import AppException
from app.common.service import get_meeting_management_service
from app.domain.models.meeting import Meeting, MeetingArchiveScope, MeetingStatus
from app.domain.models.meeting_note_chunk import MeetingNoteActionItem, MeetingNoteChunk
from app.domain.models.meeting_utterance import (
    MeetingUtterance,
    MeetingUtteranceMessage,
)
from app.domain.models.organization import OrganizationMember, OrganizationRole
from app.domain.models.user import User, UserRole
from app.services.meeting.meeting_management_service import MeetingManagementService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1") -> User:
    now = _utc(2026, 1, 1)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _membership(*, user_id: str = "user-1", organization_id: str = "org-1") -> OrganizationMember:
    now = _utc(2026, 1, 1)
    return OrganizationMember(
        _id=f"membership-{user_id}-{organization_id}",
        user_id=user_id,
        organization_id=organization_id,
        role=OrganizationRole.USER,
        added_by="admin-1",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _meeting(
    *,
    meeting_id: str,
    created_by: str = "user-1",
    organization_id: str = "org-1",
    title: str | None = "Meeting",
    started_at: datetime | None = None,
    archived_at: datetime | None = None,
) -> Meeting:
    return Meeting(
        _id=meeting_id,
        organization_id=organization_id,
        created_by=created_by,
        title=title,
        source="google_meet",
        status=MeetingStatus.COMPLETED,
        language="en",
        stream_id=f"stream-{meeting_id}",
        started_at=started_at or _utc(2026, 1, 1),
        ended_at=None,
        error_message=None,
        archived_at=archived_at,
        archived_by="user-1" if archived_at is not None else None,
    )


def _utterance(*, meeting_id: str, sequence: int) -> MeetingUtterance:
    return MeetingUtterance(
        _id=f"utterance-{sequence}",
        meeting_id=meeting_id,
        sequence=sequence,
        messages=[
            MeetingUtteranceMessage(
                speaker_index=0,
                speaker_label="speaker_1",
                text=f"Utterance {sequence}",
            )
        ],
        created_at=_utc(2026, 1, 1, sequence),
    )


def _note_chunk(*, meeting_id: str, from_sequence: int, to_sequence: int) -> MeetingNoteChunk:
    return MeetingNoteChunk(
        _id=f"chunk-{from_sequence}-{to_sequence}",
        meeting_id=meeting_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        key_points=[f"Point {from_sequence}"],
        decisions=[],
        action_items=[
            MeetingNoteActionItem(
                text=f"Action {from_sequence}",
                owner_text="Alice",
                due_text="Soon",
            )
        ],
        created_at=_utc(2026, 1, 2, from_sequence),
    )


class _InMemoryMemberRepo:
    def __init__(self, memberships: list[OrganizationMember]) -> None:
        self._memberships = list(memberships)

    async def find_by_user_and_org(
        self,
        *,
        user_id: str,
        organization_id: str,
        is_active: bool | None = None,
    ) -> OrganizationMember | None:
        for membership in self._memberships:
            if membership.user_id != user_id:
                continue
            if membership.organization_id != organization_id:
                continue
            if is_active is not None and membership.is_active != is_active:
                continue
            return membership
        return None


class _InMemoryMeetingRepo:
    def __init__(self, meetings: list[Meeting]) -> None:
        self._meetings = list(meetings)

    def _filter(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str = MeetingArchiveScope.ACTIVE,
        status: MeetingStatus | str | None = None,
        started_at_from: datetime | None = None,
        started_at_to: datetime | None = None,
        q: str | None = None,
    ) -> list[Meeting]:
        normalized_scope = (
            scope.value if isinstance(scope, MeetingArchiveScope) else scope
        )
        normalized_status = (
            status.value if isinstance(status, MeetingStatus) else status
        )
        normalized_query = (q or "").strip().lower()

        items = [
            meeting
            for meeting in self._meetings
            if meeting.organization_id == organization_id
            and meeting.created_by == created_by
        ]
        if normalized_scope == MeetingArchiveScope.ACTIVE.value:
            items = [meeting for meeting in items if meeting.archived_at is None]
        elif normalized_scope == MeetingArchiveScope.ARCHIVED.value:
            items = [meeting for meeting in items if meeting.archived_at is not None]
        if normalized_status is not None:
            items = [meeting for meeting in items if meeting.status == normalized_status]
        if started_at_from is not None:
            items = [
                meeting for meeting in items if meeting.started_at >= started_at_from
            ]
        if started_at_to is not None:
            items = [meeting for meeting in items if meeting.started_at <= started_at_to]
        if normalized_query:
            items = [
                meeting
                for meeting in items
                if meeting.title is not None
                and normalized_query in meeting.title.lower()
            ]
        items.sort(key=lambda meeting: (meeting.started_at, meeting.id), reverse=True)
        return items

    async def list_for_creator(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str = MeetingArchiveScope.ACTIVE,
        status: MeetingStatus | str | None = None,
        started_at_from: datetime | None = None,
        started_at_to: datetime | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Meeting]:
        items = self._filter(
            organization_id=organization_id,
            created_by=created_by,
            scope=scope,
            status=status,
            started_at_from=started_at_from,
            started_at_to=started_at_to,
            q=q,
        )
        return items[skip : skip + limit]

    async def count_for_creator(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str = MeetingArchiveScope.ACTIVE,
        status: MeetingStatus | str | None = None,
        started_at_from: datetime | None = None,
        started_at_to: datetime | None = None,
        q: str | None = None,
    ) -> int:
        return len(
            self._filter(
                organization_id=organization_id,
                created_by=created_by,
                scope=scope,
                status=status,
                started_at_from=started_at_from,
                started_at_to=started_at_to,
                q=q,
            )
        )

    async def get_for_creator(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by: str,
    ) -> Meeting | None:
        for meeting in self._meetings:
            if meeting.id != meeting_id:
                continue
            if meeting.organization_id != organization_id:
                continue
            if meeting.created_by != created_by:
                continue
            return meeting
        return None

    async def update_metadata_for_creator(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by: str,
        title: str | None = None,
        source: str | None = None,
        archived: bool | None = None,
        archived_by: str | None = None,
        archived_at: datetime | None = None,
    ) -> Meeting | None:
        meeting = await self.get_for_creator(
            meeting_id=meeting_id,
            organization_id=organization_id,
            created_by=created_by,
        )
        if meeting is None:
            return None

        if title is not None:
            meeting.title = title
        if source is not None:
            meeting.source = source
        if archived is True:
            meeting.archived_at = archived_at or datetime.now(timezone.utc)
            meeting.archived_by = archived_by
        elif archived is False:
            meeting.archived_at = None
            meeting.archived_by = None
        return meeting


class _InMemoryUtteranceRepo:
    def __init__(self, utterances: list[MeetingUtterance]) -> None:
        self._utterances = list(utterances)

    async def list_by_meeting_paginated(
        self,
        *,
        meeting_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MeetingUtterance]:
        items = sorted(
            [utterance for utterance in self._utterances if utterance.meeting_id == meeting_id],
            key=lambda utterance: utterance.sequence,
        )
        return items[skip : skip + limit]

    async def count_by_meeting(self, *, meeting_id: str) -> int:
        return sum(1 for utterance in self._utterances if utterance.meeting_id == meeting_id)


class _InMemoryNoteChunkRepo:
    def __init__(self, note_chunks: list[MeetingNoteChunk]) -> None:
        self._note_chunks = list(note_chunks)

    async def list_by_meeting_paginated(
        self,
        *,
        meeting_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MeetingNoteChunk]:
        items = sorted(
            [chunk for chunk in self._note_chunks if chunk.meeting_id == meeting_id],
            key=lambda chunk: (chunk.from_sequence, chunk.to_sequence),
        )
        return items[skip : skip + limit]

    async def count_by_meeting(self, *, meeting_id: str) -> int:
        return sum(1 for chunk in self._note_chunks if chunk.meeting_id == meeting_id)


def _build_app(
    *,
    current_user: User,
    service: MeetingManagementService,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        _request: Request,
        exc: AppException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(meetings_router, prefix="/api/v1")

    async def _current_user_override() -> User:
        return current_user

    def _service_override() -> MeetingManagementService:
        return service

    app.dependency_overrides[get_current_active_user] = _current_user_override
    app.dependency_overrides[get_meeting_management_service] = _service_override
    return app


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.request(method, path, headers=headers, json=json)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_meeting_api_rejects_requests_without_active_membership() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo([]),
        utterance_repo=_InMemoryUtteranceRepo([]),
        note_chunk_repo=_InMemoryNoteChunkRepo([]),
        member_repo=_InMemoryMemberRepo([]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "GET",
        "/api/v1/meetings",
        headers={"X-Organization-ID": "org-1"},
    )

    assert status_code == 403
    assert payload["detail"] == (
        "Meeting management requires an active membership in the requested organization"
    )


@pytest.mark.asyncio
async def test_meeting_api_hides_out_of_scope_updates() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo(
            [_meeting(meeting_id="meeting-2", created_by="other-user")]
        ),
        utterance_repo=_InMemoryUtteranceRepo([]),
        note_chunk_repo=_InMemoryNoteChunkRepo([]),
        member_repo=_InMemoryMemberRepo([_membership()]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "PATCH",
        "/api/v1/meetings/meeting-2",
        headers={"X-Organization-ID": "org-1"},
        json={"title": "Renamed"},
    )

    assert status_code == 404
    assert payload["detail"] == "Meeting not found"


@pytest.mark.asyncio
async def test_meeting_api_hides_out_of_scope_subresources() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo(
            [_meeting(meeting_id="meeting-2", created_by="other-user")]
        ),
        utterance_repo=_InMemoryUtteranceRepo(
            [_utterance(meeting_id="meeting-2", sequence=1)]
        ),
        note_chunk_repo=_InMemoryNoteChunkRepo([]),
        member_repo=_InMemoryMemberRepo([_membership()]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "GET",
        "/api/v1/meetings/meeting-2/utterances?skip=0&limit=20",
        headers={"X-Organization-ID": "org-1"},
    )

    assert status_code == 404
    assert payload["detail"] == "Meeting not found"


@pytest.mark.asyncio
async def test_meeting_api_returns_paginated_meeting_list_in_default_order() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo(
            [
                _meeting(
                    meeting_id="meeting-1",
                    title="Older",
                    started_at=_utc(2026, 1, 10, 9),
                ),
                _meeting(
                    meeting_id="meeting-2",
                    title="Newest",
                    started_at=_utc(2026, 1, 12, 9),
                ),
                _meeting(
                    meeting_id="meeting-3",
                    title="Middle",
                    started_at=_utc(2026, 1, 11, 9),
                ),
            ]
        ),
        utterance_repo=_InMemoryUtteranceRepo([]),
        note_chunk_repo=_InMemoryNoteChunkRepo([]),
        member_repo=_InMemoryMemberRepo([_membership()]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "GET",
        "/api/v1/meetings?skip=1&limit=1",
        headers={"X-Organization-ID": "org-1"},
    )

    assert status_code == 200
    assert payload["total"] == 3
    assert payload["skip"] == 1
    assert payload["limit"] == 1
    assert payload["has_more"] is True
    assert [item["id"] for item in payload["items"]] == ["meeting-3"]


@pytest.mark.asyncio
async def test_meeting_api_returns_paginated_utterances_in_sequence_order() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo([_meeting(meeting_id="meeting-1")]),
        utterance_repo=_InMemoryUtteranceRepo(
            [
                _utterance(meeting_id="meeting-1", sequence=3),
                _utterance(meeting_id="meeting-1", sequence=1),
                _utterance(meeting_id="meeting-1", sequence=4),
                _utterance(meeting_id="meeting-1", sequence=2),
            ]
        ),
        note_chunk_repo=_InMemoryNoteChunkRepo([]),
        member_repo=_InMemoryMemberRepo([_membership()]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "GET",
        "/api/v1/meetings/meeting-1/utterances?skip=1&limit=2",
        headers={"X-Organization-ID": "org-1"},
    )

    assert status_code == 200
    assert payload["total"] == 4
    assert payload["skip"] == 1
    assert payload["limit"] == 2
    assert payload["has_more"] is True
    assert [item["sequence"] for item in payload["items"]] == [2, 3]


@pytest.mark.asyncio
async def test_meeting_api_returns_paginated_note_chunks_in_range_order() -> None:
    service = MeetingManagementService(
        meeting_repo=_InMemoryMeetingRepo([_meeting(meeting_id="meeting-1")]),
        utterance_repo=_InMemoryUtteranceRepo([]),
        note_chunk_repo=_InMemoryNoteChunkRepo(
            [
                _note_chunk(meeting_id="meeting-1", from_sequence=5, to_sequence=6),
                _note_chunk(meeting_id="meeting-1", from_sequence=1, to_sequence=2),
                _note_chunk(meeting_id="meeting-1", from_sequence=3, to_sequence=4),
            ]
        ),
        member_repo=_InMemoryMemberRepo([_membership()]),
    )
    app = _build_app(current_user=_user(), service=service)

    status_code, payload = await _request(
        app,
        "GET",
        "/api/v1/meetings/meeting-1/note-chunks?skip=0&limit=2",
        headers={"X-Organization-ID": "org-1"},
    )

    assert status_code == 200
    assert payload["total"] == 3
    assert payload["skip"] == 0
    assert payload["limit"] == 2
    assert payload["has_more"] is True
    assert [item["from_sequence"] for item in payload["items"]] == [1, 3]
