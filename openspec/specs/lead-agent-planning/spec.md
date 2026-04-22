## Purpose

Define durable todo-based planning for the lead-agent runtime so the backend
and frontend can rely on checkpoint-backed plan state for complex work without
introducing a separate planning datastore.
## Requirements
### Requirement: Lead-agent uses todo-based planning for complex work
The system SHALL provide todo-based planning for the lead-agent runtime by
attaching LangChain `TodoListMiddleware`. The lead-agent runtime MUST make this
planning capability available for complex multi-step turns that require
progress visibility, coordination across tools, or long-running execution, and
MUST NOT require todo creation for simple one-step turns.

#### Scenario: Complex turn can create a persisted plan
- **WHEN** the lead-agent handles a complex multi-step request
- **THEN** the runtime can create or revise a todo list for that thread
- **AND** the resulting todo list becomes part of the thread state for
  subsequent execution

#### Scenario: Simple turn does not require todo planning
- **WHEN** the lead-agent handles a simple turn that can be completed without
  multi-step coordination
- **THEN** the runtime can complete the turn without creating a todo list
- **AND** the absence of todo state does not block the response

### Requirement: Checkpoint-backed todo state is the source of truth
The system SHALL persist lead-agent todo state in LangGraph checkpoint state
and MUST treat that persisted `todos` snapshot as the canonical planning record
for the thread. FE-facing projections, message metadata, socket payloads, or
older transcript history MUST NOT become the source of truth for reconstructing
plan state or for rehydrating the model's active planning context on later
turns.

#### Scenario: Todo state is recovered from checkpointed thread state
- **WHEN** the backend loads an existing lead-agent thread after one or more
  persisted todo updates
- **THEN** it reads the latest `todos` state from the LangGraph checkpoint for
  that thread
- **AND** the recovered todo state matches the latest persisted plan snapshot

#### Scenario: FE-facing projections do not replace checkpoint plan state
- **WHEN** the system emits or stores plan data for frontend consumption
- **THEN** that data acts only as a projection of the persisted checkpoint
  state
- **AND** the backend does not depend on that projection to resume planning on
  the next turn

#### Scenario: Compacted transcript history does not replace checkpoint plan state
- **WHEN** older lead-agent transcript history has been compacted into a
  summary message
- **THEN** the runtime still treats checkpoint-backed `todos` as the canonical
  planning record
- **AND** the active planning context for the next turn is derived from the
  persisted todo snapshot rather than from the compacted transcript summary

### Requirement: Persisted plan snapshots are streamed to the frontend
The system SHALL emit a dedicated chat-scoped plan update event when a
lead-agent todo snapshot has changed and the updated state has already been
persisted. Each emitted plan update MUST contain the latest full todo snapshot
for the conversation rather than an incremental patch.

#### Scenario: Plan update event is emitted after todo persistence
- **WHEN** a lead-agent turn completes a `write_todos` tool call and the
  resulting todo state has been persisted to checkpoint storage
- **THEN** the system emits a plan update event keyed by the current
  `conversation_id`
- **AND** the event payload contains the latest full todo snapshot for that
  conversation

#### Scenario: No optimistic plan event is emitted before persistence
- **WHEN** the lead-agent starts a `write_todos` tool call but the updated todo
  state has not yet been persisted
- **THEN** the system does not emit a plan update event based only on tool
  input
- **AND** the frontend waits for the persisted snapshot event

### Requirement: Latest persisted plan is readable for conversation history
The system SHALL provide an authenticated read path for the latest persisted
lead-agent plan associated with a conversation so the frontend can rehydrate
plan state after reload or reconnection.

#### Scenario: Read the latest persisted plan for a conversation
- **WHEN** an authenticated client requests plan state for a valid lead-agent
  conversation within its caller scope
- **THEN** the system returns the latest persisted todo snapshot for that
  conversation
- **AND** the returned snapshot reflects the current checkpoint-backed state

#### Scenario: Conversation without a persisted plan returns an empty snapshot
- **WHEN** an authenticated client requests plan state for a valid lead-agent
  conversation that has never persisted any todos
- **THEN** the system returns a valid empty plan representation
- **AND** the request does not fail solely because no todo list exists yet

### Requirement: Persisted todo state remains explicit runtime context after transcript compaction
The system SHALL make the current checkpoint-backed todo snapshot explicitly
available to the lead-agent model prompt on each turn, even when older
transcript history has been compacted into a summary message. The injected todo
context MUST be derived from persisted checkpoint state rather than from older
tool messages or frontend-facing projections.

#### Scenario: Runtime injects the current persisted todo snapshot after transcript compaction
- **WHEN** a lead-agent thread has an existing persisted todo snapshot and
  older transcript history has already been compacted
- **THEN** the runtime injects the current persisted todo snapshot into the
  model context for the next turn
- **AND** the model can continue reasoning from the current plan without
  depending on older `write_todos` tool-message history

#### Scenario: Todo injection reflects checkpoint state rather than transcript reconstruction
- **WHEN** the runtime prepares planning context for a lead-agent model call
- **THEN** it reads the todo snapshot from checkpoint-backed runtime state
- **AND** it does not reconstruct the active plan from assistant text, tool
  echoes, or frontend-facing message projection data

