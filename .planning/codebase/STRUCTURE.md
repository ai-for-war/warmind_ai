# Codebase Structure

**Analysis Date:** 2026-03-19

## Directory Layout

```text
ai_service_kiro/
+-- app/                  # Runtime application package
+-- tests/                # Test root; current tree only has package markers
+-- scripts/              # Launch scripts for API and workers
+-- doc/                  # Project documentation outside runtime code
+-- openspec/             # Specification artifacts
+-- tasks/                # Task/planning inputs
+-- .planning/codebase/   # Generated mapper documents
+-- README.md             # Overview and intended architecture notes
`-- requirements.txt      # Python dependency list
```

## Directory Purposes

**`app/`:**
- Purpose: Main Python application package and runtime code.
- Contains: API routers, services, repositories, domain models, infrastructure adapters, Socket.IO runtime, workers, prompts, and AI workflows.
- Key files: `app/main.py`, `app/api/v1/router.py`, `app/common/service.py`, `app/common/repo.py`

**`app/api/`:**
- Purpose: HTTP entry layer.
- Contains: Shared dependencies in `app/api/deps.py`, versioned routers in `app/api/v1/`, and feature endpoint modules such as `app/api/v1/images/router.py` and `app/api/v1/users/routes.py`.
- Key files: `app/api/deps.py`, `app/api/v1/router.py`, `app/api/v1/internal/router.py`

**`app/services/`:**
- Purpose: Feature-level business logic and orchestration.
- Contains: Feature packages such as `app/services/ai/`, `app/services/auth/`, `app/services/image/`, `app/services/organization/`, `app/services/sheet_crawler/`, `app/services/stt/`, `app/services/tts/`, `app/services/user/`, `app/services/voice/`.
- Key files: `app/services/ai/chat_service.py`, `app/services/analytics/analytics_service.py`, `app/services/sheet_crawler/crawler_service.py`, `app/services/tts/tts_service.py`

**`app/repo/`:**
- Purpose: MongoDB persistence adapters.
- Contains: One repository module per collection or aggregate root.
- Key files: `app/repo/user_repo.py`, `app/repo/conversation_repo.py`, `app/repo/sheet_data_repo.py`, `app/repo/image_generation_job_repo.py`

**`app/domain/`:**
- Purpose: Domain contracts and transport contracts.
- Contains: Persisted entities in `app/domain/models/` and API/socket payload schemas in `app/domain/schemas/`.
- Key files: `app/domain/models/user.py`, `app/domain/models/conversation.py`, `app/domain/schemas/chat.py`, `app/domain/schemas/tts.py`

**`app/infrastructure/`:**
- Purpose: External-system adapters and connection helpers.
- Contains: Provider/client packages for Cloudinary, MongoDB, Deepgram, Google Sheets, OpenAI, MCP, MiniMax, Redis, JWT/password security, and vector stores.
- Key files: `app/infrastructure/database/mongodb.py`, `app/infrastructure/redis/client.py`, `app/infrastructure/redis/redis_queue.py`, `app/infrastructure/llm/factory.py`, `app/infrastructure/mcp/manager.py`

**`app/graphs/`:**
- Purpose: LangGraph workflow definitions and registry.
- Contains: `app/graphs/registry.py`, workflow packages under `app/graphs/workflows/`, and placeholder base modules under `app/graphs/base/`.
- Key files: `app/graphs/registry.py`, `app/graphs/workflows/chat_workflow/graph.py`, `app/graphs/workflows/conversation_orchestrator_workflow/graph.py`

**`app/agents/`:**
- Purpose: ReAct-style AI agents and supporting tools.
- Contains: Agent registry, implementation packages, and shared agent tools.
- Key files: `app/agents/registry.py`, `app/agents/implementations/default_agent/agent.py`, `app/agents/implementations/data_agent/agent.py`, `app/agents/implementations/data_agent/tools.py`

**`app/socket_gateway/`:**
- Purpose: Socket.IO server runtime and emit abstractions.
- Contains: Main socket server, auth helpers, Redis managers, and worker-safe emit gateway.
- Key files: `app/socket_gateway/server.py`, `app/socket_gateway/__init__.py`, `app/socket_gateway/worker_gateway.py`, `app/socket_gateway/auth.py`

**`app/workers/`:**
- Purpose: Long-running Redis queue consumers.
- Contains: Feature-specific worker processes for sheet sync and image generation.
- Key files: `app/workers/sheet_sync_worker.py`, `app/workers/image_generation_worker.py`

**`app/prompts/`:**
- Purpose: Prompt text and loading helpers for AI flows.
- Contains: System prompts in `app/prompts/system/`, prompt templates in `app/prompts/templates/`, and loader helpers in `app/prompts/loader.py`.
- Key files: `app/prompts/system/data_agent.py`, `app/prompts/system/default_agent.py`, `app/prompts/system/conversation_orchestrator_intent_classifier.py`

**`app/common/`:**
- Purpose: Cross-cutting helpers shared across features.
- Contains: Exception hierarchy, composition-root factories, socket payload helpers, and general utilities.
- Key files: `app/common/exceptions.py`, `app/common/service.py`, `app/common/repo.py`, `app/common/event_socket.py`, `app/common/socket_payload_contract.py`

**`scripts/`:**
- Purpose: Operational entry scripts.
- Contains: System shell scripts for booting the API and workers.
- Key files: `scripts/system/start.sh`, `scripts/system/worker_image_generation.sh`, `scripts/system/worker_sheet_sync_.sh`

**`tests/`:**
- Purpose: Test root for unit and integration suites.
- Contains: `tests/unit/` and `tests/integration/`, but the current tree only includes `tests/__init__.py`, `tests/unit/__init__.py`, and `tests/integration/__init__.py`.
- Key files: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`

