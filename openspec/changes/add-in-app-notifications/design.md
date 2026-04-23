## Context

The backend already has the core building blocks needed for a notification
feature:

- FastAPI routers aggregated under `app/api/v1/router.py`
- authenticated request handling with `current user + organization context`
- MongoDB-backed repositories and typed Pydantic domain models
- singleton repo/service factories in `app/common/repo.py` and
  `app/common/service.py`
- a shared Socket.IO gateway with Redis-backed cross-process emit support in
  `app/socket_gateway/`

The product now needs a first-class in-app notification inbox for web clients.
The target interaction is a bell icon with unread badge, a recent notification
list, and direct navigation to the affected page when the user clicks an item.
The user explicitly chose realtime delivery over frontend polling, so the
backend must persist notifications and also emit newly created notifications
through the existing Socket.IO infrastructure.

For this repo, the least risky v1 is to align notifications with the existing
request model and scope records by `user + organization`. That keeps behavior
consistent with the rest of the application and fits the current socket payload
contract that already enriches organization-scoped events with
`organization_id`.

## Goals / Non-Goals

**Goals:**
- Add a durable in-app notification inbox stored in MongoDB
- Expose authenticated APIs for unread count, notification listing, and
  read-state transitions
- Emit realtime notification-created events over the existing Socket.IO user
  room model
- Standardize notification creation behind one service so feature modules do
  not hand-roll persistence and emit behavior
- Preserve stable deep-link semantics by storing target references and optional
  route overrides
- Support optional deduplication for retry-prone or grouped notification use
  cases

**Non-Goals:**
- Add push notifications, email delivery, quiet hours, or user preference
  management in v1
- Build a generic queue- or broker-based notification platform before the
  product proves it is needed
- Add dismiss/archive/delete behavior for end users in v1
- Support cross-organization or organization-agnostic global notifications in
  v1
- Add notification grouping digests beyond duplicate suppression through
  `dedupe_key`

## Decisions

### D1: Model one notification inbox record as a single MongoDB document

**Decision**: Introduce one `notifications` collection with one document per
user-visible inbox item. Recommended document shape:

```json
{
  "_id": "notification_id",
  "user_id": "user-1",
  "organization_id": "org-1",
  "type": "task_assigned",
  "title": "You were assigned a task",
  "body": "Open the task to review details",
  "target_type": "task",
  "target_id": "task-42",
  "link": "/tasks/task-42?tab=activity",
  "actor_id": "user-2",
  "dedupe_key": "task_assigned:user-1:org-1:task-42",
  "is_read": false,
  "read_at": null,
  "created_at": "2026-04-23T08:00:00Z",
  "updated_at": "2026-04-23T08:00:00Z",
  "metadata": {
    "actor_name": "Alex"
  }
}
```

Recommended indexes:

- `(user_id, organization_id, created_at desc)`
- `(user_id, organization_id, is_read, created_at desc)`
- partial unique `(user_id, organization_id, dedupe_key)` when `dedupe_key`
  exists

**Rationale**:
- one inbox item maps naturally to one stored document and one UI row
- newest-first listing and unread counting stay simple
- `target_type + target_id` preserve semantic identity even if frontend routes
  change later
- `link` remains available for deep-link cases that need tabs, query params, or
  anchors

**Alternatives considered:**
- **Unread counter table + notification table**: rejected for v1 because it
  adds write complexity and counter drift risk before there is evidence that
  `count_documents` on indexed fields is insufficient
- **Store only a URL link**: rejected because route-only storage is brittle and
  loses object semantics that are useful for future authorization and routing

### D2: Keep the MongoDB inbox as the source of truth and treat Socket.IO as a delivery signal

**Decision**: Notification creation first writes to MongoDB, then emits a
`notification:created` Socket.IO event to the owning user room. The event is a
realtime signal only; API reads remain the authoritative source of state.

**Rationale**:
- reconnects, browser refreshes, and missed websocket events are unavoidable
- persisting first guarantees the inbox remains recoverable even if event emit
  fails
- this matches the project's current Redis-backed worker emit pattern and
  avoids inventing a second source of truth

**Alternatives considered:**
- **WebSocket event as the primary state source**: rejected because it is too
  fragile across reconnects and multi-tab behavior
- **Frontend polling only**: rejected because the chosen product direction is
  realtime updates without polling

### D3: Add one dedicated notification service that owns both creation and read APIs

**Decision**: Introduce a `NotificationService` with methods for:

- `create_notification(...)`
- `list_notifications(...)`
- `get_unread_count(...)`
- `mark_as_read(...)`
- `mark_all_as_read(...)`

