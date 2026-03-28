## Context

The codebase currently has two different AI interaction models:

- legacy chat is conversation-centric and persists application-level
  `conversation` and `message` records before and after agent execution
- lead agent is thread-centric and uses LangGraph checkpoint state keyed by
  `thread_id`, with no FE-facing conversation history projection

Today this creates a product mismatch. The frontend already knows how to work
with a chat-style flow:

- `POST /messages`
- list conversations
- read messages by `conversation_id`
- receive streamed agent output via existing socket events

But the current lead-agent API instead exposes:

- `POST /lead-agent/threads`
- `POST /lead-agent/threads/{thread_id}/runs`

This means the client must understand LangGraph runtime handles directly, and
the lead-agent path cannot be browsed through the same conversation/message UX
shape that the existing chat flow already uses.

At the same time, the runtime constraint from the previous change remains
important:

- LangGraph checkpoint state must remain the source of truth for lead-agent
  multi-turn execution
- `thread_id` must continue to identify the durable runtime thread
- lead agent must remain a separate runtime path from the legacy
  `conversation_orchestrator_workflow`

This change therefore introduces a projection layer for FE history while
keeping the underlying runtime thread-native.

## Goals / Non-Goals

**Goals:**
- Replace the public lead-agent thread-centric API with a conversation-centric
  API that mirrors the existing chat interaction pattern
- Keep `thread_id` as the internal LangGraph runtime handle while persisting it
  onto `conversation` and `message` records for FE consumption
- Reuse the existing chat socket event contract for lead-agent streaming
- Keep `LeadAgentService` as the single orchestration point for the lead-agent
  flow instead of introducing a second HTTP-facing service
- Ensure `/lead-agent/conversations` only returns lead-agent projection
  records and `/chat/conversations` excludes them
- Preserve user and organization scoping across both the projection data and
  checkpoint runtime state

**Non-Goals:**
- Replace or merge the legacy `ChatService` and lead-agent runtime into one
  shared service
- Move lead-agent runtime state into the `conversation` or `message`
  collections
- Change the socket event names or payload contract used by the frontend for
  message streaming
- Introduce a new discriminator field such as `runtime_type` in this phase
- Add thread browsing directly from LangGraph checkpoints
- Add migration of old lead-agent checkpoint-only threads into conversation
  records as part of this first refactor

## Decisions

### D1: Keep `LeadAgentService` as the single orchestration and runtime service

**Decision**: Extend `LeadAgentService` instead of adding a separate
`LeadAgentChatService`.

`LeadAgentService` will own:

- conversation creation or validation
- thread creation or lookup
- user message persistence
- background lead-agent execution
- socket event emission
- assistant message persistence
- lead-agent conversation list and message history reads

It will continue to own:

- thread state seeding
- thread scope validation
- agent invocation against the LangGraph checkpointer

**Rationale**:
- the user explicitly wants orchestration to stay in `LeadAgentService`
- the lead-agent flow is still one vertical with one runtime owner
- splitting the orchestration into two services would add coordination
  overhead without reducing conceptual complexity for this change

**Alternatives considered:**
- **Create `LeadAgentChatService`**: cleaner transport separation, but rejected
  because it introduces an extra service boundary the user does not want
- **Move orchestration into the router**: rejected because it would duplicate
  authorization and persistence logic and make the async lifecycle harder to
  test

### D2: `conversation_id` becomes the public lead-agent handle, `thread_id` stays internal

**Decision**: The public lead-agent send/history/list API will use
`conversation_id`, while `thread_id` remains the backend's LangGraph runtime
handle.

The first send-message request will:
1. create a new `thread_id`
2. create a new conversation record with that `thread_id`
3. persist the user message with the same `thread_id`
4. return `conversation_id` and `user_message_id`

Subsequent requests will:
1. load the conversation by `conversation_id`
2. verify ownership and organization scope
3. read `thread_id` from that conversation
4. continue the same runtime thread

The API will not require the client to send `thread_id` for normal operation.

**Rationale**:
- the FE already thinks in terms of conversations and messages
- `thread_id` is an implementation detail of durable runtime state, not a UX
  identifier
