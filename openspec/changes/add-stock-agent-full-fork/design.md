## Context

The current `lead_agent` vertical is a complete agent product surface: LangChain `create_agent` runtime, LangGraph checkpointing, middleware, planning, subagent delegation, skill CRUD/enablement, `/lead-agent` endpoints, conversation/message projections, and socket streaming.

`Stock_Agent` must start behaviorally identical to lead-agent but must be independently customizable later. The user explicitly chose a full fork with separate API and separate persistence, including stock-agent-specific conversation/message collections and checkpoint collections.

## Goals / Non-Goals

**Goals:**
- Create a `stock_agent` runtime package that mirrors the lead-agent runtime behavior and can diverge later without touching lead-agent code.
- Expose a `/stock-agent` API equivalent to `/lead-agent`.
- Persist stock-agent skills, skill access, conversations, messages, and LangGraph checkpoints in stock-agent-specific collections.
- Keep lead-agent data, APIs, services, runtime caches, and tests isolated from stock-agent additions.
- Add tests that prove stock-agent parity and storage isolation.

**Non-Goals:**
- Add stock-specific investing, screening, backtesting, or research behavior in this change.
- Refactor lead-agent into a shared generic agent core.
- Migrate existing lead-agent conversations, skills, messages, or checkpoints into stock-agent collections.
- Change frontend event names unless a later frontend contract requires a separate socket namespace.

## Decisions

### Full fork instead of shared core

Create stock-agent modules by forking the lead-agent vertical into stock-agent-specific files, classes, functions, prompts, schemas, services, repositories, and tests.

**Rationale:** The requirement is future independent customization. A shared core would reduce duplication but would keep behavior coupled, especially around middleware, skill policy, delegation, and prompt evolution.

**Alternative considered:** Extract `configurable_agent_core` and pass agent-specific config. This is cleaner long-term but conflicts with the current request for a full fork and would increase refactor risk before the stock-agent product surface exists.

### Separate persistence collections

Use dedicated MongoDB collections:
- `stock_agent_skills`
- `stock_agent_skill_access`
- `stock_agent_conversations`
- `stock_agent_messages`
- `stock_agent_langgraph_checkpoints`
- `stock_agent_langgraph_checkpoint_writes`

**Rationale:** Conversation filtering based only on `thread_id` is not enough once multiple agent verticals exist. Dedicated collections provide hard isolation and simpler query semantics.

**Alternative considered:** Reuse `conversations` and `messages` with an `agent_type` discriminator. This would be less code, but it does not satisfy the explicit request for collection-level isolation.

### Dedicated stock-agent service and repositories

Add `StockAgentService`, `StockAgentSkillService`, `StockAgentSkillAccessResolver`, stock-agent domain models, stock-agent schemas, and stock-agent repositories rather than parameterizing the lead-agent services.

**Rationale:** Service-level isolation prevents accidental use of lead-agent repositories, exceptions, prompt functions, or runtime factories. It also makes future stock-specific behavior easier to localize.

**Alternative considered:** Subclass `LeadAgentService`. This would reduce duplication but is fragile because the service has many class/static references to lead-agent metadata, exceptions, and serialization behavior.

### Dedicated checkpointer factory

Add a stock-agent checkpointer path that uses the same MongoDBSaver implementation but different checkpoint and write collection names.

**Rationale:** LangGraph thread IDs alone are not a sufficient isolation boundary when the user requested separate stock-agent collections. Separate collections also make operational cleanup and debugging clearer.

**Alternative considered:** Reuse `get_langgraph_checkpointer()`. This would preserve runtime behavior but would store stock-agent checkpoint state in lead-agent/shared checkpoint collections.

### API parity with `/lead-agent`

Expose `/stock-agent/catalog`, `/stock-agent/tools`, `/stock-agent/skills`, `/stock-agent/messages`, `/stock-agent/conversations`, `/stock-agent/conversations/{id}/messages`, and `/stock-agent/conversations/{id}/plan`.

**Rationale:** The user requested a separate API matching lead-agent behavior. Keeping route shapes parallel reduces frontend integration friction and makes test parity straightforward.

**Alternative considered:** Add one generic `/agents/{agent_type}` API. This would be a larger API redesign and would not preserve the requested full fork boundary.

### Socket contract reuse

Reuse the existing chat socket events with stock-agent `conversation_id` values from `stock_agent_conversations`.

**Rationale:** The current lead-agent processing already streams through the chat-compatible event contract. Reusing event names minimizes frontend changes while persistence isolation comes from stock-agent conversation IDs and collections.

**Alternative considered:** Create stock-agent-specific socket event names. This adds frontend work without being necessary for backend isolation.

## Risks / Trade-offs

- **Duplicate code can drift unintentionally** -> Add parity tests and keep the initial fork mechanically close to lead-agent before stock-specific customization starts.
- **Accidental cross-agent repository usage** -> Use stock-agent-specific class names, dependency providers, collection names, and tests that assert lead-agent collections are not touched by stock-agent flows.
- **Checkpointer lifecycle complexity increases** -> Keep the stock-agent checkpointer implementation structurally equivalent to the existing checkpointer and initialize/disconnect it alongside app startup/shutdown.
- **API parity expands test surface** -> Mirror the existing lead-agent unit/integration test pattern and focus assertions on route behavior, storage isolation, runtime factory wiring, and skill enablement.
- **Full fork makes future lead-agent bugfixes manual** -> Accept this trade-off for now because independent customization is the primary goal; later shared-core extraction can be proposed only after stock-agent divergence is known.

## Migration Plan

1. Add new stock-agent collections and indexes without modifying existing lead-agent collections.
2. Initialize the stock-agent LangGraph checkpointer with stock-agent-specific checkpoint collection names.
3. Register `/stock-agent` routes alongside `/lead-agent`.
4. Deploy with no data migration; existing lead-agent data remains untouched.
5. Roll back by unregistering the `/stock-agent` router and disabling the stock-agent checkpointer initialization; existing stock-agent collections can remain inert.

## Open Questions

None. The implementation will use `stock_agent`, `StockAgent...`, `/stock-agent`, fully separate persistence collections, and behavior parity with lead-agent as the accepted baseline.
