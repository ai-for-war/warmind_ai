## 1. Lead Agent Runtime Foundations

- [x] 1.1 Create the `lead_agent` module structure under `app/agents/implementations/`
- [x] 1.2 Define `LeadAgentState` by extending `AgentState` with `user_id` and optional `organization_id`
- [x] 1.3 Add empty `tools.py` and `middleware.py` modules that export the V1 runtime extension seams
- [x] 1.4 Implement the lead-agent factory with `langchain.agents.create_agent`, `tools=[]`, `middleware=[]`, and the custom state schema

## 2. MongoDB Checkpointer Infrastructure

- [x] 2.1 Add LangGraph MongoDB checkpointer infrastructure under `app/infrastructure/langgraph/`
- [x] 2.2 Initialize and expose a shared MongoDB-backed checkpointer that reuses the existing MongoDB connection settings
- [x] 2.3 Wire checkpointer startup and shutdown into the FastAPI app lifecycle
- [x] 2.4 Ensure the lead-agent runtime is compiled or created with the MongoDB checkpointer as its durable state backend

## 3. Lead Agent Service And Thread Lifecycle

- [x] 3.1 Add a dedicated `LeadAgentService` under `app/services/ai/`
- [x] 3.2 Implement `create_thread` to generate a new `thread_id` and seed thread state with caller scope
- [x] 3.3 Implement `run_thread` to validate thread ownership from checkpointed state and invoke the lead agent with new user input
- [x] 3.4 Return the final assistant response from the lead-agent run path without using application-managed `conversation` or `message` persistence

## 4. API Schemas, Routing, And Dependency Wiring

- [ ] 4.1 Add request and response schemas for lead-agent thread creation and thread run submission
- [ ] 4.2 Add the `/lead-agent` API router with `POST /lead-agent/threads` and `POST /lead-agent/threads/{thread_id}/runs`
- [ ] 4.3 Reuse the existing authenticated user and organization-context dependencies for lead-agent requests
- [ ] 4.4 Register the lead-agent service in `app/common/service.py` and include the new router in `app/api/v1/router.py`

## 5. Verification And Hardening

- [ ] 5.1 Add tests for creating a lead-agent thread and returning a usable `thread_id`
- [ ] 5.2 Add tests that verify a run on an existing `thread_id` reuses checkpointed thread context
- [ ] 5.3 Add tests that reject malformed, unknown, or unauthorized thread access
- [ ] 5.4 Add tests that confirm the lead-agent path does not require application-managed `conversation` or `message` records
- [ ] 5.5 Run targeted verification for the new lead-agent endpoints and confirm the legacy conversation-orchestrator chat path remains unaffected
