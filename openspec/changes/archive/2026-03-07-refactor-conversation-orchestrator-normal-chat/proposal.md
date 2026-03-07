## Why

The current conversation orchestrator still carries legacy chat boundary decisions from the old `chat_workflow`, including top-level `chat` naming, reuse of legacy chat/clarify nodes, and branch-level normalization that overlaps with parent orchestration responsibilities. This makes the Part 3 refactor harder to reason about and creates unnecessary coupling before introducing the strategic planning workflow.

## What Changes

- Refactor the top-level conversation orchestrator intent taxonomy from `chat` to `normal_chat`.
- Replace legacy `chat_workflow` reuse with new branch-local nodes under `conversation_orchestrator_workflow/nodes`.
- Define the `normal_chat` branch as a thin branch that calls only a new chat node and returns a minimal branch result.
- Define the clarification branch as a thin branch that calls only a new clarify node and returns a minimal branch result.
- Move ownership of response normalization fully to the parent orchestrator so branches no longer construct the final output envelope themselves.
- Remove legacy top-level branch assumptions inherited from the old `chat_workflow`, including internal reuse of old intent routing artifacts.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `conversation-orchestrator-workflow`: Change the top-level routing taxonomy, branch boundaries, and orchestrator-owned normalization contract for `normal_chat`, `strategic_planning`, and `unclear`.

## Impact

- Affected code:
  - `app/graphs/workflows/conversation_orchestrator_workflow/graph.py`
  - `app/graphs/workflows/conversation_orchestrator_workflow/state.py`
  - `app/graphs/workflows/conversation_orchestrator_workflow/nodes/*`
- Affected behavior:
  - top-level intent naming and routing
  - branch contract between orchestrator and `normal_chat` / `clarify`
  - final output normalization ownership
- Affected systems:
  - conversation orchestration
  - normal chat handling
  - clarification handling
