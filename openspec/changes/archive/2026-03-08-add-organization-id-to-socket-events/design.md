## Context

The current socket layer authenticates a connection once, stores only `user_id` in session state, and emits events to `user:{user_id}` rooms. This is sufficient for delivery, but it does not provide organization context in emitted payloads.

Organization context already exists in the HTTP layer through `X-Organization-ID` validation and is propagated into several business services. However, socket emitters are inconsistent:

- chat lifecycle events omit `organization_id`
- chat token/tool events emitted from workflow nodes do not currently carry organization context through workflow state
- TTS includes `organization_id` on the started event only, not on chunk/completed/error events
- sheet sync queue payloads already contain `organization_id`, but the worker task model and emitted events do not preserve it consistently

This is a cross-cutting contract change affecting multiple asynchronous paths. Frontend consumers need a single, additive payload rule without changing current socket authentication or room targeting.

## Goals / Non-Goals

**Goals:**
- Add a consistent top-level `organization_id` field to outbound Socket.IO business events for organization-scoped operations
- Preserve organization context across asynchronous boundaries such as background tasks, workflow state, and queued worker jobs
- Keep the change additive so existing frontend logic and socket event names remain usable
- Limit scope to payload enrichment only, with no transport or routing redesign

**Non-Goals:**
- Introducing org-aware rooms such as `org:{org_id}:user:{user_id}`
- Changing socket handshake authentication to require organization membership validation
- Redesigning payloads into a new envelope format such as `meta` + `data`
- Changing event delivery semantics beyond the additive `organization_id` field

## Decisions

### D1: Use top-level `organization_id` as the canonical socket payload field

**Decision**: Every outbound business socket event covered by this change will include a top-level `organization_id` field.

**Alternatives considered**:
- **`org_id`**: Shorter, but inconsistent with the existing HTTP, domain, and repository naming used throughout the codebase
- **Nested `meta.organization_id`**: Cleaner for future metadata expansion, but it would require broader frontend changes with no immediate benefit for this rollout

**Rationale**: The rest of the backend already uses `organization_id` as the canonical field name. Keeping the same name in socket payloads minimizes translation logic and makes the contract obvious to both backend and frontend teams.

### D2: Enrich payloads from business context, not from socket session state

**Decision**: `organization_id` will be sourced from the request, workflow, service, or queued task context that initiated the event, rather than from socket handshake state.

**Alternatives considered**:
- **Store active organization on socket connect**: This would require handshake changes and membership validation, which are out of scope for enrich-only delivery
- **Add organization claims to JWT**: This would blur the distinction between user identity and active organization context, and would complicate org switching

**Rationale**: The current socket transport is user-scoped only. Business context already knows the active organization in HTTP and job flows, so the safest low-impact approach is to propagate that context to the emit point and enrich there.

### D3: Preserve organization context explicitly across async boundaries

**Decision**: Async flows that emit socket events SHALL explicitly carry `organization_id` across their boundary objects:

- chat background task parameters and workflow state
- workflow node emit helpers or direct node payloads
- sheet sync queue task payloads and worker task model
- service methods that emit multiple events during a lifecycle

**Alternatives considered**:
- **Repository lookup at every emit point**: Possible in some places, but it adds avoidable database reads and hides missing propagation behind implicit recovery
- **Infer organization from socket room or user session**: Not possible with the current user-only routing model

**Rationale**: Explicit propagation makes the contract testable and prevents subtle bugs where an event emitter silently loses organization context mid-flow.

### D4: Keep socket routing unchanged for this change

**Decision**: Event delivery remains targeted to the existing user room model (`user:{user_id}`).

**Alternatives considered**:
- **Switch to org-aware rooms now**: Stronger isolation, but larger scope and a different architectural problem than payload enrichment

**Rationale**: The current requirement is to enrich payloads so frontend can associate events with the active organization. Keeping routing unchanged avoids unnecessary churn and keeps the change tightly scoped.

### D5: Maintain worker compatibility when queued tasks lack `organization_id`

**Decision**: Queue-aware emit paths SHOULD treat `organization_id` as part of the task contract, while tolerating older queued payloads by resolving organization context from the underlying domain record when practical.

**Alternatives considered**:
- **Hard-fail when queued payload is missing `organization_id`**: Simpler, but risky during deploys where old jobs may still be pending
- **Never carry `organization_id` in tasks and always look it up**: Reduces queue schema changes but adds unnecessary repository coupling and lookup overhead

**Rationale**: Explicit task propagation should become the steady-state contract, but compatibility handling reduces rollout risk for in-flight worker jobs.

## Risks / Trade-offs

- **[Socket routing remains user-scoped, not org-scoped]** -> Frontend can disambiguate events using `organization_id`, but this change does not prevent delivery to multiple active tabs for the same user. This limitation will be documented explicitly in the change.
- **[Cross-cutting emitters may be missed]** -> The change touches chat, TTS, and sheet sync code paths. Mitigation: audit every `emit_to_user(...)` and worker emit call, and verify payload shape for each event family.
- **[Legacy queued tasks may not include organization context]** -> Worker code may encounter payloads created before the new task schema is deployed. Mitigation: keep task parsing tolerant and recover organization context from the connection record when possible.
- **[Inconsistent payload updates could confuse frontend consumers]** -> If some events in a lifecycle include `organization_id` and others do not, frontend filtering becomes unreliable. Mitigation: treat event families as all-or-nothing during implementation and verification.

## Migration Plan

1. Add the new capability artifacts and implement the additive payload enrichment behind existing event names
2. Update chat, TTS, and sheet sync emitters so every covered event family emits `organization_id`
3. Update async propagation objects such as workflow state and worker task payloads to preserve organization context through the emit path
4. Verify frontend-facing socket contracts for each event family before rollout
5. **Rollback**: Remove `organization_id` enrichment and revert the propagation changes. No data migration is required because this change only affects transient event payloads and queue/task contracts

## Open Questions

- Should any internal-only or future system-wide socket events remain exempt from the `organization_id` requirement, or do we want to treat all frontend-consumed business events as organization-scoped by default?
