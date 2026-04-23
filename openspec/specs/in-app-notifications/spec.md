## ADDED Requirements

### Requirement: The system persists organization-scoped in-app notification inbox records
The system SHALL persist one durable in-app notification record for one
authenticated user within one organization scope whenever an application
feature creates a notification. Each record SHALL store notification identity,
user scope, organization scope, notification type, rendered title/body, unread
state, created timestamp, and navigation metadata including `target_type`,
`target_id`, and optional `link`.

#### Scenario: Create one unread notification record
- **WHEN** a backend feature creates a notification for a user in one
  organization scope
- **THEN** the system persists one notification record for that
  `user_id + organization_id`
- **AND** the record is stored with `is_read = false`
- **AND** the record includes its `type`, `title`, `body`, `target_type`, and
  `target_id`

#### Scenario: Notification includes route override
- **WHEN** a created notification requires a route with query parameters, tab
  selection, or anchor navigation
- **THEN** the persisted notification includes an optional `link`
- **AND** the system still preserves `target_type` and `target_id` for the same
  notification

### Requirement: The system exposes authenticated notification inbox reads
The system SHALL provide authenticated APIs that return the current user's
notification inbox for the current organization context. The inbox read surface
SHALL include a newest-first notification list and an unread count.

#### Scenario: List notifications for the current scope
- **WHEN** an authenticated user requests the notification list in one
  organization context
- **THEN** the system returns only notification records owned by that user in
  that organization
- **AND** the returned items are ordered newest-first by creation time

#### Scenario: Return unread count for the current scope
- **WHEN** an authenticated user requests the unread notification count in one
  organization context
- **THEN** the system returns the count of persisted notifications in that
  scope where `is_read = false`

### Requirement: The system supports idempotent read-state transitions
The system SHALL provide authenticated notification read-state mutations for
marking one notification as read and marking all notifications as read within
the current user and organization scope.

#### Scenario: Mark one notification as read
- **WHEN** an authenticated user marks one owned unread notification as read
- **THEN** the system updates that notification to `is_read = true`
- **AND** the system stores a non-null read timestamp for that notification

#### Scenario: Marking an already read notification is idempotent
- **WHEN** an authenticated user marks an already read owned notification as
  read again
- **THEN** the system does not create a new notification
- **AND** the notification remains in the read state

#### Scenario: Mark all notifications as read in the current scope
- **WHEN** an authenticated user requests mark-all-read in one organization
  context
- **THEN** the system marks all unread notifications in that scope as read
- **AND** the system does not change notifications outside that
  `user_id + organization_id` scope

### Requirement: The system emits realtime notification-created events to the owning user
The system SHALL emit a dedicated Socket.IO notification-created event to the
owning user room after persisting a new notification record. The emitted
payload SHALL include the created notification's frontend-facing summary data.

#### Scenario: Emit newly created notification to the user room
- **WHEN** the system creates a new notification record for a user
- **THEN** it emits one notification-created Socket.IO event to that user's
  room
- **AND** the event payload includes the created notification's `id`, `type`,
  `title`, `body`, read state, target metadata, and created timestamp

#### Scenario: Realtime payload preserves organization context
- **WHEN** the system emits a notification-created Socket.IO event for an
  organization-scoped notification
- **THEN** the outbound payload includes that notification's `organization_id`

### Requirement: The system suppresses duplicates only when a dedupe key is supplied
The system SHALL treat `dedupe_key` as an optional logical notification
identity within one `user_id + organization_id` scope. When a notification is
created with a `dedupe_key`, the system MUST NOT create a second notification
record for the same scope and dedupe key.

#### Scenario: Notification without dedupe key creates a new inbox item
- **WHEN** a backend feature creates a notification without a `dedupe_key`
- **THEN** the system persists a new notification record

#### Scenario: Matching dedupe key suppresses duplicate notification creation
- **WHEN** a backend feature creates a notification with a `dedupe_key`
- **AND** a notification already exists for the same `user_id`,
  `organization_id`, and `dedupe_key`
- **THEN** the system does not create a second notification record
- **AND** the system does not emit a second notification-created event for that
  duplicate attempt
