# Phase 1: Meeting Domain Foundation - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers a dedicated AI record meeting lifecycle that users can start and stop from the frontend with organization-aware access control and a selected transcription language. The public contract must be meeting-specific rather than interview-specific, while transcript review, summary generation, and meeting history remain outside this phase.

</domain>

<decisions>
## Implementation Decisions

### Meeting start contract
- The public realtime start contract should be meeting-native, with `meeting_record:start` as the user-facing start event.
- Starting over the realtime meeting contract should create the meeting session directly; Phase 1 does not require a separate REST create step before streaming.
- The frontend should work with a meeting-native identifier only. Any linked internal conversation or transcript identifiers stay backend-internal.
- Start success should return a full ready payload rather than a minimal acknowledgment.
- Only one active meeting session is allowed per socket. A second start request must be rejected until the active meeting is stopped.

### Organization scoping and access
- The frontend must send an explicit `organization_id` when starting a meeting.
- If the supplied `organization_id` is invalid or the user is not allowed to use it, the backend must reject the start request immediately and create no meeting shell.
- The meeting session binds organization context at start time. The backend may echo `organization_id` back in emitted client events, but the client should not need to resend org scope on every audio packet.
- Only the user who started the meeting can stop that active meeting in Phase 1.

### Stop and lifecycle semantics
- Stop means "finalize then finish cleanly", not "cut the stream immediately".
- After a stop request, the client should first receive a stopping/in-progress event and only receive completed once finalize has finished.
- If the client disconnects unexpectedly during an active meeting, the backend should try to finalize and close the meeting cleanly before falling back to failure.
- A completed meeting is terminal. Resuming streaming must create a new meeting rather than reopening the completed one.

### Language policy
- Language may be omitted at start time; if omitted, the backend should default to `en`.
- Phase 1 may allow free-form language code input in the UI, but the backend must validate the submitted value against a supported allowlist before starting the meeting.
- A meeting uses one selected language for its full lifecycle. Mixed-language speech is acceptable operationally, but Phase 1 should not switch languages mid-session.

### Claude's Discretion
- Exact ready/stopping/completed event names after `meeting_record:start`
- Whether the client waits for ready before sending audio or buffers locally first
- The exact allowlist source and how supported language codes are exposed in UI copy
- Internal linkage between the meeting-native record and any reusable conversation/transcript storage primitives

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product scope and requirements
- `.planning/ROADMAP.md` - Phase 1 goal, success criteria, and plan boundaries for Meeting Domain Foundation
- `.planning/REQUIREMENTS.md` - `MEET-01`, `MEET-02`, and `MEET-03` define the required start, stop, and language behavior
- `.planning/PROJECT.md` - product boundary that AI record is separate from interview flows, uses frontend-streamed audio in v1, and must preserve independent meeting semantics

### Codebase maps
- `.planning/codebase/ARCHITECTURE.md` - current FastAPI/service/repo/socket layering and live STT runtime shape
- `.planning/codebase/STRUCTURE.md` - expected locations for new feature routes, services, repositories, models, and schemas
- `.planning/codebase/CONVENTIONS.md` - module naming, imports, exception handling, and service/repo patterns to match

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/socket_gateway/server.py`: authenticated Socket.IO lifecycle, user-room emits, and long-lived STT listener task management can be reused for a meeting-specific realtime contract.
- `app/services/stt/session.py`: existing provider-session orchestration, finalize handling, keepalive, and transcript assembly are reusable once interview-specific speaker assumptions are removed.
- `app/infrastructure/deepgram/client.py`: normalized Deepgram live adapter already provides provider isolation, finalize, close, and transcript events.
- `app/common/service.py` and `app/common/repo.py`: cached dependency factories are the established place to wire new meeting repositories and services.
- `app/api/deps.py`: current auth and organization validation logic is the reference pattern for any meeting REST endpoints.
- `app/repo/conversation_repo.py` and `app/services/ai/conversation_service.py`: existing durable conversation storage can be reused internally if meetings need linked conversation records without exposing chat-style identifiers publicly.

### Established Patterns
- New product features are added as dedicated modules under `app/api/v1/<feature>/`, `app/services/<feature>/`, `app/repo/`, and `app/domain/models|schemas/`.
- Socket sessions are process-local and the current STT manager already enforces one active stream per socket.
- HTTP organization scoping is explicit today via `X-Organization-ID`; the meeting flow should move realtime behavior toward similarly explicit scoping instead of implicit org inference.
- Global error translation is built around `AppException` subclasses surfaced through `app/main.py`.

### Integration Points
- `app/common/event_socket.py`: add meeting-specific realtime event constants here instead of leaking interview/STT naming upward.
- `app/api/v1/router.py`: register any meeting-specific REST endpoints here if Phase 1 introduces non-socket lifecycle APIs.
- `app/common/service.py` and `app/common/repo.py`: add meeting-specific factories here for repositories/services.
- `app/infrastructure/database/mongodb.py`: add meeting collection indexes here once meeting-native persistence models are introduced.
- `app/domain/schemas/stt.py`, `app/services/stt/session_manager.py`, and `app/services/interview/answer_service.py` are the main coupling points that currently assume interview roles, a 2-channel map, and interview-answer side effects; planning should explicitly decouple meeting flows from those assumptions.

</code_context>

<specifics>
## Specific Ideas

- The meeting product surface should not expose `stt:*` as its primary contract. STT remains an internal implementation detail under a meeting-native API.
- The chosen public start event name is `meeting_record:start`.
- Server-emitted meeting events may include `organization_id` for clarity, even though org binding happens once at start.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 1 scope.

</deferred>

---

*Phase: 01-meeting-domain-foundation*
*Context gathered: 2026-03-19*
