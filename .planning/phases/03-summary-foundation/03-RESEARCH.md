# Phase 03: Summary Foundation - Research

**Researched:** 2026-03-20
**Confidence:** HIGH

## User Constraints from CONTEXT

### Locked Decisions

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

### Deferred Ideas
None - discussion stayed within Phase 3 scope.

## Existing Code Findings

- `app/services/meeting/meeting_service.py` already has the right Phase 3 trigger surface: it receives `MeetingSessionEventKind.TRANSCRIPT` events, filters for finalized transcript blocks, and schedules transcript persistence in the background. The important implication is that summary enqueueing must happen after durable transcript persistence succeeds, not at raw socket-event time, because `_schedule_transcript_persistence()` currently uses `asyncio.create_task(...)` and does not wait for durability. `HIGH`
- `app/services/meeting/meeting_service.py` already normalizes and validates one meeting language per session. Summary generation should reuse the meeting record language instead of re-detecting language from transcript text, so live and final summaries cannot drift away from the session contract. `HIGH`
- `app/services/meeting/meeting_service.py` already drives `mark_stopping()`, `mark_completed()`, and `mark_failed()` from meeting lifecycle events. Final summary handoff should hook this existing stop/completion path instead of adding a parallel post-meeting lifecycle. `HIGH`
- `app/services/meeting/transcript_service.py` and `app/repo/meeting_transcript_repo.py` already provide the durable summary input source: finalized transcript segments stored in oldest-first block order with cursorable block and segment positions. Summary jobs should read from this durable store up to a target `block_sequence`, not from transient socket payloads. `HIGH`
- `app/repo/meeting_transcript_repo.py` is already idempotent at the transcript layer by upserting on `meeting_id + segment_id`. Phase 3 should copy this style and make summary deduplication key off durable meeting progress, for example `meeting_id + mode + target_block_sequence`, rather than queue timing. `HIGH`
- `app/common/event_socket.py` and `app/socket_gateway/server.py` centralize the meeting socket contract under `meeting_record:*` and emit to user rooms through one path. Phase 3 should extend this contract with one summary event surface on the same channel instead of inventing a second transport or mixing summary events into transcript events. `HIGH`
- `app/socket_gateway/server.py` already has a meeting listener loop that relays live session events, and the broader codebase already uses worker-safe socket emission for async jobs. That means summary work can use the existing meeting socket contract while emitting queued/processing/final states from a background worker. `HIGH`
- `app/infrastructure/redis/redis_queue.py` is only a thin FIFO wrapper over Redis list operations. It adds `queued_at`, but it does not provide ack, retry, visibility timeout, or dedup behavior. A Phase 3 design that relies on Redis queue items alone would be fragile; durable summary job state in MongoDB is required. `HIGH`
- `app/workers/image_generation_worker.py` is the best local orchestration template: queue DTO, bounded concurrency, reload job from MongoDB, skip terminal states, `claim_pending_job(...)`, persist terminal status, and emit lifecycle events after persistence. Summary generation should follow this pattern instead of calling the LLM directly from the meeting service or socket server. `HIGH`
- `app/infrastructure/llm/factory.py` already provides the repo-standard `ChatOpenAI` construction path. The summary worker should reuse that factory with worker-friendly parameters such as non-streaming responses and stable prompting rather than introducing a separate OpenAI client stack. `MEDIUM`
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, and `.planning/codebase/CONVENTIONS.md` all point to the same shape for new Phase 3 code: meeting-specific services under `app/services/meeting/`, dedicated repositories under `app/repo/`, new summary models and schemas under `app/domain/models/` and `app/domain/schemas/`, socket event constants in `app/common/event_socket.py`, worker entrypoint under `app/workers/`, and dependency wiring via `app/common/service.py` and `app/common/repo.py`. `HIGH`
- The checked-in `tests/` tree currently contains only package marker files, even though `__pycache__` names show prior `pytest` usage. Phase 3 should plan test creation as first-class work rather than assuming reusable source tests already exist. `HIGH`

## Recommended Architecture Patterns

### Debounce Trigger Design

- Trigger summary decisions from durable transcript progress, not from every finalized provider event. The natural hook is the finalized transcript block path in `app/services/meeting/meeting_service.py`, but the actual enqueue point should be after `app/services/meeting/transcript_service.py` finishes persisting that block.
- Store summary progress against the meeting in dedicated summary state, not in socket-local session memory. The minimum state Phase 3 needs is: latest persisted transcript `block_sequence`, latest summarized `block_sequence`, latest enqueued `block_sequence`, latest live summary revision, and current summary status.
- Debounce by transcript delta, not by wall-clock alone. The plan should use a "meaningful batch" gate based on new durable transcript content since the last successful summary, such as new closed block count and/or transcript growth. Exact thresholds remain Phase 3 discretion, but the mechanism should be based on durable transcript progression.
- Coalesce refreshes. If a live summary job is already queued or processing for a meeting, new transcript blocks should update the target coverage in durable state instead of creating multiple equivalent jobs for the same meeting.

