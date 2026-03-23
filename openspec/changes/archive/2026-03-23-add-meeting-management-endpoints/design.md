## Context

The codebase already has the durable data needed for meeting history:

- `meetings` store session metadata such as `organization_id`, `created_by`,
  `title`, `status`, `source`, `stream_id`, and timestamps
- `meeting_utterances` store canonical transcript utterances keyed by
  `meeting_id` and monotonic `sequence`
- `meeting_note_chunks` store additive structured note chunks keyed by meeting
  and utterance range

The current implementation is optimized for realtime meeting ingestion and
incremental AI note generation, but it does not yet expose an authenticated
HTTP API for browsing and managing this persisted history. The new change adds
that management surface without changing the existing realtime socket flow or
the raw note-chunk storage model.

This change is cross-cutting because it touches API routing, domain schemas,
meeting persistence, query patterns, and organization-scoped authorization.

## Goals / Non-Goals

**Goals:**
- Provide authenticated HTTP endpoints for listing the current user's meetings
  in the organization passed via `x-organization-id`
- Support meeting list filters for archive scope, lifecycle status, started-at
  range, and title search
- Support paginated reads for meeting utterances and raw meeting note chunks
- Support a single update endpoint that can mutate `title`, `source`, and
  archive state
- Keep archive state separate from lifecycle status so existing meeting
  semantics remain intact
- Preserve the current raw note-chunk model and avoid server-side merged note
  snapshots

**Non-Goals:**
- Add a separate `GET /meetings/{meeting_id}` detail endpoint in this change
- Replace `skip/limit` with cursor pagination in phase 1
- Broaden access from creator-scoped meetings to organization-wide meeting
  browsing
- Change the realtime meeting or meeting-note socket contracts
- Introduce hard delete or transcript/note data removal semantics

## Decisions

### D1: Add a dedicated HTTP meeting management service instead of overloading the live meeting session service

**Decision**: Keep the existing `MeetingService` focused on realtime socket
session lifecycle and add a separate HTTP-oriented service, e.g.
`MeetingManagementService`, for creator-scoped reads and updates.

**Alternatives considered:**
- **Extend the existing `MeetingService`**: fewer classes initially, but it
  mixes live socket session control with paginated HTTP query concerns
- **Put query logic directly in the router**: simpler wiring, but duplicates
  authorization and filtering logic and weakens testability

**Rationale**: The current `MeetingService` already encapsulates live session
ownership and membership checks for realtime flows. HTTP management adds a
different responsibility set: list filters, pagination, resource hiding, and
patch validation. Splitting those concerns keeps the code more maintainable and
avoids turning the live meeting service into a mixed transport abstraction.

### D2: Use `x-organization-id` as the sole organization context for HTTP meeting management

**Decision**: Meeting management routes stay under `/meetings` and derive
organization scope from the required `x-organization-id` header rather than
embedding organization identifiers into the URL path.

**Alternatives considered:**
- **Nest routes under `/organizations/{organization_id}/meetings`**: explicit
  in the URL, but redundant with the team's current request-scoped organization
  header model
- **Infer the organization implicitly from the user**: ambiguous when a user
  belongs to multiple organizations

**Rationale**: The user explicitly chose header-scoped organization context.
This aligns with the existing multi-tenant direction of the codebase and keeps
all meeting routes short while still requiring explicit organization selection.

### D3: Enforce both organization membership and creator ownership at the service layer

**Decision**: Every list, subresource read, and update first validates active
membership in the header organization, then constrains access to
`organization_id == x-organization-id` and `created_by == current_user.id`.
Out-of-scope meetings are treated as missing resources.

**Alternatives considered:**
- **Authorize only by organization membership**: simpler, but violates the
  confirmed requirement that users see only their own meetings
- **Check ownership only in routers**: possible, but spreads security logic
  across multiple endpoints and risks drift

