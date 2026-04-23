## Why

The product currently has no first-class notification inbox, so users can miss
important state changes unless they manually revisit each screen. This now
blocks a standard application pattern: a bell icon with unread count, a recent
notification list, and direct navigation to the affected page when something
important happens.

## What Changes

- Add an authenticated in-app notification capability for web clients with a
  notification inbox as the source of truth
- Persist per-user notification records with unread/read state, notification
  type, message content, target reference, optional deep link, and optional
  deduplication key
- Expose read APIs for unread count, latest/history notification listing, and
  read-state updates including mark-one-read and mark-all-read behavior
- Emit realtime Socket.IO notification-created events to the owning user so the
  frontend can update the bell badge and inbox without polling
- Standardize notification payload semantics so backend features can create
  notifications through one service instead of hand-rolling per-feature logic
- Establish a notification model that can later extend to push or email
  delivery without changing the in-app inbox contract

## Capabilities

### New Capabilities
- `in-app-notifications`: manage authenticated user notification inbox data,
  unread counts, read-state transitions, deep-link targets, and realtime
  Socket.IO delivery for newly created notifications

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds authenticated notification endpoints for unread
  count, notification list/history, mark-one-read, and mark-all-read flows
- **Affected realtime surface**: adds a dedicated Socket.IO notification event
  for new notification delivery to the owning user room
- **Affected code**: introduces notification domain models, schemas,
  repositories, service-layer orchestration, and API/router wiring
- **Data layer**: adds persistent notification storage plus indexes for
  per-user newest-first reads and unread count efficiency
- **Cross-cutting behavior**: creates one notification service that other
  business modules can call when they need to notify a user
- **Future extensibility**: keeps the in-app inbox as the authoritative source
  of truth while leaving room for later push/email channel fan-out
