## Context

The current lead-agent runtime already has the transport and persistence
contract needed for skill-aware execution:

- `LeadAgentService` owns conversation validation, message persistence,
  background execution, and socket streaming
- the runtime is built with `langchain.agents.create_agent`
- thread state is checkpointed through LangGraph and keyed by `thread_id`
- `LeadAgentState` currently carries caller scope (`user_id`,
  `organization_id`)
- the lead-agent implementation exposes explicit seams for `tools.py` and
  `middleware.py`, but both are still intentionally empty

That foundation is good for the next step, because skills are not a new public
API surface in phase 1. They are an internal execution layer that should let
lead agent:

- discover which capabilities are available for the current caller
- load specialized instructions only when needed
- expose only the tools relevant to the selected skill
- persist enough metadata for debugging and evaluation

Constraints and realities from the current codebase:

- the public lead-agent API is already conversation-centric and should remain
  unchanged in this phase
- socket event names and payload shape should remain unchanged
- the current `LeadAgentService` caches a compiled agent runtime, so the design
  should avoid requiring one agent instance per user
- the repo does not yet have a user-settings system that can naturally hold
  per-user skill access
- skill execution must continue to respect `user_id` and `organization_id`
  scoping

## Goals / Non-Goals

**Goals:**
- Add an internal skill architecture to lead agent without changing the
  frontend message flow
- Support per-user skill enablement for each turn
- Let the model discover skills cheaply, then activate a skill on demand
- Limit tool visibility dynamically based on active skill context
- Keep the lead-agent runtime checkpoint-backed and conversation-centric
- Persist skill metadata and telemetry for debugging and evaluation
- Preserve a clear path to future growth without prematurely introducing a
  full multi-agent topology

**Non-Goals:**
- Let the client explicitly choose a skill in phase 1
- Introduce user-uploaded or untrusted custom skills
- Build a specialist-agent handoff system in this phase
- Add a frontend or admin UI to manage skill assignments
- Change the lead-agent socket protocol or conversation API
- Rebuild the runtime around per-request compiled agents

## Decisions

### D1: Keep one lead-agent runtime and model skills as progressive capability bundles

**Decision**: Phase 1 will keep `lead_agent` as a single stateful runtime.
Skills will be modeled as internal capability bundles rather than standalone
specialist agents.

A skill bundle contains:

- `skill_id`
- `name`
- `description`
- lightweight discovery summary
- full instructions for activated execution
- `allowed_tool_names`
- optional examples, tags, and version metadata

**Rationale**:
- the current runtime already has durable thread state, background execution,
  and socket streaming; adding skill awareness is lower risk than introducing
  another routing layer
- the product requirement for phase 1 is internal-only skill activation, not a
  user-visible specialist topology
- the skills pattern maps cleanly onto the existing extension seams in
  `lead_agent/agent.py`, `tools.py`, `middleware.py`, and `state.py`

**Alternatives considered:**
- **Specialist sub-agents with handoff**: more flexible long term, but rejected
  for phase 1 because it introduces extra model calls, more complex tracing,
  and more failure modes than the current product scope needs
- **Static mega-prompt with all skill content always loaded**: rejected because
  it increases token cost, dilutes routing quality, and makes future skill
  growth expensive

### D2: Store trusted skills locally as manifests with separate summary and activation content

**Decision**: Skills will be implemented as trusted local manifests under the
lead-agent implementation boundary, with a registry abstraction that can return
either:

- a lightweight discovery view for prompt injection
- the full activated instructions for one specific skill

Recommended structure:

- `app/agents/implementations/lead_agent/skills/types.py`
- `app/agents/implementations/lead_agent/skills/registry.py`
- `app/agents/implementations/lead_agent/skills/catalog/*.py` or local content
  files referenced by the registry

Each manifest should distinguish between:

- `summary_prompt`: short, discoverable description shown before activation
- `activation_prompt`: full instructions shown only after the skill is active

**Rationale**:
- skills are trusted backend-owned assets in phase 1, so local versioned
  manifests are the simplest and safest storage model
- separating summary from full instructions allows progressive disclosure and
  keeps every turn from paying the cost of the entire skill catalog
