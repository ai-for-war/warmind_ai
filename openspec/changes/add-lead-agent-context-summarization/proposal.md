## Why

The lead-agent runtime now supports durable thread state, planning, and
subagent orchestration, but it still keeps the parent thread transcript in one
growing `messages` history. As turns accumulate, especially around tool usage,
planning updates, and orchestration-heavy work, the runtime risks input-context
overflow and degraded reasoning because old thread context is never compacted
into a durable replacement form.

## What Changes

- Add automatic context compaction for the lead-agent runtime by attaching a
  summarization layer that can replace older checkpointed message history with a
  bounded summary plus a recent message window before model calls
- Define lead-agent-specific summarization behavior so compacted history retains
  the user's session intent, key decisions, important tool findings,
  constraints, and next-step context instead of generic chat summaries
- Preserve planning continuity after transcript compaction by injecting the
  current persisted todo snapshot into the model prompt as authoritative runtime
  context for each turn
- Keep checkpoint-backed thread state as the runtime source of truth while
  continuing to use application-managed conversation and message records only as
  FE-facing projections
- Preserve the existing conversation-centric API, socket contracts, and
  subagent manager-worker model without introducing a separate long-term memory
  store, retrieval layer, or user-facing memory API in phase 1

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `lead-agent-runtime`: extend runtime requirements so lead-agent can compact
  older checkpointed message history into a bounded summary before model calls
  while preserving recent execution context and thread-scoped continuity
- `lead-agent-planning`: extend planning requirements so the current persisted
  todo snapshot remains explicitly available to the runtime prompt even after
  transcript compaction replaces older message history

## Impact

- **Runtime behavior**: lead-agent gains automatic checkpoint-context
  compaction before model reasoning instead of retaining an unbounded transcript
- **Prompt composition**: lead-agent middleware stack must inject both
  summarization behavior and authoritative todo-state context in a stable order
- **State handling**: checkpoint-backed `messages` history may be replaced by a
  summary message plus a recent message window, while `todos` remain canonical
  planning state in checkpoint storage
- **No public API break by default**: existing `POST /lead-agent/messages`,
  conversation history endpoints, and socket event contracts remain intact
- **Affected code**: `app/agents/implementations/lead_agent/agent.py`,
  `app/agents/implementations/lead_agent/middleware.py`, new lead-agent context
  middleware or prompt helpers, `app/prompts/system/lead_agent.py`, and related
  lead-agent tests and runtime wiring
