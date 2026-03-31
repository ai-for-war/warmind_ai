## Purpose

Define the lead-agent runtime that runs independently from the legacy
conversation orchestrator, persists state through LangGraph checkpoints, and
exposes a conversation-centric authenticated API with FE-facing history
projection while keeping checkpointed thread state as the runtime source of
truth.

## Requirements

### Requirement: Thread-native lead agent runtime
The system SHALL provide a new `lead_agent` runtime that is separate from the
legacy `conversation_orchestrator_workflow` path. The lead-agent runtime SHALL
use `langchain.agents.create_agent` as its execution primitive and SHALL be
invoked using a LangGraph `thread_id`.

#### Scenario: Invoke the lead agent on its own runtime path
- **WHEN** the system receives a valid lead-agent request
- **THEN** it invokes the dedicated lead-agent runtime instead of routing the
  request through `conversation_orchestrator_workflow`

#### Scenario: Legacy orchestrator remains available
- **WHEN** the system handles an existing legacy chat request
- **THEN** it continues using the current conversation-orchestrator path
- **AND** the lead-agent runtime does not replace or remove that path

### Requirement: Lead-agent state extends AgentState
The lead-agent runtime SHALL define its state schema by extending
`AgentState`. The custom state SHALL support thread-scoped metadata needed by
the backend, including `user_id` and optional `organization_id`, and SHALL
also support skill-related runtime metadata needed to preserve skill-aware
execution across turns, including enabled skills, active skill identity,
loaded skill history, and skill-scoped tool availability. The runtime state
model, including middleware-contributed state, SHALL also support planning
metadata needed to preserve checkpoint-backed todo state across turns.

#### Scenario: Create the lead-agent with a skill-aware and planning-aware state model
- **WHEN** the lead-agent runtime is initialized
- **THEN** the agent is created with a state schema that extends `AgentState`
- **AND** the runtime state model can represent caller scope, skill-related
  execution metadata, and planning state for the same thread

#### Scenario: Runtime metadata is available in thread state
- **WHEN** the system invokes the lead agent for an authenticated user
- **THEN** the thread state includes the requesting `user_id`
- **AND** the thread state includes `organization_id` when one is provided
- **AND** the thread state can retain both skill-related execution metadata and
  planning metadata across turns for the same thread

### Requirement: MongoDB checkpointer is the source of truth for thread state
The lead-agent runtime SHALL persist runtime state through a MongoDB-backed
LangGraph checkpointer. The lead-agent path MUST use checkpointed thread state
as the source of truth for multi-turn execution, while application-managed
`conversation` and `message` records MAY be created as FE-facing projection
data.

#### Scenario: Resume an existing lead-agent thread from checkpointed state
- **WHEN** the system receives new input for an existing lead-agent
  conversation
- **THEN** the lead-agent runtime resolves the stored `thread_id`
- **AND** the lead-agent runtime loads prior state from the MongoDB
  checkpointer for that thread

#### Scenario: Conversation and message records do not replace checkpoint state
- **WHEN** the system creates or updates application-level `conversation` and
  `message` records for a lead-agent turn
- **THEN** those records act as FE-facing history projection only
- **AND** the system MUST NOT require those records to reconstruct the
  lead-agent runtime state for the next turn

### Requirement: Lead-agent send-message endpoint uses conversation handles
The system SHALL provide an authenticated `POST /lead-agent/messages`
endpoint that accepts `content` and an optional `conversation_id`. The client
MUST NOT be required to provide `thread_id` directly for normal lead-agent
message submission.

#### Scenario: First lead-agent message creates conversation and thread
- **WHEN** an authenticated client submits a lead-agent message without a
  `conversation_id`
- **THEN** the system creates a new application-level `conversation`
- **AND** the system creates a new LangGraph `thread_id`
- **AND** the system associates that `thread_id` with the created
  conversation
- **AND** the system persists the user message
- **AND** the system returns the created `conversation_id` and
  `user_message_id`

#### Scenario: Follow-up lead-agent message reuses conversation-scoped thread
- **WHEN** an authenticated client submits a lead-agent message with a valid
  `conversation_id`
- **THEN** the system loads that conversation
- **AND** the system reuses the conversation's stored `thread_id`
- **AND** the system persists the new user message before background runtime
  execution starts

#### Scenario: Reject non-lead-agent or unknown conversation handles
- **WHEN** an authenticated client submits a lead-agent message with an
  unknown `conversation_id`
- **OR** with a conversation that is outside the caller scope
- **OR** with a conversation that is not mapped to a lead-agent `thread_id`
- **THEN** the system rejects the request with an appropriate not-found style
  error response

### Requirement: Lead-agent conversation and message projections store thread identity
The system SHALL persist the resolved lead-agent `thread_id` on the
application-level `conversation` record and on each persisted lead-agent
`message` record so the frontend can browse history using application IDs
without managing checkpoint identifiers directly.

#### Scenario: New lead-agent conversation stores thread identity
- **WHEN** the system creates a new lead-agent conversation from the first
  message
- **THEN** the created conversation record includes the generated `thread_id`

#### Scenario: Persisted lead-agent messages carry the mapped thread identity
- **WHEN** the system persists a user or assistant message for a lead-agent
  conversation
- **THEN** the created message record includes the conversation's `thread_id`

