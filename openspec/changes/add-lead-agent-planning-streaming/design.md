## Context

The current lead-agent runtime already has the right architectural seams for
adding planning without introducing a second orchestration subsystem:

- `create_lead_agent()` builds a cached `create_agent(...)` runtime with
  middleware, tool registration, and a MongoDB-backed LangGraph checkpointer
- `LeadAgentService` owns conversation validation, message persistence,
  checkpoint lookups, background execution, and socket event emission
- checkpointed thread state is already the runtime source of truth, while
  conversation and message records are FE-facing projections
- skill-aware execution already exists through prompt injection, `load_skill`,
  and tool filtering

The missing piece is a durable planning layer that the backend and frontend can
both trust. The product decision for this change is:

- planning will reuse LangChain `TodoListMiddleware`
- `todos` in checkpoint state will be the canonical plan record
- plan updates will be emitted only after `write_todos` has finished and the
  updated state is already persisted
- the frontend needs both realtime updates and a reload path for the latest
  plan snapshot

Constraints and realities from the current codebase:

- `LeadAgentService` caches a compiled runtime, so the design should not depend
  on per-user or per-thread agent compilation
- the current tool filtering middleware only exposes a narrow base surface, so
  planning will break unless `write_todos` is explicitly preserved
- the existing socket contract already supports chat-scoped events keyed by
  `conversation_id`, which is the correct place to add plan projection
- no separate plan datastore is desired in phase 1

## Goals / Non-Goals

**Goals:**
- Add durable todo-based planning to lead-agent without replacing the current
  runtime architecture
- Reuse LangChain `TodoListMiddleware` directly instead of building a custom
  planner or tool
- Keep checkpoint state as the source of truth for plan persistence and reload
- Stream plan updates to the UI only after persistence has completed
- Preserve skill-aware execution and ensure trusted coordination tools remain
  available
- Keep rollout additive and backward-compatible for existing lead-agent flows

**Non-Goals:**
- Build a standalone planning datastore, planner microservice, or custom todo
  engine
- Emit optimistic plan events before checkpoint persistence
- Make the client responsible for constructing or patching todo state
- Add user-editable plan management in phase 1
- Introduce a separate planning classifier or specialist planning agent before
  validating the simpler middleware-based approach

## Decisions

### D1: Reuse `TodoListMiddleware` directly and configure it, do not subclass it

**Decision**: The runtime will attach LangChain `TodoListMiddleware` directly
and configure it with lead-agent-specific `system_prompt` and
`tool_description`. We will not create a custom planning tool and we will not
subclass the middleware unless a later requirement cannot be expressed through
configuration.

Recommended runtime shape:

- keep `LeadAgentSkillPromptMiddleware`
- add `TodoListMiddleware(system_prompt=..., tool_description=...)`
- keep `LeadAgentToolSelectionMiddleware`

**Rationale**:
- the middleware already injects `write_todos` and the corresponding planning
  state model
- configuration is enough for the current product decisions
- avoiding subclassing reduces maintenance risk when LangChain updates its
  built-in planning behavior

**Alternatives considered:**
- **Subclass `TodoListMiddleware` immediately**: rejected because there is no
  current requirement that needs hook-level behavior changes
- **Implement a custom `write_todos` tool**: rejected because it duplicates
  LangChain behavior and creates unnecessary compatibility risk

### D2: Keep planning state in checkpoint storage and do not duplicate the schema in application persistence

**Decision**: The canonical plan record will be `todos` in LangGraph
checkpoint state. The backend may project this state into socket payloads or a
read endpoint, but it will not persist a second source of truth in message
metadata or a separate collection in phase 1.

Implementation detail:

- `LeadAgentState` remains focused on application-specific fields
- planning state is contributed by middleware and merged into the runtime state
  model by LangChain/LangGraph
- no manual `todos` declaration is required for runtime correctness

**Rationale**:
- this matches the existing lead-agent contract that checkpoint state is the
  source of truth and conversations/messages are projections
