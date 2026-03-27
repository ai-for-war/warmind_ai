## ADDED Requirements

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
the backend, including `user_id` and optional `organization_id`.

#### Scenario: Create the lead-agent with a custom state schema
- **WHEN** the lead-agent runtime is initialized
- **THEN** the agent is created with a state schema that extends `AgentState`

#### Scenario: Runtime metadata is available in thread state
- **WHEN** the system invokes the lead agent for an authenticated user
- **THEN** the thread state includes the requesting `user_id`
- **AND** the thread state includes `organization_id` when one is provided

### Requirement: MongoDB checkpointer is the source of truth for thread state
The lead-agent runtime SHALL persist thread state through a MongoDB-backed
LangGraph checkpointer. The lead-agent path MUST NOT require the existing
application-managed `conversation` and `message` persistence model in order to
store or resume runtime state.

#### Scenario: Resume an existing lead-agent thread
- **WHEN** the system receives new input for an existing `thread_id`
- **THEN** the lead-agent runtime loads prior state from the MongoDB
  checkpointer for that thread

#### Scenario: Lead-agent runtime does not depend on conversation records
- **WHEN** the system processes a lead-agent request
- **THEN** the request succeeds without creating or updating application-level
  `conversation` or `message` records for that runtime

### Requirement: Lead-agent thread creation endpoint
The system SHALL provide an authenticated API endpoint to create a new
lead-agent thread. The endpoint SHALL return a new `thread_id` that the client
can use for subsequent lead-agent requests.

#### Scenario: Create a new lead-agent thread
- **WHEN** an authenticated client calls the thread-creation endpoint
- **THEN** the system returns a newly generated `thread_id`

#### Scenario: Created thread can be used as the lead-agent handle
- **WHEN** the client receives the new `thread_id`
- **THEN** the client can use that `thread_id` to submit the next lead-agent
  input

### Requirement: Lead-agent accepts new input for an existing thread
The system SHALL provide an authenticated API endpoint that accepts new user
input for an existing lead-agent `thread_id`. The request SHALL append the new
input to the agent's thread context through the lead-agent runtime.

#### Scenario: Submit a new user turn to an existing thread
- **WHEN** an authenticated client submits valid input for an existing
  `thread_id`
- **THEN** the system invokes the lead agent with that input against the
  existing thread

#### Scenario: Reject input for an invalid thread identifier
- **WHEN** the client submits input for a malformed or unknown `thread_id`
- **THEN** the system rejects the request with an appropriate error response

### Requirement: Initial lead-agent runtime starts with no custom tools
The initial lead-agent runtime SHALL be created with an empty tool registry.
V1 MUST establish the thread-native runtime contract without requiring custom
application tools.

#### Scenario: Create the lead agent with an empty tool list
- **WHEN** the system initializes the lead-agent runtime for V1
- **THEN** the runtime registers no custom application tools

### Requirement: Initial lead-agent runtime starts with no custom middleware
The initial lead-agent runtime SHALL be created with no custom middleware.
V1 MUST preserve a clear extension point for future middleware without making
middleware a dependency of the first release.

#### Scenario: Create the lead agent with no middleware
- **WHEN** the system initializes the lead-agent runtime for V1
- **THEN** the runtime registers no custom middleware layers

### Requirement: Lead-agent requests remain scoped to the authenticated caller
The system SHALL bind lead-agent requests to the authenticated user and, when
provided, to the current organization context so thread execution remains
properly scoped.

#### Scenario: Thread creation stores caller scope
- **WHEN** an authenticated user creates a lead-agent thread
- **THEN** the resulting thread state is associated with that user's identity
- **AND** the current organization context is stored when available

#### Scenario: Subsequent thread input preserves caller scope
- **WHEN** the same authenticated caller submits new input to the thread
- **THEN** the lead-agent runtime continues execution within that caller's
  stored scope
