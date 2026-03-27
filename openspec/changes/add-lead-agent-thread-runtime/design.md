## Context

The codebase already has a LangGraph-based chat path centered around
application-managed `conversation` and `message` persistence. That flow works
for the existing `conversation_orchestrator_workflow`, but it is a poor fit
for a new lead-agent runtime that should be thread-native and checkpoint-based.

The new capability changes the ownership model:

- the legacy runtime continues to use application-level conversation storage
- the new lead-agent runtime uses LangGraph `thread_id` as the primary handle
- thread state is persisted through a LangGraph checkpointer instead of custom
  conversation/message persistence

Current constraints:

- the lead agent must use `langchain.agents.create_agent`
- the state schema must extend `AgentState`
- the initial runtime must use empty `tools=[]`
- the initial runtime must use empty `middleware=[]`
- the checkpointer backend must be MongoDB
- V1 only needs two endpoints:
  - create a thread
  - submit new input to an existing thread
- V1 does not need thread listing, history retrieval, or application-managed
  message persistence

This is a cross-cutting change because it introduces a new agent vertical that
touches:

- API routing under `app/api/v1/ai/`
- service wiring under `app/services/ai/`
- agent construction under `app/agents/implementations/`
- MongoDB-backed LangGraph persistence infrastructure
- dependency registration in `app/common/service.py` and app startup

## Goals / Non-Goals

**Goals:**
- Introduce a new `lead_agent` runtime that is independent from the legacy
  conversation orchestrator
- Use `create_agent` as the high-level agent primitive for the new runtime
- Persist thread state through MongoDB-backed LangGraph checkpointing
- Expose a minimal authenticated HTTP contract for:
  - thread creation
  - submitting new input to an existing thread
- Keep the first release intentionally small by deferring tools, middleware,
  thread browsing, and transcript retrieval
- Preserve a clear extension path for future tool and middleware growth

**Non-Goals:**
- Replacing `conversation_orchestrator_workflow`
- Migrating legacy chat conversations into LangGraph threads
- Adding custom business tools to the lead agent in V1
- Adding custom middleware behavior in V1
- Adding realtime token streaming in this change
- Adding thread history, search, title management, or thread archive features
- Building a supervisor or multi-agent topology

## Decisions

### D1: Introduce the lead agent as a separate vertical, not as a branch of the legacy orchestrator

**Decision**: The lead agent will live in a new runtime path with its own API,
service, agent implementation, and persistence wiring. It will not be added as
another branch inside `conversation_orchestrator_workflow`.

**Rationale**:
- the new runtime has a different state ownership model
- the new runtime uses `thread_id`, not `conversation_id`
- the new runtime should not inherit assumptions from the legacy
  conversation/message persistence flow
- keeping the runtimes separate reduces migration risk and architectural
  coupling

**Alternatives considered:**
- **Add `lead_agent` as one more orchestrator branch**: rejected because the
  legacy parent graph would still own the entrypoint and lifecycle contract
- **Replace the orchestrator entrypoint entirely**: rejected because the change
  must coexist with the legacy path

### D2: Use `create_agent` with a minimal custom `AgentState`

**Decision**: The new runtime will use `langchain.agents.create_agent` with a
custom state schema that extends `AgentState`.

Proposed V1 state:

```python
class LeadAgentState(AgentState):
    user_id: str
    organization_id: str | None
```

The runtime starts with:

```python
tools = []
middleware = []
```

**Rationale**:
- `create_agent` is the forward-compatible LangChain v1 surface for agents
- `AgentState` already gives the runtime a standard `messages` channel
- adding only caller-scope metadata keeps V1 state small and stable
- empty tools and middleware let the team land the runtime contract first

**Alternatives considered:**
- **Use `create_react_agent`**: rejected because the new runtime should align
  with the LangChain v1 direction
- **Introduce richer custom state on day one**: rejected because there is no
  immediate product need yet

### D3: MongoDB checkpointer is the only durable state backend for the lead-agent runtime

**Decision**: The lead-agent runtime will use MongoDB-backed LangGraph
checkpointing as its durable state layer. Application-managed
`conversation`/`message` collections are out of scope for this capability.

