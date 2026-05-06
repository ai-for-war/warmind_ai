# stock-agent-conversations Specification

## Purpose
TBD - created by archiving change add-stock-agent-full-fork. Update Purpose after archive.
## Requirements
### Requirement: Stock-agent exposes a dedicated conversation API
The system SHALL expose a `/stock-agent` API surface equivalent to the existing `/lead-agent` API for runtime catalog, tools, skills, message submission, conversation listing, message history, and plan snapshots.

#### Scenario: Register stock-agent router
- **WHEN** the API v1 router is initialized
- **THEN** it includes the stock-agent router under `/stock-agent`
- **AND** lead-agent routes remain available under `/lead-agent`

#### Scenario: Stock-agent catalog endpoint returns runtime options
- **WHEN** an authenticated caller requests `GET /stock-agent/catalog`
- **THEN** the system returns stock-agent provider, model, default provider, and reasoning option metadata

### Requirement: Stock-agent conversations use isolated collections
The system SHALL persist stock-agent conversations and messages in stock-agent-specific collections. Stock-agent conversation and message operations MUST NOT read from or write to the shared `conversations` and `messages` collections used by legacy chat or lead-agent projections.

#### Scenario: First stock-agent message creates isolated records
- **WHEN** an authenticated caller submits `POST /stock-agent/messages` without a `conversation_id`
- **THEN** the system creates a conversation record in `stock_agent_conversations`
- **AND** it creates a user message record in `stock_agent_messages`
- **AND** it does not create corresponding records in lead-agent or legacy chat collections

#### Scenario: Follow-up stock-agent message reuses isolated conversation
- **WHEN** an authenticated caller submits `POST /stock-agent/messages` with a valid stock-agent `conversation_id`
- **THEN** the system loads the conversation from `stock_agent_conversations`
- **AND** it persists the new user message in `stock_agent_messages`

### Requirement: Stock-agent message submission runs asynchronously
The system SHALL provide `POST /stock-agent/messages` that accepts content, runtime provider/model/reasoning, optional `conversation_id`, and optional turn-scoped subagent enablement. The endpoint SHALL persist the user message, return IDs without waiting for the final assistant response, and continue stock-agent runtime processing in the background.

#### Scenario: Submit first stock-agent message
- **WHEN** an authenticated caller posts a valid stock-agent message without a conversation handle
- **THEN** the system returns a `conversation_id` and `user_message_id`
- **AND** background stock-agent response processing starts for that conversation

#### Scenario: Submit follow-up stock-agent message
- **WHEN** an authenticated caller posts a valid stock-agent message with an existing stock-agent conversation handle
- **THEN** the system reuses that conversation's stock-agent thread
- **AND** background stock-agent response processing starts for the new user message

### Requirement: Stock-agent socket streaming mirrors lead-agent behavior
Stock-agent background response processing SHALL stream progress through the existing chat socket event contract using stock-agent conversation IDs. The system SHALL emit started, token, tool start, tool end, plan updated, completed, and failed events as appropriate.

#### Scenario: Stream stock-agent response
- **WHEN** the stock-agent runtime produces streamed assistant output
- **THEN** the system emits token events keyed by the stock-agent `conversation_id`
- **AND** it emits a completion event after the assistant message is persisted in `stock_agent_messages`

#### Scenario: Stream stock-agent plan updates
- **WHEN** a stock-agent turn persists a changed todo snapshot
- **THEN** the system emits a plan update event keyed by the stock-agent `conversation_id`
- **AND** the payload contains the latest full stock-agent todo snapshot

### Requirement: Stock-agent conversation browsing reads isolated storage
The system SHALL provide authenticated stock-agent endpoints for listing stock-agent conversations, reading stock-agent message history, and reading the latest stock-agent plan snapshot from stock-agent storage and checkpoint state.

#### Scenario: List stock-agent conversations
- **WHEN** an authenticated caller requests `GET /stock-agent/conversations`
- **THEN** the system returns only records from `stock_agent_conversations` scoped to the caller and organization

#### Scenario: Read stock-agent message history
- **WHEN** an authenticated caller requests `GET /stock-agent/conversations/{conversation_id}/messages`
- **THEN** the system returns chronological messages from `stock_agent_messages` for that stock-agent conversation

#### Scenario: Read stock-agent plan snapshot
- **WHEN** an authenticated caller requests `GET /stock-agent/conversations/{conversation_id}/plan`
- **THEN** the system reads the latest todo snapshot from the stock-agent checkpointed thread state

### Requirement: Stock-agent requests are scoped to caller and organization
The system SHALL bind stock-agent conversations, messages, skill access, and checkpointed thread state to the authenticated user and optional organization context. Requests outside the caller scope MUST be rejected.

#### Scenario: Reject cross-scope stock-agent conversation access
- **WHEN** an authenticated caller requests a stock-agent conversation owned by another user or organization
- **THEN** the system rejects the request as not found for the stock-agent API

#### Scenario: Reject lead-agent conversation handle on stock-agent API
- **WHEN** an authenticated caller submits a lead-agent conversation ID to `/stock-agent/messages`
- **THEN** the system does not load that conversation from lead-agent storage
- **AND** it rejects the request as not found for the stock-agent API

### Requirement: Lead-agent and legacy chat browsing remain isolated
The system SHALL keep stock-agent records out of lead-agent and legacy chat browsing endpoints.

#### Scenario: Lead-agent list excludes stock-agent conversations
- **WHEN** an authenticated caller requests `GET /lead-agent/conversations`
- **THEN** the system does not return records from `stock_agent_conversations`

#### Scenario: Legacy chat list excludes stock-agent conversations
- **WHEN** an authenticated caller requests legacy chat conversations
- **THEN** the system does not return records from `stock_agent_conversations`