- versioned local manifests make it easier to test and diff skill changes in
  source control

**Alternatives considered:**
- **Database-stored skill content**: more dynamic, but rejected for phase 1
  because there is no product requirement for runtime editing and it adds
  editorial and validation complexity
- **One Python string blob per skill in code**: simple, but rejected as the
  primary pattern because larger skill prompts become hard to review and reuse

### D3: Resolve per-user skill access in the service layer on every turn

**Decision**: `LeadAgentService` will resolve enabled skills for the caller
before invoking the runtime and inject the result into thread state for that
turn.

Recommended abstraction:

- `LeadAgentSkillAccessResolver`
- backed by a new additive persistence source such as
  `lead_agent_skill_access` documents keyed by `user_id` and optional
  `organization_id`

Suggested access document:

```json
{
  "user_id": "user-123",
  "organization_id": "org-456",
  "enabled_skill_ids": ["sales-analytics", "web-research"],
  "updated_at": "2026-03-29T00:00:00Z"
}
```

Resolution rules:

1. Resolve the caller's current enabled skills before each runtime execution
2. Inject enabled skill IDs into state regardless of prior thread state
3. If no access document exists, use a safe default such as an empty skill set
   or a configured default allowlist

**Rationale**:
- per-user access is a product requirement, so the source of truth must be more
  specific than a global config
- resolving access on every turn prevents stale thread state from granting
  skills that were later removed
- placing this logic in `LeadAgentService` keeps authorization and runtime
  orchestration in one place

**Alternatives considered:**
- **Persist enabled skills only at thread creation**: rejected because access
  changes would not take effect for existing threads
- **Compile a separate agent per user**: rejected because the current service
  caches a compiled agent and per-user compilation would increase latency and
  complexity

### D4: Use middleware plus a `load_skill` tool, but avoid storing full skill prompts in thread message history

**Decision**: Skill activation will use both middleware and an internal
`load_skill` tool.

Proposed flow:

1. Service injects `enabled_skill_ids` into state before execution
2. `SkillContextMiddleware` injects lightweight summaries for enabled skills
3. The model can answer normally or call `load_skill(skill_id)`
4. `load_skill` validates access and updates state with:
   - `active_skill_id`
   - `loaded_skills`
   - `allowed_tool_names`
   - `active_skill_version`
5. On the next model call, middleware injects the activated skill instructions
   from the registry
6. `ToolSelectionMiddleware` exposes only the allowed tools for that call

Important implementation detail:

- `load_skill` should return a concise acknowledgement, not the entire skill
  body
- the full activation prompt should be re-injected by middleware based on
  state

**Rationale**:
- this preserves the ergonomic “skill loading” pattern while preventing large
  prompt blobs from being appended to checkpointed message history on every
  activation
- middleware is the natural place to vary prompt context and visible tools per
  model call
- the approach keeps the model aware of skills before activation, but still
  constrains expensive context to the turns that need it

**Alternatives considered:**
- **Return full skill content directly from `load_skill`**: rejected because it
  would bloat durable thread history and degrade long-lived threads
- **Have middleware activate skills automatically with no tool call**: rejected
  because explicit activation is easier to trace, test, and reason about

### D5: Keep a singleton compiled runtime and make skill tools runtime-context-aware

**Decision**: The lead-agent runtime will remain a cached compiled agent.
All tools that may be exposed through skills must be registered in the runtime
up front and must read caller scope from runtime state instead of being baked
per user.

This implies:

- `create_lead_agent()` returns one compiled graph instance
- tools rely on runtime state and service abstractions to enforce
  user/org/skill scope at execution time
- middleware filters visible tools per call so the model does not see the full
  union of registered tools on every turn

**Rationale**:
- this fits the current `LeadAgentService.agent` lifecycle
- it avoids repeated agent compilation and keeps checkpoint usage stable
- it still supports per-user behavior because visibility and authorization are
  enforced at runtime rather than construction time

**Alternatives considered:**
- **Create an agent per request with only that user's tools**: rejected because
  it complicates runtime caching, adds latency, and makes cross-turn behavior
  harder to keep consistent