### Queue and Worker Orchestration

- Use the existing persisted-job-plus-Redis-queue pattern, not a fire-and-forget `asyncio.create_task(...)` summary call. The Redis payload should be small and durable-job based, for example `job_id`, `meeting_id`, `organization_id`, `user_id`, `mode`, and `target_block_sequence`.
- Add a dedicated summary job collection. Redis alone is not sufficient because `app/infrastructure/redis/redis_queue.py` removes items at dequeue time and cannot recover from worker crashes by itself.
- Mirror the image-generation worker lifecycle: enqueue durable job, worker reloads job, skips terminal/obsolete work, claims pending work, runs the LLM, persists the new summary snapshot, then emits lifecycle events.
- Enforce one active summary job per meeting. Global worker concurrency can still allow multiple meetings to process in parallel, but Phase 3 should not let one meeting run overlapping live/final summary generations.

### Dedicated Summary Storage

- Keep summary storage separate from `app/repo/meeting_transcript_repo.py`. Phase 3 should introduce a dedicated summary collection for short-summary snapshots or revisions and a separate summary job collection for orchestration state.
- Persist summary snapshots with meeting-scoped metadata that later phases can build on: `meeting_id`, `organization_id`, `summary_type`, `revision`, `source_block_sequence`, `language`, `bullets`, `status`, `is_final`, `created_at`, and `finalized_at` when applicable.
- Preserve a revision trail for each meaningful live refresh. This matches the project requirement for durable summary history and gives finalization a clear path: either promote the latest live revision to final if it already covers the last stable transcript block, or create one last revision and mark that one final.
- Add an internal transcript-read path for summary generation that fetches durable transcript items up to a target block sequence. Do not build summary input by replaying public paginated responses or by keeping a second transcript cache in the summary worker.

### Live and Final Summary State Transitions

- Use one summary surface and one state machine. A practical Phase 3 state model is `idle -> queued -> updating -> live -> finalizing -> final`, plus `failed` for observability while keeping the last good summary payload visible.
- On active-meeting refresh, emit an updating state immediately while retaining the previous bullets. Only replace bullets when the worker persists a newer live revision.
- On stop, keep the latest live summary visible and emit a finalizing state on the same event surface. If the latest live revision already covers the final persisted transcript block, promote it to final. If not, enqueue one final job to cover the remaining transcript and then mark that revision final.
- If a meeting ends before any live summary has been generated, the finalization path must still be able to create the first and final short summary from durable transcript data.

### Language Handling

- Use the normalized meeting language already enforced by `app/services/meeting/meeting_service.py` as the only summary language source of truth.
- Persist language on both summary jobs and summary snapshots so retries and finalization stay consistent.
- Keep prompts speaker-neutral and explicitly request `2-3` concise bullets in the meeting language. Do not include anonymous speaker labels unless the summarizer needs attribution for clarity in a specific bullet.

### Socket Event Integration

- Extend `app/common/event_socket.py` with a dedicated summary event under the existing meeting namespace, preferably a single `meeting_record:summary` event rather than separate live and final events.
- Reuse the current user-room routing model in `app/socket_gateway/server.py`. The main process can emit immediate queued/finalizing state changes, while the worker can emit live/final/failure results through the worker-side gateway using the same event name.
- Keep the payload shape stable across live and final states. The planner should assume a payload with at least `meeting_id`, `status`, `is_final`, `language`, `source_block_sequence`, `bullets`, `updated_at`, and optional `error_message`.

### Idempotency and Dedup Rules

- Deduplicate live summary work by durable coverage, not by socket event count. If a trigger targets a `block_sequence` that is already summarized or already queued for that meeting, it should no-op.
- Make finalization idempotent. Repeated stop/disconnect handling must not create duplicate final summaries if the meeting already has a final short summary covering the latest durable transcript.
- Use durable summary status plus target coverage to decide skips in the worker. Queue duplicates are acceptable only if the worker can safely discard obsolete jobs after reload and claim.
- Keep Redis payloads opaque and small. The durable job document should be the source of truth for mode, retry count, target coverage, and whether work is still necessary.

## Risks and Pitfalls

