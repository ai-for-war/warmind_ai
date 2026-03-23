## Why

The meeting transcription and incremental AI note flows already persist the
meeting session, canonical utterances, and additive note chunks, but the
product still lacks authenticated HTTP endpoints for users to browse and manage
their meeting history after or during a session.

The frontend now needs a stable meeting management API so a user can list only
their own meetings in the current organization, read the persisted transcript
and raw note chunks, and update meeting metadata or archive state without
depending on realtime events alone.

## What Changes

- Add authenticated HTTP endpoints for listing meetings created by the current
  user within the organization identified by `x-organization-id`
- Support list filtering by archive scope (`active`, `archived`, `all`),
  meeting lifecycle `status`, started-at date range, and title search query
- Support paginated retrieval of persisted meeting utterances and raw meeting
  note chunks for one meeting
- Add one meeting update endpoint that can rename a meeting, update its
  `source`, and toggle archive or restore state
- Add durable archive metadata on meetings so archived sessions can be hidden
  from the default list without deleting transcript or note history
- Enforce organization membership and creator ownership checks consistently
  across meeting list, detail subresources, and update operations

## Capabilities

### New Capabilities
- `meeting-management`: Browse and manage persisted meetings, meeting
  utterances, and raw meeting note chunks over authenticated HTTP APIs scoped
  to the current organization and meeting creator

### Modified Capabilities
None.

## Impact

- **New API surface**: add `GET /meetings`, `PATCH /meetings/{meeting_id}`,
  `GET /meetings/{meeting_id}/utterances`, and
  `GET /meetings/{meeting_id}/note-chunks`
- **Persistence updates**: extend the durable meeting record with archive
  metadata such as `archived_at` and `archived_by`
- **Repository and service changes**: add creator-scoped meeting filters,
  paginated utterance and note-chunk reads, and metadata update/archive
  operations
- **Schema updates**: add request and response schemas for meeting list,
  meeting updates, and paginated utterance/note-chunk results
- **Affected code**: `app/api/v1/meetings/`, `app/api/v1/router.py`,
  `app/common/service.py`, `app/domain/models/meeting.py`,
  `app/domain/schemas/meeting.py`, `app/repo/meeting_repo.py`,
  `app/repo/meeting_utterance_repo.py`, `app/repo/meeting_note_chunk_repo.py`,
  and `app/services/meeting/`
