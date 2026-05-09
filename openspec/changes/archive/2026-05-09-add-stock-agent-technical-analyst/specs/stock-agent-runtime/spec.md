## ADDED Requirements

### Requirement: Stock-agent delegation supports technical analyst selection
The stock-agent runtime SHALL support `technical_analyst` as a validated preset subagent ID for delegated stock-agent work. Delegated technical-analysis work MUST execute through the dedicated technical analyst runtime rather than the generic worker runtime.

#### Scenario: Parent delegates to technical analyst
- **WHEN** the stock agent invokes `delegate_tasks` with `agent_id` set to `technical_analyst`
- **THEN** the system executes the delegated task through the preset technical analyst subagent
- **AND** the technical analyst receives the delegated objective and optional context

#### Scenario: Technical analyst remains subordinate to parent stock agent
- **WHEN** the technical analyst completes a delegated task
- **THEN** the parent stock agent receives the technical analyst result
- **AND** the parent stock agent remains responsible for combining technical evidence with other evidence and producing the final user-facing answer

#### Scenario: Technical analyst cannot recursively delegate
- **WHEN** the technical analyst runtime prepares a model call
- **THEN** recursive stock-agent delegation is unavailable
- **AND** attempts to delegate from technical analyst worker context are rejected by backend guardrails

### Requirement: Stock-agent orchestration routes technical work to technical analyst
The stock-agent orchestration guidance SHALL describe `technical_analyst` and instruct the parent stock agent to use it for chart, indicator, technical trend, support/resistance, entry, stop loss, target, setup, risk/reward, and technical backtest subtasks.

#### Scenario: Route chart analysis to technical analyst
- **WHEN** a user request requires chart reading, indicator analysis, trend analysis, momentum analysis, volatility analysis, volume confirmation, or support/resistance analysis
- **THEN** the stock-agent orchestration guidance directs the parent to use `technical_analyst`
- **AND** the delegated objective or context includes the relevant stock target and technical-analysis scope when known

#### Scenario: Route trading-plan analysis to technical analyst
- **WHEN** a user request asks for technical entry zone, stop loss, target, risk/reward, setup validation, or technical backtest evidence
- **THEN** the stock-agent orchestration guidance directs the parent to use `technical_analyst`
- **AND** the parent remains responsible for required user clarification before delegation when stock-agent context gates require it
