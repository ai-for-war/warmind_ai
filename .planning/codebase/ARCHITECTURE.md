# Architecture

**Analysis Date:** 2026-03-19

## Pattern Overview

**Overall:** Layered modular monolith with a feature-oriented FastAPI API layer, repository-backed persistence, LangGraph/LangChain AI orchestration, Socket.IO realtime delivery, and Redis-driven worker processes.

**Key Characteristics:**
- `app/main.py` is the single HTTP/ASGI bootstrap and composes FastAPI with Socket.IO into `combined_app`.
- `app/api/v1/router.py` aggregates feature routers, while request-scoped auth and organization context live in `app/api/deps.py`.
- `app/common/service.py` and `app/common/repo.py` act as the composition root, assembling services and repositories from shared infrastructure clients.
- `app/services/` owns business rules; `app/repo/` owns MongoDB access; `app/domain/models/` and `app/domain/schemas/` define internal and external contracts.
- AI execution is split between workflow graphs in `app/graphs/workflows/`, ReAct agents in `app/agents/`, and prompt modules in `app/prompts/`.
- Realtime and async work are first-class subsystems through `app/socket_gateway/`, `app/infrastructure/redis/redis_queue.py`, and `app/workers/`.

## Layers

**Runtime Composition Layer:**
- Purpose: Build the application, initialize shared resources, and expose dependency factories.
- Location: `app/main.py`, `app/config/settings.py`, `app/config/mcp.py`, `app/common/service.py`, `app/common/repo.py`
- Contains: FastAPI setup, lifespan startup/shutdown, settings, MCP config, `@lru_cache` service/repository factories.
- Depends on: `app/api/v1/router.py`, `app/infrastructure/database/mongodb.py`, `app/infrastructure/redis/client.py`, `app/infrastructure/mcp/manager.py`, `app/socket_gateway/__init__.py`
- Used by: `scripts/system/start.sh`, API routes, socket handlers, workers.

**API Layer:**
- Purpose: Define HTTP endpoints, request validation, auth dependencies, and response shaping.
- Location: `app/api/v1/router.py`, `app/api/deps.py`, `app/api/v1/ai/chat.py`, `app/api/v1/auth/routes.py`, `app/api/v1/images/router.py`, `app/api/v1/image_generations/router.py`, `app/api/v1/internal/router.py`, `app/api/v1/organizations/routes.py`, `app/api/v1/sheet_crawler/router.py`, `app/api/v1/tts/router.py`, `app/api/v1/users/routes.py`, `app/api/v1/voices/router.py`
- Contains: `APIRouter` modules, `Depends(...)` auth/organization guards, background task dispatch, schema-to-domain mapping.
- Depends on: `app/common/service.py`, `app/common/repo.py`, `app/domain/schemas/`, `app/api/deps.py`
- Used by: `app/main.py`

**Application Service Layer:**
- Purpose: Centralize business rules and feature orchestration.
- Location: `app/services/ai/`, `app/services/analytics/`, `app/services/auth/`, `app/services/image/`, `app/services/interview/`, `app/services/organization/`, `app/services/sheet_crawler/`, `app/services/stt/`, `app/services/tts/`, `app/services/user/`, `app/services/voice/`
- Contains: Feature services such as `app/services/ai/chat_service.py`, `app/services/analytics/analytics_service.py`, `app/services/sheet_crawler/crawler_service.py`, `app/services/tts/tts_service.py`
- Depends on: `app/repo/`, `app/infrastructure/`, `app/graphs/`, `app/socket_gateway/`, `app/common/exceptions.py`
- Used by: `app/api/`, `app/socket_gateway/server.py`, `app/workers/`

**AI Orchestration Layer:**
- Purpose: Execute LLM-backed flows, branching logic, tool calls, and prompt-driven reasoning.
- Location: `app/graphs/registry.py`, `app/graphs/workflows/chat_workflow/`, `app/graphs/workflows/conversation_orchestrator_workflow/`, `app/agents/registry.py`, `app/agents/implementations/default_agent/`, `app/agents/implementations/data_agent/`, `app/prompts/system/`, `app/chains/`
- Contains: LangGraph state graphs, ReAct agents, graph/agent registries, prompt templates, tool factories.
- Depends on: `app/infrastructure/llm/factory.py`, `app/infrastructure/mcp/manager.py`, `app/services/ai/data_query_service.py`, `app/socket_gateway/__init__.py`
- Used by: `app/services/ai/chat_service.py`, workflow nodes under `app/graphs/workflows/*/nodes/`

