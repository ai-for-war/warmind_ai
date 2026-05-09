## ADDED Requirements

### Requirement: Stock-agent delegation supports fundamental analyst subagent
The stock-agent runtime SHALL support `fundamental_analyst` as a validated preset subagent ID for delegated stock-agent work. Delegated fundamental-analysis work MUST execute through the dedicated fundamental analyst runtime rather than the generic worker runtime.

#### Scenario: Parent delegates to fundamental analyst
- **WHEN** the stock agent invokes `delegate_tasks` with `agent_id` set to `fundamental_analyst`
- **THEN** the system executes the delegated task through the preset fundamental analyst subagent
- **AND** the delegated result identifies `subagent_id` as `fundamental_analyst`

#### Scenario: Fundamental analyst remains subordinate to parent stock agent
- **WHEN** a delegated fundamental analyst task completes
- **THEN** the parent stock agent receives the fundamental analyst result
- **AND** the parent stock agent remains responsible for combining that result with technical, event, and other available evidence
- **AND** the parent stock agent remains responsible for producing the final user-facing answer

#### Scenario: Unknown stock subagent remains rejected
- **WHEN** the stock agent invokes `delegate_tasks` with an unsupported `agent_id`
- **THEN** the runtime rejects the delegated task before invoking any worker runtime
- **AND** it returns a bounded failure outcome to the parent stock agent

### Requirement: Stock-agent orchestration routes fundamental work to fundamental analyst
The stock-agent orchestration guidance SHALL describe `fundamental_analyst` and instruct the parent stock agent to use it for business profile, business quality, growth, profitability, financial health, balance-sheet strength, cash-flow quality, reported financial ratios, and reported valuation-ratio subtasks.

#### Scenario: Route broad fundamental analysis to fundamental analyst
- **WHEN** the user asks for financial statement analysis, fundamental analysis, company quality, business health, or valuation-ratio context for a Vietnam-listed stock
- **THEN** the stock-agent orchestration guidance directs the parent to use `fundamental_analyst`
- **AND** the parent includes required task details such as symbol, company context, requested period, and user decision context in `objective` or `context`

#### Scenario: Route ratio and valuation evidence to fundamental analyst
- **WHEN** the user asks about P/E, P/B, EPS, ROE, ROA, leverage, liquidity, margins, or reported financial ratios for a Vietnam-listed stock
- **THEN** the stock-agent orchestration guidance directs the parent to use `fundamental_analyst`

#### Scenario: Do not use general worker for specialist fundamental work
- **WHEN** a delegated subtask matches the fundamental analyst scope
- **THEN** the parent stock agent MUST NOT use `general_worker` as a shortcut for that fundamental-analysis work
- **AND** it MUST use `fundamental_analyst` unless blocking context is missing

#### Scenario: Ask user before delegation when blocking context is missing
- **WHEN** the user request needs fundamental analysis but lacks a clear Vietnam-listed stock symbol
- **THEN** the parent stock agent asks the user for the missing stock context before delegating
- **AND** it MUST NOT ask the fundamental analyst to ask the user for clarification
