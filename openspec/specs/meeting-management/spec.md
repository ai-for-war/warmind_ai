## Purpose

Define the authenticated meeting management capability that lets a user browse,
filter, update, and archive their own persisted meetings within the
organization selected by `x-organization-id`, including transcript utterances
and raw note chunks.

## Requirements

### Requirement: Meeting management APIs are authenticated and scoped to the current organization and meeting creator
The system SHALL provide authenticated HTTP APIs for meeting management. Every
meeting management request MUST require an active membership in the
organization identified by `x-organization-id`, and the system MUST expose
only meetings whose `created_by` matches the current authenticated user.

#### Scenario: List meetings for the current creator in the current organization
- **WHEN** an authenticated user with active membership calls the meeting management API with a valid `x-organization-id`
- **THEN** the system returns only meetings whose `organization_id` matches that header
- **AND** the system returns only meetings whose `created_by` matches the current authenticated user

#### Scenario: Reject access without valid organization membership
- **WHEN** a request omits `x-organization-id` or the current user does not have an active membership in that organization
- **THEN** the system MUST reject the meeting management request

#### Scenario: Hide a meeting that is outside creator or organization scope
- **WHEN** an authenticated user requests a meeting, utterance list, note-chunk list, or update for a meeting outside their creator scope or organization scope
- **THEN** the system MUST NOT expose that meeting resource

### Requirement: Users can list their meetings with archive scope, filters, and pagination
The system SHALL provide a paginated meeting list endpoint for the current
creator within the current organization. The endpoint MUST support archive
scope filtering with `active`, `archived`, and `all`, and MUST support filters
for meeting lifecycle `status`, started-at date range, and title search query.

#### Scenario: List active meetings by default
- **WHEN** the user calls the meeting list endpoint without explicitly setting an archive scope
- **THEN** the system returns only meetings that are not archived

#### Scenario: List archived meetings only
- **WHEN** the user calls the meeting list endpoint with archive scope `archived`
- **THEN** the system returns only meetings that are archived

#### Scenario: List all meetings regardless of archive state
- **WHEN** the user calls the meeting list endpoint with archive scope `all`
- **THEN** the system returns both archived and non-archived meetings that remain in the user's creator scope

#### Scenario: Filter meetings by lifecycle status, started-at range, and title search
- **WHEN** the user supplies one or more of `status`, started-at date range, or title search query
- **THEN** the system applies all supplied filters together before pagination

#### Scenario: Paginate the meeting list with skip and limit
- **WHEN** the user supplies `skip` and `limit`
- **THEN** the system returns that slice of the filtered meeting list
- **AND** the system orders the list by most recent `started_at` first before applying pagination

### Requirement: Meeting list responses expose summary metadata needed by the frontend
The system SHALL return meeting summary data that is sufficient for the
frontend meeting list. Each meeting summary MUST include `id`, `title`,
`status`, `started_at`, `ended_at`, and `source`.

#### Scenario: Return summary fields for one meeting list item
- **WHEN** the meeting list endpoint returns a meeting
- **THEN** that meeting item includes `id`, `title`, `status`, `started_at`, `ended_at`, and `source`

### Requirement: One meeting update endpoint manages title, source, and archive state
The system SHALL provide a single meeting update endpoint that can update a
meeting title, update the persisted `source`, and toggle archive state for one
meeting. The request MUST include at least one of `title`, `source`, or
`archived`.

#### Scenario: Rename a meeting
- **WHEN** the user updates a meeting with a new `title`
- **THEN** the system persists the new title for that meeting
- **AND** the system leaves other mutable fields unchanged unless they are also included in the request

#### Scenario: Update a meeting source
- **WHEN** the user updates a meeting with a new `source`
- **THEN** the system persists the normalized source value for that meeting

#### Scenario: Archive a meeting
- **WHEN** the user updates a meeting with `archived=true`
- **THEN** the system marks that meeting as archived without deleting its persisted utterances or note chunks

#### Scenario: Restore a meeting
- **WHEN** the user updates a meeting with `archived=false`
- **THEN** the system clears the archive state for that meeting without altering its persisted utterances or note chunks

#### Scenario: Reject an empty meeting update
- **WHEN** the user calls the meeting update endpoint without providing any of `title`, `source`, or `archived`
- **THEN** the system MUST reject the request

### Requirement: Meeting archive state is independent from meeting lifecycle status
The system SHALL keep archive state separate from the durable meeting lifecycle
status. Archiving a meeting MUST NOT change whether the meeting is
`streaming`, `completed`, `interrupted`, or `failed`.

#### Scenario: Preserve lifecycle status when archiving
- **WHEN** the user archives a completed or interrupted meeting
- **THEN** the system keeps the existing meeting lifecycle status unchanged

### Requirement: Users can list persisted meeting utterances in meeting sequence order
The system SHALL provide a paginated endpoint that returns the persisted
canonical utterances for one meeting. The utterance list MUST be ordered by
ascending meeting-local `sequence`.

#### Scenario: Return paginated utterances for one owned meeting
- **WHEN** the user requests utterances for a meeting in their creator scope
- **THEN** the system returns persisted utterances only for that meeting
- **AND** the system paginates the results using `skip` and `limit`

#### Scenario: Preserve canonical utterance ordering
- **WHEN** the utterance list endpoint returns multiple utterances
- **THEN** the system returns them in ascending `sequence` order

### Requirement: Users can list raw persisted meeting note chunks without server-side merging
The system SHALL provide a paginated endpoint that returns the raw persisted
meeting note chunks for one meeting. The endpoint MUST return additive note
chunks as stored durably and MUST NOT require the backend to generate a merged
meeting note snapshot.

#### Scenario: Return raw note chunks for one owned meeting
- **WHEN** the user requests note chunks for a meeting in their creator scope
- **THEN** the system returns persisted note chunks only for that meeting
- **AND** the system paginates the results using `skip` and `limit`

#### Scenario: Preserve note chunk range ordering
- **WHEN** the note chunk list endpoint returns multiple note chunks
- **THEN** the system returns them in ascending `from_sequence` order

#### Scenario: Do not merge note chunks in the response
- **WHEN** a meeting has multiple persisted note chunks
- **THEN** the system returns those raw note chunks individually
- **AND** the system MUST NOT replace them with a server-generated merged note document