- storing the mapping in application records lets the backend evolve the graph
  runtime without forcing client contract changes

**Alternatives considered:**
- **Keep exposing `thread_id` and add separate list/history endpoints**:
  rejected because it still leaks runtime internals into the frontend contract
- **Replace `thread_id` with `conversation_id` inside LangGraph config**:
  rejected because `thread_id` is the documented checkpointer handle and should
  remain explicit in the runtime layer

### D3: Checkpoint state remains the source of truth; conversation/message become FE-facing projections

**Decision**: Lead-agent runtime state will continue to live in LangGraph
checkpoints. Application-level `conversation` and `message` records become a
projection layer only.

Projection behavior:
- `conversation.thread_id` stores the runtime thread mapping
- `message.thread_id` stores the same mapping on each persisted turn
- message history endpoints read from persisted `message` records
- runtime continuation reads from checkpoint state, not from persisted messages

**Rationale**:
- this preserves the architectural contract of the previous lead-agent change
- FE history and runtime state have different optimization goals
- checkpoint-driven continuation avoids duplicating history-rebuild logic in
  the service layer

**Alternatives considered:**
- **Reconstruct runtime state from persisted messages**: rejected because it
  undermines the checkpoint-based runtime model
- **Avoid projection entirely and read history from checkpoints**: rejected
  because FE needs stable application IDs and list/history semantics

### D4: Reuse the chat-style async HTTP lifecycle and existing socket contract

**Decision**: `POST /lead-agent/messages` will follow the same high-level
transport pattern as the existing chat send endpoint:

- save the user message immediately
- return `conversation_id` and `user_message_id`
- continue agent execution asynchronously via `BackgroundTasks`
- stream progress and completion over the existing `chat:message:*` events

Lead-agent processing will reuse:
- `chat:message:started`
- `chat:message:token`
- `chat:message:tool_start`
- `chat:message:tool_end`
- `chat:message:completed`
- `chat:message:failed`

All events stay keyed by `conversation_id`.

**Implementation direction**:
- the lead-agent router will gain a `BackgroundTasks` dependency, like
  `chat.py`
- `LeadAgentService.send_message(...)` will persist the user turn and return
  identifiers
- `LeadAgentService.process_agent_response(...)` will run in the background
  and emit socket events
- lead-agent streaming will use `agent.astream_events(..., version="v2")`
  directly inside `LeadAgentService` because there is no branch-local graph
  node layer like the orchestrator path

**Rationale**:
- this gives FE one consistent realtime contract across chat and lead agent
- it avoids inventing a second socket protocol for nearly identical UX
- it keeps lead-agent transport semantics aligned with the repo's existing API
  style

**Alternatives considered:**
- **Keep synchronous `run_thread` responses**: rejected because the user wants
  lead-agent to behave like chat with socket streaming
- **Invent lead-agent-specific socket event names**: rejected because it adds
  frontend branching with little value

### D5: Add `thread_id` as an additive field on both conversation and message models

**Decision**: Extend the durable application models with optional `thread_id`
fields:

- `Conversation.thread_id: str | None`
- `Message.thread_id: str | None`

The field is additive and optional to preserve compatibility with legacy chat
records that have no runtime thread mapping.

**Implementation direction**:
- extend domain models and response schemas
- extend repository create/update methods so lead-agent flows can persist
  `thread_id`
- treat missing `thread_id` on older documents as legacy chat data

**Rationale**:
- FE needs the thread mapping available on both conversation summaries and
  turn-level records
- optional additive fields minimize migration risk and keep old records valid

**Alternatives considered:**
- **Store `thread_id` only on conversations**: rejected because the user wants
  it available on messages too for FE use
- **Store `thread_id` only in checkpoint metadata**: rejected because FE
  cannot browse checkpoint state directly

### D6: Partition legacy chat and lead-agent browsing using `thread_id` presence

**Decision**: The runtime discriminator for browsing will be `thread_id`
presence:

- lead-agent conversations: `thread_id != null`
- legacy chat conversations: `thread_id == null` or field absent