- `app/services/meeting/meeting_service.py` persists transcripts via background task, so summary work can race ahead of transcript durability if Phase 3 enqueues on raw final transcript events. This is the biggest Phase 3 design hazard because the worker could summarize stale data. `HIGH`
- `app/infrastructure/redis/redis_queue.py` provides no ack or visibility timeout. If the summary design relies on queue items alone, worker crashes can silently drop work. Durable job state is required to keep live/final summary generation recoverable. `HIGH`
- A naive "summarize every closed block" policy will violate the locked low-churn UX and create noisy, expensive updates. The trigger must be based on meaningful new stable content, not per-block reflexes. `HIGH`
- If summary storage is mixed into transcript collections, later phases for key points, decisions, and action items will inherit a brittle schema. Phase 3 should keep summary artifacts in dedicated collections now. `HIGH`
- If the worker infers language from transcript text instead of using the meeting language, live and final summaries can switch languages mid-meeting on bilingual content. The meeting record language must stay authoritative. `HIGH`
- If finalization always regenerates from scratch, the UI contract from context is broken because the latest live summary is supposed to remain visible and be promoted to final when possible. Finalization should be a state transition first, not a second independent summary product. `HIGH`
- Repeated stop/disconnect flows can produce duplicate final-summary jobs unless finalization is keyed by durable transcript coverage and existing final state. `HIGH`
- Source tests are effectively absent in the checked-in tree. Phase 3 planning that treats validation as optional will likely ship regressions in debounce logic, dedup rules, and socket state transitions. `HIGH`

## Validation Architecture

Nyquist validation is enabled in `.planning/config.json`, so Phase 3 should plan both unit and integration coverage.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` (inferred from cached `tests/**/__pycache__/*pytest*.pyc` artifacts; no checked-in config file detected) |
| Config file | none detected |
| Quick run command | `pytest tests/unit -q` |
| Full suite command | `pytest -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SUMM-01 | Debounced live short summary appears only after meaningful durable transcript growth, updates in batches, and keeps the last good summary visible while a refresh is running | unit + integration | `pytest tests/unit/services/test_meeting_summary_trigger_service.py tests/integration/socket_gateway/test_meeting_record_summary_socket.py -q` | No - Wave 0 |
| SUMM-07 | Meeting stop reuses the same summary surface, keeps the latest live summary visible during finalization, and ends with one finalized short summary for the latest durable transcript state | unit + integration | `pytest tests/unit/services/test_meeting_summary_service.py tests/unit/test_meeting_summary_worker.py tests/integration/socket_gateway/test_meeting_record_summary_socket.py -q` | No - Wave 0 |

### Wave 0 Gaps

- `tests/unit/services/test_meeting_summary_trigger_service.py` for debounce thresholds, coalescing, and no-op dedup when the target block sequence is already covered
- `tests/unit/services/test_meeting_summary_service.py` for live-to-final transition rules, language propagation, and finalization fallback when no live summary exists
- `tests/unit/repo/test_meeting_summary_repo.py` for revision storage, unique keys, latest-live lookup, and idempotent promotion to final
- `tests/unit/test_meeting_summary_worker.py` for claim/skip/generate/fail behavior and worker-side obsolete-job discard rules
- `tests/integration/socket_gateway/test_meeting_record_summary_socket.py` for `meeting_record:*` summary event delivery, queued/updating/live/finalizing/final states, and reuse of the same summary surface
- `tests/conftest.py` or equivalent shared fixtures for MongoDB, Redis queue, and socket gateway setup if the existing test harness is not restored

## Summary

Phase 3 should be planned as a durable summary pipeline layered on top of the closed-block transcript pipeline from Phase 2. The key architectural choice is to trigger summary work from persisted transcript progress, store summary state and summary jobs in dedicated collections, and run generation through a dedicated worker instead of inside the live meeting service.

The cleanest plan is: extend the existing `meeting_record:*` socket contract with one summary event surface, debounce on meaningful durable transcript deltas, keep one active summary job per meeting, persist revisioned short-summary snapshots, and make finalization a promotion of the latest live summary whenever transcript coverage already matches the meeting end. The highest-risk area is the transcript-persistence race; planning should explicitly close that gap before worker orchestration is added.

## Sources

- `.planning/phases/03-summary-foundation/03-CONTEXT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- `.planning/PROJECT.md`
- `.planning/phases/02-live-transcript-capture/02-CONTEXT.md`
- `.planning/phases/02-live-transcript-capture/02-RESEARCH.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/STRUCTURE.md`
- `.planning/codebase/CONVENTIONS.md`
- `app/services/meeting/meeting_service.py`
- `app/services/meeting/transcript_service.py`
- `app/repo/meeting_transcript_repo.py`
- `app/common/event_socket.py`
- `app/socket_gateway/server.py`
- `app/infrastructure/redis/redis_queue.py`
- `app/infrastructure/llm/factory.py`
- `app/workers/image_generation_worker.py`
- `.planning/config.json`
- `tests/` tree inspection (`tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, and cached `__pycache__` filenames)
