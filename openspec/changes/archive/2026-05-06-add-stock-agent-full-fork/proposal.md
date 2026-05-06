## Why

The existing lead-agent runtime now has a complete conversation-centric API, skill system, planning state, subagent delegation, and checkpoint-backed execution path. The product needs a separate `Stock_Agent` that starts with the same behavior but can be customized independently without risking regressions in lead-agent behavior or sharing persisted agent data.

This change creates a full stock-agent fork with its own runtime, API, services, repositories, MongoDB collections, and LangGraph checkpoint namespace so future stock-specific behavior can diverge cleanly.

## What Changes

- Add a new `stock_agent` implementation under `app/agents/implementations/` that mirrors lead-agent runtime behavior, including model catalog, state schema, tools, middleware, planning, skill loading, subagent delegation, tool selection, tool error handling, and summarization.
- Add a dedicated `StockAgentService` with conversation, message, plan, runtime configuration, streaming, and thread validation behavior equivalent to `LeadAgentService`.
- Add a dedicated `/stock-agent` API surface equivalent to `/lead-agent`, including runtime catalog, selectable tools, skill CRUD/enablement, message submission, conversation listing, message history, and plan snapshot endpoints.
- Add isolated stock-agent domain schemas, domain models, repositories, service factories, exceptions, and MongoDB indexes for stock-agent skills, skill access, conversations, messages, and checkpointer persistence.
- Ensure stock-agent conversations and messages are stored in stock-agent-specific collections rather than the shared conversation/message collections used by normal chat or lead-agent projections.
- Preserve lead-agent behavior and persisted data unchanged; this change adds a parallel stock-agent vertical instead of modifying lead-agent contracts.

## Capabilities

### New Capabilities
- `stock-agent-runtime`: Defines the checkpoint-backed `Stock_Agent` runtime, state, model configuration, prompt, middleware stack, tools, planning, and subagent delegation behavior.
- `stock-agent-skills`: Defines isolated stock-agent skill CRUD, skill enablement, selectable tool catalog, per-caller access resolution, and runtime skill loading behavior.
- `stock-agent-conversations`: Defines the `/stock-agent` API, stock-agent conversation/message/plan persistence, socket streaming behavior, and collection isolation.

### Modified Capabilities
- None.

## Impact

- **Runtime code**: adds `app/agents/implementations/stock_agent/` and `app/prompts/system/stock_agent.py`, forked from lead-agent equivalents.
- **API surface**: adds `app/api/v1/ai/stock_agent.py` and registers it in the v1 router under `/stock-agent`.
- **Services and dependency wiring**: adds stock-agent service, skill service, skill access resolver, repository/service factory helpers, and agent-specific exceptions.
- **Persistence**: adds MongoDB collections and indexes for `stock_agent_skills`, `stock_agent_skill_access`, `stock_agent_conversations`, `stock_agent_messages`, and stock-agent LangGraph checkpoints.
- **Tests**: adds unit and integration coverage mirroring the lead-agent runtime, middleware, tool catalog, skills, service, and API tests.
- **Non-goal**: this proposal does not customize stock-specific investing behavior yet; it creates a behaviorally equivalent fork that can be customized later.
