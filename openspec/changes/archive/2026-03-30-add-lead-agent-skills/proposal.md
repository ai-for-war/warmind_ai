## Why

The current lead-agent runtime was intentionally introduced with an empty tool
registry and no custom middleware so the team could first land the
conversation-centric, checkpoint-backed execution contract. That foundation now
exists, but the lead agent still behaves like a generic assistant and cannot
activate specialized workflows, policies, or tool subsets based on user intent.

The product now needs lead agent to grow through internal skills without
changing the frontend chat flow. A skill system gives the backend a structured
way to add domain-specific behavior, progressively load specialized context,
and control which tools are exposed at runtime while keeping the existing
conversation and socket contracts stable.

## What Changes

- Add a new internal lead-agent skill system that lets the runtime discover
  which skills are enabled for the current user, expose lightweight skill
  summaries to the model, and load a skill on demand during a turn
- Introduce a built-in skill catalog and `load_skill` mechanism so the agent
  can progressively load full skill instructions only when a request requires
  specialized behavior
- Extend lead-agent thread state to track skill-related metadata such as
  enabled skills, active skill, loaded skills, and skill-scoped tool
  availability
- Add custom lead-agent middleware to inject available skill summaries into the
  system prompt, filter tools dynamically based on active skill context, and
  capture skill selection metadata for observability
- Preserve the current conversation-centric lead-agent API and existing socket
  streaming contract; skill activation remains internal-only in phase 1 and is
  not exposed as a required frontend input
- Persist skill execution metadata alongside assistant messages so the backend
  can debug, evaluate, and later expose skill usage if needed

## Capabilities

### New Capabilities
- `lead-agent-skills`: provide an internal skill catalog, per-user skill
  enablement, on-demand skill loading, dynamic tool exposure, and skill-aware
  execution metadata for lead-agent turns

### Modified Capabilities
- `lead-agent-runtime`: change runtime requirements so lead agent can use
  custom middleware, non-empty tool registries, extended thread state, and
  skill-aware execution while preserving the existing conversation-backed API
  and checkpoint-backed thread model

## Impact

- **Runtime behavior**: lead-agent moves from a minimal empty-tool runtime to a
  skill-aware runtime with custom middleware and dynamic tool selection
- **No public API break in phase 1**: existing lead-agent message, conversation
  listing, and message history endpoints remain the same while skill routing
  stays backend-managed
- **State and metadata changes**: lead-agent thread state and assistant message
  metadata will carry skill-related information needed for execution and
  observability
- **New internal registry/configuration**: add trusted skill manifests or
  registry entries and a per-user skill access source
- **Affected code**: `app/agents/implementations/lead_agent/agent.py`,
  `app/agents/implementations/lead_agent/state.py`,
  `app/agents/implementations/lead_agent/tools.py`,
  `app/agents/implementations/lead_agent/middleware.py`,
  `app/services/ai/lead_agent_service.py`, and new lead-agent skill registry or
  manifest modules under `app/agents/implementations/lead_agent/`