This filtering will be enforced in the repository/service layer, not only in
routers.

**Implementation direction**:
- add an optional runtime filter parameter, e.g. `has_thread_id: bool | None`,
  to conversation search methods
- `LeadAgentService.search_conversations(...)` will call with
  `has_thread_id=True`
- `ChatService.search_conversations(...)` will call with
  `has_thread_id=False`
- both history endpoints will verify the conversation belongs to the expected
  runtime class before returning messages

**Rationale**:
- without the reverse filter, `/chat/conversations` would start returning
  lead-agent projection records
- centralizing this rule in data access prevents drift across routes

**Alternatives considered:**
- **Add a new `runtime_type` field immediately**: clearer long term, but
  rejected for this phase because `thread_id` already exists as the required
  lead-agent discriminator
- **Filter only in lead-agent endpoints**: rejected because legacy chat would
  still leak lead-agent conversations

### D7: Keep conversation/message helper reuse, but extend them for lead-agent projection writes

**Decision**: Reuse the existing conversation and message persistence helpers
where possible, but extend them to accept `thread_id` so lead-agent writes do
not bypass shared behavior such as:

- message count updates
- `last_message_at` updates
- default title generation from the first user turn

**Implementation direction**:
- extend `ConversationRepository.create(...)` to accept optional `thread_id`
- extend `MessageRepository.create(...)` to accept optional `thread_id`
- extend `ConversationService.create_conversation(...)` and
  `ConversationService.add_message(...)` to forward optional `thread_id`
- keep title generation behavior unchanged so lead-agent gets the same
  conversation title UX as chat

**Rationale**:
- the repo already has solid conversation/message accounting logic
- reusing that logic reduces duplicate behavior and keeps the FE history model
  consistent

**Alternatives considered:**
- **Write directly to repos only from `LeadAgentService`**: possible, but
  rejected because it would duplicate title/stat update behavior that already
  exists in `ConversationService`

### D8: Add direct lead-agent background streaming inside `LeadAgentService`

**Decision**: `LeadAgentService` will gain a dedicated background processing
method, conceptually similar to `ChatService.process_agent_response(...)`, but
implemented directly against the lead-agent runtime.

Proposed flow:
1. emit `chat:message:started`
2. load conversation and verify it maps to a valid `thread_id`
3. load checkpoint thread state and validate caller scope
4. stream the lead-agent runtime via `astream_events`
5. emit token and tool events as they occur
6. persist the final assistant message with `thread_id`
7. emit `chat:message:completed`
8. on failure, emit `chat:message:failed`

The service will retain an internal helper for extracting the final assistant
response, but it will now work alongside streamed event handling.

**Rationale**:
- lead-agent has no orchestrator node boundary to host token emission
- putting streaming inside `LeadAgentService` keeps the entire lead-agent
  lifecycle in one owner, which matches the user's desired structure

**Alternatives considered:**
- **Introduce a dedicated lead-agent workflow node only for streaming**:
  rejected because it adds a graph layer solely to mirror the legacy
  orchestrator structure
- **Stream directly from the router**: rejected because it mixes transport
  concerns into the HTTP layer and complicates reuse/testing

### D9: Treat partial projection persistence failure as a bounded consistency risk

**Decision**: The system will accept that checkpoint state and FE-facing
projection records are two separate durable layers.

Consistency model:
- user message must be persisted before background execution starts
- assistant message is persisted only after runtime completion
- if background execution fails, the conversation can remain with only the
  user message and a failed socket event

This is acceptable for the first iteration as long as:
- runtime continuation still works from checkpoint state
- FE gets an explicit failed event
- logs capture the failure for operator debugging

**Rationale**:
- introducing distributed transaction behavior across checkpoint storage and
  application collections is too heavy for this change
- the existing chat flow already tolerates post-acceptance background failure

**Alternatives considered:**
- **Attempt transactional coupling across both layers**: rejected because the
  checkpoint and application collections are not managed as one atomic domain
- **Write assistant placeholder rows before execution**: rejected because the
  current product pattern does not require partial assistant records

