# External Integrations

**Analysis Date:** 2026-03-19

## APIs & External Services

**LLM and Agent Tooling:**
- OpenAI - Chat model provider for agents, graph nodes, and interview answer generation in `app/infrastructure/llm/factory.py`, `app/agents/implementations/chat_agent/agent.py`, `app/graphs/workflows/conversation_orchestrator_workflow/nodes/intent_classifier.py`, and `app/services/interview/answer_service.py`
  - SDK/Client: `langchain-openai` and `openai`
  - Auth: `OPENAI_API_KEY` and optional `OPENAI_API_BASE`
- DuckDuckGo MCP server - Web search and fetch tools exposed to LangGraph agents in `app/config/mcp.py`, `app/infrastructure/mcp/manager.py`, `app/agents/implementations/chat_agent/agent.py`, and `app/agents/implementations/data_agent/agent.py`
  - SDK/Client: `langchain-mcp-adapters`, `mcp`, and stdio process `uvx duckduckgo-mcp-server`
  - Auth: Not detected

**Speech, Voice, and Media Providers:**
- Deepgram - Live speech-to-text provider for Socket.IO-driven STT sessions in `app/infrastructure/deepgram/client.py`, `app/socket_gateway/server.py`, and `app/services/stt/`
  - SDK/Client: `deepgram-sdk`
  - Auth: `DEEPGRAM_API_KEY`
- MiniMax - Voice cloning, synchronous/streaming TTS, and text-to-image generation in `app/infrastructure/minimax/client.py`, `app/infrastructure/minimax/image_client.py`, `app/services/voice/voice_service.py`, `app/services/tts/tts_service.py`, and `app/workers/image_generation_worker.py`
  - SDK/Client: custom `httpx` clients
  - Auth: `MINIMAX_API_KEY`