**Rationale**: Creator ownership is a business rule, not just a presentation
concern. Centralizing it in the service layer makes list, update, utterance,
and note-chunk behavior consistent and reduces accidental data exposure.

### D4: Represent archive state as meeting metadata, not as a lifecycle status

**Decision**: Extend the durable meeting model with archive metadata such as
`archived_at` and `archived_by`, and keep `status` reserved for the realtime
lifecycle (`streaming`, `finalizing`, `completed`, `interrupted`, `failed`).

**Alternatives considered:**
- **Reuse `status` for archive semantics**: fewer fields, but it overloads one
  field with two independent concepts and breaks existing lifecycle queries
- **Create a separate archive collection**: more flexible, but unnecessary for
  a per-meeting boolean-like state

**Rationale**: Archive is a UI and management concern, while `status` is the
record of runtime session state. Keeping them separate avoids semantic drift
and lets filters combine archive scope with lifecycle status cleanly.

### D5: Use one PATCH endpoint for meeting metadata and archive-state mutations

**Decision**: Implement a single `PATCH /meetings/{meeting_id}` endpoint whose
request model supports optional `title`, `source`, and `archived`. At least one
field must be present. Missing fields mean "leave unchanged".

**Alternatives considered:**
- **Separate archive endpoint**: explicit, but the user chose a single endpoint
  and it adds extra client branching without meaningful domain separation
- **Use multiple PATCH endpoints by field type**: fine-grained, but increases
  route count for closely related meeting metadata mutations

**Rationale**: The mutable fields all belong to the same meeting management
surface. One PATCH endpoint is simpler for frontend integration and still keeps
server-side validation straightforward.

### D6: Keep phase-1 pagination as `skip/limit` with a shared envelope

**Decision**: `GET /meetings`, `GET /meetings/{meeting_id}/utterances`, and
`GET /meetings/{meeting_id}/note-chunks` all use `skip` and `limit` and return
an envelope containing `items` plus pagination metadata such as `skip`,
`limit`, `total`, and `has_more`.

**Alternatives considered:**
- **Cursor pagination**: more stable for append-heavy feeds, but the user chose
  `skip/limit` for phase 1 and it adds more stateful client behavior
- **Return raw arrays only**: simpler shape, but forces clients to reconstruct
  pagination metadata themselves

**Rationale**: The user explicitly selected `skip/limit`. A shared envelope
keeps the API consistent across resources and leaves room for a future cursor
upgrade behind a new contract if needed.

### D7: Define deterministic default ordering per resource

**Decision**:
- Meetings sort by `started_at desc`, then `id desc`
- Utterances sort by `sequence asc`
- Note chunks sort by `from_sequence asc`, then `to_sequence asc`

**Alternatives considered:**
- **Descending order for every resource**: convenient for "latest first", but
  worse for transcript and note playback because sequence-based rendering needs
  stable chronological order
- **Configurable sort order in phase 1**: flexible, but not needed for the
  confirmed UI scope

**Rationale**: The ordering follows the user's preference and the structure of
the data. Meetings are browsed as a history list, while utterances and note
chunks are timeline resources.

### D8: Return raw note chunks exactly as stored; do not build merged meeting notes

**Decision**: The note-chunk endpoint reads directly from
`meeting_note_chunks`, paginates by meeting, and returns stored additive chunks
without any server-side merge step.

**Alternatives considered:**
- **Return a merged note document**: easier for some clients, but contradicts
  the chosen note model and duplicates client merge logic already implied by
  the realtime contract
- **Return both raw and merged forms**: more flexible, but expands the API
  surface and introduces extra computation with no confirmed requirement

**Rationale**: The existing meeting note design is chunk-based both in
durability and realtime delivery. Keeping the HTTP read contract aligned with
that model avoids a second source of truth.

### D9: Repository methods should expose creator-scoped filtering and paginated reads explicitly

**Decision**: Extend repositories with explicit query methods rather than
building ad hoc Mongo queries inside services:

