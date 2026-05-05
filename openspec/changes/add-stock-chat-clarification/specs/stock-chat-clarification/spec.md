## ADDED Requirements

### Requirement: Stock-chat messages use a dedicated authenticated endpoint
The system SHALL provide a dedicated authenticated `POST /stock-chat/messages` endpoint for stock-chat phase-1 intake and clarification. Requests MUST be scoped to the active user and current organization context, consistent with the application's authenticated organization request model.

#### Scenario: Submit a first stock-chat message
- **WHEN** an authenticated active user calls `POST /stock-chat/messages` without a `conversation_id`
- **THEN** the system creates a new stock-chat conversation in the current user and organization scope
- **AND** the system persists the submitted user message in that stock-chat conversation
- **AND** the HTTP response returns the created `conversation_id` and `user_message_id`
- **AND** clarification evaluation runs asynchronously after the HTTP response

#### Scenario: Submit a follow-up stock-chat message
- **WHEN** an authenticated active user calls `POST /stock-chat/messages` with a valid stock-chat `conversation_id`
- **THEN** the system appends the submitted user message to that stock-chat conversation
- **AND** the HTTP response returns the `conversation_id` and `user_message_id`
- **AND** the asynchronous clarification evaluation uses the full persisted stock-chat message history

#### Scenario: Reject inaccessible stock-chat conversation
- **WHEN** a user submits a stock-chat message with a `conversation_id` that does not exist or belongs to another user or organization
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT append a message to that conversation

### Requirement: Stock-chat persistence uses dedicated collections
The system SHALL store stock-chat conversations and stock-chat messages in dedicated MongoDB collections that are separate from the existing generic chat, lead-agent, and stock-research report collections.

#### Scenario: Create stock-chat records in dedicated collections
- **WHEN** the system creates a stock-chat conversation and message
- **THEN** the conversation is stored in the stock-chat conversation collection
- **AND** the message is stored in the stock-chat message collection

#### Scenario: Existing chat collections are not used for stock-chat turns
- **WHEN** the system processes a stock-chat message turn
- **THEN** it MUST NOT create or mutate records in the existing generic `conversations` or `messages` collections for that stock-chat turn

### Requirement: Clarification Agent reads full stock-chat message history
The system SHALL evaluate stock-chat readiness by invoking a Clarification Agent with the full persisted stock-chat message history in chronological order. The Clarification Agent MUST use the transcript as the source of context rather than backend-managed option value patches or canonical request state.

#### Scenario: Clarification uses previous assistant question for short follow-up
- **WHEN** a user answers a previous clarification prompt with a short response such as `Trung hạn`
- **THEN** the system provides the prior stock-chat assistant clarification message and the new user message to the Clarification Agent
- **AND** the Clarification Agent can evaluate readiness from that history

#### Scenario: Option values are not required for follow-up interpretation
- **WHEN** the client submits a follow-up after selecting a clarification option
- **THEN** the system accepts natural-language `content` as the clarification answer
- **AND** the system MUST NOT require a backend state patch payload for the selected option

### Requirement: Clarification response emits user-facing questions and options when context is missing
When the Clarification Agent determines that context is insufficient, the system SHALL emit a Socket.IO `stock-chat:clarification:required` event containing `status: clarification_required` with a `clarification` list of one to three user-facing clarification items. Each clarification item MUST contain one user-facing question and two to four user-facing options. The socket payload MUST include an `assistant_message_id` for the persisted clarification message.

#### Scenario: Ask for time horizon when investment-decision question is missing it
- **WHEN** a user asks whether to buy, sell, or hold a stock without specifying a time horizon
- **THEN** the system emits `status: clarification_required`
- **AND** one clarification item asks for the intended time horizon
- **AND** that clarification item includes user-facing options such as short term, medium term, and long term
- **AND** the system persists the assistant clarification message

#### Scenario: Ask for symbol when stock identity is missing
- **WHEN** a user asks a stock question without a clear stock symbol or company identity
- **THEN** the system emits `status: clarification_required`
- **AND** one clarification item asks which stock or company the user wants to discuss

#### Scenario: Ask for intent when requested task is unclear
- **WHEN** a user mentions a stock but does not make the desired task clear
- **THEN** the system emits `status: clarification_required`
- **AND** one clarification item asks what kind of help the user wants

### Requirement: Sufficient context hands off internally without a readiness response
When the Clarification Agent determines that the conversation has enough context for later analyst agents, the system SHALL hand off to downstream processing instead of returning a user-facing readiness response. The system MUST NOT persist an assistant message for the clarification step when no clarification is required.

#### Scenario: Hand off after required context is present
- **WHEN** the stock-chat history identifies the stock, the user intent, and any required time horizon
- **THEN** the system does not return a `ready_for_analysis` response to the client
- **AND** the system proceeds with downstream handling

#### Scenario: Do not persist readiness as an assistant message
- **WHEN** the Clarification Agent determines that no clarification is required
- **THEN** the system MUST NOT append an assistant message to the stock-chat message collection for that turn

### Requirement: Phase-1 stock chat does not perform analysis
The stock-chat phase-1 endpoint SHALL only perform intake and clarification readiness evaluation. It MUST NOT run technical, fundamental, news, risk, decision, report-generation, or trading agents, and it MUST NOT return an investment recommendation.

#### Scenario: Clarification step does not return stock analysis
- **WHEN** context is sufficient and the system hands off internally
- **THEN** the clarification step does not return a buy, sell, hold, price target, risk assessment, news summary, technical analysis, or fundamental analysis result as a readiness response

#### Scenario: Clarification response does not call analyst agents
- **WHEN** the system emits `status: clarification_required`
- **THEN** no stock analyst agent is invoked for that request
