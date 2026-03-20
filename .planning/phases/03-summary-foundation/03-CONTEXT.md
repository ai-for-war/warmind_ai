# Phase 3: Summary Foundation - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 delivers short meeting summaries on top of the stable transcript pipeline from Phase 2. The scope is debounced batch summary generation during an active meeting plus a finalized short summary when the meeting ends. Structured outputs such as key points, decisions, action items, notes, follow-up questions, and meeting history remain outside this phase.

</domain>

<decisions>
## Implementation Decisions

### Short summary format
- The meeting summary should use a short `2-3` bullet format rather than a paragraph.
- The short summary may be compact rather than ultra-short, allowing a bit more detail when the meeting content warrants it.
- Summary language should follow the language selected for the meeting session.
- The short summary should avoid anonymous speaker labels by default and stay speaker-neutral unless the implementation absolutely needs attribution for clarity.

### Live summary cadence
- In-progress summaries should refresh only when enough new stable transcript content has accumulated to noticeably improve the summary, not after every closed transcript block.
- The first live summary should wait until enough stable transcript context exists to produce a useful result.
- While a refresh is in progress, the UI should keep showing the last good summary and only indicate a light updating state.

### Final summary handoff
- The finalized summary should reuse the same summary surface as the live summary rather than introducing a separate parallel panel.
- After the meeting is stopped, the UI should keep showing the latest live summary while indicating that finalization is in progress.
- The final summary should be the latest live summary promoted to final state, not a separately rewritten richer summary.

### Claude's Discretion
- The exact debounce threshold that qualifies as a "meaningful batch" of transcript content before enqueueing live summary work.
- The exact bullet wording, style constraints, and prompt instructions used to keep summaries concise and speaker-neutral.
- Retry, deduplication, and concurrency rules for summary job orchestration.
- The exact event names and payload shape used to deliver live/final summary states over the existing meeting socket contract.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product scope and requirements
- `.planning/ROADMAP.md` - Phase 3 goal, success criteria, and plan boundaries for Summary Foundation
- `.planning/REQUIREMENTS.md` - `SUMM-01` and `SUMM-07` define the required in-progress and finalized short-summary behavior
- `.planning/PROJECT.md` - batch-oriented summary generation, dedicated meeting workflow boundaries, and dedicated summary storage expectation
- `.planning/phases/01-meeting-domain-foundation/01-CONTEXT.md` - carry forward the meeting-native contract, organization scoping, and one-language-per-meeting rule
- `.planning/phases/02-live-transcript-capture/02-CONTEXT.md` - carry forward stable closed transcript blocks, chronological transcript review shape, and transcript durability expectations

### Codebase maps
- `.planning/codebase/ARCHITECTURE.md` - current FastAPI/service/repo/socket/worker layering and Redis-backed async processing model
- `.planning/codebase/STRUCTURE.md` - expected locations for new meeting summary services, repositories, schemas, worker entrypoints, and router wiring
- `.planning/codebase/CONVENTIONS.md` - module naming, factory wiring, logging, and service/repository conventions to follow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/services/meeting/session.py`: already emits stable finalized transcript blocks with block sequence and meeting-relative timing; this is the natural source event for batch summary triggering.
- `app/services/meeting/transcript_service.py` and `app/repo/meeting_transcript_repo.py`: already persist and read durable transcript segments in chronological order; this is the durable input source for summary generation and replay.
- `app/services/meeting/meeting_service.py`: already reacts to finalized transcript block events and schedules non-blocking side effects, making it the natural integration point for debounce bookkeeping and summary enqueueing.
- `app/common/event_socket.py` and `app/socket_gateway/server.py`: already centralize the `meeting_record:*` realtime contract and user-room emission flow; live/final summary events should extend this path instead of inventing a parallel transport.
- `app/infrastructure/redis/redis_queue.py`, `app/services/image/image_generation_service.py`, and `app/workers/image_generation_worker.py`: provide the established persisted-job plus Redis queue plus worker pattern for async processing and lifecycle events.
- `app/infrastructure/llm/factory.py`: already provides the repo-standard OpenAI chat client factory for prompt-driven summary generation.

### Established Patterns
- Meeting artifacts are modeled as meeting-specific services and repositories rather than exposed through interview-specific product contracts.
- Durable async work in this codebase is expressed as queued jobs processed by dedicated workers, not long-running request handlers.
- Event names are centralized in `app/common/event_socket.py` and emitted to user rooms through socket gateway helpers rather than being scattered across services.
- Shared dependencies are introduced through `app/common/service.py`, `app/common/repo.py`, and `app/config/settings.py` rather than ad hoc constructors.

### Integration Points
- `app/services/meeting/meeting_service.py`: hook live-summary debounce decisions to finalized transcript block arrival and meeting completion.
- `app/common/service.py` and `app/common/repo.py`: add summary-specific repositories, services, and queue accessors here.
- `app/common/event_socket.py` and `app/socket_gateway/server.py`: add meeting summary lifecycle events and emit them through the existing meeting listener flow.
- `app/workers/` and `scripts/system/`: add a dedicated meeting summary worker entrypoint if Phase 3 uses background queue processing.
- `app/domain/models/` and `app/domain/schemas/`: summary-specific meeting models and payload contracts do not exist yet and will need to be introduced.

</code_context>

<specifics>
## Specific Ideas

- One summary area should serve both the in-progress and finalized short summary states.
- The live summary should feel low-churn: keep the previous version visible until a meaningfully improved replacement is ready.
- Finalization should primarily be a state transition from live to final, not an opportunity to expand into a richer post-meeting artifact.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 3 scope.

</deferred>

---

*Phase: 03-summary-foundation*
*Context gathered: 2026-03-20*
