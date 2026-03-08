## Purpose

Define a consistent Socket.IO payload contract for organization-scoped business
events so frontend consumers can reliably associate real-time updates with the
active organization without changing existing routing semantics.

## Requirements

### Requirement: Organization-scoped socket payloads include `organization_id`
The system SHALL include a top-level `organization_id` field on every outbound Socket.IO business event emitted for an organization-scoped operation.

#### Scenario: Chat lifecycle event includes organization context
- **WHEN** the backend emits a chat lifecycle event for a request resolved under an organization context
- **THEN** the emitted payload includes that organization's `organization_id`

#### Scenario: TTS event includes organization context
- **WHEN** the backend emits a TTS started, chunk, completed, or error event for a request resolved under an organization context
- **THEN** the emitted payload includes that request's `organization_id`

#### Scenario: Sheet sync event includes organization context
- **WHEN** the backend emits a sheet sync started, completed, or failed event for a connection associated with an organization
- **THEN** the emitted payload includes that connection's `organization_id`

### Requirement: Asynchronous socket emitters preserve organization context
The system SHALL preserve resolved organization context when emitting socket events from asynchronous execution paths including background tasks, workflow nodes, and worker jobs.

#### Scenario: Chat workflow token event preserves request organization
- **WHEN** a chat request is accepted under an organization context and later emits token or tool events from workflow execution
- **THEN** each emitted payload includes the same `organization_id` that was resolved for the original request

#### Scenario: Queued worker event preserves queued organization
- **WHEN** a worker processes a queued organization-scoped job that emits socket events after the original HTTP request has completed
- **THEN** the worker-emitted payloads include the queued job's `organization_id`

### Requirement: Payload enrichment remains additive and backward compatible
The system SHALL preserve existing socket event names and existing domain payload fields while adding `organization_id` as an additive field.

#### Scenario: Existing payload fields remain available
- **WHEN** an existing socket event is enriched with `organization_id`
- **THEN** the payload still includes its prior domain-specific fields needed by current consumers

#### Scenario: Existing routing semantics remain unchanged
- **WHEN** the system emits an enriched socket event
- **THEN** delivery continues to use the current user-scoped socket routing model without requiring socket handshake changes for this capability
