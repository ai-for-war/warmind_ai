## ADDED Requirements

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

## MODIFIED Requirements

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
