## Why

The current lead-agent API is thread-centric: clients must first create a
thread, then submit follow-up turns directly against `thread_id`. That keeps
the runtime simple, but it pushes LangGraph runtime details into the frontend
contract and leaves the lead-agent flow without the conversation and message
history shape that the existing chat experience already uses.

The product now needs lead agent to feel like the existing chat API for the
frontend: send one message, get realtime streaming over socket events, list
lead-agent conversations, and read persisted message history by
`conversation_id`. At the same time, the backend still needs LangGraph
checkpointing and `thread_id` to remain the runtime source of truth for
durable agent state.

## What Changes

- Replace the public lead-agent thread creation and direct thread run contract
  with a conversation-centric API surface that mirrors the existing chat
  pattern:
  - `POST /lead-agent/messages`
  - `GET /lead-agent/conversations`
  - `GET /lead-agent/conversations/{conversation_id}/messages`
- Keep `thread_id` as the internal LangGraph runtime handle, but persist it on
  application-level `conversation` and `message` records so the frontend can
  render and reconcile lead-agent history without depending on checkpoint
  internals
- Extend `LeadAgentService` to own the full lead-agent request lifecycle:
  conversation creation or validation, thread creation or lookup, user message
  persistence, background lead-agent execution, socket streaming, and final
  assistant message persistence
- Treat MongoDB-backed LangGraph checkpoints as the source of truth for runtime
  state, while treating `conversation` and `message` records as FE-facing
  projection data
- Partition conversation browsing by runtime so lead-agent conversation lists
  include only records with `thread_id`, while legacy `/chat/conversations`
  excludes those records to prevent mixed runtime history in one list
- Update models, schemas, repositories, and indexes to support `thread_id`
  projection and runtime-aware conversation filtering

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `lead-agent-runtime`: expose a conversation-centric API and persisted
  FE-facing history projection while preserving thread-native LangGraph
  execution and checkpoint-backed state

## Impact

- **Lead-agent API changes**: replace the thread-create and thread-run client
  flow with chat-style send, list, and history endpoints scoped to lead agent
- **Realtime behavior alignment**: reuse the existing socket streaming contract
  for lead-agent responses so the frontend receives the same event shape it
  already handles for chat
- **Persistence updates**: add `thread_id` to `conversation` and `message`
  records so lead-agent runtime identity can be mapped to FE-visible history
- **Legacy chat isolation**: update conversation list filtering so `/chat`
  continues to show only legacy chat conversations after lead-agent projection
  data is introduced
- **Repository and service changes**: extend `LeadAgentService`,
  conversation/message persistence helpers, and conversation search filters for
  runtime-aware behavior
- **Affected code**: `app/api/v1/ai/lead_agent.py`,
  `app/services/ai/lead_agent_service.py`, `app/api/v1/ai/chat.py`,
  `app/services/ai/chat_service.py`, `app/services/ai/conversation_service.py`,
  `app/domain/models/conversation.py`, `app/domain/models/message.py`,
  `app/domain/schemas/chat.py`, `app/domain/schemas/lead_agent.py`,
  `app/repo/conversation_repo.py`, `app/repo/message_repo.py`, and
  `app/infrastructure/database/mongodb.py`