- **Register all tools and never filter them**: rejected because prompt clutter
  and tool confusion would grow as the skill surface expands

### D6: Extend thread state and assistant metadata additively

**Decision**: Skill state and skill telemetry will be additive extensions to
existing runtime and persistence models.

Recommended runtime state additions:

```python
class LeadAgentState(AgentState):
    user_id: str
    organization_id: str | None
    enabled_skill_ids: list[str] = []
    active_skill_id: str | None = None
    loaded_skills: list[str] = []
    allowed_tool_names: list[str] = []
    active_skill_version: str | None = None
```

Recommended assistant metadata additions:

- `skill_id`
- `skill_version`
- `loaded_skills`

The existing public API remains unchanged; these fields are additive to backend
state and persisted metadata.

**Rationale**:
- additive changes minimize migration risk and preserve compatibility with
  existing conversations
- skill metadata needs to survive across turns for observability and debugging
- storing only compact identifiers and versions is enough; there is no need to
  persist full skill prompts in message metadata

**Alternatives considered:**
- **Store full skill content in metadata**: rejected because it is noisy,
  unnecessary, and increases storage footprint
- **Keep skill state only in volatile memory**: rejected because activation and
  observability need durable thread-aware state

### D7: Keep the public lead-agent API unchanged and make skill behavior backend-managed

**Decision**: Phase 1 will not add skill parameters to:

- `POST /lead-agent/messages`
- `GET /lead-agent/conversations`
- `GET /lead-agent/conversations/{conversation_id}/messages`

Skill resolution, activation, and tool gating stay backend-managed.

**Rationale**:
- this matches the agreed phase 1 requirement for internal-only skill
  activation
- it avoids introducing frontend dependency on internal runtime abstractions
- it keeps the rollout reversible behind backend logic and feature flags

**Alternatives considered:**
- **Require client-specified skill IDs**: rejected because it creates UX and
  API complexity before the automatic routing behavior is validated
- **Expose active skill immediately in public response models**: deferred until
  the team decides whether skill transparency belongs in the product UX

## Risks / Trade-offs

- **[Wrong skill gets activated]** → Mitigation: keep skill summaries explicit,
  include positive/negative examples in manifests, preserve a no-skill path,
  and log activation outcomes for review
- **[Prompt bloat from many skills or repeated activations]** → Mitigation:
  separate summary from activation prompts, inject full instructions only for
  the active skill, and avoid returning full skill bodies from `load_skill`
- **[Skill access changes do not affect existing threads]** → Mitigation:
  resolve enabled skills on every turn and overwrite state from the current
  access source before execution
- **[Permission leaks through tools]** → Mitigation: enforce access twice, once
  in middleware for visibility and again inside tools or service calls for
  authorization
- **[Singleton runtime accumulates too many registered tools over time]** →
  Mitigation: keep a small base tool surface, use tool filtering aggressively,
  and split overly broad tools into skill-specific subsets only when needed
- **[No current admin UI for per-user skill access]** → Mitigation: start with
  backend-managed access documents or seed data, then add an admin surface in a
  later change if the operational need becomes real

## Migration Plan

1. Add the skill registry, access resolver, middleware, internal `load_skill`
   tool, and additive state or metadata changes behind a global feature flag
   such as `LEAD_AGENT_SKILLS_ENABLED`
2. Deploy with the feature flag disabled so the existing lead-agent runtime
   behavior remains unchanged
3. Seed the initial trusted skills and create access records for a small set of
   internal users
4. Enable the feature flag for controlled traffic and validate:
   - skill activation rate
   - tool call success rate
   - token and latency regression
   - socket completion behavior
5. Expand access gradually once telemetry shows stable behavior

Rollback:

- disable the global feature flag to return the runtime to its non-skill path
- leave additive state and access documents in place; they are backward
  compatible and can remain unused

## Open Questions

- Which concrete skills should ship in the first rollout, and which tools does
  each one need?
- Should the default for users without access records be “no skills” or a small
  baseline allowlist?
- Does the team want a future organization-level override model in addition to
  per-user access?
- When should skill usage become visible in the UI, if at all?