**Domain Contract Layer:**
- Purpose: Define internal entities and external request/response payloads.
- Location: `app/domain/models/`, `app/domain/schemas/`
- Contains: Pydantic models such as `app/domain/models/user.py`, `app/domain/models/conversation.py`, `app/domain/models/image_generation_job.py`, plus API/socket schemas such as `app/domain/schemas/chat.py`, `app/domain/schemas/tts.py`, `app/domain/schemas/stt.py`
- Depends on: Pydantic and stdlib types only.
- Used by: `app/api/`, `app/services/`, `app/repo/`, `app/socket_gateway/server.py`

**Persistence Layer:**
- Purpose: Isolate MongoDB collection access and document conversion.
- Location: `app/repo/`, `app/infrastructure/database/mongodb.py`
- Contains: Collection-specific repositories such as `app/repo/user_repo.py`, `app/repo/conversation_repo.py`, `app/repo/sheet_data_repo.py`, `app/repo/image_generation_job_repo.py`
- Depends on: `app/infrastructure/database/mongodb.py`, `app/domain/models/`, `bson.ObjectId`
- Used by: `app/common/repo.py`, `app/services/`

**Infrastructure Adapter Layer:**
- Purpose: Encapsulate external systems and low-level clients.
- Location: `app/infrastructure/cloudinary/`, `app/infrastructure/database/`, `app/infrastructure/deepgram/`, `app/infrastructure/google_sheets/`, `app/infrastructure/llm/`, `app/infrastructure/mcp/`, `app/infrastructure/minimax/`, `app/infrastructure/redis/`, `app/infrastructure/security/`, `app/infrastructure/vector_store/`
- Contains: Provider clients, Redis queue, JWT/password helpers, MCP manager, Google Sheets rate limiter.
- Depends on: Settings from `app/config/settings.py`
- Used by: `app/common/service.py`, `app/common/repo.py`, `app/main.py`, `app/workers/`

**Realtime and Worker Runtime Layer:**
- Purpose: Manage socket sessions, publish business events, and process queued background jobs.
- Location: `app/socket_gateway/`, `app/workers/`
- Contains: `app/socket_gateway/server.py`, `app/socket_gateway/__init__.py`, `app/socket_gateway/worker_gateway.py`, `app/workers/sheet_sync_worker.py`, `app/workers/image_generation_worker.py`
- Depends on: `app/services/`, `app/common/event_socket.py`, `app/infrastructure/redis/`, `app/repo/`
- Used by: `app/main.py`, `scripts/system/worker_image_generation.sh`, `scripts/system/worker_sheet_sync_.sh`

## Data Flow

**HTTP Request Flow:**

1. `scripts/system/start.sh` starts `uvicorn app.main:combined_app`, and `app/main.py` initializes Cloudinary, MongoDB, Redis, and MCP tools in the FastAPI lifespan.
2. `app/main.py` includes `app/api/v1/router.py`, which dispatches requests into feature modules such as `app/api/v1/users/routes.py` or `app/api/v1/images/router.py`.
3. Route dependencies in `app/api/deps.py` authenticate JWTs, resolve the current user, and enforce organization scope from the `X-Organization-ID` header.
4. Routes obtain service instances from `app/common/service.py` and call feature services such as `app/services/user/user_service.py` or `app/services/image/image_service.py`.
5. Services call repositories from `app/common/repo.py` and external adapters in `app/infrastructure/*`.
6. Repository methods in `app/repo/*.py` execute MongoDB operations through `app/infrastructure/database/mongodb.py` and return `app/domain/models/*.py`, which routes map into `app/domain/schemas/*.py` responses.

**Chat + AI Response Flow:**