- `MeetingRepository.list_for_creator(...)`
- `MeetingRepository.count_for_creator(...)`
- `MeetingRepository.get_for_creator(...)`
- `MeetingRepository.update_metadata_for_creator(...)`
- `MeetingUtteranceRepository.list_by_meeting_paginated(...)`
- `MeetingUtteranceRepository.count_by_meeting(...)`
- `MeetingNoteChunkRepository.list_by_meeting_paginated(...)`
- `MeetingNoteChunkRepository.count_by_meeting(...)`

**Alternatives considered:**
- **Reuse existing `list_by_creator` and filter in memory**: simple, but it
  does not support the required archive scope, search, or date filters well
- **Let services compose raw collection queries directly**: flexible, but leaks
  persistence details upward and makes testing less clean

**Rationale**: The new HTTP endpoints introduce richer filtering than the
current meeting repo supports. Explicit repo methods keep Mongo query logic
centralized and make the new API deterministic and testable.

### D10: Phase-1 title search uses normalized case-insensitive matching, not full-text search

**Decision**: Implement `q` as case-insensitive title matching in the meeting
repository for phase 1. If performance later becomes an issue, evolve to a
dedicated text index or search layer.

**Alternatives considered:**
- **Require exact title matching**: too weak for a browsing UI
- **Add full-text indexing immediately**: more scalable, but heavier than the
  current scope requires

**Rationale**: The filter needs are clear, but nothing in the confirmed scope
justifies a more complex search subsystem yet. A simple query path keeps the
initial implementation small while preserving a future upgrade path.

## Risks / Trade-offs

**[Skip/limit pagination can drift when new meetings are inserted]** ->
Mitigation: keep ordering deterministic, return `total` and `has_more`, and
accept this phase-1 trade-off because the user explicitly chose `skip/limit`.

**[Title search via case-insensitive matching may not scale well for large datasets]** ->
Mitigation: scope all queries by organization and creator first, and reserve a
future indexed search upgrade if list volume grows.

**[Archive metadata on old meeting documents will be absent]** -> Mitigation:
treat missing `archived_at` as "not archived" and backfill lazily if needed.

**[A single PATCH endpoint can blur validation rules across fields]** ->
Mitigation: use a dedicated request schema that requires at least one mutable
field and normalizes each field independently.

**[Separating HTTP management from live meeting service adds one more service class]** ->
Mitigation: keep the new service focused on query/update orchestration only and
reuse existing repos and membership validation patterns.

## Migration Plan

1. Extend the durable meeting model and schema with archive metadata fields.
2. Add or update meeting repository methods for creator-scoped filtered lists,
   counts, resource lookups, and PATCH-style metadata updates.
3. Add paginated list and count methods for meeting utterances and meeting note
   chunks.
4. Introduce a dedicated meeting management service that:
   - validates active organization membership
   - enforces creator ownership
   - orchestrates list filters and pagination
   - applies meeting metadata and archive updates
5. Add new request and response schemas for:
   - meeting list filters and result envelope
   - meeting PATCH request and summary response
   - utterance list result envelope
   - note-chunk list result envelope
6. Add a new `/meetings` API router and register it in the v1 aggregate router.
7. Verify behavior for:
   - `scope=active|archived|all`
   - status/date/title filters
   - creator-scoped access only
   - PATCH updates for `title`, `source`, and `archived`
   - utterance ordering by `sequence`
   - note chunk ordering by `from_sequence`

**Rollback**
- remove the new router registration
- disable the meeting management service wiring
- leave stored archive metadata in place because it is additive and harmless to
  existing realtime meeting behavior

## Open Questions

- Should `PATCH /meetings/{meeting_id}` allow explicitly clearing `title` by
  sending `null`, or should it accept only non-empty replacement values?
- Does the frontend need `archived_at` in meeting list items immediately, or is
  archive scope filtering alone sufficient for phase 1?