### D10: Add runtime-aware indexes for conversation listing while keeping message history keyed by conversation

**Decision**: Conversation list queries need index support for the new
`thread_id`-presence filtering, while message history can continue to use the
existing `conversation_id + created_at` access pattern.

**Implementation direction**:
- keep the existing message index because history reads still key by
  `conversation_id`
- add a conversation index that supports scoped list queries with
  `user_id`, `organization_id`, `deleted_at`, optional `thread_id`, and
  `updated_at`
- allow missing `thread_id` to continue matching old legacy chat documents

**Rationale**:
- list endpoints are the new place where runtime partitioning becomes a query
  concern
- message retrieval does not change its primary lookup shape

**Alternatives considered:**
- **No new conversation index**: rejected because runtime filtering could make
  list queries slower as data grows
- **Query messages by `thread_id`**: rejected because the public history API is
  conversation-based, not thread-based

## Risks / Trade-offs

**[Projection records can drift from checkpoint state]** ->
Mitigation: keep checkpoint state as the runtime source of truth, emit failed
events when background processing breaks, and centralize lead-agent projection
writes in one service.

**[Using `thread_id` presence as the runtime discriminator is less expressive
than a dedicated field]** -> Mitigation: keep repository filters isolated so a
future migration to `runtime_type` can happen behind one query boundary.

**[Lead-agent streaming logic inside `LeadAgentService` makes the service
broader]** -> Mitigation: keep internal helper methods separate for send,
stream, validation, and persistence so the service remains internally modular
even without adding another class.

**[Existing legacy chat queries may accidentally leak lead-agent records if one
call site forgets to pass the runtime filter]** -> Mitigation: update the
public service methods used by routers so runtime-aware defaults are applied
consistently at the service boundary.

**[Older documents will not have `thread_id`]** -> Mitigation: treat missing
`thread_id` as legacy chat by design and keep the new fields optional.

**[Checkpoint-only lead-agent threads created before this change will not
automatically appear in conversation lists]** -> Mitigation: treat this as an
accepted compatibility constraint for phase 1 and document it clearly.

## Migration Plan

1. Extend conversation and message domain models with optional `thread_id`.
2. Extend request/response schemas for lead-agent send/list/history and include
   `thread_id` where FE needs it.
3. Extend repository create/search methods:
   - conversation create accepts `thread_id`
   - message create accepts `thread_id`
   - conversation search accepts runtime-aware filtering
4. Extend `ConversationService` so shared conversation/message persistence can
   carry `thread_id` without losing existing title/stat behaviors.
5. Refactor `LeadAgentService`:
   - keep thread creation and scope validation helpers
   - add `send_message(...)`
   - add background `process_agent_response(...)`
   - add lead-agent conversation list/history reads
   - add streamed runtime execution helpers
6. Replace the lead-agent router contract with:
   - `POST /lead-agent/messages`
   - `GET /lead-agent/conversations`
   - `GET /lead-agent/conversations/{conversation_id}/messages`
7. Update legacy chat service/router calls so `/chat/conversations` and
   `/chat/.../messages` exclude lead-agent projection records.
8. Add or update MongoDB indexes for runtime-aware conversation listing.
9. Verify:
   - first lead-agent send creates conversation and thread
   - follow-up sends reuse stored `thread_id`
   - lead-agent responses stream over existing chat socket events
   - lead-agent conversations appear only in lead-agent list endpoints
   - legacy chat endpoints exclude lead-agent records
   - checkpoint state remains sufficient for runtime continuation

**Rollback**
- restore the old lead-agent thread endpoints
- remove new lead-agent conversation endpoints
- stop writing `thread_id` projection fields
- keep additive `thread_id` data in Mongo as harmless leftover metadata if
  rollback must happen after deployment

## Open Questions

- Should lead-agent list and message responses expose `thread_id` directly to
  the FE on day one, or is it sufficient to store it durably without returning
  it in every response shape?
- If the team later wants to show checkpoint-only historical lead-agent
  sessions, do we backfill conversation projections lazily on first access or
  run a one-time migration job?
