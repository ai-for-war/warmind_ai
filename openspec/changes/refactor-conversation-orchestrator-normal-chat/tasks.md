## 1. Update orchestrator contracts

- [ ] 1.1 Rename the top-level conversational intent from `chat` to `normal_chat` in orchestrator state types and classifier schemas
- [ ] 1.2 Update orchestrator routing logic and normalization defaults to use `normal_chat`, `strategic_planning`, and `unclear`
- [ ] 1.3 Remove branch-level assumptions that require legacy `chat_workflow` route metadata in orchestrator code

## 2. Introduce branch-local handlers

- [ ] 2.1 Create a new `chat_node` under `app/graphs/workflows/conversation_orchestrator_workflow/nodes`
- [ ] 2.2 Create a new `clarify_node` under `app/graphs/workflows/conversation_orchestrator_workflow/nodes`
- [ ] 2.3 Update the normal chat branch wrapper to call only the new local `chat_node`
- [ ] 2.4 Update the clarify branch wrapper to call only the new local `clarify_node`

## 3. Simplify branch contracts

- [ ] 3.1 Change normal chat branch results to return only minimal branch-local fields needed by the parent workflow
- [ ] 3.2 Change clarify branch results to return only minimal branch-local fields needed by the parent workflow
- [ ] 3.3 Keep final output envelope construction only in the parent normalization node
- [ ] 3.4 Verify the strategic branch still composes correctly with parent-owned normalization

## 4. Validate and clean up

- [ ] 4.1 Remove remaining imports from `app/graphs/workflows/chat_workflow` inside orchestrator branch code
- [ ] 4.2 Update tests or add coverage for `normal_chat`, `strategic_planning`, and `unclear` routing behavior
- [ ] 4.3 Add or update tests for normalized orchestrator output after branch execution
- [ ] 4.4 Run targeted validation to confirm the orchestrator no longer depends on legacy `chat_workflow` for `normal_chat` and `clarify`
