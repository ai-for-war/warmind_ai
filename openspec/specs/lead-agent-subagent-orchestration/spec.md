## Purpose

Define how the lead-agent can delegate bounded work to worker agents while
keeping the lead agent responsible for the final user-facing response.

## Requirements

### Requirement: Lead agent can delegate complex work to worker agents
The system SHALL allow the lead agent to decide per turn whether to answer
directly or delegate complex work to one or more worker agents through an
internal delegation mechanism. The lead agent SHALL remain the only agent that
produces the final response shown to the user in the conversation.

#### Scenario: Lead agent handles simple work directly
- **WHEN** a lead-agent turn does not need to be broken into subtasks
- **THEN** the lead agent completes that turn without invoking worker agents

#### Scenario: Lead agent delegates complex work
- **WHEN** a lead-agent turn requires multiple steps or multiple perspectives
  and turn-scoped subagent orchestration is enabled
- **THEN** the lead agent invokes the internal delegation mechanism
- **AND** delegated work is executed through one or more worker agents
- **AND** the lead agent remains responsible for synthesizing the final
  response

### Requirement: Worker agents run in isolated contexts
Each worker agent SHALL run in a runtime context that is isolated from the
parent lead-agent context. Worker runtime SHALL receive only the delegated task
instructions, trusted runtime scope, and explicitly assigned inputs needed for
that delegated task.

#### Scenario: Worker receives the delegated task instead of the full parent history
- **WHEN** the lead agent delegates a task to a worker agent
- **THEN** the worker starts with its own clean execution context
- **AND** the worker does not inherit the full parent conversation transcript
- **AND** the worker receives the delegated task description together with the
  trusted caller scope needed to complete that task

#### Scenario: Parent context stays compact after worker completion
- **WHEN** a worker agent completes a delegated task
- **THEN** the lead agent receives the worker's final delegated result
- **AND** the parent context does not need to retain the worker's full
  intermediate tool trace to continue the turn

### Requirement: Delegated workers can run in parallel
The system SHALL support running multiple worker agents in parallel for the
same lead-agent turn when delegated subtasks are independent.

#### Scenario: Lead agent delegates multiple independent research tasks
- **WHEN** the lead agent decomposes a complex request into multiple
  independent subtasks
- **THEN** the system can execute those worker tasks concurrently
- **AND** the system gathers each worker's result before the lead agent
  synthesizes the final response

### Requirement: Delegation is constrained by backend guardrails
The system SHALL enforce backend guardrails for subagent orchestration,
including maximum delegation depth and trusted worker execution boundaries. In
the initial version, worker agents MUST NOT be allowed to spawn additional
worker agents.

#### Scenario: Worker cannot delegate recursively
- **WHEN** a worker agent is executing a delegated task
- **THEN** the delegation mechanism is not available for spawning another
  worker layer
- **AND** the current execution remains bounded by the configured maximum depth

#### Scenario: Delegation respects backend limits
- **WHEN** the lead agent attempts to delegate work for a turn
- **THEN** the system applies configured delegation limits such as allowed
  depth, worker concurrency, and worker execution boundaries before or during
  execution

### Requirement: Worker completion returns concise results to the lead agent
Worker agents SHALL return concise task results suitable for lead-agent
synthesis instead of raw execution traces or unbounded intermediate output.

#### Scenario: Worker returns a synthesis-ready summary
- **WHEN** a worker agent completes a delegated task successfully
- **THEN** the worker returns a concise delegated result to the lead agent
- **AND** that result is suitable to be synthesized directly into the final
  answer

#### Scenario: Worker failure returns a bounded error outcome
- **WHEN** a worker agent cannot complete a delegated task
- **THEN** the worker returns a bounded failure result to the lead agent
- **AND** the lead agent can continue the turn by retrying, using other worker
  results, or responding without that worker's contribution
