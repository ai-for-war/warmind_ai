## Why

The current conversation entry flow is centered around `chat_workflow`, which mixes top-level intent routing with branch-specific handling. This makes it difficult to introduce a dedicated strategic planning branch while keeping routing behavior simple, auditable, and easy to evolve.

Now is the right time to introduce a top-level orchestrator because the military strategic planning feature requires a clean parent workflow that can decide whether a request should go to normal chat, strategic planning, or clarification without pushing deeper reasoning into the entrypoint.

## What Changes

- Add a new top-level `conversation_orchestrator_workflow` that prepares shared state, classifies top-level intent, routes to the correct branch, and normalizes the final output.
- Standardize top-level routing intents to `chat`, `strategic_planning`, and `unclear`.
- Define a normalized response envelope for orchestrator outputs so downstream service logic receives a stable contract regardless of the selected branch.
- Keep clarification as a lightweight top-level node in V1 instead of a separate workflow.
- Preserve the existing service-layer responsibilities for persistence, streaming, and completion events.

## Capabilities

### New Capabilities
- `conversation-orchestrator-workflow`: Top-level conversation orchestration for shared state preparation, intent routing, clarification fallback, and normalized output handling.

### Modified Capabilities
- None.

## Impact

- Affected systems:
  - workflow orchestration in `app/graphs/workflows/`
  - graph registration and top-level workflow selection
  - service integration that invokes the parent workflow entrypoint
- Affected behavior:
  - top-level requests will be routed through a dedicated parent workflow instead of relying on `chat_workflow` as the entrypoint
  - branch outputs will be normalized into a shared response contract
- Dependencies:
  - existing LangGraph-based workflow patterns
  - current classifier and clarify patterns, which may be reused or adapted
