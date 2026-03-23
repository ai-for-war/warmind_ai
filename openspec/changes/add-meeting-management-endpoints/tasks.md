## 1. Meeting Persistence And Schemas

- [x] 1.1 Extend the durable `meeting` model and schema with archive metadata fields such as `archived_at` and `archived_by`
- [x] 1.2 Add meeting management request and response schemas for list filters, `scope=active|archived|all`, shared pagination envelopes, and `PATCH /meetings/{meeting_id}`
- [x] 1.3 Add meeting repository methods for creator-scoped list filters, counts, owned meeting lookup, and metadata/archive updates
- [x] 1.4 Add paginated list and count methods for `meeting_utterances` and `meeting_note_chunks`

## 2. Meeting Management Service

- [ ] 2.1 Add a dedicated `MeetingManagementService` that validates active organization membership from `x-organization-id`
- [ ] 2.2 Implement creator-scoped meeting listing with archive scope, lifecycle status, started-at range, title search, and default `started_at desc` ordering
- [ ] 2.3 Implement owned meeting update logic for `title`, `source`, and `archived`, including rejection of empty PATCH requests
- [ ] 2.4 Implement paginated owned-meeting reads for utterances ordered by `sequence asc` and note chunks ordered by `from_sequence asc`

## 3. HTTP API And Service Wiring

- [ ] 3.1 Wire the new meeting management service and supporting repositories into the shared service factory/container
- [ ] 3.2 Add the `/meetings` API router with `GET /meetings`, `PATCH /meetings/{meeting_id}`, `GET /meetings/{meeting_id}/utterances`, and `GET /meetings/{meeting_id}/note-chunks`
- [ ] 3.3 Register the meeting router in the v1 API aggregate router and ensure request handling uses the authenticated user plus `x-organization-id`

## 4. Verification

- [ ] 4.1 Add repository-level tests for creator-scoped meeting filters, archive scope handling, title search, and metadata/archive updates
- [ ] 4.2 Add service or router tests for membership enforcement, creator ownership enforcement, and hidden out-of-scope meeting resources
- [ ] 4.3 Add API tests for pagination envelopes and default ordering of meetings, utterances, and note chunks
- [ ] 4.4 Run targeted verification for the new meeting management endpoints and confirm the existing realtime meeting and note flows remain unaffected
