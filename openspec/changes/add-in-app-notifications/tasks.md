## 1. Notification domain foundations

- [x] 1.1 Add notification domain models under `app/domain/models/` for one persisted inbox record with scope, target metadata, read state, optional actor metadata, and optional `dedupe_key`
- [x] 1.2 Add notification request and response schemas under `app/domain/schemas/` for unread count, notification list items, list responses, mark-one-read, and mark-all-read flows
- [x] 1.3 Add notification-specific error types for not-found or invalid ownership access when mutating read state

## 2. Persistence and indexing

- [x] 2.1 Add a notification repository under `app/repo/` for create, list-by-user-and-organization newest-first, unread count, find-owned-notification, mark-as-read, mark-all-as-read, and dedupe-key lookup behavior
- [x] 2.2 Create MongoDB indexes for newest-first scoped reads, unread-count queries, and optional dedupe-key uniqueness within one `user_id + organization_id` scope
- [x] 2.3 Wire the notification repository into `app/common/repo.py`

## 3. Notification service and realtime delivery

- [x] 3.1 Add a dedicated notification service under `app/services/` for create/list/count/read-state orchestration
- [x] 3.2 Implement notification normalization so creation persists `target_type`, `target_id`, optional `link`, unread defaults, and stable timestamps
- [x] 3.3 Implement optional dedupe-key suppression so duplicate create attempts reuse the existing logical notification instead of creating a second record
- [x] 3.4 Add a dedicated notification socket event constant and emit newly created notifications through the existing Socket.IO gateway or worker gateway after persistence succeeds
- [x] 3.5 Wire the notification service into `app/common/service.py`

## 4. Authenticated notification API surface

- [x] 4.1 Add an authenticated notification router under `app/api/v1/` for unread count, notification listing, mark-one-read, and mark-all-read endpoints
- [x] 4.2 Apply `get_current_active_user` and `get_current_organization_context` so all notification reads and mutations stay scoped to the authenticated user and organization
- [x] 4.3 Register the notification router in the v1 API aggregation

## 5. Producer integration and verification

- [ ] 5.1 Integrate at least one confirmed business flow with `NotificationService.create_notification(...)` so the inbox is exercised end to end
- [ ] 5.2 Add repository tests for scoped reads, unread counts, dedupe-key suppression, and read-state updates
- [ ] 5.3 Add service tests for ownership enforcement, default unread behavior, target/link persistence, and realtime emit behavior
- [ ] 5.4 Add API tests for list, unread count, mark-one-read, and mark-all-read behavior under organization-scoped authentication