Implementation direction:

- add a dedicated checkpointer manager in `app/infrastructure/langgraph/`
- initialize one shared MongoDB checkpointer at app startup
- reuse the existing MongoDB cluster and database configuration
- keep checkpoint collections logically separate from application business
  collections

**Rationale**:
- the user explicitly wants thread-native persistence, not custom conversation
  storage
- MongoDB is already an operational dependency in the repo
- a shared checkpointer manager matches the current singleton-style
  infrastructure patterns

**Alternatives considered:**
- **Reuse conversation/message collections**: rejected because it defeats the
  new state ownership model
- **Use Redis or Postgres checkpointer**: rejected because the chosen backend
  for this change is MongoDB

### D4: Thread creation is an explicit backend API that seeds caller scope into thread state

**Decision**: V1 will expose a `create thread` endpoint even though LangGraph
threads can conceptually appear on first invoke. The backend will generate a
new `thread_id` and seed the initial thread state with caller scope so the
thread can be authorized later without relying on a separate thread metadata
store.

Proposed flow:

1. Generate a UUID `thread_id`
2. Build LangGraph config:
   ```python
   {"configurable": {"thread_id": thread_id}}
   ```
3. Seed the thread state with:
   - `user_id`
   - `organization_id`
   - `messages=[]`
4. Return the `thread_id`

Preferred implementation direction:
- use LangGraph state seeding through the graph API for an empty thread rather
  than inventing a parallel thread metadata collection

**Rationale**:
- the API needs a stable handle before the first user message
- later authorization checks need caller scope to already exist in thread
  state
- seeding thread state avoids creating another custom persistence path

**Alternatives considered:**
- **Return a UUID without seeding checkpoint state**: rejected because the
  server would not have a durable ownership record until the first run
- **Store thread ownership in a custom MongoDB collection**: rejected because
  it reintroduces custom thread persistence outside LangGraph

### D5: The run endpoint invokes the agent with only the new input and relies on checkpointed state loading

**Decision**: The lead-agent run endpoint will submit only the new user input
for a given `thread_id`. The service will not manually fetch the prior thread
messages and pass them back into the agent.

Proposed invocation shape:

```python
agent.ainvoke(
    {
        "messages": [{"role": "user", "content": content}],
        "user_id": current_user.id,
        "organization_id": organization_id,
    },
    config={"configurable": {"thread_id": thread_id}},
)
```

Before invocation, the service should load the current thread state and verify
that the stored `user_id` and `organization_id` match the authenticated caller.

**Rationale**:
- LangGraph checkpointers are designed to reload prior state automatically for
  a thread
- manually rehydrating messages would duplicate ownership between the service
  layer and the graph runtime
- authorization can be enforced from persisted thread state

**Alternatives considered:**
- **Fetch state, merge history manually, then invoke**: rejected because it is
  the wrong persistence pattern for checkpoint-backed graphs
- **Skip authorization and trust any valid thread_id**: rejected because
  thread state must remain user-scoped

### D6: V1 uses a synchronous request-response API for lead-agent runs

**Decision**: The V1 lead-agent run endpoint will execute as a normal HTTP
request-response flow and return the final assistant output directly in the
response body.

Proposed endpoint shape:

- `POST /api/v1/lead-agent/threads`
- `POST /api/v1/lead-agent/threads/{thread_id}/runs`

Proposed response contract for `runs`:

```json
{
  "thread_id": "uuid",
  "response": "final assistant response"
}
```

**Rationale**:
- the requested scope only includes thread creation and input submission
- streaming would pull socket event design, partial output contracts, and
  background lifecycle concerns into the same change
- a synchronous endpoint is the smallest usable interface for validating the
  runtime contract

**Alternatives considered:**
- **Reuse background task + Socket.IO streaming from legacy chat**: rejected
  because it expands the first version unnecessarily
- **Asynchronous job submission with polling**: rejected because it adds a job
  lifecycle without product need in V1

### D7: Keep extension seams explicit even though tools and middleware are empty in V1

**Decision**: The implementation will still define explicit modules for tools
and middleware boundaries, even if they export empty lists in the first
version.

Recommended structure:

