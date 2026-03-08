## 1. Shared Socket Payload Contract

- [x] 1.1 Audit all outbound Socket.IO business emitters in server and worker paths
- [x] 1.2 Standardize payload enrichment so covered events add top-level `organization_id` without removing existing fields
- [x] 1.3 Confirm event names, socket auth flow, and user-room routing remain unchanged

## 2. Chat Event Propagation

- [x] 2.1 Add `organization_id` to chat lifecycle payloads emitted from `ChatService`
- [x] 2.2 Extend orchestrator and chat workflow state/contracts to preserve `organization_id`
- [x] 2.3 Update chat token and tool event emitters to include `organization_id` on every emitted payload

## 3. TTS Event Propagation

- [ ] 3.1 Update TTS chunk, completed, and error payloads to include `organization_id`
- [ ] 3.2 Verify TTS started payload remains aligned with the shared contract

## 4. Sheet Sync Worker Propagation

- [ ] 4.1 Extend queued sheet sync task contracts to preserve `organization_id`
- [ ] 4.2 Update worker and crawler service emit paths so started, completed, and failed events include `organization_id`
- [ ] 4.3 Handle backward compatibility for older queued tasks that may not yet carry `organization_id`

## 5. Verification

- [ ] 5.1 Verify each chat event family emits `organization_id` consistently across started, token/tool, completed, and failed paths
- [ ] 5.2 Verify each TTS event family emits `organization_id` consistently across started, chunk, completed, and error paths
- [ ] 5.3 Verify each sheet sync worker event family emits `organization_id` consistently across started, completed, and failed paths
- [ ] 5.4 Review frontend-facing payload compatibility to ensure existing fields remain intact
