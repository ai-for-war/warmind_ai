## 1. Orchestrator foundations

- [ ] 1.1 Create the `conversation_orchestrator_workflow` module structure under `app/graphs/workflows/`
- [ ] 1.2 Define the parent workflow state with only shared orchestrator fields
- [ ] 1.3 Define the normalized orchestrator output envelope fields and route result contract

## 2. Top-level routing

- [ ] 2.1 Implement the top-level intent classifier for `chat`, `strategic_planning`, and `unclear`
- [ ] 2.2 Add conservative fallback behavior so ambiguous or invalid classification routes to `unclear`
- [ ] 2.3 Implement the route function that maps top-level intent to the correct handling path

## 3. Branch invocation and normalization

- [ ] 3.1 Add the chat branch wrapper node that invokes the chat handling path and maps its result into the parent envelope
- [ ] 3.2 Add the strategic branch wrapper node that invokes the strategic planning handling path and maps its result into the parent envelope
- [ ] 3.3 Reuse or adapt the clarification node as the top-level unclear handling path
- [ ] 3.4 Add a normalization step so every branch returns `intent`, `response_type`, `agent_response`, `final_payload`, `tool_calls`, and `error`

## 4. Workflow assembly and integration

- [ ] 4.1 Build the orchestrator graph with explicit conditional routing
- [ ] 4.2 Register `conversation_orchestrator_workflow` as a workflow that can be created through the graph registry
- [ ] 4.3 Update the service entrypoint to invoke the orchestrator instead of calling `chat_workflow` directly

## 5. Validation and hardening

- [ ] 5.1 Add tests for routing `chat` requests to the chat handling path
- [ ] 5.2 Add tests for routing `strategic_planning` requests to the strategic handling path
- [ ] 5.3 Add tests for routing ambiguous or failed classification to the clarification handling path
- [ ] 5.4 Add tests that verify all routes return the normalized orchestrator output envelope
- [ ] 5.5 Add lightweight logging or route metadata for selected intent, selected path, and normalized response type
