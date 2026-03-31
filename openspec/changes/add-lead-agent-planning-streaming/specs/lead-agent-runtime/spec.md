## MODIFIED Requirements

### Requirement: Lead-agent state extends AgentState
The lead-agent runtime SHALL define its state schema by extending
`AgentState`. The runtime state model, including middleware-contributed state,
SHALL support thread-scoped metadata needed by the backend, including `user_id`
and optional `organization_id`, SHALL support skill-related runtime metadata
needed to preserve skill-aware execution across turns, including enabled
skills, active skill identity, loaded skill history, and skill-scoped tool
availability, and SHALL support planning metadata needed to preserve
checkpoint-backed todo state across turns.

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