## Key File Locations

**Entry Points:**
- `app/main.py`: FastAPI bootstrap, lifespan resource initialization, and `combined_app` ASGI composition.
- `app/socket_gateway/server.py`: Socket.IO event handlers for connect/disconnect and STT event flow.
- `app/workers/sheet_sync_worker.py`: Redis-backed sheet sync worker process.
- `app/workers/image_generation_worker.py`: Redis-backed image generation worker process.
- `scripts/system/start.sh`: Shell entry point for the API + socket server.
- `scripts/system/worker_sheet_sync_.sh`: Shell entry point for the sheet sync worker.
- `scripts/system/worker_image_generation.sh`: Shell entry point for the image generation worker.

**Configuration:**
- `requirements.txt`: Python dependencies.
- `app/config/settings.py`: Environment-backed runtime settings.
- `app/config/mcp.py`: MCP server definitions.
- `app/infrastructure/docker/docker-compose.yaml`: Local infrastructure compose file.
- `app/infrastructure/docker/.env`: Environment configuration file present; do not read secrets from it.

**Core Logic:**
- `app/api/v1/router.py`: Aggregates all active v1 routers.
- `app/common/service.py`: Service factory/composition root.
- `app/common/repo.py`: Repository factory/composition root.
- `app/services/ai/chat_service.py`: Chat orchestration and async AI response flow.
- `app/services/sheet_crawler/crawler_service.py`: Google Sheets sync orchestration.
- `app/services/tts/tts_service.py`: TTS generation, streaming, and access control.
- `app/graphs/workflows/conversation_orchestrator_workflow/graph.py`: Top-level AI conversation routing workflow.
- `app/agents/registry.py`: Agent factory registry.

**Testing:**
- `tests/unit/`: Intended unit-test root; current source test files are not detected.
- `tests/integration/`: Intended integration-test root; current source test files are not detected.

## Naming Conventions

**Files:**
- Use snake_case Python modules such as `app/services/image/image_service.py`, `app/repo/user_repo.py`, and `app/workers/image_generation_worker.py`.
- Use `router.py` or `routes.py` inside feature API packages, for example `app/api/v1/images/router.py` and `app/api/v1/users/routes.py`.
- Use `*_service.py` for service modules, `*_repo.py` for repository modules, and singular entity files in `app/domain/models/` such as `app/domain/models/user.py`.
- Use workflow package internals named `graph.py`, `state.py`, and `nodes/*.py`, as in `app/graphs/workflows/chat_workflow/graph.py`.

**Directories:**
- Put feature APIs under `app/api/v1/<feature>/`, feature services under `app/services/<feature>/`, and provider adapters under `app/infrastructure/<provider>/`.
- Put workflow packages under `app/graphs/workflows/<workflow_name>/` and agent packages under `app/agents/implementations/<agent_name>/`.
- Keep shared helpers in horizontal directories such as `app/common/`, `app/repo/`, and `app/domain/`.

## Where to Add New Code

**New Feature:**
- Primary code: Create a feature router under `app/api/v1/<feature>/`, a feature service under `app/services/<feature>/`, any new repository in `app/repo/`, and matching contracts in `app/domain/schemas/` and `app/domain/models/` if persistence is involved.
- Tests: Add unit tests under `tests/unit/` and integration tests under `tests/integration/`.
- Wiring: Register the new router in `app/api/v1/router.py` and add any new factory functions to `app/common/service.py` or `app/common/repo.py`.
- Active route convention: Prefer the active feature packages already aggregated by `app/api/v1/router.py`; do not place new public routes under `app/api/v1/business/` unless you also wire that package into `app/api/v1/router.py`.

**New Component/Module:**
- Implementation: Add reusable workflows under `app/graphs/workflows/<workflow_name>/` with `graph.py`, `state.py`, and `nodes/`; register them in `app/graphs/registry.py`.
- Implementation: Add reusable agents under `app/agents/implementations/<agent_name>/` and expose them from `app/agents/registry.py`.
- Implementation: Add external provider adapters under `app/infrastructure/<provider>/` and instantiate them through `app/common/service.py`.

**Utilities:**
- Shared helpers: Put cross-feature utilities in `app/common/`.
- Feature-local helpers: Keep feature-specific helpers beside the feature package, for example `app/services/analytics/strategies.py` or `app/services/sheet_crawler/column_mapper.py`.
- Prompt and AI text assets: Put prompt text under `app/prompts/system/` or `app/prompts/templates/`, not inline in service code.

## Special Directories

**`app/graphs/workflows/strategic_planning_workflow/`:**
- Purpose: Reserved workflow location referenced by `app/graphs/workflows/conversation_orchestrator_workflow/nodes/strategic_branch.py`.
- Generated: No
- Committed: Yes
- Current state: Source workflow files are not detected in the current tree; only Python cache files are present.

**`app/infrastructure/docker/`:**
- Purpose: Local infrastructure support files for development/runtime services.
- Generated: No
- Committed: Yes

**`openspec/`:**
- Purpose: Specification and planning artifacts outside the runtime code path.
- Generated: No
- Committed: Yes

**`tests/`:**
- Purpose: Test root package reserved for unit and integration suites.
- Generated: No
- Committed: Yes
- Current state: Only package marker files are present in `tests/__init__.py`, `tests/unit/__init__.py`, and `tests/integration/__init__.py`.

---

*Structure analysis: 2026-03-19*
