## Context

The current lead-agent runtime already has durable checkpoint-backed thread
state, skill-aware middleware, todo-based planning, and optional subagent
orchestration. The remaining gap is that the parent thread transcript grows
without any bounded compaction strategy, even though many turns now include
tool traces, planning updates, and synthesis loops that expand the checkpointed
`messages` history quickly.

The product direction for this change is intentionally narrow:

- compact checkpoint-backed message history before model calls instead of
  adding a separate long-term memory system
- preserve recent local execution context for the lead agent
- keep persisted `todos` authoritative even when older transcript history is
  replaced by a summary message
- preserve the current conversation-centric API, socket contracts, and
  worker-isolation model

Relevant constraints from the current codebase:

- `create_lead_agent()` builds a cached `create_agent(...)` runtime, so the
  design should fit middleware-driven runtime behavior rather than per-thread
  custom graph construction
- `LeadAgentService` already owns conversation projection, message persistence,
  socket emission, and checkpoint access, so compaction should not move the
  frontend source of history away from the existing conversation/message model
- `TodoListMiddleware` persists `todos` into checkpoint state, but the model
  currently relies on prompt/tool-message context to remain aware of plan state
  during later turns
- delegated workers already return concise bounded summaries, so the main
  compaction pressure is on the parent lead-agent thread

## Goals / Non-Goals

**Goals:**
- Add automatic checkpoint-context compaction for the lead-agent runtime before
  model reasoning
- Reuse LangChain `SummarizationMiddleware` instead of building a custom
  transcript-rewrite subsystem in phase 1
- Keep recent execution context in raw message form while replacing older
  history with a bounded summary message
- Ensure the current persisted todo snapshot remains explicit model-visible
  runtime context after transcript compaction
- Preserve checkpoint state as the runtime source of truth and keep
  conversation/message persistence as a frontend-facing projection only
- Keep rollout additive and backward-compatible for existing lead-agent
  endpoints and socket event contracts

**Non-Goals:**
- Build long-term semantic memory, retrieval augmentation, or a separate memory
  store in this phase
- Expose a user-facing memory management API or editable summary history
- Redesign the worker orchestration model, socket transport, or conversation
  projection architecture
- Reconstruct plan state from assistant text, tool traces, or conversation
  history instead of checkpoint state
- Introduce a custom summarization service or per-thread runtime compilation
  before validating the middleware-based approach

## Decisions

### D1: Use `SummarizationMiddleware` inside the lead-agent middleware stack

**Decision**: The lead-agent runtime will attach LangChain
`SummarizationMiddleware` so older checkpointed `messages` can be replaced
before model calls with a bounded summary plus a recent message window.

Recommended configuration shape:

- trigger summarization using stable thresholds such as message count
- keep a bounded suffix of recent messages in raw form
- trim the summarization input used to generate the replacement summary so the
  summarization step itself stays bounded

**Rationale:**
- the middleware already knows how to replace message history using
  `RemoveMessage(REMOVE_ALL_MESSAGES)` and preserve safe AI/tool boundaries
- it fits the existing `create_agent(..., middleware=[...])` construction
  pattern with minimal architecture disruption
- it keeps compaction inside the runtime state lifecycle rather than bolting on
  transcript rewrites in the service layer

**Alternatives considered:**
- **Custom service-side compaction before every invocation**: rejected because
  it duplicates runtime state management and increases race-condition risk
  around checkpoint updates
- **Separate long-term memory or retrieval layer**: rejected for phase 1
  because the immediate problem is checkpoint-context bloat, not semantic recall

### D2: Replace the static middleware constant with a middleware factory

**Decision**: The lead-agent runtime will stop using a single static
`LEAD_AGENT_MIDDLEWARE` constant and instead build the middleware stack through
one factory that accepts the summarization model dependency.

Recommended shape:

- `create_lead_agent()` resolves the runtime model first
- a new middleware factory builds the middleware list for that model
- summarization is configured in the same factory as the existing skill,
  planning, orchestration, and tool-filtering middleware

**Rationale:**
- `SummarizationMiddleware` requires a model instance or model identifier at
  initialization time
- the current static middleware constant cannot express model-dependent
  configuration cleanly
- a factory keeps middleware order explicit and testable

**Alternatives considered:**
- **Keep a static middleware constant and create summarization elsewhere**:
  rejected because it makes runtime configuration implicit and harder to reason
  about
- **Compile separate summarizer-only runtimes per thread**: rejected because it
  does not fit the cached runtime model already used by `LeadAgentService`

### D3: Use a lead-agent-specific summarization prompt rather than the generic default

**Decision**: The runtime will configure `SummarizationMiddleware` with a
lead-agent-specific summary prompt so compacted history preserves the session
intent, key decisions, retained constraints, important tool findings, and next
steps needed for continued execution.

The summary prompt should explicitly deprioritize:

- verbose raw tool traces
- token-level streaming artifacts
- redundant planning tool echoes
- low-signal repeated coordination chatter

**Rationale:**
- the generic middleware prompt is useful as a base pattern, but lead-agent
  turns care more about preserved execution intent and coordination context than
  generic conversational summaries