Feature modules call the same service to create notifications. HTTP routers use
the same service for user-facing reads and read-state transitions.

**Rationale**:
- keeps duplicate suppression, normalization, and emit behavior in one place
- prevents business modules from drifting into inconsistent notification payload
  shapes
- aligns with the service/repository layering already used throughout the repo

**Alternatives considered:**
- **Inline notification writes in each feature service**: rejected because it
  would duplicate dedupe logic, payload shaping, and realtime emission paths

### D4: Scope notification data and APIs by `current user + organization`

**Decision**: All v1 notification reads and writes are scoped to the
authenticated user and current organization context. The notification routers
follow the existing authenticated API pattern used elsewhere in the project.

Recommended endpoints:

- `GET /notifications/unread-count`
- `GET /notifications`
- `POST /notifications/{notification_id}/read`
- `POST /notifications/read-all`

**Rationale**:
- matches the repo's existing multi-tenant request model
- keeps socket payload organization enrichment compatible with the existing
  contract
- avoids undefined behavior around whether the bell icon should merge
  notifications across organizations

**Alternatives considered:**
- **Global per-user inbox across all organizations**: rejected for v1 because
  the frontend context and authorization semantics are not yet defined for that
  view

### D5: Use optional `dedupe_key` only for explicit duplicate-suppression cases

**Decision**: `dedupe_key` is nullable and not required for every notification.
When supplied, the service treats `user_id + organization_id + dedupe_key` as
the identity of one logical notification and MUST NOT create a second record
for the same logical item.

Recommended v1 behavior:

- if `dedupe_key` is absent, always create a new notification
- if `dedupe_key` exists and a matching record already exists, return the
  existing notification without creating another row or emitting another
  created event

**Rationale**:
- covers retry-safe creation and long-lived state notifications without
  accidentally collapsing distinct events
- keeps the first implementation deterministic and simple

**Alternatives considered:**
- **Always dedupe by `type + target`**: rejected because many event streams
  legitimately need multiple notifications for the same target over time
- **Auto-group and mutate existing rows in v1**: rejected because grouped copy
  and counters are a product decision, not just an implementation detail

### D6: Return notification summaries directly from the API and realtime event payload

**Decision**: The read APIs and `notification:created` event will expose the
same frontend-facing summary shape:

- `id`
- `type`
- `title`
- `body`
- `target_type`
- `target_id`
- `link`
- `is_read`
- `created_at`
- optional `actor_id`
- optional `metadata`

The realtime event payload may omit an authoritative unread count. The
frontend can increment locally on new events and recover with count/list API
reads on reconnect or page refresh.

**Rationale**:
- one stable summary contract reduces frontend branching
- avoids coupling websocket events to extra count queries at write time
- keeps API and realtime consumers aligned

**Alternatives considered:**
- **Emit only notification IDs and force refetch on every event**: rejected
  because it adds avoidable latency and defeats much of the realtime UX value
- **Emit authoritative unread count on every event**: rejected for v1 because
  it adds extra write-path work while the inbox API already provides recovery

## Risks / Trade-offs

**[Socket emit fails after the DB insert succeeds]** -> Mitigation: treat the
inbox record as the source of truth and rely on later API reads or reconnect
flows to heal the UI state.

**[Unread count queries grow expensive as volume increases]** -> Mitigation:
add the compound unread index from day one and defer denormalized counters until
real query metrics justify the added complexity.

**[A poorly chosen dedupe key suppresses legitimate notifications]** ->
Mitigation: keep `dedupe_key` opt-in and document that only explicit retry-safe
or stateful cases should use it.

**[Future product needs global notifications across organizations]** ->
Mitigation: keep `organization_id` explicit in the data model so later global
support can be added intentionally instead of leaking into v1 implicitly.

## Migration Plan

1. Add notification domain models and request/response schemas.
2. Add a notification repository with indexes for newest-first reads, unread
   counts, and optional dedupe-key uniqueness.
3. Add a notification service for create/list/count/read-state behavior.
4. Add authenticated notification API routes and register them in the v1 router.
5. Add one notification socket event constant and emit helper usage through the
   existing Socket.IO gateway or worker gateway.
6. Integrate one or more initial business flows with `NotificationService` so
   the feature is exercised end to end.
7. Add repository, service, API, and socket-oriented tests.

**Rollback**

- remove the notification router from the v1 API aggregation
- stop creating notifications from business modules
- disable frontend notification consumption
- optionally drop the `notifications` collection and indexes if full rollback is
  required

## Open Questions

- Which concrete business events should be wired first for end-to-end
  notification creation in the initial implementation, so the first release has
  clear value instead of an empty inbox?
