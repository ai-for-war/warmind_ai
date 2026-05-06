## 1. Stock-Agent Runtime Fork

- [x] 1.1 Create `app/agents/implementations/stock_agent/` by forking the lead-agent runtime package structure, including `agent.py`, `runtime.py`, `state.py`, `tools.py`, `tool_catalog.py`, `delegation.py`, and middleware modules.
- [x] 1.2 Rename runtime symbols to `StockAgent...`, `create_stock_agent`, `get_stock_agent_*`, and `STOCK_AGENT_*` while preserving lead-agent-equivalent behavior.
- [x] 1.3 Add `app/prompts/system/stock_agent.py` with stock-agent-specific prompt functions for base, todo, orchestration, worker, and summarization prompts.
- [x] 1.4 Update stock-agent middleware imports so all prompt, state, constants, and helper references point to stock-agent modules.
- [x] 1.5 Update stock-agent delegation executor to compile worker runtimes with `create_stock_agent` and stock-agent runtime config.
- [x] 1.6 Add stock-agent runtime unit tests mirroring lead-agent agent, runtime, middleware, tool catalog, tools, and delegation coverage.

## 2. Stock-Agent Checkpoint Persistence

- [x] 2.1 Add stock-agent LangGraph checkpointer infrastructure using `stock_agent_langgraph_checkpoints` and `stock_agent_langgraph_checkpoint_writes`.
- [x] 2.2 Wire application startup and shutdown to initialize and disconnect the stock-agent checkpointer alongside the existing checkpointer lifecycle.
- [x] 2.3 Update `create_stock_agent` to use the stock-agent checkpointer instead of the shared lead-agent checkpointer.
- [x] 2.4 Add tests that verify stock-agent checkpoint configuration uses stock-agent collection names and does not use lead-agent/shared collection names.

## 3. Stock-Agent Domain Models and Repositories

- [x] 3.1 Add stock-agent conversation and message domain models or stock-agent-specific repository model mappings that preserve the lead-agent conversation/message API shape.
- [x] 3.2 Add `StockAgentConversationRepository` backed by `stock_agent_conversations`.
- [x] 3.3 Add `StockAgentMessageRepository` backed by `stock_agent_messages`.
- [x] 3.4 Add stock-agent skill and skill-access domain models backed by `stock_agent_skills` and `stock_agent_skill_access`.
- [x] 3.5 Add `StockAgentSkillRepository` and `StockAgentSkillAccessRepository` with behavior equivalent to lead-agent skill repositories.
- [x] 3.6 Add MongoDB indexes for stock-agent conversations, messages, skills, and skill access without modifying lead-agent indexes.
- [x] 3.7 Add repository tests that verify reads and writes target only stock-agent collections.

## 4. Stock-Agent Services

- [ ] 4.1 Add `StockAgentSkillAccessResolver` that resolves enabled stock-agent skills from stock-agent repositories only.
- [ ] 4.2 Add `StockAgentSkillService` with selectable tool listing, skill CRUD, and enablement behavior equivalent to `LeadAgentSkillService`.
- [ ] 4.3 Add `StockAgentService` with runtime configuration, conversation creation, message persistence, background runtime processing, streaming, history reads, plan reads, and caller-scope validation equivalent to `LeadAgentService`.
- [ ] 4.4 Ensure `StockAgentService` uses stock-agent repositories, stock-agent exceptions, stock-agent runtime factories, stock-agent skill resolver, and stock-agent checkpointer state.
- [ ] 4.5 Add service factory helpers in `app/common/repo.py` and `app/common/service.py` for stock-agent repositories, skill resolver, skill service, and agent service.
- [ ] 4.6 Add stock-agent exception classes for invalid thread, thread not found, conversation not found, skill not found, invalid skill configuration, and run failure.
- [ ] 4.7 Add service tests mirroring lead-agent service and skill-service behavior, including cross-scope rejection and storage isolation.

## 5. Stock-Agent API

- [ ] 5.1 Add stock-agent request and response schemas equivalent to lead-agent schemas under a stock-agent schema module.
- [ ] 5.2 Add `app/api/v1/ai/stock_agent.py` with `/stock-agent/catalog`, `/stock-agent/tools`, `/stock-agent/skills`, `/stock-agent/messages`, `/stock-agent/conversations`, `/stock-agent/conversations/{conversation_id}/messages`, and `/stock-agent/conversations/{conversation_id}/plan`.
- [ ] 5.3 Register the stock-agent router in the v1 API router without changing lead-agent route registration.
- [ ] 5.4 Ensure `/stock-agent/messages` configures stock-agent runtime overrides, persists the user message, returns IDs immediately, and schedules stock-agent background processing.
- [ ] 5.5 Ensure stock-agent list/history/plan endpoints read from stock-agent storage and reject lead-agent or legacy chat conversation IDs.
- [ ] 5.6 Add integration tests mirroring lead-agent conversation and skill API coverage for `/stock-agent`.

## 6. Streaming, Metadata, and Planning Parity

- [ ] 6.1 Ensure stock-agent background processing emits existing chat socket started, token, tool start, tool end, plan updated, completed, and failed events keyed by stock-agent `conversation_id`.
- [ ] 6.2 Ensure stock-agent assistant messages persist runtime model metadata, token usage, finish reason, tool calls, skill metadata, loaded skills, orchestration mode, delegation metadata, and subagent enablement.
- [ ] 6.3 Ensure stock-agent plan snapshots are read from stock-agent checkpointed todo state and returned through `/stock-agent/conversations/{conversation_id}/plan`.
- [ ] 6.4 Ensure stock-agent delegated worker events are filtered or surfaced consistently with lead-agent streaming behavior.
- [ ] 6.5 Add tests for stock-agent streaming event payloads, plan update snapshots, assistant metadata, and delegated execution metadata.

## 7. Isolation and Regression Verification

- [ ] 7.1 Add tests proving lead-agent API calls do not return stock-agent conversations or messages.
- [ ] 7.2 Add tests proving legacy chat browsing does not return stock-agent conversations or messages.
- [ ] 7.3 Add tests proving stock-agent API calls do not return lead-agent conversations, messages, skills, or skill access records.
- [ ] 7.4 Run the stock-agent-focused unit and integration test suite.
- [ ] 7.5 Run existing lead-agent unit and integration tests to verify the fork did not regress lead-agent behavior.
- [ ] 7.6 Run OpenSpec validation/status for `add-stock-agent-full-fork` and fix any artifact or requirement issues.
