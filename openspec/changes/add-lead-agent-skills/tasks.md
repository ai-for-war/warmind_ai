## 1. Skill Catalog And Access Infrastructure

- [x] 1.1 Add lead-agent skill types, registry abstractions, and trusted local skill manifests with separate discovery summaries and activation instructions
- [x] 1.2 Add additive persistence and repository helpers for per-user lead-agent skill access records keyed by `user_id` and optional `organization_id`
- [x] 1.3 Implement a `LeadAgentSkillAccessResolver` and register any required service wiring or feature-flag configuration for skill-aware execution

## 2. Lead-Agent Runtime State And Internal Skill Tooling

- [x] 2.1 Extend `LeadAgentState` with skill-aware fields such as `enabled_skill_ids`, `active_skill_id`, `loaded_skills`, `allowed_tool_names`, and `active_skill_version`
- [x] 2.2 Implement the internal `load_skill` tool so it validates skill access, updates runtime state, and returns only a concise acknowledgement instead of full skill content
- [x] 2.3 Update the lead-agent factory to register the internal skill-support tool surface while preserving the shared singleton compiled runtime model

## 3. Middleware And Dynamic Tool Exposure

- [x] 3.1 Implement middleware that injects lightweight summaries for enabled skills into the model context before initial reasoning
- [x] 3.2 Extend middleware behavior so an active skill re-injects its full activation instructions on subsequent model calls without bloating thread message history
- [x] 3.3 Implement dynamic tool-selection middleware that exposes only the base or skill-allowed tool subset for each model call and re-evaluates when skill state changes

## 4. Lead-Agent Service, Metadata, And Runtime Integration

- [x] 4.1 Update `LeadAgentService` to resolve enabled skills on every turn and inject the resolved skill access state before invoking or streaming the runtime
- [x] 4.2 Extend assistant message metadata models and persistence so skill execution details such as `skill_id`, `skill_version`, and `loaded_skills` can be stored additively
- [x] 4.3 Update lead-agent response processing to capture skill-aware telemetry and metadata while preserving the existing conversation-centric API and socket event contract

## 5. Verification And Rollout Hardening

- [ ] 5.1 Add tests for per-user skill access resolution, including enabled, disabled, and missing-access-record cases
- [ ] 5.2 Add tests that verify `load_skill`, middleware prompt injection, and dynamic tool exposure work together across multiple model calls in one thread
- [ ] 5.3 Add tests that verify skill execution metadata is persisted correctly and that normal no-skill turns still work without API contract changes
- [ ] 5.4 Run targeted verification for feature-flagged rollout behavior and confirm the existing lead-agent conversation flow and socket lifecycle remain unaffected when skills are disabled