- `app/agents/implementations/lead_agent/agent.py`
- `app/agents/implementations/lead_agent/state.py`
- `app/agents/implementations/lead_agent/tools.py`
- `app/agents/implementations/lead_agent/middleware.py`
- `app/services/ai/lead_agent_service.py`
- `app/api/v1/ai/lead_agent.py`
- `app/infrastructure/langgraph/checkpointer.py`

**Rationale**:
- the runtime contract is easier to extend if the seams exist from day one
- this avoids refactoring import and wiring patterns when tools are added later

**Alternatives considered:**
- **Inline empty lists directly inside `agent.py` and defer modules**: rejected
  because it creates avoidable refactor churn later

### D8: Reuse existing auth and organization context dependencies from the API layer

**Decision**: The lead-agent API will use the same authenticated user and
organization context dependencies that the current chat endpoints use.

Validation rules:
- thread creation requires an authenticated user
- run submission requires an authenticated user
- run submission must verify that the `thread_id` belongs to the authenticated
  caller
- when an organization context is present, it must match the thread's stored
  `organization_id`

**Rationale**:
- this keeps lead-agent authorization behavior consistent with the rest of the
  API surface
- the repo already has the required dependency injection path

**Alternatives considered:**
- **Create a new auth model just for the lead agent**: rejected because there
  is no security requirement that justifies divergence

## Risks / Trade-offs

- [MongoDB checkpointer behavior in an async FastAPI app may add blocking I/O]
  -> Mitigation: isolate checkpointer creation behind one infrastructure
  boundary and keep the backend swappable if load characteristics require a
  different saver strategy later.

- [Thread bootstrap on creation depends on LangGraph state-seeding behavior]
  -> Mitigation: keep thread creation logic in one service/infrastructure layer
  so the bootstrap mechanism can be adjusted without touching the public API.

- [Without list/history endpoints, clients must persist `thread_id`]
  -> Mitigation: keep the V1 API contract explicit and document that the client
  owns the thread handle for follow-up turns.

- [Empty tools make the lead agent initially low-capability]
  -> Mitigation: treat this change as runtime foundation only and leave clear
  seams for later tool expansion.

- [Thread authorization relies on checkpointed state instead of a dedicated
  thread index]
  -> Mitigation: always seed caller scope at thread creation and verify it on
  every run request before invoking the agent.

- [The team may later want realtime streaming, which does not fit the V1 HTTP
  contract]
  -> Mitigation: keep response assembly inside `LeadAgentService` so a future
  streaming transport can reuse the same runtime builder and authorization
  logic.

## Migration Plan

1. Add a new lead-agent implementation package under
   `app/agents/implementations/lead_agent/`.
2. Define `LeadAgentState` as an `AgentState` extension with caller-scope
   metadata.
3. Add MongoDB-backed LangGraph checkpointer infrastructure and initialize it
   during app startup.
4. Add a `LeadAgentService` that:
   - creates threads
   - seeds initial thread state
   - validates thread ownership
   - invokes the agent for new input
5. Add request/response schemas for thread creation and thread runs.
6. Add an API router for:
   - `POST /lead-agent/threads`
   - `POST /lead-agent/threads/{thread_id}/runs`
7. Register the router and service in the existing dependency graph without
   changing the legacy chat runtime.
8. Validate:
   - thread creation succeeds for an authenticated caller
   - thread runs reuse checkpointed context for the same `thread_id`
   - cross-user thread reuse is rejected
   - no conversation/message records are required for the lead-agent path

Rollback strategy:

- remove the new lead-agent router from `app/api/v1/router.py`
- remove lead-agent service wiring
- leave the legacy chat and orchestrator runtime untouched
- keep or clean up checkpoint collections separately if needed

## Open Questions

- Does the selected MongoDB checkpointer package expose a clean enough thread
  bootstrap API for empty-thread creation, or will the service need a thin
  compatibility wrapper around LangGraph state seeding?
- Should the lead-agent API return only the final text response in V1, or
  should it also return lightweight metadata such as checkpoint identifiers?
- Should the MongoDB checkpointer use the same application database name with
  separate collections, or should it use a dedicated LangGraph database within
  the same cluster for stronger operational separation?
