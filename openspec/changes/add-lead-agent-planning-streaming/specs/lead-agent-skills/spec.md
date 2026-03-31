## MODIFIED Requirements

### Requirement: Lead-agent tool availability is constrained by skill context
The system SHALL expose tools dynamically based on the current skill context.
For each model call, the runtime MUST restrict the visible tool subset to the
tools allowed by the active skill, caller scope, and backend policy. The base
runtime tool surface MUST continue to expose trusted coordination tools needed
for backend-managed planning and skill discovery even when skill-specific tool
filtering is applied.

#### Scenario: Active skill limits visible tools while preserving trusted coordination tools
- **WHEN** a skill has been activated for the current lead-agent execution
- **THEN** the next model call sees only the tools permitted for that skill and
  caller scope
- **AND** tools outside that allowed subset are not exposed to the model for
  that call
- **AND** trusted runtime coordination tools required by backend policy remain
  available for the same call

#### Scenario: No active skill keeps runtime on base tool surface
- **WHEN** no skill has been activated for the current execution path
- **THEN** the runtime exposes only the base internal tool surface configured
  for no-skill execution
- **AND** that base surface includes the trusted coordination tools required
  for planning and skill discovery