1. `app/api/v1/ai/chat.py` validates the request, saves the user message through `app/services/ai/chat_service.py`, and schedules background processing with `BackgroundTasks`.
2. `app/services/ai/chat_service.py` uses `app/services/ai/conversation_service.py` to load stored message history and normalize it into LangChain messages.
3. `app/graphs/registry.py` returns `app/graphs/workflows/conversation_orchestrator_workflow/graph.py`, which classifies top-level intent and routes to chat, clarification, or strategic handling.
4. Branch logic may invoke `app/graphs/workflows/chat_workflow/graph.py` or a LangGraph ReAct agent from `app/agents/registry.py` such as `app/agents/implementations/data_agent/agent.py`.
5. Workflow nodes emit token/tool events through `app/socket_gateway/__init__.py` using event names from `app/common/event_socket.py`.
6. The final assistant response is persisted via `app/services/ai/conversation_service.py` and emitted back to the user room as `chat:message:completed`.

**Queued Background Flow:**

1. API modules such as `app/api/v1/sheet_crawler/router.py`, `app/api/v1/image_generations/router.py`, and `app/api/v1/internal/router.py` enqueue Redis jobs through `app/infrastructure/redis/redis_queue.py`.
2. `scripts/system/worker_sheet_sync_.sh` and `scripts/system/worker_image_generation.sh` start `app/workers/sheet_sync_worker.py` and `app/workers/image_generation_worker.py`.
3. Workers dequeue tasks, call feature services or repositories, and update MongoDB-backed state.
4. Worker-side progress and terminal events are published through `app/socket_gateway/worker_gateway.py`; the main server receives them via Redis when `app/socket_gateway/manager.py` has an `AsyncRedisManager`.

**Live STT Socket Flow:**

1. `app/socket_gateway/server.py` authenticates socket connections with `app/socket_gateway/auth.py` and assigns each socket to a `user:{user_id}` room.
2. Socket STT events are validated against `app/domain/schemas/stt.py` and dispatched to `app/services/stt/stt_service.py`.
3. `app/services/stt/stt_service.py` delegates to session managers in `app/services/stt/session_manager.py` and `app/services/stt/interview_session_manager.py`, which own provider connections and in-memory session state.
4. `app/socket_gateway/server.py` converts emitted `STTSessionEvent` objects back into Socket.IO business events and sends them through `app/socket_gateway/gateway`.

**State Management:**
- Request handling is stateless at the FastAPI layer; per-request context is derived in `app/api/deps.py`.
- Shared long-lived objects are cached in `app/common/service.py` and `app/common/repo.py` via `@lru_cache`, backed by class-level clients in `app/infrastructure/database/mongodb.py`, `app/infrastructure/redis/client.py`, and `app/infrastructure/mcp/manager.py`.
- Workflow state is explicit `TypedDict` state in `app/graphs/workflows/chat_workflow/state.py` and `app/graphs/workflows/conversation_orchestrator_workflow/state.py`.
- Live STT state is process-local and socket-bound in `app/socket_gateway/server.py` and `app/services/stt/session_manager.py`.
- Cross-process async state is coordinated with Redis queues in `app/infrastructure/redis/redis_queue.py` and optional Redis Pub/Sub managers in `app/socket_gateway/manager.py`.

## Key Abstractions

**Composition Root:**
- Purpose: Wire repositories, services, and infrastructure into reusable factories.
- Examples: `app/common/service.py`, `app/common/repo.py`
- Pattern: `@lru_cache` factory functions return singleton-style objects while keeping constructors explicit.

**Repository Adapter:**
- Purpose: Hide MongoDB collection details and return typed domain models.
- Examples: `app/repo/user_repo.py`, `app/repo/conversation_repo.py`, `app/repo/sheet_data_repo.py`
- Pattern: One repository per collection, `ObjectId` conversion at the boundary, soft delete where the feature requires it.

**Domain Model / Schema Split:**
- Purpose: Separate persisted entities from API and socket contracts.
- Examples: `app/domain/models/user.py`, `app/domain/models/conversation.py`, `app/domain/schemas/chat.py`, `app/domain/schemas/image_generation.py`
- Pattern: `app/domain/models/` mirrors storage shape; `app/domain/schemas/` mirrors request/response/event payload shape.

**Workflow Graph:**
- Purpose: Express multi-step AI orchestration with explicit state and routing.
- Examples: `app/graphs/workflows/chat_workflow/graph.py`, `app/graphs/workflows/conversation_orchestrator_workflow/graph.py`
- Pattern: `TypedDict` state module + `StateGraph` builder + factory/registry access through `app/graphs/registry.py`.

