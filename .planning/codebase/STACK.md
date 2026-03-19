# Technology Stack

**Analysis Date:** 2026-03-19

## Languages

**Primary:**
- Python 3.12.0 - Main application, workers, repositories, and tests in `app/` and `tests/`; the project virtual environment is defined in `.venv/pyvenv.cfg`

**Secondary:**
- Shell (`sh`) - Local startup and worker entry scripts in `scripts/system/start.sh`, `scripts/system/worker_image_generation.sh`, `scripts/system/worker_sheet_sync_.sh`, and `scripts/system/requriements.sh`

## Runtime

**Environment:**
- Python virtual environment 3.12.0 in `.venv` (`.venv/pyvenv.cfg`)
- ASGI app entrypoint is `app.main:combined_app` in `app/main.py`

**Package Manager:**
- pip 26.0.1 inside `.venv`
- Manifest: `requirements.txt`
- Lockfile: missing

## Frameworks

**Core:**
- FastAPI 0.135.1 - REST API and lifespan wiring in `app/main.py` and `app/api/v1/router.py`
- Pydantic 2.12.5 - Domain and request/response schemas in `app/domain/schemas/`
- pydantic-settings 2.13.1 - Environment-based config in `app/config/settings.py`
- LangChain 1.2.10 / langchain-core 1.2.16 - LLM message, tool, and prompt abstractions in `app/agents/`, `app/services/interview/answer_service.py`, and `app/prompts/`
- LangGraph 1.0.10 - Compiled workflows and ReAct agents in `app/graphs/registry.py`, `app/agents/registry.py`, and `app/agents/implementations/*/agent.py`
- python-socketio 5.16.1 - Realtime client transport and Redis-backed fan-out in `app/main.py`, `app/socket_gateway/server.py`, and `app/socket_gateway/manager.py`

**Testing:**
- pytest 9.0.2 - Test runner for `tests/`
- pytest-asyncio 1.3.0 - Async test support for coroutine-based services and adapters

**Build/Dev:**
- Uvicorn 0.41.0 - ASGI server launched by `scripts/system/start.sh`
- python-dotenv 1.2.2 - `.env` loading through `app/config/settings.py`
- `uvx` + DuckDuckGo MCP server - stdio MCP tool process configured in `app/config/mcp.py`

## Key Dependencies

**Critical:**
- `fastapi` 0.135.1 - Main HTTP interface in `app/main.py` and `app/api/v1/`
- `langchain-openai` 1.1.10 - OpenAI-backed chat model factory in `app/infrastructure/llm/factory.py`
- `langgraph` 1.0.10 - Agent/workflow orchestration in `app/graphs/workflows/` and `app/agents/implementations/`
- `motor` 3.7.1 and `pymongo` 4.16.0 - Async MongoDB client and index creation in `app/infrastructure/database/mongodb.py`
- `redis` 7.2.1 - Cache, queue, and Socket.IO backplane in `app/infrastructure/redis/`, `app/services/analytics/cache_manager.py`, and `app/socket_gateway/manager.py`
- `deepgram-sdk` 6.0.1 - Live speech-to-text adapter in `app/infrastructure/deepgram/client.py`

**Infrastructure:**
- `cloudinary` 1.44.1 - Authenticated media storage and signed delivery in `app/infrastructure/cloudinary/client.py`
- `gspread` 6.0.2, `gspread-asyncio` 2.0.0, and `google-auth` 2.48.0 - Google Sheets service-account access in `app/infrastructure/google_sheets/client.py`
- `httpx` 0.28.1 - Outbound HTTP clients for MiniMax integrations in `app/infrastructure/minimax/client.py` and `app/infrastructure/minimax/image_client.py`
- `python-jose` 3.5.0 and `bcrypt` 5.0.0 - JWT auth and password hashing in `app/infrastructure/security/jwt.py` and `app/infrastructure/security/password.py`
- `langchain-mcp-adapters` 0.2.1 and `mcp` 1.26.0 - MCP tool loading in `app/infrastructure/mcp/manager.py`
- `python-magic-bin` 0.4.14 - MIME sniffing for upload validation in `app/services/image/image_service.py` and `app/services/voice/voice_service.py`
- Placeholder-only modules exist at `app/infrastructure/vector_store/factory.py`, `app/infrastructure/vector_store/qdrant.py`, `app/infrastructure/embeddings/factory.py`, `app/infrastructure/llm/anthropic_client.py`, and `app/infrastructure/llm/openai_client.py`; no active runtime wiring was detected beyond `app/infrastructure/llm/factory.py`

## Configuration

**Environment:**
- `app/config/settings.py` loads configuration from `.env` with `BaseSettings`, UTF-8 decoding, and `extra="ignore"`
- Required provider and infrastructure settings live in `app/config/settings.py`: MongoDB, Redis, JWT, internal API key, Google service account, OpenAI, MiniMax, Deepgram, Cloudinary, queue tuning, and CORS
- Root `.env` and `.env.example` files are present; `app/infrastructure/docker/.env` is also present and was not inspected

**Build:**
- Dependency manifest: `requirements.txt`
- Runtime config: `app/config/settings.py`
- MCP config: `app/config/mcp.py`
- Launch scripts: `scripts/system/start.sh`, `scripts/system/worker_image_generation.sh`, `scripts/system/worker_sheet_sync_.sh`
- Container assets present: `app/infrastructure/docker/docker-compose.yaml`

## Platform Requirements

**Development:**
- Python 3.12 virtual environment from `.venv`
- MongoDB reachable through `MONGODB_URI`
- Redis reachable through `REDIS_URL`
- Provider credentials for OpenAI, Deepgram, MiniMax, Cloudinary, Google service account, JWT signing, and internal API authentication
- The checked-in scripts use `python`, so local execution depends on activating `.venv` or otherwise pointing `python` at the Python 3.12 environment described in `.venv/pyvenv.cfg`

**Production:**
- ASGI process serving `app.main:combined_app`
- Separate worker processes for `app.workers.sheet_sync_worker` and `app.workers.image_generation_worker`
- MongoDB as the primary persistence layer and Redis as the queue/cache/pub-sub layer
- External provider connectivity for OpenAI, Deepgram, MiniMax, Cloudinary, Google Sheets, and MCP tooling

---

*Stack analysis: 2026-03-19*
