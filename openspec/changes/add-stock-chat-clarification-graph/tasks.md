## 1. Workflow Structure

- [ ] 1.1 Add `app/graphs/workflows/stock_chat_workflow/` package with graph, state, and node modules.
- [ ] 1.2 Define `StockChatWorkflowState` with message history, request context identifiers, `clarification_result`, and `error`.
- [ ] 1.3 Register the compiled workflow as `stock_chat_workflow` in the graph registry.

## 2. Clarification Graph Node

- [ ] 2.1 Implement a clarification node that invokes the existing stock-chat Clarification Agent.
- [ ] 2.2 Parse and validate the agent `structured_response` with the existing stock-chat clarification validation helper.
- [ ] 2.3 Return `StockChatClarificationResult` through graph state without persisting messages or emitting socket events.
- [ ] 2.4 Ensure agent failures or invalid structured output propagate as stock-chat clarification errors.

## 3. Graph Routing

- [ ] 3.1 Build the stock-chat workflow with `START -> clarification_node`.
- [ ] 3.2 Add conditional routing after clarification for `clarification_required` and `continue`.
- [ ] 3.3 Route both phase-1 outcomes to `END` and do not add downstream analyst nodes.
- [ ] 3.4 Compile the workflow without a checkpointer and without interrupt/resume behavior.

## 4. Service Integration

- [ ] 4.1 Update `StockChatService` to invoke the stock-chat workflow after loading chronological history.
- [ ] 4.2 Preserve existing assistant clarification persistence and `stock-chat:clarification:required` socket emission when graph state contains `clarification_required`.
- [ ] 4.3 End silently when graph state contains `continue`: no assistant clarification message, no readiness event, no downstream handoff, and no downstream-not-implemented failure.
- [ ] 4.4 Preserve existing `stock-chat:failed` error emission when graph invocation or clarification parsing fails.

## 5. Tests

- [ ] 5.1 Add unit tests for stock-chat workflow construction and routing through the clarification node.
- [ ] 5.2 Add unit tests proving the clarification node reuses the existing agent contract and returns `StockChatClarificationResult`.
- [ ] 5.3 Update stock-chat service tests to assert graph invocation replaces direct agent invocation.
- [ ] 5.4 Update stock-chat service tests for `clarification_required` persistence and socket behavior.
- [ ] 5.5 Update stock-chat service tests for silent `continue` behavior.
- [ ] 5.6 Add or update tests proving no checkpointer, thread resume command, analyst node, or downstream handler is required in phase 1.
