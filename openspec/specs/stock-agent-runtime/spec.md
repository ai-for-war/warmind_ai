# stock-agent-runtime Specification

## Purpose
TBD - created by archiving change add-stock-agent-full-fork. Update Purpose after archive.
## Requirements
### Requirement: Dedicated stock-agent runtime fork
The system SHALL provide a new `stock_agent` runtime that is separate from the existing `lead_agent` runtime. The stock-agent runtime SHALL use `langchain.agents.create_agent` as its execution primitive and SHALL be created through stock-agent-specific factory functions, state schema, runtime configuration helpers, tool catalog, middleware builder, and system prompt functions.

#### Scenario: Invoke stock agent through its own runtime factory
- **WHEN** the backend starts a stock-agent turn
- **THEN** it creates or reuses the compiled runtime from `create_stock_agent`
- **AND** it does not call `create_lead_agent` for stock-agent execution

#### Scenario: Lead agent runtime remains unchanged
- **WHEN** the backend starts a lead-agent turn
- **THEN** it continues using the existing lead-agent runtime factory and prompt
- **AND** stock-agent runtime additions do not alter lead-agent runtime behavior

### Requirement: Stock-agent state supports lead-agent-equivalent metadata
The stock-agent runtime SHALL define a state schema extending `AgentState`. The schema MUST support caller scope, runtime model metadata, skill metadata, planning metadata, and subagent delegation metadata equivalent to the lead-agent runtime state.

#### Scenario: Stock-agent thread state carries required metadata
- **WHEN** a stock-agent thread is created
- **THEN** the thread state includes `user_id`, optional `organization_id`, runtime provider/model/reasoning fields, skill fields, todo revision fields, orchestration mode, delegation depth, and delegated execution metadata

### Requirement: Stock-agent runtime uses isolated checkpoint collections
The stock-agent runtime SHALL persist LangGraph checkpoint state in stock-agent-specific MongoDB checkpoint collections. Stock-agent checkpoint reads and writes MUST NOT use the lead-agent/shared checkpoint collection names.

#### Scenario: Stock-agent checkpoint is written to stock-agent collections
- **WHEN** a stock-agent thread state update is persisted
- **THEN** the checkpointer writes to `stock_agent_langgraph_checkpoints` and `stock_agent_langgraph_checkpoint_writes`
- **AND** it does not write that state to the lead-agent checkpoint collections

#### Scenario: Stock-agent thread resumes from stock-agent checkpoint state
- **WHEN** a follow-up stock-agent turn runs for an existing stock-agent conversation
- **THEN** the runtime loads prior thread state from the stock-agent checkpoint collections

### Requirement: Stock-agent middleware mirrors lead-agent execution behavior
The stock-agent runtime SHALL include middleware equivalent to the lead-agent stack for transcript summarization, orchestration prompt injection, skill prompt injection, todo planning, delegation limits, dynamic tool selection, tool output limiting, and tool error conversion.

#### Scenario: Stock-agent model call receives equivalent runtime guidance
- **WHEN** the stock-agent runtime prepares a model call
- **THEN** middleware can inject stock-agent system guidance, available skill summaries, current todo context, orchestration guidance, and filtered tool visibility before the model call

#### Scenario: Worker stock-agent runtime cannot recursively delegate
- **WHEN** a stock-agent delegated worker runtime prepares a model call
- **THEN** recursive delegation is unavailable
- **AND** the worker remains bounded by stock-agent delegation limits

### Requirement: Stock-agent tools mirror lead-agent runtime tools
The stock-agent runtime SHALL register internal coordination tools equivalent to lead-agent, including skill loading and task delegation. The runtime MAY expose selectable MCP research tools when they are available, using stock-agent-specific catalog functions.

#### Scenario: Stock-agent registers internal tools
- **WHEN** the stock-agent runtime is initialized
- **THEN** its tool catalog includes stock-agent internal tools for loading skills and delegating tasks

#### Scenario: Stock-agent selectable tools are resolved independently
- **WHEN** the backend lists stock-agent selectable tools
- **THEN** it calls stock-agent tool catalog functions
- **AND** the returned descriptors can be used by stock-agent skill configuration

### Requirement: Stock-agent prompt is independently customizable
The stock-agent runtime SHALL use stock-agent-specific system, planning, orchestration, worker, and summarization prompt functions. The default prompt content MAY initially mirror lead-agent behavior, but it MUST live in stock-agent prompt modules so it can diverge later.

#### Scenario: Stock-agent prompt is loaded from stock-agent module
- **WHEN** `create_stock_agent` renders the base system prompt
- **THEN** it uses `app.prompts.system.stock_agent`
- **AND** changing stock-agent prompt text does not require editing `app.prompts.system.lead_agent`

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

