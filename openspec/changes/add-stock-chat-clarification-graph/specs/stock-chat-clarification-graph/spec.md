## ADDED Requirements

### Requirement: Stock-chat uses a dedicated phase-1 graph workflow
The system SHALL provide a dedicated LangGraph workflow for stock-chat phase-1 clarification orchestration. The workflow MUST be separate from existing generic chat and conversation orchestrator workflows.

#### Scenario: Invoke stock-chat workflow for clarification processing
- **WHEN** stock-chat background processing evaluates a persisted user turn
- **THEN** the system invokes the dedicated stock-chat workflow
- **AND** the workflow receives the chronological stock-chat message history
- **AND** the workflow starts at the clarification node

#### Scenario: Existing chat workflows remain unchanged
- **WHEN** the stock-chat workflow is added
- **THEN** the system MUST NOT route stock-chat turns through the generic chat workflow
- **AND** the system MUST NOT route stock-chat turns through the conversation orchestrator workflow

### Requirement: Clarification node reuses the existing Clarification Agent
The stock-chat clarification node SHALL invoke the existing stock-chat Clarification Agent and parse its structured output using the existing stock-chat clarification validation contract.

#### Scenario: Clarification Agent returns missing context
- **WHEN** the existing Clarification Agent returns `status: clarification_required`
- **THEN** the clarification node stores the parsed `StockChatClarificationResult` in graph state
- **AND** the graph completes without invoking analyst nodes

#### Scenario: Clarification Agent returns sufficient context
- **WHEN** the existing Clarification Agent returns `status: continue`
- **THEN** the clarification node stores the parsed `StockChatClarificationResult` in graph state
- **AND** the graph completes without invoking analyst nodes

#### Scenario: Clarification Agent returns invalid output
- **WHEN** the existing Clarification Agent fails or returns invalid structured output
- **THEN** the stock-chat workflow invocation MUST fail in a way the stock-chat service can report through the existing stock-chat failure event

### Requirement: Service retains persistence and socket side effects
The stock-chat workflow SHALL return clarification decisions through graph state. The stock-chat service MUST remain responsible for persistence, Socket.IO events, ownership validation, and HTTP acknowledgement behavior.

#### Scenario: Context is missing
- **WHEN** the graph returns a `clarification_required` result
- **THEN** the service persists the assistant clarification message
- **AND** the service emits the existing `stock-chat:clarification:required` event
- **AND** the socket payload shape remains unchanged

#### Scenario: Context is sufficient
- **WHEN** the graph returns a `continue` result
- **THEN** the service MUST NOT persist a clarification assistant message
- **AND** the service MUST NOT emit a readiness event
- **AND** the service MUST NOT emit a downstream-not-implemented failure
- **AND** the graph ends silently for this phase

### Requirement: Phase-1 graph does not use checkpoint interrupt semantics
The stock-chat phase-1 workflow SHALL NOT depend on LangGraph checkpointing, `interrupt()`, or `Command(resume=...)` semantics. The persisted stock-chat transcript MUST remain the source of context across user turns.

#### Scenario: Follow-up clarification answer
- **WHEN** a user submits a follow-up answer to a prior clarification prompt
- **THEN** the service loads the persisted chronological stock-chat transcript
- **AND** the graph evaluates the follow-up from that transcript
- **AND** the system MUST NOT require a LangGraph resume command

#### Scenario: Workflow compilation
- **WHEN** the stock-chat phase-1 workflow is compiled
- **THEN** it MUST NOT require a checkpointer configuration
- **AND** invoking the workflow MUST NOT require a LangGraph `thread_id`

### Requirement: Phase-1 graph stops at clarification
The stock-chat phase-1 workflow SHALL stop after the clarification node until downstream analyst nodes are explicitly introduced by a later change.

#### Scenario: Analyst nodes are not invoked
- **WHEN** the stock-chat phase-1 workflow processes any message history
- **THEN** it MUST NOT invoke technical analyst, fundamental analyst, news analyst, risk, decision, report-generation, or trading nodes
- **AND** it MUST NOT return investment analysis or an investment recommendation
