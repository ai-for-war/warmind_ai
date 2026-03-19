# Phase 1: Meeting Domain Foundation - Research

**Researched:** 2026-03-19
**Domain:** Meeting-native realtime audio session orchestration on top of the existing FastAPI, Socket.IO, MongoDB, and Deepgram stack
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- The public realtime start contract should be meeting-native, with `meeting_record:start` as the user-facing start event.
- Starting over the realtime meeting contract should create the meeting session directly; Phase 1 does not require a separate REST create step before streaming.
- The frontend should work with a meeting-native identifier only. Any linked internal conversation or transcript identifiers stay backend-internal.
- Start success should return a full ready payload rather than a minimal acknowledgment.
- Only one active meeting session is allowed per socket. A second start request must be rejected until the active meeting is stopped.
- The frontend must send an explicit `organization_id` when starting a meeting.
- If the supplied `organization_id` is invalid or the user is not allowed to use it, the backend must reject the start request immediately and create no meeting shell.
- The meeting session binds organization context at start time. The backend may echo `organization_id` back in emitted client events, but the client should not need to resend org scope on every audio packet.
- Only the user who started the meeting can stop that active meeting in Phase 1.
- Stop means "finalize then finish cleanly", not "cut the stream immediately".
- After a stop request, the client should first receive a stopping/in-progress event and only receive completed once finalize has finished.
- If the client disconnects unexpectedly during an active meeting, the backend should try to finalize and close the meeting cleanly before falling back to failure.
- A completed meeting is terminal. Resuming streaming must create a new meeting rather than reopening the completed one.
- Language may be omitted at start time; if omitted, the backend should default to `en`.
- Phase 1 may allow free-form language code input in the UI, but the backend must validate the submitted value against a supported allowlist before starting the meeting.
- A meeting uses one selected language for its full lifecycle. Mixed-language speech is acceptable operationally, but Phase 1 should not switch languages mid-session.

### Claude's Discretion
- Exact ready, stopping, and completed event names after `meeting_record:start`
- Whether the client waits for ready before sending audio or buffers locally first
- The exact allowlist source and how supported language codes are exposed in UI copy
- Internal linkage between the meeting-native record and any reusable conversation or transcript storage primitives

### Deferred Ideas (OUT OF SCOPE)
- Transcript review, summary generation, and meeting history
- Real participant identity mapping
- Any frontend design contract work beyond honoring the chosen realtime contract
</user_constraints>

<research_summary>
## Summary

Phase 1 should not extend the current public `stt:*` contract. The existing speech stack is technically reusable at the Deepgram adapter boundary, but every public layer above that boundary is interview-shaped today: request schemas require `conversation_id` and `channel_map`, session state assumes two fixed interview roles, durable persistence writes to `interview_conversations` and `interview_utterances`, and socket handlers emit `InterviewEvents`. Planning should therefore introduce a meeting-native facade instead of trying to "rename" the current interview flow in place.

The pragmatic implementation path is a thin meeting-specific realtime slice that owns start, audio, and stop semantics while reusing only shared infrastructure: JWT-authenticated Socket.IO connections, `DeepgramLiveClient`, repository and service factories, MongoDB index creation, and the existing socket payload enrichment that echoes `organization_id`. This keeps Phase 1 bounded to lifecycle and contract independence, without prematurely pulling transcript persistence or summary generation into scope.

**Primary recommendation:** Add a dedicated `meeting_record:*` contract, meeting-specific settings/models/repository/service/session manager, and explicit organization plus language validation before provider open; do not route meeting start or stop through interview schemas, interview repos, or `InterviewEvents`.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | repo-managed | HTTP app and shared dependency wiring | Already owns auth, organization validation, and service composition in this codebase |
| python-socketio | repo-managed | Realtime client lifecycle and event handling | Existing authenticated socket runtime already exposes stable user-room emits |
| motor + MongoDB | repo-managed | Durable meeting lifecycle persistence | Current repository pattern and index bootstrap already standardize Mongo access |
| deepgram-sdk Listen v1 | repo-managed | Live meeting audio transport, finalize, and close semantics | Current adapter already normalizes provider events behind `DeepgramLiveClient` |
| Pydantic / pydantic-settings | repo-managed | Strict socket payload validation and runtime settings | Existing domain schema and settings patterns are already consistent with new feature work |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | repo-managed | Unit and integration verification | Validate meeting schemas, lifecycle rules, and socket handler behavior |
| pytest-asyncio | repo-managed | Async service and socket tests | Required for session manager and socket event flows |
| python-jose | repo-managed | Existing socket auth decoding | Reuse through current `authenticate()` flow rather than adding parallel auth |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Dedicated meeting session manager | Reusing `STTSessionManager` directly | Faster short term, but keeps interview-only concepts (`channel_map`, interview answer triggers, interview utterance persistence) in the meeting path |
| Meeting-native socket contract | Reusing `stt:start` and renaming in the frontend | Less code initially, but violates the explicit phase goal of contract independence |
| Separate meeting settings | Reusing `INTERVIEW_*` settings | Fewer config fields, but cements the wrong defaults such as 2-channel interview assumptions |
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```text
app/
+-- common/
|   +-- event_socket.py              # MeetingRecordEvents constants
|   +-- exceptions.py                # Meeting lifecycle and validation errors
+-- config/
|   +-- settings.py                  # Meeting STT defaults and language allowlist
+-- domain/
|   +-- models/
|   |   +-- meeting_record.py        # Durable meeting lifecycle model
|   +-- schemas/
|       +-- meeting_record.py        # Public meeting-native socket payloads
+-- repo/
|   +-- meeting_record_repo.py       # Durable meeting session persistence
+-- services/
|   +-- meeting/
|       +-- meeting_service.py       # Organization, ownership, and lifecycle orchestration
|       +-- session.py               # One live meeting session
|       +-- session_manager.py       # Process-local active meeting registry
+-- socket_gateway/
    +-- server.py                    # `meeting_record:*` handlers and emits
```

