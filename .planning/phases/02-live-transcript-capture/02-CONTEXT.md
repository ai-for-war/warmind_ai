# Phase 2: Live Transcript Capture - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers durable live and saved meeting transcript capture for the meeting-native workflow introduced in Phase 1. The scope is transcript ingest, live transcript block assembly, anonymous speaker labeling, timestamped persistence, and read paths for active and completed meetings. Summary generation, speaker identity mapping, and broader meeting history UX remain outside this phase.

</domain>

<decisions>
## Implementation Decisions

### Live transcript behavior
- During an active meeting, users should see transcript text live before the utterance is fully stabilized.
- When provider output is corrected by a later finalized transcript fragment, the current live text should be rewritten in place rather than appended as a correction trail.
- The live transcript should be shaped around transcript blocks. Each block can contain multiple finalized speaker segments plus one draft segment, and the next transcript content should begin a new transcript block after a provider boundary closes the current one.
- Frontend scrolling behavior is not locked in this phase discussion and can remain implementation discretion.

### Speaker grouping and labeling
- Transcript storage and presentation should preserve chronological segment order inside a transcript block rather than collapsing the whole block into one speaker label.
- Anonymous speaker labels do not need to remain perfectly stable across an entire meeting session.
- The preferred visible label format is `speaker 1`, `speaker 2`, and so on.
- If diarization is unclear for a captured segment, the system should still retain that segment and use a fallback label such as `speaker unknown` rather than dropping transcript text.

### Timestamp fidelity
- Saved transcript items should carry both utterance start and utterance end timestamps.
- The canonical stored timing representation should be milliseconds from meeting start rather than preformatted display strings.
- Timestamp display during the live meeting is not a locked requirement for this phase; the important requirement is durable timing for saved review.
- If provider timing is imperfect, the system should persist best-effort timestamps instead of rejecting otherwise valid transcript content.

### Saved transcript review shape
- Saved transcript review should be a chronological list of transcript items rather than speaker-grouped sections.
- Each saved transcript item should minimally include anonymous speaker label, transcript text, and timestamps.
- Read paths for completed transcripts should be paginated in Phase 2 rather than only returning the full transcript in one fetch.
- Paginated transcript review should default to oldest-first ordering so review reads naturally from meeting start to meeting end.

### Claude's Discretion
- Exact socket or API payload shapes used to emit live transcript updates during an active meeting
- The exact fallback label string for unclear diarization as long as it is anonymous and non-destructive
- Pagination mechanics for completed transcript reads, including page size and cursor/offset style
- Whether transcript persistence uses a meeting-specific utterance store, a linked conversation/message structure, or another meeting-native durable model that does not leak chat semantics publicly

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product scope and prior decisions
- `.planning/ROADMAP.md` - Phase 2 goal, success criteria, and plan boundaries for Live Transcript Capture
- `.planning/REQUIREMENTS.md` - `TRNS-01`, `TRNS-02`, `TRNS-03`, and `TRNS-04` define the live view, saved review, anonymous speaker grouping, and timestamp requirements
- `.planning/PROJECT.md` - meeting workflow must stay separate from interview semantics, persist durable transcript history, keep anonymous speaker labels, and continue using frontend-streamed audio in v1
- `.planning/phases/01-meeting-domain-foundation/01-CONTEXT.md` - carry forward the meeting-native contract, organization scoping, one-language-per-meeting rule, and terminal meeting lifecycle decisions from Phase 1

### Codebase maps
- `.planning/codebase/ARCHITECTURE.md` - current FastAPI/service/repo/socket layering and realtime STT runtime shape
- `.planning/codebase/STRUCTURE.md` - expected locations for new meeting transcript services, repositories, schemas, and API wiring
- `.planning/codebase/CONVENTIONS.md` - module naming, factory wiring, and service/repository conventions to match existing code

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/services/stt/session.py`: already assembles partial, final, utterance-closed, and timed transcript state from provider events; this is the strongest reference for provider-boundary lifecycle behavior even though it is interview-oriented today.
- `app/infrastructure/deepgram/client.py`: already normalizes Deepgram partial/final transcript events, utterance boundaries, diarization metadata, and word timing into provider-agnostic events.
- `app/socket_gateway/server.py`: already owns the meeting-native socket contract for `meeting_record:*` events and the long-lived listener pattern for STT provider event collection.
- `app/services/meeting/session.py`: already owns meeting-native provider lifecycle for start/stop/finalize, but currently stops at lifecycle events and does not yet project transcript events upward.
- `app/repo/meeting_record_repo.py`: already persists durable meeting lifecycle records and provides the natural anchor entity for transcript persistence and later transcript reads.
- `app/common/service.py` and `app/common/repo.py`: established composition points for introducing meeting transcript repositories/services without bypassing the current dependency wiring style.

### Established Patterns
- Realtime payload contracts are centralized in `app/common/event_socket.py` and emitted through `app/socket_gateway/server.py` rather than ad hoc event names spread across services.
- Process-local live session state is managed in session manager classes, while durable state is written through repositories backed by MongoDB.
- Existing STT code is optimized for interview channels and role mapping; Phase 2 planning must explicitly reuse transcript assembly mechanics without reintroducing interview-specific semantics into the meeting product surface.
- The codebase already differentiates meeting-native lifecycle state from generic conversation/chat state. Transcript persistence should preserve that boundary even if some lower-level storage primitives are reused internally.

### Integration Points
- `app/common/event_socket.py`: add any meeting transcript live-update events here rather than reusing `stt:*` events directly as the public meeting contract.
- `app/services/meeting/session.py` and `app/services/meeting/session_manager.py`: extend the meeting runtime to consume provider transcript events and emit meeting transcript updates, not just lifecycle state.
- `app/socket_gateway/server.py`: wire transcript event emission for active meetings and connect saved transcript read paths to the meeting domain.
- `app/api/v1/router.py`: register any new meeting transcript review endpoints here because there is no meeting review router yet.
- `app/common/service.py` and `app/common/repo.py`: add meeting transcript repository/service factories here for durable persistence and retrieval.

</code_context>

<specifics>
## Specific Ideas

- Transcript should be treated as a block timeline with ordered speaker segments, not as a speaker-merged document.
- Live transcript can show provisional multi-speaker text in `draft_segments[]`, but finalized `segments[]` should preserve the stable transcript content accumulated for the block.
- Frontend scrolling behavior for the live transcript is intentionally left to frontend implementation and does not need to be locked in Phase 2 planning.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 2 scope.

</deferred>

---

*Phase: 02-live-transcript-capture*
*Context gathered: 2026-03-19*
