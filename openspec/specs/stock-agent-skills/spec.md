# stock-agent-skills Specification

## Purpose
TBD - created by archiving change add-stock-agent-full-fork. Update Purpose after archive.
## Requirements
### Requirement: Stock-agent skills use isolated collections
The system SHALL persist stock-agent skill definitions and per-user skill access records in stock-agent-specific MongoDB collections. Stock-agent skill operations MUST NOT read from or write to lead-agent skill collections.

#### Scenario: Create stock-agent skill
- **WHEN** an authenticated caller creates a skill through the stock-agent skill API
- **THEN** the skill is persisted in `stock_agent_skills`
- **AND** no record is created in `lead_agent_skills`

#### Scenario: Enable stock-agent skill
- **WHEN** an authenticated caller enables a stock-agent skill for an organization
- **THEN** the enablement is persisted in `stock_agent_skill_access`
- **AND** no record is created in `lead_agent_skill_access`

### Requirement: Stock-agent exposes skill CRUD and enablement API
The system SHALL provide stock-agent skill endpoints equivalent to lead-agent skill endpoints under `/stock-agent`. The API SHALL support listing selectable tools, listing skills, creating skills, reading one skill, updating skills, deleting skills, enabling skills, and disabling skills.

#### Scenario: List stock-agent tools
- **WHEN** an authenticated caller requests `GET /stock-agent/tools`
- **THEN** the system returns the stock-agent selectable tool catalog

#### Scenario: Manage stock-agent skill lifecycle
- **WHEN** an authenticated caller creates, updates, reads, enables, disables, or deletes a skill through `/stock-agent/skills`
- **THEN** the operation is scoped to stock-agent repositories and the caller's organization context

### Requirement: Stock-agent skill access is resolved per caller
Before each stock-agent runtime turn executes, the backend SHALL resolve enabled stock-agent skills for the authenticated caller and current organization context, then inject the enabled stock-agent skill identifiers into stock-agent runtime state.

#### Scenario: Resolve enabled stock-agent skills before execution
- **WHEN** the backend starts processing a stock-agent message
- **THEN** it resolves enabled skill IDs through `StockAgentSkillAccessResolver`
- **AND** it injects those IDs into stock-agent runtime state before model execution

#### Scenario: Lead-agent skills are not visible to stock-agent runtime
- **WHEN** a lead-agent skill exists for the same caller and organization
- **THEN** the stock-agent runtime does not expose that lead-agent skill unless an equivalent stock-agent skill exists and is enabled in stock-agent storage

### Requirement: Stock-agent can load enabled skills during execution
The stock-agent runtime SHALL provide a stock-agent `load_skill` internal tool that loads only enabled stock-agent skills for the current caller scope. Loading a skill SHALL update stock-agent thread state with the active skill, loaded skill history, allowed tool names, and active skill version.

#### Scenario: Load enabled stock-agent skill
- **WHEN** the stock-agent runtime calls `load_skill` with an enabled stock-agent skill ID
- **THEN** the runtime loads that skill from stock-agent skill storage
- **AND** the thread state records the active skill metadata for subsequent model calls

#### Scenario: Reject unavailable stock-agent skill
- **WHEN** the stock-agent runtime calls `load_skill` with an unknown or disabled skill ID
- **THEN** the runtime does not activate that skill
- **AND** it returns a tool acknowledgement that the skill is unavailable for the thread

### Requirement: Stock-agent tool visibility is constrained by stock-agent skill context
The stock-agent runtime SHALL dynamically filter visible tools based on the active stock-agent skill, caller scope, backend policy, and delegation boundary. Trusted stock-agent coordination tools required for planning, skill loading, and backend policy MUST remain available when appropriate.

#### Scenario: Active stock-agent skill filters tools
- **WHEN** a stock-agent skill with allowed tool names is active
- **THEN** the next stock-agent model call exposes only the permitted selectable tools plus trusted coordination tools
- **AND** tools outside that set are hidden from the model call

### Requirement: Stock-agent skill metadata is persisted for observability
The system SHALL persist stock-agent skill execution metadata with stock-agent assistant messages when a stock-agent turn loads or uses a skill.

#### Scenario: Persist stock-agent skill metadata
- **WHEN** a stock-agent turn completes after loading a skill
- **THEN** the persisted stock-agent assistant message metadata includes the active skill ID, skill version, and loaded skill list