- Cloudinary - Authenticated storage and signed delivery for uploaded images, generated images, cloned voice source audio, and generated TTS audio in `app/infrastructure/cloudinary/client.py`, `app/services/image/image_service.py`, `app/services/voice/voice_service.py`, `app/services/tts/tts_service.py`, and `app/workers/image_generation_worker.py`
  - SDK/Client: `cloudinary`
  - Auth: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`

**Sheets and Internal Automation:**
- Google Sheets - Service-account access for connection validation, metadata, preview, and incremental sync in `app/infrastructure/google_sheets/client.py`, `app/services/sheet_crawler/crawler_service.py`, `app/api/v1/sheet_crawler/router.py`, and `app/workers/sheet_sync_worker.py`
  - SDK/Client: `gspread`, `gspread-asyncio`, and `google-auth`
  - Auth: `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SERVICE_ACCOUNT_EMAIL`
- Cloud Scheduler-style internal trigger - API-key protected sync trigger in `app/api/v1/internal/router.py`
  - SDK/Client: FastAPI `APIKeyHeader`
  - Auth: `INTERNAL_API_KEY` via `X-API-Key`

**Realtime Client Integration:**
- Socket.IO clients - Browser/mobile clients receive chat, STT, sheet sync, image generation, interview answer, and TTS events through `app/main.py`, `app/socket_gateway/server.py`, `app/socket_gateway/auth.py`, and `app/socket_gateway/manager.py`
  - SDK/Client: `python-socketio`
  - Auth: JWT bearer token validated by `app/socket_gateway/auth.py`
- Stub integrations only - `app/infrastructure/vector_store/factory.py`, `app/infrastructure/vector_store/qdrant.py`, `app/infrastructure/embeddings/factory.py`, `app/infrastructure/llm/anthropic_client.py`, and `app/infrastructure/llm/openai_client.py` are present as placeholders and are not wired into current request flows
  - SDK/Client: Not applicable
  - Auth: Not applicable

## Data Storage

**Databases:**
- MongoDB
  - Connection: `MONGODB_URI` and `MONGODB_DB_NAME`
  - Client: `motor`/`pymongo` via `app/infrastructure/database/mongodb.py`

**File Storage:**
- Cloudinary authenticated asset storage via `app/infrastructure/cloudinary/client.py`

**Caching:**
- Redis
  - Connection: `REDIS_URL`
  - Client: `redis.asyncio` via `app/infrastructure/redis/client.py`
  - Uses: analytics cache in `app/services/analytics/cache_manager.py`, FIFO task queues in `app/infrastructure/redis/redis_queue.py`, STT interview context in `app/services/stt/context_store.py`, and Socket.IO pub/sub in `app/socket_gateway/manager.py`

## Authentication & Identity

**Auth Provider:**
- Custom
  - Implementation: email/password login in `app/api/v1/auth/routes.py` and `app/services/auth/auth_service.py`, JWT issue/verify in `app/infrastructure/security/jwt.py`, bcrypt password hashing in `app/infrastructure/security/password.py`, bearer auth dependencies in `app/api/deps.py`, and socket token auth in `app/socket_gateway/auth.py`

## Monitoring & Observability

**Error Tracking:**
- None detected

**Logs:**
- Standard library `logging` configured in `app/main.py`, `app/workers/image_generation_worker.py`, and `app/workers/sheet_sync_worker.py`

## CI/CD & Deployment

**Hosting:**
- Not detected
- Runtime entrypoint: `scripts/system/start.sh` launches `uvicorn app.main:combined_app --reload --port 8080`
- Worker entrypoints: `scripts/system/worker_sheet_sync_.sh` and `scripts/system/worker_image_generation.sh`
- Docker assets exist at `app/infrastructure/docker/docker-compose.yaml` and `app/infrastructure/docker/.env`; contents were not inspected

**CI Pipeline:**
- Not detected

## Environment Configuration

**Required env vars:**
- `MONGODB_URI`
- `MONGODB_DB_NAME`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `JWT_EXPIRATION_DAYS`
- `INTERNAL_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SERVICE_ACCOUNT_EMAIL`
- `SHEET_SYNC_QUEUE_NAME`
- `IMAGE_GENERATION_QUEUE_NAME`
- `IMAGE_GENERATION_MAX_CONCURRENCY`
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `MINIMAX_API_KEY`
- `DEEPGRAM_API_KEY`
- `DEEPGRAM_MODEL`
- `DEEPGRAM_ENDPOINTING_MS`
- `DEEPGRAM_UTTERANCE_END_MS`
- `DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS`
- `INTERVIEW_STT_CHANNELS`
- `INTERVIEW_STT_MULTICHANNEL`
- `INTERVIEW_STT_ENDPOINTING_MS`
- `INTERVIEW_STT_UTTERANCE_END_MS`
- `INTERVIEW_STT_KEEPALIVE_INTERVAL_SECONDS`
- `INTERVIEW_TURN_CLOSE_GRACE_MS`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `CORS_ORIGINS`

**Secrets location:**
- `app/config/settings.py` loads root `.env`
- Root `.env.example` is present for environment scaffolding
- `GOOGLE_SERVICE_ACCOUNT_JSON` accepts either inline JSON or a file path resolved by `app/infrastructure/google_sheets/client.py`
- `app/infrastructure/docker/.env` is present under Docker assets

## Webhooks & Callbacks

**Incoming:**
- `POST /api/v1/internal/trigger-sync` in `app/api/v1/internal/router.py` for Cloud Scheduler or another internal caller, authenticated with `X-API-Key`
- Root Socket.IO connection/event callbacks mounted by `app/main.py` and implemented in `app/socket_gateway/server.py`

**Outgoing:**
- No outbound HTTP webhooks detected
- Realtime Socket.IO emits are sent to connected clients from `app/services/ai/chat_service.py`, `app/services/sheet_crawler/crawler_service.py`, `app/services/tts/tts_service.py`, `app/services/image/image_generation_service.py`, and `app/workers/image_generation_worker.py`

---

*Integration audit: 2026-03-19*