### Pattern 1: Reuse the provider adapter, replace the public contract
**What:** Keep `DeepgramLiveClient` as the only provider-facing layer, but stop exposing interview-specific payloads or session state above it.
**When to use:** Whenever the provider transport is reusable but product semantics are different.
**Why it fits Phase 1:** `DeepgramLiveClient` already supports `open(language=...)`, `send_audio(...)`, `finalize()`, and `close()`, which are the exact lifecycle primitives Phase 1 needs. The coupling problem starts above that layer.

### Pattern 2: Validate organization and language before any durable side effect
**What:** Treat `organization_id` membership checks and language allowlist checks as preconditions for creating a meeting record or opening Deepgram.
**When to use:** Any multi-tenant realtime start flow where the request chooses tenant context or provider configuration.
**Why it fits Phase 1:** The context explicitly requires "reject immediately and create no meeting shell" for invalid org access. Validation must happen before repo `create(...)` or provider `open(...)`.

### Pattern 3: Model stop as a state transition, not a socket disconnect shortcut
**What:** Emit a stopping event first, mark the durable record as stopping, request provider finalize, then emit completed only after provider close or explicit completion handling.
**When to use:** Any streamed workflow where completion must flush provider state before the session becomes terminal.
**Why it fits Phase 1:** It is the only way to satisfy the user decision that stop means "finalize then finish cleanly" and that completed is emitted after finalize, not before.

### Anti-Patterns to Avoid
- **Reusing `STTChannelMap` or interview roles for meeting start:** meetings do not have fixed `interviewer` and `user` channels.
- **Inferring organization from the socket session during meeting start:** Phase 1 requires explicit `organization_id` in the start payload.
- **Writing meeting state into `interview_conversations` or `interview_utterances`:** that would make Phase 1 fail its independence requirement before Phase 2 even begins.
- **Keeping meeting language as a loose string with no allowlist check:** the context requires backend validation before start succeeds.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Provider websocket lifecycle | A second raw Deepgram websocket client for meetings | `app/infrastructure/deepgram/client.py` | The adapter already normalizes connect, finalize, close, and provider event translation |
| Socket authentication | Meeting-specific JWT parsing | `app/socket_gateway/auth.py` | Existing connection auth already populates the socket user identity |
| Organization access rules | Ad hoc membership queries in socket handlers | `OrganizationRepository` plus `OrganizationMemberRepository` patterns used by `app/api/deps.py` | Reusing the existing validation pattern avoids tenant drift |
| Persistence wiring | Inline collection access from service code | `app/repo/*` plus `app/common/repo.py` factories | The codebase consistently isolates Mongo access behind repositories |

**Key insight:** The repo already has good infrastructure primitives. The risky part is not transport plumbing; it is accidentally leaking interview semantics into a new meeting domain. Reuse shared adapters, not shared product contracts.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Leaving `conversation_id` in the public meeting contract
**What goes wrong:** The frontend still thinks in chat or interview identifiers, so meeting flows can never evolve independently.
**Why it happens:** `STTStartRequest` and `STTAudioMetadata` already require `conversation_id`, making copy-paste integration tempting.
**How to avoid:** Create meeting-native schemas that expose only `meeting_id` after start and keep any internal conversation link backend-only.
**Warning signs:** Meeting handlers calling `request.conversation_id` or `payload["conversation_id"]`.

