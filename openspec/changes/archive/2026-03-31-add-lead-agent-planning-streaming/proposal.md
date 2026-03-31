## Why

The lead-agent runtime already has durable checkpoint-backed thread state,
skill-aware middleware, and FE-facing conversation projection, but it still
lacks a canonical planning layer for multi-step work. As the lead agent gains
more tools and skill-guided workflows, users and the frontend need durable
visibility into what the agent plans to do, what step is currently active, and
how that plan changes during execution.

Reusing LangChain's built-in `TodoListMiddleware` solves this with less
architecture risk than introducing a custom planner. It lets the backend keep
planning state inside the existing LangGraph checkpoint model while exposing a
stable UI projection only after plan updates have actually been persisted.

## What Changes

- Add an internal lead-agent planning layer by attaching LangChain
  `TodoListMiddleware` with lead-agent-specific planning instructions and tool
  description
- Treat checkpoint-backed `todos` state as the source of truth for planning and
  use it only for complex multi-step turns instead of every user message
- Stream FE-facing plan snapshots only after `write_todos` completes and the
  updated `todos` state has been persisted, using a dedicated socket event
  keyed by `conversation_id`
- Add a history/read path so the frontend can reload the latest persisted plan
  snapshot for an existing lead-agent conversation
- Update skill-aware tool exposure rules so `write_todos` remains available as
  part of the lead-agent base orchestration surface without breaking
  skill-scoped tool filtering
- Preserve the current conversation-centric lead-agent API, existing assistant
  token streaming flow, and checkpoint-backed runtime model without adding a
  separate planning datastore in phase 1

## Capabilities

### New Capabilities
- `lead-agent-planning`: provide internal todo-based planning for complex
  lead-agent turns, durable checkpoint-backed todo state, and FE-facing plan
  projection/streaming

### Modified Capabilities
- `lead-agent-runtime`: extend runtime requirements so lead-agent can surface
  persisted planning state in realtime and on reload while preserving existing
  conversation-backed response projection
- `lead-agent-skills`: adjust requirement-level tool exposure behavior so
  planning remains available alongside skill-aware tool filtering

## Impact

- **Runtime behavior**: lead-agent gains a first-class planning state for
  complex work instead of relying only on implicit reasoning or assistant text
- **Socket contract**: add a new plan-update style event emitted only after a
  persisted todo snapshot is available
- **History projection**: frontend can rehydrate the latest plan state for a
  conversation without reconstructing it from assistant text or raw tool traces
- **Checkpoint state**: LangGraph thread state gains durable `todos` data but
  phase 1 does not introduce a separate planner collection
- **No public API break by default**: existing send-message and chat-response
  flow remains intact while planning stays backend-managed
- **Affected code**: `app/agents/implementations/lead_agent/agent.py`,
  `app/agents/implementations/lead_agent/middleware.py`,
  `app/agents/implementations/lead_agent/state.py`,
  `app/services/ai/lead_agent_service.py`,
  `app/common/event_socket.py`, related lead-agent API/schema modules, and new
  OpenSpec delta specs under `openspec/changes/add-lead-agent-planning-streaming/specs/`