- the lead-agent runtime now includes skills, planning, and subagent
  orchestration, so losing decision context is more dangerous than losing raw
  phrasing

**Alternatives considered:**
- **Use the package default prompt unchanged**: rejected because it is not
  tailored to the lead-agent execution model
- **Store raw extracted metadata in a new summary state field**: rejected for
  phase 1 because summary replacement in `messages` is sufficient for the first
  rollout

### D4: Inject checkpoint-backed todo state into the model prompt on every turn

**Decision**: Add a dedicated lead-agent middleware that reads the current
checkpoint-backed `todos` snapshot from runtime state and injects it into the
system prompt as authoritative planning context for each model call.

Recommended behavior:

- render a bounded todo summary section from `state["todos"]`
- present counts and ordered todo items
- instruct the model to treat this snapshot as more authoritative than older
  transcript references
- keep the prompt bounded so large todo lists do not become a new source of
  context bloat

**Rationale:**
- transcript compaction can remove older `write_todos` tool messages, but the
  model still needs explicit visibility into the current plan state
- `todos` are already canonical checkpoint state, so prompt injection should
  project that state directly instead of reconstructing it from transcript
- this preserves planning continuity without introducing a separate planner or
  memory subsystem

**Alternatives considered:**
- **Rely on old tool messages or the summary to carry todo state**: rejected
  because planning continuity becomes hostage to how well summarization preserves
  tool echoes
- **Persist todo state into assistant message metadata only**: rejected because
  message metadata is a projection, not the runtime source of truth

### D5: Keep compaction scoped to checkpoint runtime state, not conversation history

**Decision**: Transcript compaction will only mutate checkpoint-backed runtime
`messages`. The frontend-facing conversation and message records will continue
to be persisted exactly through the existing conversation service path.

**Rationale:**
- this preserves the current contract that conversation/message collections are
  the user-facing browsing history while LangGraph checkpoint state is the
  runtime source of truth
- it avoids confusing user-visible history rewrites when the runtime compacts
  internal context
- it keeps existing list/history endpoints backward-compatible

**Alternatives considered:**
- **Rewrite persisted conversation history to match compacted runtime state**:
  rejected because it would destroy user-facing history semantics
- **Stop persisting assistant/user messages once checkpoint state exists**:
  rejected because the current frontend depends on conversation projections

### D6: Prefer message-count triggering before provider-dependent token fractions

**Decision**: The first rollout will use explicit message-count thresholds for
  summarization triggering and retention, with bounded trim tokens for the
  summarization prompt itself.

**Rationale:**
- the runtime spans multiple model providers and current configuration does not
  guarantee a stable `max_input_tokens` profile for all of them
- message-count thresholds are easier to reason about and tune in production
  traces
- the first rollout values operational predictability more than perfect token
  packing efficiency

**Alternatives considered:**
- **Use fractional max-input thresholds immediately**: rejected because model
  profile limits are not the most stable cross-provider contract here
- **Disable summarization input trimming**: rejected because the summarization
  step itself could become too large or expensive

## Risks / Trade-offs

- **[Summary loses important old context]** → Mitigation: use a lead-agent
  specific summary prompt, keep a recent raw message suffix, and tune thresholds
  using runtime traces
- **[Todo prompt injection becomes a new source of prompt bloat]** → Mitigation:
  bound rendered todo context and prefer compact summary/count formatting when
  the list grows
- **[Middleware ordering produces stale or conflicting prompt state]** →
  Mitigation: build middleware through one ordered factory and add integration
  tests that inspect effective prompt composition and tool visibility
- **[Compaction behavior differs across model providers]** → Mitigation: start
  with message-count triggers and provider-agnostic bounded settings before
  token-based optimization
- **[Runtime summary diverges from user-facing history]** → Mitigation: keep the
  split explicit in design and tests: checkpoint state is runtime context,
  conversation/message records are user-facing projection

## Migration Plan

1. Replace the static lead-agent middleware list with a runtime middleware
   factory.
2. Attach `SummarizationMiddleware` with lead-agent-specific configuration.
3. Add todo-state prompt injection middleware and place it in the ordered stack
   with planning and skill-aware middleware.
4. Add or update tests that cover transcript compaction, todo continuity after
   compaction, and stable conversation projection behavior.
5. Roll out behind configuration defaults that are conservative enough to tune
   without breaking current lead-agent flows.

Rollback strategy:

- remove `SummarizationMiddleware` from the runtime middleware factory
- remove the todo-state injection middleware
- keep all existing conversation/message projection behavior unchanged
- no data migration is required because compacted state lives only in checkpoint
  runtime context

## Open Questions

- Should the summarization layer eventually use a cheaper dedicated model than
  the primary lead-agent runtime model once the behavior is validated?
- What production threshold values should be the initial default for trigger,
  keep, and summarization-input trimming after trace-based evaluation?
- Do we want to expose compacted-summary diagnostics in internal observability
  metadata, or keep compaction fully invisible outside runtime traces in phase
  1?