### Pitfall 2: Carrying forward the 2-channel interview assumption
**What goes wrong:** The meeting flow is forced into `channel_map` and `channels=2`, which mismatches browser-captured meeting audio and delays later diarization work.
**Why it happens:** `STTChannelMap`, `InterviewChannelMap`, and `INTERVIEW_STT_CHANNELS` are the most developed current patterns.
**How to avoid:** Add separate meeting settings with `channels=1` and `multichannel=false`, then reserve speaker grouping for Phase 2.
**Warning signs:** New meeting code importing `STTChannelMap`, `InterviewChannelMap`, or `INTERVIEW_STT_*`.

### Pitfall 3: Treating stop as immediate close with no intermediate state
**What goes wrong:** Clients see a completed event before provider finalize finishes, or disconnect handling drops the meeting into an ambiguous state.
**Why it happens:** `session.stop()` in the current STT flow moves directly to provider close, which is good for interview streaming but too coarse for the meeting requirement.
**How to avoid:** Introduce a meeting `stopping` state in both durable storage and emitted payloads, and only move to `completed` after finalize plus close handling finishes.
**Warning signs:** `meeting_record:stop` emits completed directly or only calls `close()` with no finalize step.
</common_pitfalls>

<validation_architecture>
## Validation Architecture

- Use `pytest` and `pytest-asyncio`, both already declared in `requirements.txt`.
- Add unit coverage for meeting schema validation, meeting language normalization, organization and ownership checks, and meeting session manager lifecycle transitions.
- Add socket-level integration tests for `meeting_record:start` success, invalid `organization_id`, unsupported language, duplicate active start rejection, and stop completion ordering (`started` -> `stopping` -> `completed`).
- Keep acceptance criteria grep-verifiable inside each plan so execute-phase can prove contract independence even before full meeting transcript features land.
</validation_architecture>

<open_questions>
## Open Questions

1. **Should meeting records immediately create a linked generic conversation document in Phase 1?**
   - What we know: the context allows an internal linkage to reusable conversation storage primitives, but says the frontend must not see those identifiers.
   - What's unclear: whether creating that linkage now helps later phases enough to justify extra coupling in Phase 1.
   - Recommendation: keep the durable meeting record authoritative in Phase 1 and make any linked conversation id optional or deferred until transcript persistence work in Phase 2 clarifies the storage shape.

2. **Where should the supported language allowlist live?**
   - What we know: the backend must validate against an allowlist and default to `en`; the source of the allowlist is Claude's discretion.
   - What's unclear: whether product wants environment-driven configurability now or just a code-level v1 list.
   - Recommendation: store the allowlist in `Settings` as `MEETING_SUPPORTED_LANGUAGES` with default `["en", "vi"]`, then mirror it in `.env.example` for easy later extension.
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- Local phase context and planning docs:
  - `.planning/phases/01-meeting-domain-foundation/01-CONTEXT.md`
  - `.planning/ROADMAP.md`
  - `.planning/REQUIREMENTS.md`
  - `.planning/PROJECT.md`
  - `.planning/STATE.md`
- Local implementation references:
  - `app/socket_gateway/server.py`
  - `app/services/stt/session.py`
  - `app/services/stt/session_manager.py`
  - `app/services/stt/stt_service.py`
  - `app/common/event_socket.py`
  - `app/common/service.py`
  - `app/common/repo.py`
  - `app/infrastructure/deepgram/client.py`
  - `app/infrastructure/database/mongodb.py`
  - `app/api/deps.py`
- Official Deepgram docs:
  - https://developers.deepgram.com/docs/understand-endpointing-interim-results

### Secondary (MEDIUM confidence)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/STRUCTURE.md`
- `.planning/codebase/CONVENTIONS.md`
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Socket.IO meeting lifecycle on top of Deepgram live transcription
- Ecosystem: FastAPI dependencies, repository wiring, Mongo indexes, provider adapter reuse
- Patterns: meeting-native contracts, explicit organization validation, finalize-before-complete stop flow
- Pitfalls: interview coupling, implicit org resolution, two-channel assumptions

**Confidence breakdown:**
- Product boundary: HIGH - directly defined in CONTEXT, ROADMAP, and REQUIREMENTS
- Architecture approach: HIGH - grounded in current code seams and existing repo conventions
- Provider lifecycle assumptions: HIGH - supported by the local Deepgram adapter and official Deepgram websocket docs
- Future-proofing notes: MEDIUM - transcript and summary phases may refine the internal storage link shape

**Research date:** 2026-03-19
**Valid until:** 2026-04-18
</metadata>

---

*Phase: 01-meeting-domain-foundation*
*Research completed: 2026-03-19*
*Ready for planning: yes*
