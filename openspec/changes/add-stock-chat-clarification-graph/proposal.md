## Why

Stock-chat phase 1 currently invokes the Clarification Agent directly from the service layer, even though the intended stock-chat architecture is graph-based. Moving the phase-1 decision into a dedicated graph establishes the orchestration boundary needed for later analyst nodes while keeping the existing clarification behavior intact.

## What Changes

- Add a dedicated stock-chat LangGraph workflow that starts with a clarification node.
- Keep the existing stock-chat Clarification Agent implementation and invoke it from the graph node.
- Return the parsed clarification result through graph state so the service can keep handling persistence, socket emission, and error reporting.
- End the graph after clarification for both outcomes in this phase:
  - `clarification_required`: service persists the assistant clarification and emits the existing socket event.
  - `continue`: graph ends silently; no downstream analyst node is invoked and no readiness event is emitted.
- Do not introduce LangGraph interrupt/resume or checkpointer usage for this phase.
- Do not change the stock-chat HTTP API, dedicated MongoDB collections, clarification socket payload, or readiness policy.

## Capabilities

### New Capabilities
- `stock-chat-clarification-graph`: Graph-based orchestration for stock-chat phase-1 clarification intake.

### Modified Capabilities
None.

## Impact

- Adds a new workflow under `app/graphs/workflows/stock_chat_workflow/`.
- Updates `StockChatService` to invoke the stock-chat workflow instead of directly invoking the Clarification Agent.
- Reuses existing stock-chat clarification schemas, validation, prompt, agent runtime, repositories, and Socket.IO events.
- Updates or adds tests around graph invocation, clarification-required behavior, silent continue behavior, and error propagation.
