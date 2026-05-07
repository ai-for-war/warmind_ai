## ADDED Requirements

### Requirement: Stock-agent delegation supports typed subagent selection
The stock-agent runtime SHALL require each delegated task to identify the target subagent through a validated `agent_id`. The initial supported subagent IDs MUST include `general_worker` and `event_analyst`.

#### Scenario: Parent delegates to a valid general worker
- **WHEN** the stock agent invokes `delegate_tasks` with `agent_id` set to `general_worker`
- **THEN** the system executes the task through the existing generic isolated worker behavior
- **AND** the worker receives the delegated `objective` and optional `context`

#### Scenario: Parent delegates to a valid event analyst
- **WHEN** the stock agent invokes `delegate_tasks` with `agent_id` set to `event_analyst`
- **THEN** the system executes the task through the preset event analyst subagent
- **AND** the event analyst receives the delegated `objective` and optional `context`

#### Scenario: Parent delegates to an unknown subagent
- **WHEN** the stock agent invokes `delegate_tasks` with an unsupported `agent_id`
- **THEN** the system rejects the delegated task
- **AND** it returns a bounded failure outcome to the parent stock agent

### Requirement: Delegated task input excludes parent-defined output format
The stock-agent runtime SHALL NOT accept `expected_output` or any equivalent parent-defined output-format field in delegated task input. Each subagent MUST own its own output contract.

#### Scenario: Delegated task input contains only supported fields
- **WHEN** the stock agent invokes `delegate_tasks`
- **THEN** the delegated task input contains `agent_id`, `objective`, and optionally `context`
- **AND** the worker task message does not include a parent-provided expected output section

#### Scenario: Delegated task input includes expected output
- **WHEN** delegated task validation receives `expected_output`
- **THEN** the input is rejected or fails validation before worker execution
- **AND** no subagent runtime is invoked for that invalid task

### Requirement: General worker preserves existing generic worker behavior
The stock-agent runtime SHALL keep `general_worker` as the generic isolated worker path for delegated tasks that do not match a preset specialist. The `general_worker` MUST remain unable to recursively delegate.

#### Scenario: General worker executes generic delegated work
- **WHEN** a delegated task targets `general_worker`
- **THEN** the worker runs in an isolated stock-agent worker context
- **AND** it receives trusted caller scope and runtime model metadata from the parent state
- **AND** it does not inherit the full parent conversation transcript

#### Scenario: General worker cannot delegate recursively
- **WHEN** a `general_worker` runtime prepares a model call
- **THEN** the delegation tool is not visible to that worker
- **AND** attempts to delegate from a worker context are rejected by backend guardrails

### Requirement: Event analyst uses fixed specialist behavior
The stock-agent runtime SHALL provide an `event_analyst` subagent specialized for stock-relevant events, news, catalysts, policy/regulatory developments, macro developments, and industry developments affecting Vietnam-listed equities. The `event_analyst` MUST NOT produce the final user-facing recommendation.

#### Scenario: Event analyst investigates stock events
- **WHEN** a delegated task targets `event_analyst`
- **THEN** the event analyst focuses on event/news/catalyst/policy/regulatory/macro-industry evidence relevant to the delegated objective and context
- **AND** it returns a synthesis-ready event impact package to the parent stock agent

#### Scenario: Event analyst output stays subordinate to parent synthesis
- **WHEN** the event analyst completes successfully
- **THEN** the parent stock agent receives the analyst result
- **AND** the parent stock agent remains responsible for combining that result with other evidence and producing the final user-facing answer

### Requirement: Event analyst tool surface is limited to web research
The `event_analyst` subagent SHALL only have access to the normalized MCP web research tools `search` and `fetch_content`.

#### Scenario: Event analyst prepares a model call
- **WHEN** the event analyst runtime prepares a model call
- **THEN** the visible tool set contains `search` and `fetch_content`
- **AND** it does not expose stock-agent internal coordination tools such as `delegate_tasks` or `load_skill`

#### Scenario: Required web research tools are unavailable
- **WHEN** the event analyst runtime cannot resolve `search` or `fetch_content`
- **THEN** event analyst creation or execution fails with a bounded error
- **AND** the parent stock agent can continue the turn without an unhandled exception

### Requirement: Stock-agent orchestration prompt describes available subagents
The stock-agent orchestration prompt SHALL describe the available subagent IDs and their intended routing rules. The prompt MUST instruct the parent stock agent to place required task details such as symbol, company, time window, and user decision context inside `objective` or `context`.

#### Scenario: Parent routes event work to event analyst
- **WHEN** a user request requires event, news, catalyst, policy, regulatory, macro, or industry impact analysis
- **THEN** the stock-agent orchestration guidance directs the parent to use `event_analyst`
- **AND** the delegated objective or context includes the relevant stock target and investigation scope when known

#### Scenario: Parent routes non-specialist work to general worker
- **WHEN** a delegated subtask does not match any preset specialist
- **THEN** the stock-agent orchestration guidance directs the parent to use `general_worker`
- **AND** the parent does not invent a new `agent_id`
