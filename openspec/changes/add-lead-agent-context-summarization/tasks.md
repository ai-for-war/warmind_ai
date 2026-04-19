## 1. Runtime middleware wiring

- [x] 1.1 Replace the static lead-agent middleware list with a middleware factory that can build the stack from the resolved runtime model
- [x] 1.2 Attach LangChain `SummarizationMiddleware` to the lead-agent runtime with bounded trigger, keep, and summarization-input settings
- [x] 1.3 Add lead-agent-specific summarization prompt configuration so compacted summaries retain session intent, key decisions, constraints, and next-step context

## 2. Todo-state continuity

- [ ] 2.1 Add a lead-agent middleware that renders the current checkpoint-backed todo snapshot into a bounded authoritative prompt section before each model call
- [ ] 2.2 Integrate the todo-state injection middleware into the lead-agent middleware order so it composes correctly with planning, skill, orchestration, and tool-selection behavior
- [ ] 2.3 Ensure the injected todo context is derived from persisted runtime state rather than reconstructed from prior tool-message history

## 3. Verification and regression coverage

- [ ] 3.1 Add or update tests covering transcript compaction behavior, including replacement of older checkpointed history with a summary plus a recent raw-message window
- [ ] 3.2 Add or update tests covering todo-state continuity after compaction, including prompt-visible plan context on later turns
- [ ] 3.3 Add or update regression tests confirming conversation/message projection APIs remain unchanged while runtime checkpoint context is compacted
