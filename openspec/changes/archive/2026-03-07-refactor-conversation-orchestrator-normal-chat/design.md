## Context

`conversation_orchestrator_workflow` is already the intended top-level entrypoint for conversation handling, but its current boundaries still reflect the old `chat_workflow` architecture. The orchestrator state and normalization layer are designed as parent concerns, yet the current `chat_branch` and `clarify_branch` still reuse legacy nodes from `chat_workflow` and pre-normalize branch output before the parent normalization step runs.

This creates three problems for Part 3 of the military graph plan:

1. The top-level routing taxonomy still uses `chat` instead of the approved `normal_chat`.
2. Branch handlers are coupled to legacy `chat_workflow` artifacts that were designed around internal intent routing and a deprecated `data_query` path.
3. Output normalization responsibility is split across both branch wrappers and the parent orchestrator, which makes the branch contract less clear and harder to evolve before strategic planning integration grows.

The design for this change is intentionally narrow: redefine the orchestrator branch boundaries for `normal_chat` and `unclear` so they become thin branch-local handlers, while preserving the orchestrator as the only owner of top-level route identity and final output normalization.

## Goals / Non-Goals

**Goals:**
- Rename the top-level conversational intent from `chat` to `normal_chat`.
- Remove all reuse of the legacy `chat_workflow` from orchestrator branches.
- Introduce a new branch-local `chat_node` and a new branch-local `clarify_node` under `conversation_orchestrator_workflow/nodes`.
- Keep branch return values minimal so the orchestrator remains the sole owner of normalized output construction.
- Preserve a stable parent output envelope for the service layer.
- Keep the strategic planning path conceptually separate from the `normal_chat` refactor.

**Non-Goals:**
- Rebuild or redesign the strategic planning workflow internals.
- Change service-layer persistence contracts.
- Move all streaming behavior out of branch-local nodes in this change.
- Preserve backward compatibility for the legacy `chat_workflow`.
- Reintroduce legacy `data_query` behavior into the new top-level routing taxonomy.

## Decisions

### Decision: The orchestrator owns top-level route identity and output normalization

The parent workflow will remain responsible for:
- classifying the request into `normal_chat`, `strategic_planning`, or `unclear`
- selecting the branch path
- mapping branch results into the final normalized output envelope

This avoids duplicate normalization logic and prevents branch nodes from having to know route metadata that the parent already owns.

**Alternatives considered**
- Let each branch return a full normalized envelope.
  - Rejected because it duplicates logic, increases coupling, and makes the `chat` to `normal_chat` rename leak into every branch.

### Decision: `normal_chat` and `clarify` become thin branch-local handlers

The orchestrator will call a new `chat_node` and a new `clarify_node` located under `conversation_orchestrator_workflow/nodes`. These nodes are local to the orchestrator capability and are not imported from the legacy `chat_workflow`.

This makes the Part 3 boundary explicit: branch behavior belongs to the orchestrator capability, while the deprecated workflow remains outside the forward path.

**Alternatives considered**
- Continue reusing legacy nodes from `chat_workflow`.
  - Rejected because it keeps legacy contracts and assumptions alive inside the new parent workflow boundary.
- Continue reusing the entire `chat_workflow`.
  - Rejected because it preserves internal intent routing that conflicts with the orchestrator role.

### Decision: Branch handlers return partial state updates only

The branch contract will be minimal. `normal_chat` returns:
- `agent_response`
- `tool_calls`
- `error`

`clarify` returns:
- `agent_response`
- `error`

`strategic_planning` may continue returning a richer branch result internally, but the orchestrator remains the only place that assembles the final public envelope.

This aligns with LangGraph's state-update model and keeps parent and branch schemas loosely coupled.

**Alternatives considered**
- Require every branch to return `intent`, `response_type`, `final_payload`, `tool_calls`, and `error`.
  - Rejected because the parent already knows the selected route and should derive these values consistently.

### Decision: Top-level intent taxonomy is fixed to three values

The parent workflow will use exactly:
- `normal_chat`
- `strategic_planning`
- `unclear`

This matches the approved scope from the military graph plan and removes the legacy top-level ambiguity introduced by `chat_workflow` and `data_query`.

**Alternatives considered**
- Keep `chat` as the top-level conversational route name.
  - Rejected because it is no longer the approved product language for the orchestrator capability.

## Risks / Trade-offs

- `Intent rename drift` -> Update classifier schema, routing logic, state literals, normalization defaults, and specs in one coordinated change.
- `Legacy imports survive the refactor` -> Treat imports from `app/graphs/workflows/chat_workflow` as invalid for the new `normal_chat` and `clarify` branches.
- `Double normalization persists` -> Ensure branch nodes return only partial updates and that `normalize_output` is the single envelope builder.
- `Thin branches lose observability` -> Keep tracing and logging at the orchestrator and node levels instead of expanding the branch return contract.
- `Branch-local streaming behavior remains coupled to node execution` -> Accept this as an intentional short-term trade-off; streaming extraction is outside the scope of this change.

## Migration Plan

1. Update the orchestrator intent taxonomy and parent state literals to use `normal_chat`.
2. Add new branch-local `chat_node` and `clarify_node` under `conversation_orchestrator_workflow/nodes`.
3. Update `chat_branch` and `clarify_branch` to call only the new local nodes and return partial state updates.
4. Remove branch-level output normalization and keep final output normalization only in the parent normalization node.
5. Verify strategic branch behavior still composes cleanly with the parent normalization layer.
6. After the orchestrator path is stable, retire or ignore the old `chat_workflow` for this feature path.

Rollback is low risk because the change is isolated to orchestrator contracts and branch-local wiring. If needed, the parent graph can be reverted to its previous route names and branch imports without changing service-layer APIs.

## Open Questions

- Should `final_payload` remain empty for `normal_chat` and `clarify`, or should the parent create lightweight default payloads for consistency?
- Should node filenames also be renamed from `chat_branch` to `normal_chat_branch`, or is keeping the existing file name acceptable as an implementation detail?
- Should branch-local streaming helpers be duplicated from legacy nodes now, or extracted into shared utilities in a later refactor?
