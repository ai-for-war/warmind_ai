## MODIFIED Requirements

### Requirement: Lead-agent state extends AgentState
The lead-agent runtime SHALL define its state schema by extending
`AgentState`. The custom state SHALL support thread-scoped metadata needed by
the backend, including `user_id` and optional `organization_id`, and SHALL
also support skill-related runtime metadata needed to preserve skill-aware
execution across turns, including enabled skills, active skill identity,
loaded skill history, and skill-scoped tool availability.

#### Scenario: Create the lead-agent with a skill-aware state schema
- **WHEN** the lead-agent runtime is initialized
- **THEN** the agent is created with a state schema that extends `AgentState`
- **AND** that state schema can represent both caller scope and skill-related
  execution metadata

#### Scenario: Runtime metadata is available in thread state
- **WHEN** the system invokes the lead agent for an authenticated user
- **THEN** the thread state includes the requesting `user_id`
- **AND** the thread state includes `organization_id` when one is provided
- **AND** the thread state can retain skill-related execution metadata across
  turns for the same thread

## REMOVED Requirements

### Requirement: Initial lead-agent runtime starts with no custom tools
**Reason**: The runtime now requires internal skill-loading and skill-aware
tool exposure behavior rather than an intentionally empty tool surface.
**Migration**: Update lead-agent initialization and tests to expect internal
skill support tools and non-empty runtime tool registration where configured.

### Requirement: Initial lead-agent runtime starts with no custom middleware
**Reason**: The runtime now requires middleware to inject skill discovery
context and apply per-call skill-aware tool selection.
**Migration**: Update lead-agent initialization and tests to expect custom
lead-agent middleware layers instead of an empty middleware registry.

## ADDED Requirements

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
skill-aware execution. Middleware MUST be able to inject available skill
summaries into runtime context and to apply dynamic tool selection before each
model call.

#### Scenario: Runtime injects discoverable skill context before model reasoning
- **WHEN** the lead-agent runtime prepares a model call for a caller with
  enabled skills
- **THEN** middleware injects the available skill summaries into the runtime
  context before the model reasons about the turn

#### Scenario: Runtime re-evaluates tool exposure after skill state changes
- **WHEN** the current thread state changes the active skill or allowed tool
  set during execution
- **THEN** middleware applies the updated tool exposure rules before the next
  model call
