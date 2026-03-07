## Purpose

Define the top-level conversation orchestrator capability that routes requests across
chat, strategic planning, and clarification paths with a stable normalized output
contract for the service layer.

## Requirements

### Requirement: Top-level conversation orchestrator
The system SHALL provide a `conversation_orchestrator_workflow` as the top-level conversation workflow entrypoint. The orchestrator SHALL prepare shared conversation state, classify the top-level user intent, route the request to the correct handling path, and return a normalized result.

#### Scenario: Route a normal conversation request
- **WHEN** the orchestrator receives a user request whose top-level intent is `chat`
- **THEN** it routes the request to the chat handling path and returns a normalized orchestrator result

#### Scenario: Route a strategic planning request
- **WHEN** the orchestrator receives a user request whose top-level intent is `strategic_planning`
- **THEN** it routes the request to the strategic planning handling path and returns a normalized orchestrator result

#### Scenario: Route an unclear request
- **WHEN** the orchestrator receives a user request whose top-level intent is `unclear`
- **THEN** it routes the request to the clarification handling path and returns a normalized orchestrator result

### Requirement: Restricted top-level intent taxonomy
The top-level orchestrator SHALL classify requests using exactly three intents: `chat`, `strategic_planning`, and `unclear`. The orchestrator MUST NOT expose any additional top-level routing intents for this capability.

#### Scenario: Classifier returns a supported intent
- **WHEN** the classifier successfully evaluates a request
- **THEN** the resulting top-level intent is one of `chat`, `strategic_planning`, or `unclear`

#### Scenario: Unsupported top-level intent is not accepted
- **WHEN** a classifier or intermediate step produces an unsupported top-level intent value
- **THEN** the orchestrator treats the request as `unclear` and routes it to the clarification handling path

### Requirement: Conservative clarification fallback
The orchestrator SHALL use clarification as the safe fallback path whenever top-level classification is ambiguous, low-confidence, or fails. The orchestrator MUST prefer `unclear` over guessing between `chat` and `strategic_planning`.

#### Scenario: Ambiguous request falls back to clarification
- **WHEN** the top-level classifier cannot confidently distinguish between `chat` and `strategic_planning`
- **THEN** the orchestrator routes the request to the clarification handling path

#### Scenario: Classifier failure falls back to clarification
- **WHEN** the top-level classifier errors or cannot produce a valid routing decision
- **THEN** the orchestrator routes the request to the clarification handling path instead of failing the entire request

### Requirement: Normalized orchestrator output envelope
The orchestrator SHALL return a normalized output envelope for every route. The envelope SHALL include `intent`, `response_type`, `agent_response`, `final_payload`, `tool_calls`, and `error` fields so the service layer receives a stable contract regardless of the selected route.

#### Scenario: Chat route returns normalized output
- **WHEN** the orchestrator completes a request through the chat handling path
- **THEN** the result includes `intent`, `response_type`, `agent_response`, `final_payload`, `tool_calls`, and `error`

#### Scenario: Clarification route returns normalized output
- **WHEN** the orchestrator completes a request through the clarification handling path
- **THEN** the result includes `intent`, `response_type`, `agent_response`, `final_payload`, `tool_calls`, and `error`

#### Scenario: Strategic route returns normalized output
- **WHEN** the orchestrator completes a request through the strategic planning handling path
- **THEN** the result includes `intent`, `response_type`, `agent_response`, `final_payload`, `tool_calls`, and `error`

### Requirement: Response type identifies result semantics
The normalized orchestrator output SHALL include a `response_type` field that identifies the kind of result produced. At minimum, the system SHALL distinguish between conversational responses, clarification responses, and strategic planning responses.

#### Scenario: Chat result identifies conversational response
- **WHEN** the orchestrator returns a result from the chat handling path
- **THEN** `response_type` identifies the result as a conversational response

#### Scenario: Clarification result identifies clarification response
- **WHEN** the orchestrator returns a result from the clarification handling path
- **THEN** `response_type` identifies the result as a clarification response

#### Scenario: Strategic result identifies strategic response
- **WHEN** the orchestrator returns a result from the strategic planning handling path
- **THEN** `response_type` identifies the result as a strategic planning response

### Requirement: Service-layer lifecycle remains outside orchestrator
The orchestrator SHALL focus on state preparation, routing, and normalized output only. Persistence, token streaming, and completion event dispatch MUST remain outside the orchestrator workflow boundary.

#### Scenario: Orchestrator returns result without owning persistence
- **WHEN** the orchestrator finishes processing a request
- **THEN** it returns the normalized output to the caller without requiring the workflow itself to persist the final assistant message

#### Scenario: Orchestrator returns result without owning streaming
- **WHEN** the orchestrator selects a branch and receives a branch result
- **THEN** the workflow contract does not require the orchestrator itself to manage token streaming or completion event dispatch