- it avoids consistency bugs between plan state and runtime state
- it preserves the ability to resume existing threads from checkpoint alone

**Alternatives considered:**
- **Store plan snapshots in message metadata as canonical state**: rejected
  because assistant message persistence is not the runtime source of truth
- **Create a dedicated plan collection**: rejected for phase 1 because it adds
  write amplification, reconciliation complexity, and a second persistence
  model without a clear product need

### D3: Emit plan updates from `LeadAgentService` after persisted state is observable

**Decision**: Plan streaming will be implemented in `LeadAgentService`, inside
the existing `_stream_thread_execution(...)` event loop. The service will
observe tool activity, detect `write_todos`, read the latest checkpoint state
after tool completion, compare it with the previous snapshot, and emit a
dedicated socket event only when the persisted snapshot has changed.

Proposed flow:

1. Load `last_todos` from checkpoint before streaming begins
2. Continue handling token and tool events as today
3. When `on_tool_end` occurs for `write_todos`, call `aget_state(...)`
4. Read the current persisted `todos`
5. If the snapshot differs from `last_todos`, emit `chat:message:plan_updated`
6. Replace `last_todos` with the new snapshot and continue execution

**Rationale**:
- the service already owns socket emission and checkpoint access, so it is the
  lowest-risk place to add plan projection
- emitting only after `on_tool_end` enforces the product rule that the UI sees
  persisted state, not speculative input
- diffing snapshots avoids redundant UI updates when a tool call does not
  change the todo list

**Alternatives considered:**
- **Emit from `on_tool_start` using tool arguments**: rejected because it would
  expose optimistic state before persistence
- **Poll checkpoint storage from the frontend**: rejected because it adds
  latency, waste, and duplicated state logic on the client
- **Use LangGraph `custom` stream mode for this phase**: rejected because the
  current lead-agent transport already uses `astream_events(...)`, and adding a
  second streaming path would increase complexity for little gain

### D4: Use full-snapshot plan payloads rather than patch semantics

**Decision**: Every emitted plan update and every history read will return the
full current todo snapshot for the conversation. The UI reducer will replace
its local plan state with the latest server snapshot rather than applying
incremental patches.

Recommended payload shape:

```json
{
  "conversation_id": "conv-123",
  "thread_id": "thread-456",
  "todos": [
    {"content": "Inspect request", "status": "completed"},
    {"content": "Search references", "status": "in_progress"},
    {"content": "Write response", "status": "pending"}
  ],
  "summary": {
    "total": 3,
    "completed": 1,
    "in_progress": 1,
    "pending": 1
  }
}
```

**Rationale**:
- `write_todos` itself replaces the full list, not a single item
- snapshot replacement is easier for frontend state management and reconnect
  flows
- it avoids ordering bugs caused by partial patch application on the client

**Alternatives considered:**
- **Emit add/update/remove patches**: rejected because it does not match the
  underlying tool semantics and complicates replay
- **Parse todo changes from assistant text**: rejected because plan state must
  stay structured and backend-owned

### D5: Add a dedicated conversation-scoped read path for the latest plan snapshot

**Decision**: The backend will add a dedicated authenticated read path for the
latest persisted plan associated with a conversation, rather than trying to
embed the latest plan into every message history response.

Recommended shape:

- `GET /lead-agent/conversations/{conversation_id}/plan`

Response rules:

- return the latest checkpoint-backed snapshot for the mapped thread
- return an empty-but-valid plan representation if no todos exist yet
- remain scoped to authenticated `user_id` and `organization_id`

**Rationale**:
- plan state belongs to thread state, not to one specific assistant message
- a dedicated endpoint keeps message history focused on messages
- the UI can hydrate plan state independently on reload or socket reconnect

**Alternatives considered:**
- **Embed the latest plan in every message list response**: rejected because it
  couples unrelated projections and bloats a frequently used endpoint
