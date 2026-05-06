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

