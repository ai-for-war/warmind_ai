from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.common.exceptions import (
    AppException,
    InvalidMeetingUpdateError,
    MeetingNotFoundError,
    PermissionDeniedError,
)
from app.domain.models.meeting import Meeting, MeetingArchiveScope, MeetingStatus
from app.domain.models.meeting_note_chunk import MeetingNoteActionItem, MeetingNoteChunk
from app.domain.models.meeting_utterance import (
    MeetingUtterance,
    MeetingUtteranceMessage,
)
from app.domain.models.organization import OrganizationMember, OrganizationRole
from app.domain.schemas.meeting import (
    MeetingListQuery,
    MeetingPaginationParams,
    MeetingUpdateRequest,
)
from app.services.meeting.meeting_management_service import MeetingManagementService


def _service() -> tuple[
    MeetingManagementService,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    meeting_repo = AsyncMock()
    utterance_repo = AsyncMock()
    note_chunk_repo = AsyncMock()
    member_repo = AsyncMock()
    return (
        MeetingManagementService(
            meeting_repo=meeting_repo,
            utterance_repo=utterance_repo,
            note_chunk_repo=note_chunk_repo,
            member_repo=member_repo,
        ),
        meeting_repo,
        utterance_repo,
        note_chunk_repo,
        member_repo,
    )


def _membership() -> OrganizationMember:
    now = datetime.now(timezone.utc)
    return OrganizationMember(
        _id="membership-1",
        user_id="user-1",
        organization_id="org-1",
        role=OrganizationRole.USER,
        added_by="admin-1",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _meeting(*, meeting_id: str = "meeting-1") -> Meeting:
    now = datetime.now(timezone.utc)
    return Meeting(
        _id=meeting_id,
        organization_id="org-1",
        created_by="user-1",
        title="Weekly sync",
        source="google_meet",
        status=MeetingStatus.COMPLETED,
        language="en",
        stream_id="stream-1",
        started_at=now,
        ended_at=now,
        archived_at=None,
        archived_by=None,
    )


@pytest.mark.asyncio
async def test_list_meetings_enforces_active_membership() -> None:
    service, meeting_repo, _, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = None

    with pytest.raises(PermissionDeniedError):
        await service.list_meetings(
            user_id="user-1",
            organization_id="org-1",
            query=MeetingListQuery(),
        )

    meeting_repo.list_for_creator.assert_not_awaited()
    meeting_repo.count_for_creator.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_meetings_passes_filters_and_returns_paginated_summary() -> None:
    service, meeting_repo, _, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    meeting = _meeting()
    query = MeetingListQuery(
        scope=MeetingArchiveScope.ALL,
        status=MeetingStatus.COMPLETED,
        started_at_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at_to=datetime(2026, 1, 31, tzinfo=timezone.utc),
        q="sync",
        skip=5,
        limit=10,
    )
    meeting_repo.list_for_creator.return_value = [meeting]
    meeting_repo.count_for_creator.return_value = 17

    response = await service.list_meetings(
        user_id="user-1",
        organization_id=" org-1 ",
        query=query,
    )

    meeting_repo.list_for_creator.assert_awaited_once_with(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ALL,
        status=MeetingStatus.COMPLETED,
        started_at_from=query.started_at_from,
        started_at_to=query.started_at_to,
        q="sync",
        skip=5,
        limit=10,
    )
    meeting_repo.count_for_creator.assert_awaited_once_with(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ALL,
        status=MeetingStatus.COMPLETED,
        started_at_from=query.started_at_from,
        started_at_to=query.started_at_to,
        q="sync",
    )
    assert response.total == 17
    assert response.skip == 5
    assert response.limit == 10
    assert response.has_more is True
    assert [item.id for item in response.items] == [meeting.id]


@pytest.mark.asyncio
async def test_update_meeting_rejects_empty_patch_requests() -> None:
    service, meeting_repo, _, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    request = MeetingUpdateRequest.model_construct()

    with pytest.raises(InvalidMeetingUpdateError):
        await service.update_meeting(
            meeting_id="meeting-1",
            user_id="user-1",
            organization_id="org-1",
            request=request,
        )

    meeting_repo.update_metadata_for_creator.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_meeting_applies_archive_and_metadata_changes() -> None:
    service, meeting_repo, _, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    updated_meeting = _meeting()
    updated_meeting.title = "Renamed"
    updated_meeting.source = "zoom"
    updated_meeting.archived_at = datetime.now(timezone.utc)
    updated_meeting.archived_by = "user-1"
    meeting_repo.update_metadata_for_creator.return_value = updated_meeting

    response = await service.update_meeting(
        meeting_id="meeting-1",
        user_id="user-1",
        organization_id="org-1",
        request=MeetingUpdateRequest(title="Renamed", source="zoom", archived=True),
    )

    meeting_repo.update_metadata_for_creator.assert_awaited_once_with(
        meeting_id="meeting-1",
        organization_id="org-1",
        created_by="user-1",
        title="Renamed",
        source="zoom",
        archived=True,
        archived_by="user-1",
    )
    assert response.meeting.title == "Renamed"
    assert response.meeting.source == "zoom"
    assert response.meeting.archived_by == "user-1"


@pytest.mark.asyncio
async def test_list_meeting_utterances_hides_out_of_scope_meetings() -> None:
    service, meeting_repo, utterance_repo, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    meeting_repo.get_for_creator.return_value = None

    with pytest.raises(MeetingNotFoundError):
        await service.list_meeting_utterances(
            meeting_id="missing",
            user_id="user-1",
            organization_id="org-1",
            pagination=MeetingPaginationParams(skip=0, limit=20),
        )

    utterance_repo.list_by_meeting_paginated.assert_not_awaited()
    utterance_repo.count_by_meeting.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_meeting_note_chunks_returns_paginated_raw_chunks() -> None:
    service, meeting_repo, _, note_chunk_repo, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    meeting_repo.get_for_creator.return_value = _meeting()
    note_chunk = MeetingNoteChunk(
        _id="chunk-1",
        meeting_id="meeting-1",
        from_sequence=1,
        to_sequence=2,
        key_points=["First point"],
        decisions=[],
        action_items=[
            MeetingNoteActionItem(
                text="Send notes",
                owner_text="Alice",
                due_text="Tomorrow",
            )
        ],
        created_at=datetime.now(timezone.utc),
    )
    note_chunk_repo.list_by_meeting_paginated.return_value = [note_chunk]
    note_chunk_repo.count_by_meeting.return_value = 1

    response = await service.list_meeting_note_chunks(
        meeting_id="meeting-1",
        user_id="user-1",
        organization_id="org-1",
        pagination=MeetingPaginationParams(skip=0, limit=5),
    )

    note_chunk_repo.list_by_meeting_paginated.assert_awaited_once_with(
        meeting_id="meeting-1",
        skip=0,
        limit=5,
    )
    note_chunk_repo.count_by_meeting.assert_awaited_once_with(meeting_id="meeting-1")
    assert response.total == 1
    assert response.has_more is False
    assert response.items[0].from_sequence == 1
    assert response.items[0].action_items[0].text == "Send notes"


@pytest.mark.asyncio
async def test_list_meeting_utterances_returns_sequence_ordered_page() -> None:
    service, meeting_repo, utterance_repo, _, member_repo = _service()
    member_repo.find_by_user_and_org.return_value = _membership()
    meeting_repo.get_for_creator.return_value = _meeting()
    utterance = MeetingUtterance(
        _id="utterance-1",
        meeting_id="meeting-1",
        sequence=1,
        messages=[
            MeetingUtteranceMessage(
                speaker_index=0,
                speaker_label="speaker_1",
                text="Xin chao",
            )
        ],
        created_at=datetime.now(timezone.utc),
    )
    utterance_repo.list_by_meeting_paginated.return_value = [utterance]
    utterance_repo.count_by_meeting.return_value = 3

    response = await service.list_meeting_utterances(
        meeting_id="meeting-1",
        user_id="user-1",
        organization_id="org-1",
        pagination=MeetingPaginationParams(skip=1, limit=1),
    )

    utterance_repo.list_by_meeting_paginated.assert_awaited_once_with(
        meeting_id="meeting-1",
        skip=1,
        limit=1,
    )
    utterance_repo.count_by_meeting.assert_awaited_once_with(meeting_id="meeting-1")
    assert response.total == 3
    assert response.has_more is True
    assert response.items[0].sequence == 1


@pytest.mark.asyncio
async def test_list_meetings_requires_non_empty_organization_header() -> None:
    service, meeting_repo, _, _, member_repo = _service()

    with pytest.raises(AppException, match="X-Organization-ID header is required"):
        await service.list_meetings(
            user_id="user-1",
            organization_id="   ",
            query=MeetingListQuery(),
        )

    member_repo.find_by_user_and_org.assert_not_awaited()
    meeting_repo.list_for_creator.assert_not_awaited()