**ReAct Agent Factory:**
- Purpose: Create LangGraph agents with prompts and tools.
- Examples: `app/agents/implementations/default_agent/agent.py`, `app/agents/implementations/data_agent/agent.py`, `app/agents/registry.py`
- Pattern: Cache generic agents, but build data-scoped agents per request when the toolset depends on user connections.

**Socket Gateway:**
- Purpose: Provide a stable emit API for both the main server and worker processes.
- Examples: `app/socket_gateway/__init__.py`, `app/socket_gateway/worker_gateway.py`, `app/common/socket_payload_contract.py`
- Pattern: Thin facade that normalizes payloads, targets per-user rooms, and hides the Socket.IO transport details.

**Queue Task DTOs:**
- Purpose: Normalize Redis task payloads before workers process them.
- Examples: `app/workers/sheet_sync_worker.py`, `app/workers/image_generation_worker.py`
- Pattern: `@dataclass` wrappers (`SyncTask`, `ImageGenerationTask`) with `from_dict()` constructors over JSON queue payloads.

## Entry Points

**HTTP + Socket ASGI Application:**
- Location: `app/main.py`
- Triggers: `scripts/system/start.sh`
- Responsibilities: Initialize shared infrastructure, register API routers, apply CORS, and expose `combined_app` for FastAPI + Socket.IO traffic.

**Socket.IO Event Server:**
- Location: `app/socket_gateway/server.py`
- Triggers: Client connect/disconnect and STT events
- Responsibilities: Authenticate sockets, join user rooms, dispatch live STT commands, and relay provider/worker events back to clients.

**Sheet Sync Worker:**
- Location: `app/workers/sheet_sync_worker.py`
- Triggers: `scripts/system/worker_sheet_sync_.sh`
- Responsibilities: Dequeue sheet sync jobs, apply rate limiting, invoke `app/services/sheet_crawler/crawler_service.py`, retry failures, and emit sync lifecycle events.

**Image Generation Worker:**
- Location: `app/workers/image_generation_worker.py`
- Triggers: `scripts/system/worker_image_generation.sh`
- Responsibilities: Dequeue text-to-image jobs, claim pending work, call the provider, persist outputs, and emit job lifecycle events.

**Internal Scheduler Endpoint:**
- Location: `app/api/v1/internal/router.py`
- Triggers: Authenticated POST requests to `/api/v1/internal/trigger-sync`
- Responsibilities: Enqueue sync jobs for all enabled sheet connections without blocking the caller.

## Error Handling

**Strategy:** Centralize application errors with `AppException` subclasses in `app/common/exceptions.py`, translate them globally in `app/main.py`, and use route-local `HTTPException` checks for request-specific auth/ownership failures.

**Patterns:**
- Service-layer business failures raise typed exceptions from `app/common/exceptions.py`.
- `app/main.py` registers a global exception handler for `AppException`, converting it into `{ "detail": ... }` JSON with the exception status code.
- Route modules such as `app/api/v1/ai/chat.py` and `app/api/v1/sheet_crawler/router.py` use `HTTPException` for 4xx request validation and ownership checks.
- Async flows catch broad exceptions near runtime boundaries and convert them into socket or job-state failure signals, as in `app/services/ai/chat_service.py`, `app/services/sheet_crawler/crawler_service.py`, and `app/workers/image_generation_worker.py`.
- Startup failure of MCP in `app/main.py` is intentionally non-fatal; the app logs the error and continues without MCP tools.

## Cross-Cutting Concerns

**Logging:** Standard library logging is configured in `app/main.py`, and most feature modules create local loggers with `logging.getLogger(__name__)`.
**Validation:** Pydantic request/response models live in `app/domain/schemas/`; auth and organization validation live in `app/api/deps.py`; aggregation safety validation lives in `app/services/ai/pipeline_validator.py`; upload MIME/size validation lives in `app/services/image/image_service.py` and `app/services/voice/voice_service.py`.
**Authentication:** JWT verification is handled by `app/infrastructure/security/jwt.py` and consumed by `app/services/auth/auth_service.py`, `app/api/deps.py`, and `app/socket_gateway/auth.py`; organization scoping is enforced centrally in `app/api/deps.py` and re-used in role-aware services such as `app/services/image/image_generation_service.py` and `app/services/tts/tts_service.py`.

---

*Architecture analysis: 2026-03-19*
