## Why

The current AI chat flow is centered around application-managed
`conversation` and `message` persistence, with
`conversation_orchestrator_workflow` acting as the main entrypoint. That model
works for explicit graph-based routing, but it is not a good fit for a new
lead agent runtime that should behave more like a durable, thread-native
agent.

The new lead agent needs to use LangGraph thread persistence and checkpointing
as its source of truth so it can evolve independently from the legacy
conversation model. This lets the system support a more flexible agent
execution path without forcing the existing orchestrator workflow to absorb a
different runtime model.

## What Changes

- Add a new `lead_agent` implementation under `app/agents/implementations/`
  built with `langchain.agents.create_agent`
- Define a custom lead-agent state schema by extending `AgentState` for
  thread-scoped metadata such as `user_id` and optional `organization_id`
- Introduce a MongoDB-backed LangGraph checkpointer so lead-agent thread state
  is persisted in MongoDB instead of the existing application-managed
  conversation/message collections
- Add a dedicated service and API path for lead-agent thread creation and new
  thread input submission
- Keep the initial lead-agent runtime intentionally minimal with empty tool and
  middleware registries so the runtime contract can land before capability
  expansion
- Preserve the existing `conversation_orchestrator_workflow` and chat service
  path as a separate legacy runtime

## Capabilities

### New Capabilities
- `lead-agent-runtime`: Create and run a thread-native lead agent using
  LangChain `create_agent`, LangGraph thread IDs, and MongoDB-backed
  checkpoint persistence

### Modified Capabilities
- None.

## Impact

- **New runtime path**: add a lead-agent vertical that does not depend on
  application-managed conversation/message persistence
- **New API surface**: add endpoints to create a lead-agent thread and submit
  new user input to an existing thread
- **Persistence changes**: introduce MongoDB collections for LangGraph
  checkpoints and thread state managed by the checkpointer
- **Service and infrastructure additions**: add a lead-agent service and a
  MongoDB checkpointer factory or manager for durable runtime state
- **Initial scope constraints**: V1 does not add custom tools, middleware,
  conversation listing, message history endpoints, or migration of the legacy
  orchestrator flow
- **Affected code**: `app/agents/implementations/`, `app/services/ai/`,
  `app/api/v1/ai/`, `app/common/service.py`, and new LangGraph/MongoDB
  infrastructure wiring