### Requirement: Lead-agent runtime supports skill-aware tool registration
The lead-agent runtime SHALL register the internal tools required for skill
discovery and skill-aware execution. The runtime MAY register additional
domain tools, but it MUST expose only the tool subset allowed by the current
skill context and caller scope for a given model call.

#### Scenario: Runtime includes internal skill support tools
- **WHEN** the lead-agent runtime is initialized for skill-aware execution
- **THEN** it registers the internal tool surface required to discover or load
  skills during a turn

#### Scenario: Runtime exposes only the allowed tools for a model call
- **WHEN** the lead-agent runtime prepares a model call inside a thread
- **THEN** it exposes only the tools permitted by the current skill context and
  caller scope for that call

### Requirement: Lead-agent runtime supports custom middleware for skill-aware execution
The lead-agent runtime SHALL use custom middleware layers to support
skill-aware execution and todo-based planning. Middleware MUST be able to
inject available skill summaries into runtime context, attach lead-agent
planning instructions and the planning tool surface, and apply dynamic tool
selection before each model call.

#### Scenario: Runtime injects discoverable skill context and planning guidance before model reasoning
- **WHEN** the lead-agent runtime prepares a model call for a caller with
  enabled skills
- **THEN** middleware injects the available skill summaries into the runtime
  context before the model reasons about the turn
- **AND** middleware also preserves the planning guidance needed for todo-based
  execution in that call

#### Scenario: Runtime re-evaluates tool exposure after skill or planning context changes
- **WHEN** the current thread state changes the active skill, allowed tool set,
  or persisted planning context during execution
- **THEN** middleware applies the updated tool exposure rules before the next
  model call
- **AND** trusted runtime coordination tools required by backend policy remain
  available for that call

### Requirement: Lead-agent responses stream through the existing chat socket contract
Lead-agent message processing SHALL stream realtime progress and completion to
the client by reusing the existing chat socket namespace keyed by
`conversation_id`. In addition to the existing started, token, tool, completed,
and failed events, the lead-agent runtime SHALL emit a dedicated plan update
event when a persisted todo snapshot changes.

#### Scenario: Lead-agent response starts after message submission returns
- **WHEN** the system accepts a valid `POST /lead-agent/messages` request
- **THEN** the HTTP response returns without waiting for the final assistant
  text
- **AND** the lead-agent response processing continues asynchronously in the
  background
- **AND** the system emits the existing started event for that
  `conversation_id`

#### Scenario: Lead-agent response emits token and completion events
- **WHEN** the lead-agent runtime generates a streamed assistant response for a
  persisted lead-agent conversation
- **THEN** the system emits token events using the existing chat socket event
  names and payload shape keyed by `conversation_id`
- **AND** the system emits the existing completed event after the final
  assistant message has been persisted

#### Scenario: Lead-agent response emits persisted plan update events
- **WHEN** a lead-agent turn persists a changed todo snapshot during execution
- **THEN** the system emits a dedicated plan update event keyed by
  `conversation_id`
- **AND** the event payload reflects the latest persisted todo snapshot for
  that conversation

#### Scenario: Lead-agent runtime failure emits the existing failed event
- **WHEN** background lead-agent processing fails after a message has been
  accepted
- **THEN** the system emits the existing failed event keyed by
  `conversation_id`

### Requirement: Lead-agent conversations are browsable through conversation and message endpoints
The system SHALL provide authenticated endpoints for listing lead-agent
conversations and reading persisted lead-agent message history using
`conversation_id`.

#### Scenario: List only lead-agent conversations
- **WHEN** an authenticated client calls `GET /lead-agent/conversations`
- **THEN** the system returns only conversations that are mapped to a
  lead-agent `thread_id`
- **AND** the results remain scoped to the authenticated caller and current
  organization context

#### Scenario: Read message history for a lead-agent conversation
- **WHEN** an authenticated client calls
  `GET /lead-agent/conversations/{conversation_id}/messages` for a valid
  lead-agent conversation
- **THEN** the system returns persisted messages for that conversation in
  chronological order

### Requirement: Legacy chat browsing excludes lead-agent conversations
The system SHALL keep legacy chat browsing behavior isolated from lead-agent
projection records so that `/chat` list and history endpoints do not mix
runtime types.

#### Scenario: Legacy chat conversation list excludes lead-agent records
- **WHEN** an authenticated client calls `GET /chat/conversations`
- **THEN** the system returns only conversations that are not mapped to a
  lead-agent `thread_id`

#### Scenario: Legacy chat history endpoint does not read lead-agent conversations
- **WHEN** an authenticated client calls
  `GET /chat/conversations/{conversation_id}/messages` for a conversation that
  is mapped to a lead-agent `thread_id`
- **THEN** the system rejects the request as not found for the legacy chat
  endpoint

### Requirement: Lead-agent requests remain scoped to the authenticated caller
The system SHALL bind lead-agent requests to the authenticated user and, when
provided, to the current organization context so thread execution remains
properly scoped.

#### Scenario: First lead-agent message stores caller scope
- **WHEN** an authenticated user sends the first lead-agent message that
  creates a new conversation-backed thread
- **THEN** the resulting thread state is associated with that user's identity
- **AND** the current organization context is stored when available

#### Scenario: Subsequent lead-agent messages preserve caller scope
- **WHEN** the same authenticated caller submits a new input to the existing
  lead-agent conversation
- **THEN** the lead-agent runtime continues execution within that caller's
  stored scope
