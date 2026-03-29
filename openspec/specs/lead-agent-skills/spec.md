## Purpose

Define the internal skill-catalog, skill-loading, and skill-aware tool
exposure behavior for the lead-agent runtime while keeping the public
conversation-centric API unchanged.

## Requirements

### Requirement: Lead-agent skill catalog is resolved per user
The system SHALL provide a trusted internal lead-agent skill catalog. Before a
lead-agent turn executes, the backend SHALL resolve which skills are enabled
for the authenticated caller and current organization context, and SHALL pass
that skill access result into the lead-agent runtime state.

#### Scenario: Resolve enabled skills for a caller before runtime execution
- **WHEN** the backend starts processing a lead-agent message for an
  authenticated caller
- **THEN** it resolves the set of skill identifiers that caller is allowed to
  use for that turn
- **AND** it injects those enabled skill identifiers into the lead-agent
  runtime state before model execution begins

#### Scenario: Disabled skills are excluded from runtime access
- **WHEN** a skill exists in the internal catalog but is not enabled for the
  current caller scope
- **THEN** the lead-agent runtime does not expose that skill as available for
  the turn

### Requirement: Lead-agent runtime exposes lightweight skill discovery context
The system SHALL expose only lightweight skill summaries to the model by
default. The initial lead-agent runtime context MUST describe each available
skill with discoverable metadata such as name, description, and appropriate use
cases without preloading the full skill instructions into every turn.

#### Scenario: Model sees only skill summaries before a skill is loaded
- **WHEN** the lead-agent begins a turn for a caller with one or more enabled
  skills
- **THEN** the runtime context includes discoverable summaries for those skills
- **AND** the runtime context does not include the full content of each skill
  by default

### Requirement: Lead-agent can load a skill on demand during execution
The system SHALL provide an internal mechanism for the lead-agent runtime to
load the full content of an enabled skill during a turn. When a skill is
loaded, the runtime SHALL update thread state to reflect the active skill and
loaded skill history for subsequent model calls in that thread.

#### Scenario: Load an enabled skill during a turn
- **WHEN** the lead-agent runtime determines that a user request requires a
  specific enabled skill
- **THEN** it loads the full instructions and metadata for that skill into the
  runtime context
- **AND** it updates thread state to mark that skill as active for the current
  execution path

#### Scenario: Reject loading an unknown or disabled skill
- **WHEN** the lead-agent runtime attempts to load a skill that is unknown or
  not enabled for the current caller scope
- **THEN** the runtime does not activate that skill
- **AND** the system records the load attempt as a failure or rejection for
  observability

### Requirement: Lead-agent tool availability is constrained by skill context
The system SHALL expose tools dynamically based on the current skill context.
For each model call, the runtime MUST restrict the visible tool subset to the
tools allowed by the active skill, caller scope, and backend policy.

#### Scenario: Active skill limits visible tools
- **WHEN** a skill has been activated for the current lead-agent execution
- **THEN** the next model call sees only the tools permitted for that skill and
  caller scope
- **AND** tools outside that allowed subset are not exposed to the model for
  that call

#### Scenario: No active skill keeps runtime on base tool surface
- **WHEN** no skill has been activated for the current execution path
- **THEN** the runtime exposes only the base internal tool surface configured
  for no-skill execution

### Requirement: Skill activation remains internal to the existing lead-agent API
The system SHALL keep skill activation internal-only for phase 1. The public
lead-agent message submission and conversation browsing APIs MUST NOT require
the client to specify a skill identifier in order to execute a skill-aware
turn.

#### Scenario: Client submits a skill-eligible request without a skill handle
- **WHEN** an authenticated client submits a normal lead-agent message through
  the existing conversation-centric API
- **THEN** the backend performs any required skill discovery and activation
  internally
- **AND** the request succeeds without the client providing a skill parameter

### Requirement: Skill execution metadata is persisted for observability
The system SHALL persist skill execution metadata for lead-agent turns so the
backend can inspect and evaluate skill usage. Persisted metadata MUST be able
to identify the selected skill context for an assistant response when a skill
was used.

#### Scenario: Persist metadata for a skill-assisted response
- **WHEN** a lead-agent turn completes after loading or using a skill
- **THEN** the persisted assistant-side metadata identifies the skill used for
  that execution
- **AND** the system retains enough metadata to correlate tool activity with
  the skill-aware turn

#### Scenario: Persist a normal response without a loaded skill
- **WHEN** a lead-agent turn completes without activating any skill
- **THEN** the persisted response metadata remains valid without requiring a
  skill identifier
