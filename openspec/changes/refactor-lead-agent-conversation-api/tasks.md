## 1. Persistence Models, Schemas, And Indexes

- [x] 1.1 Extend durable `conversation` and `message` models with optional `thread_id` so lead-agent turns can be projected into application-managed history records without breaking legacy chat data
- [x] 1.2 Update lead-agent and chat request/response schemas to support the new `POST /lead-agent/messages`, `GET /lead-agent/conversations`, and `GET /lead-agent/conversations/{conversation_id}/messages` contract, including any FE-facing `thread_id` fields that should be returned
- [x] 1.3 Extend conversation and message repository create/read/query methods to persist `thread_id` and support runtime-aware conversation filtering such as `has_thread_id=True|False`
- [x] 1.4 Add or update MongoDB indexes needed for runtime-aware conversation list queries while preserving the existing `conversation_id + created_at` access path for message history

## 2. Shared Conversation Persistence Helpers

- [x] 2.1 Extend `ConversationService.create_conversation(...)` so lead-agent can create conversation projections with a stored `thread_id`
- [x] 2.2 Extend `ConversationService.add_message(...)` so lead-agent can persist user and assistant messages with `thread_id` while still reusing conversation stats updates and first-message title generation
- [x] 2.3 Add any shared helper logic needed to validate whether a loaded conversation belongs to the expected runtime class before list/history endpoints return data

## 3. Lead Agent Service Refactor

- [x] 3.1 Refactor `LeadAgentService` so `send_message(...)` creates or validates the conversation projection, creates or reuses the mapped `thread_id`, persists the user message, and returns `user_message_id` plus `conversation_id`
- [x] 3.2 Implement background `LeadAgentService.process_agent_response(...)` that validates caller scope, streams the lead-agent runtime with `astream_events`, emits the existing `chat:message:*` socket events, and persists the final assistant message with `thread_id`
- [x] 3.3 Replace the old public thread-run flow with internal runtime helpers that continue to use checkpointed LangGraph state as the source of truth for multi-turn execution
- [x] 3.4 Add lead-agent conversation list and message history reads in `LeadAgentService` that return only conversations mapped to a lead-agent `thread_id`

## 4. HTTP API And Legacy Chat Isolation

- [x] 4.1 Replace the lead-agent router contract with `POST /lead-agent/messages`, `GET /lead-agent/conversations`, and `GET /lead-agent/conversations/{conversation_id}/messages`, using `BackgroundTasks` and the existing authenticated user plus organization-context dependencies
- [x] 4.2 Update legacy chat service/router list behavior so `/chat/conversations` excludes records mapped to a lead-agent `thread_id`
- [x] 4.3 Update legacy chat history behavior so `/chat/conversations/{conversation_id}/messages` does not return lead-agent conversations and instead treats them as out-of-scope resources
- [x] 4.4 Update shared service wiring and router registration as needed so the refactored lead-agent flow coexists cleanly with the legacy chat runtime

## 5. Verification

- [ ] 5.1 Add tests that verify the first lead-agent send creates both a new conversation projection and a new checkpoint-backed `thread_id`, then returns `conversation_id` and `user_message_id`
- [ ] 5.2 Add tests that verify a follow-up lead-agent send reuses the stored `thread_id`, preserves caller scope, and rejects unknown, unauthorized, or non-lead-agent `conversation_id` values
- [ ] 5.3 Add tests that verify lead-agent list/history endpoints return only `thread_id`-backed conversations and persisted messages in chronological order
- [ ] 5.4 Add tests that verify legacy `/chat/conversations` and `/chat/conversations/{conversation_id}/messages` exclude lead-agent projection records after the new discriminator logic is introduced
- [ ] 5.5 Add targeted tests or service-level verification for the async lead-agent socket lifecycle, including started, token, completed, and failed event behavior plus final assistant message persistence
- [ ] 5.6 Run targeted verification to confirm the refactored lead-agent flow works end-to-end and the legacy conversation-orchestrator chat path remains unaffected
