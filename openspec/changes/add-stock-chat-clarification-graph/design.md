## Context

Stock-chat phase 1 already has a dedicated authenticated API, MongoDB-backed stock-chat transcript persistence, a Clarification Agent, structured output validation, and Socket.IO clarification events. The current service still invokes the Clarification Agent directly, while the intended stock-chat architecture is graph-based and later phases will add technical, fundamental, news, risk, and decision nodes.

The phase-1 clarification design is intentionally history-driven: the system persists user and assistant clarification messages, loads the full chronological stock-chat transcript, and lets the Clarification Agent determine readiness from that transcript. It does not maintain backend slot patches or normalized option state.

LangGraph supports checkpointers and interrupt/resume flows, but those are not needed for this phase because every turn is an independent HTTP request followed by background processing, and MongoDB transcript history is already the source of truth.

## Goals / Non-Goals

**Goals:**

- Add a dedicated stock-chat workflow under `app/graphs/workflows/stock_chat_workflow/`.
- Start the workflow at a clarification node.
- Reuse the existing Clarification Agent, prompt, runtime config, and structured output validation.
- Return a `StockChatClarificationResult` through graph state for the service to handle.
- Keep all persistence, Socket.IO emission, ownership checks, and HTTP acknowledgement behavior in `StockChatService`.
- End the graph after clarification in phase 1.
- End silently when clarification returns `continue`.

**Non-Goals:**

- No technical, fundamental, news, risk, decision, trading, or final-answer nodes.
- No investment recommendation, data retrieval, report generation, or analyst execution.
- No frontend contract changes.
- No LangGraph `interrupt()` or resume flow.
- No LangGraph checkpointer dependency for this workflow in phase 1.
- No backend-managed normalized clarification state or option value patches.

## Decisions

### Decision: Create a dedicated stock-chat workflow

Create a new workflow package:

- `app/graphs/workflows/stock_chat_workflow/state.py`
- `app/graphs/workflows/stock_chat_workflow/graph.py`
- `app/graphs/workflows/stock_chat_workflow/nodes/clarification_node.py`

Register it as `stock_chat_workflow` in the graph registry.

This is preferred over adding stock-chat routing to the existing generic chat or conversation orchestrator workflows because stock-chat has a separate domain, persistence model, socket event contract, and future analyst graph.

Alternative considered: reuse `chat_workflow` or `conversation_orchestrator_workflow`. That would reduce file count, but it would couple stock analysis orchestration to unrelated chat paths and make later analyst nodes harder to isolate.

### Decision: Keep service side effects outside graph nodes

The graph node will call the existing Clarification Agent and return the parsed `StockChatClarificationResult` in graph state. `StockChatService` will continue to:

- validate conversation ownership,
- persist user messages,
- load chronological history,
- persist assistant clarification messages,
- emit `stock-chat:clarification:required`,
- emit `stock-chat:failed` on errors.

This keeps graph nodes deterministic enough to test without repository or socket fixtures and avoids mixing orchestration decisions with external side effects.

Alternative considered: let the graph node persist and emit socket events directly. That would make the graph self-contained, but it would duplicate service responsibilities and make future graph tests slower and more fragile.

### Decision: Use `clarification_result` as the graph output contract

The workflow state will include:

```python
clarification_result: StockChatClarificationResult | None
```

This is preferred over separate `clarification_status` and `clarification` fields because the existing domain contract already validates the allowed statuses and payload constraints. The service can inspect `clarification_result.status` and reuse existing response-building logic.

Alternative considered: flatten status and clarification into separate graph state fields. That would be simple, but it would duplicate the structured output schema and increase the chance of state drift.

### Decision: End silently on `continue`

For this phase, when the Clarification Agent returns `continue`, the graph ends and the service performs no downstream handoff, emits no readiness event, persists no assistant message, and raises no downstream-not-implemented error.

This matches the current implementation scope: build the graph only through clarification. Later changes can replace the silent `continue` end edge with downstream analyst nodes.

Alternative considered: keep calling a downstream placeholder and emit failure when downstream is not implemented. That exposes an implementation gap as a user-facing failure even though phase 1 has completed successfully.

### Decision: Do not use checkpointer or interrupt/resume

Compile the stock-chat workflow without a LangGraph checkpointer for phase 1. Do not use `interrupt()`.

This is preferred because each stock-chat turn reloads the full persisted transcript from MongoDB and the clarification loop continues through normal `POST /stock-chat/messages` calls. Checkpointing would add `thread_id` management, checkpoint cleanup, state versioning, and additional persistence tests without solving a current problem.

Alternative considered: compile with the existing MongoDB checkpointer and use `conversation_id` as `thread_id`. That may become useful for long-running analyst graphs or human approval checkpoints, but it is unnecessary for a single-node clarification workflow.

## Risks / Trade-offs

- Silent `continue` can leave a future frontend without a terminal socket event if it assumes every message produces one. This is acceptable for now because the frontend is not implemented and downstream graph nodes are out of scope.
- A graph that wraps an existing agent is a nested graph call. This is acceptable for phase 1 because it avoids refactoring a completed Clarification Agent; later work can convert the agent into a direct model-call node if nested graph debugging becomes painful.
- No checkpointer means the workflow cannot resume from the middle of a failed run. This is acceptable because the workflow has only one meaningful node and can be re-run from the MongoDB transcript.
- The graph boundary adds files and tests before downstream nodes exist. This is intentional so future analyst nodes can attach to a dedicated stock-chat workflow instead of growing service orchestration.

## Migration Plan

Deploying this change should not require data migration. Existing stock-chat conversations and messages remain valid because the graph reads the same chronological transcript that the service already loads.

Rollback is straightforward: restore the service to invoke the Clarification Agent directly. No database schema, API, or socket event contract rollback is required.

## Open Questions

None.