- **Only rely on socket updates with no read path**: rejected because refresh
  and reconnect need deterministic hydration

### D6: Preserve trusted coordination tools in the skill-aware tool filter

**Decision**: `LeadAgentToolSelectionMiddleware` will treat planning and skill
discovery tools as trusted coordination tools that remain part of the base
surface even when skill-specific filtering is applied. In practice, this means
`write_todos` must be preserved alongside tools such as `load_skill`.

Recommended model:

- base trusted tools: `load_skill`, `write_todos`, and any future backend
  coordination tools
- skill-specific tools: dynamically merged on top of the base set

**Rationale**:
- planning is backend-managed orchestration, not an optional domain tool
- removing `write_todos` from the visible surface would silently disable the
  middleware integration
- this keeps the runtime predictable as more skills and tools are added

**Alternatives considered:**
- **Expose `write_todos` only for some skills**: rejected because planning is a
  runtime capability, not a skill-owned tool
- **Never filter tools**: rejected because prompt clutter and tool confusion
  would scale badly as the runtime grows

### D7: Enforce the "complex tasks only" policy through prompt guidance, not a separate classifier

**Decision**: Planning will be available on every lead-agent turn because the
middleware is attached globally, but the lead-agent-specific todo instructions
will strongly direct the model to use `write_todos` only for complex multi-step
work and to skip it for simple requests.

**Rationale**:
- this matches how LangChain intends `TodoListMiddleware` to be used
- it avoids introducing a second routing or classification layer before there
  is evidence that prompt guidance is insufficient
- it keeps the first rollout simpler and easier to tune using evals

**Alternatives considered:**
- **Add a hard backend complexity classifier before every turn**: rejected for
  phase 1 because it increases latency, maintenance cost, and failure modes
- **Always force a plan on every turn**: rejected because it wastes tokens and
  adds UI noise for trivial tasks

## Risks / Trade-offs

- **[Planning prompt collides with skill prompt composition]** → Mitigation:
  keep middleware ordering explicit, add integration tests that inspect the
  effective prompt/tool surface, and avoid custom prompt-merging logic inside
  the planning middleware
- **[Plan update event fires redundantly or misses changes]** → Mitigation:
  compare the previous and current persisted snapshots after each
  `write_todos` completion and emit only when the persisted list changed
- **[Frontend shows stale plan after reload]** → Mitigation: add a dedicated
  plan read endpoint backed directly by checkpoint state and use it for initial
  hydration and reconnect recovery
- **[Planning is silently unavailable because of tool filtering]** →
  Mitigation: treat `write_todos` as a trusted base coordination tool and add
  tests that verify it remains visible across skill states
- **[Token and latency cost increase on simple turns]** → Mitigation: encode
  "complex tasks only" policy in the todo instructions and evaluate turn traces
  to tune prompt wording before broad rollout
- **[Existing conversations have no plan state]** → Mitigation: define a valid
  empty snapshot contract so older or simpler threads continue working without
  migration

## Migration Plan

1. Add the planning middleware to the lead-agent runtime and preserve
   `write_todos` in the trusted base tool surface.
2. Extend service-layer streaming to detect persisted todo changes and emit the
   new plan update socket event.
3. Add the authenticated read path for the latest plan snapshot of a
   conversation.
4. Update response schemas and frontend integration to consume snapshot-based
   plan hydration and realtime updates.
5. Roll out behind a backend feature flag if needed, with trace-based
   verification on complex and simple turns.

Rollback strategy:

- remove `TodoListMiddleware` from the runtime
- stop emitting the dedicated plan event
- keep the read endpoint returning an empty plan or remove it behind the same
  feature flag
- existing conversations remain valid because no canonical data was moved out
  of checkpoint state

## Open Questions

- Should the completed assistant message also store a compact final plan
  snapshot in metadata for debugging convenience, even though checkpoint state
  remains canonical?
- Does the frontend want a summary-only preview in conversation lists, or is
  plan visibility limited to the active conversation view for phase 1?
