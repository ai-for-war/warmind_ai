## 1. Lead-Agent Planning Runtime Integration

- [x] 1.1 Add lead-agent planning prompt constants and `tool_description` text for `TodoListMiddleware` so planning guidance is explicit about complex-task-only usage
- [x] 1.2 Update the lead-agent factory to attach LangChain `TodoListMiddleware` alongside the existing skill-aware middleware without replacing the singleton compiled runtime pattern
- [x] 1.3 Verify the runtime can access checkpoint-backed `todos` state without introducing a second source of truth in application persistence

## 2. Tool Exposure And Middleware Coordination

- [ ] 2.1 Update lead-agent tool-selection rules so `write_todos` is preserved as a trusted coordination tool alongside `load_skill`
- [ ] 2.2 Add integration coverage for middleware ordering so skill prompt injection, todo guidance, and filtered tool visibility remain active in the same model call
- [ ] 2.3 Verify simple turns can still complete without mandatory todo creation while complex turns retain access to planning tools

## 3. Persisted Plan Streaming

- [ ] 3.1 Extend `LeadAgentService` streaming flow to capture the last persisted todo snapshot before runtime execution begins
- [ ] 3.2 Detect completed `write_todos` tool calls, reload the latest checkpoint state, diff the persisted `todos` snapshot, and emit a dedicated `chat:message:plan_updated` event only when the persisted snapshot changes
- [ ] 3.3 Define and wire the new socket event payload shape so it returns the full todo snapshot plus summary counts keyed by `conversation_id`

## 4. Plan History Projection

- [ ] 4.1 Add an authenticated conversation-scoped read path for the latest persisted lead-agent plan snapshot backed directly by checkpoint state
- [ ] 4.2 Add or update API schemas so the plan endpoint returns both populated todo snapshots and a valid empty representation when no plan exists yet
- [ ] 4.3 Ensure conversation-to-thread validation and caller scoping for plan reads match the existing lead-agent conversation rules

## 5. Verification And Regression Coverage

- [ ] 5.1 Add tests for planning-enabled runtime behavior, including `write_todos` visibility and persisted `todos` state on complex turns
- [ ] 5.2 Add tests for service-layer plan streaming so `plan_updated` events are emitted only after persisted state changes and not from optimistic tool input alone
- [ ] 5.3 Add tests for the plan history endpoint covering valid scoped reads, empty-plan conversations, and not-found or cross-scope access failures
- [ ] 5.4 Run targeted regression checks for existing lead-agent token streaming, tool streaming, skill loading, and conversation history flows to confirm the planning rollout stays additive
