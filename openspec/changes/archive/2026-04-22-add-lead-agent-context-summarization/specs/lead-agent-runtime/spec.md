## ADDED Requirements

### Requirement: Lead-agent runtime compacts older checkpointed message history
The system SHALL compact older lead-agent checkpointed `messages` history
before model calls when the runtime context exceeds configured summarization
thresholds. The compaction process SHALL replace older transcript history with
one bounded summary message while preserving a bounded recent message window in
raw form.

#### Scenario: Older runtime history is replaced with a bounded summary
- **WHEN** a lead-agent thread reaches the configured transcript compaction
  threshold before a model call
- **THEN** the runtime replaces older checkpointed message history with a
  bounded summary message
- **AND** the runtime preserves a bounded recent window of raw messages for
  continued local reasoning

#### Scenario: Transcript compaction does not require frontend projection
- **WHEN** the runtime compacts older checkpointed message history for a
  lead-agent thread
- **THEN** the compaction uses checkpoint-backed runtime state as its source of
  history
- **AND** the runtime does not require application-managed conversation or
  message projection records to reconstruct the compacted context

## MODIFIED Requirements

### Requirement: Lead-agent runtime supports custom middleware for skill-aware execution
The lead-agent runtime SHALL use custom middleware layers to support
skill-aware execution, todo-based planning, transcript compaction, and
subagent orchestration. Middleware MUST be able to inject available skill
summaries into runtime context, compact older checkpointed message history into
a bounded summary before model reasoning, attach lead-agent planning guidance
and the planning tool surface, inject the current persisted todo snapshot as
authoritative runtime context for each model call, switch the lead agent into
orchestration behavior when turn-scoped subagent mode is enabled, and apply
dynamic tool selection before each model call.

#### Scenario: Runtime injects compacted context, skill context, and orchestration guidance before model reasoning
- **WHEN** the lead-agent runtime prepares a model call for a caller with
  enabled skills and turn-scoped subagent orchestration enabled
- **THEN** middleware can compact older checkpointed message history before the
  model reasons about the turn
- **AND** middleware injects the available skill summaries into the runtime
  context before the model reasons about the turn
- **AND** middleware also preserves the planning guidance needed for todo-based
  execution in that call
- **AND** middleware injects the current persisted todo snapshot as explicit
  authoritative planning context for that call
- **AND** middleware applies orchestration guidance so the lead agent can
  decide between answering directly or delegating work

#### Scenario: Runtime re-evaluates tool exposure after skill, planning, delegation, or compaction context changes
- **WHEN** the current thread state changes the active skill, allowed tool set,
  persisted planning context, compacted transcript state, or delegation context
  during execution
- **THEN** middleware applies the updated tool exposure rules before the next
  model call
- **AND** trusted runtime coordination tools required by backend policy remain
  available for that call
