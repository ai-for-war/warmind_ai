## Why

The platform is moving toward organization-scoped SaaS workflows, but outbound Socket.IO payloads are still inconsistent about carrying organization context. Frontend consumers need a reliable `organization_id` on socket events so they can associate real-time updates with the active organization without changing the current socket routing model.

## What Changes

- Add a top-level `organization_id` field to outbound business Socket.IO payloads for organization-scoped flows
- Standardize organization context propagation across chat, TTS, and sheet sync event emitters, including background tasks, workflow nodes, and worker jobs
- Keep existing socket event names, user-targeted room routing, and authentication behavior unchanged for this rollout
- Preserve existing payload fields so the contract change remains additive and backward compatible for current consumers

## Capabilities

### New Capabilities
- `socket-event-organization-context`: Ensure outbound Socket.IO business events consistently include `organization_id` and preserve that context across asynchronous execution boundaries

### Modified Capabilities
- None

## Impact

- **Affected systems**: shared Socket.IO gateway, chat service/workflows, TTS streaming service, sheet sync worker/service
- **Affected code**: `app/socket_gateway/`, `app/services/ai/chat_service.py`, `app/graphs/workflows/**`, `app/services/tts/tts_service.py`, `app/services/sheet_crawler/crawler_service.py`, `app/workers/sheet_sync_worker.py`
- **API impact**: additive payload contract update for frontend socket consumers; no new REST endpoints and no socket handshake changes
- **Dependencies**: no new external dependencies expected
