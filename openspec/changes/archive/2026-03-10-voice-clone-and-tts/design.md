## Context

The platform currently supports image upload/management via Cloudinary and has an established pattern of Organization-scoped resources with 3-tier access control (super admin / org admin / owner). The codebase follows clean architecture: API router → Service → Repository → Infrastructure, with singleton DI via `lru_cache` factories in `common/repo.py` and `common/service.py`.

This change introduces voice cloning and text-to-speech (TTS) powered by MiniMax API. It is the first audio capability in the system and the first external AI provider integration outside of LLM providers (OpenAI/Anthropic). It also introduces the first WebSocket-based data streaming endpoint (existing Socket.IO is used for chat events, not binary data streaming).

**Stakeholders**: Backend team (implementation), Frontend team (API consumers), DevOps (new env var, new dependency).

**Constraints**:
- MiniMax API key is global (single key for all organizations)
- Audio files stored on Cloudinary using `resource_type="video"` (Cloudinary's category for audio/video)
- Must follow existing patterns for repos, services, routers, exceptions, and DI
- FastAPI native WebSocket (not Socket.IO) for binary audio streaming

## Goals / Non-Goals

**Goals:**
- Enable users to clone voices from uploaded audio via MiniMax API
- Enable text-to-speech with real-time WebSocket streaming and sync generation
- Persist all generated audio to Cloudinary with metadata in MongoDB
- Provide voice and audio file management (list, get, delete) with organization-scoped access control
- Follow existing codebase patterns exactly for consistency
- API-first design suitable for any frontend implementation

**Non-Goals:**
- AI Agent integration (future work — agents reading responses with cloned voices)
- WebSocket streaming via MiniMax's native WebSocket API (`wss://api.minimax.io/ws/v1/t2a_v2`) — we consume MiniMax via HTTP SSE and relay to our own WebSocket
- Voice generation (AI-designed voices) — only cloning from user-uploaded audio
- Audio format selection — MP3 only for MVP
- Concurrent request optimization or rate limit management beyond basic error handling
- Audio transcription or speech-to-text

## Decisions

### D1: WebSocket for TTS streaming (not SSE)

**Decision**: Use FastAPI native WebSocket (`@app.websocket`) for streaming audio to clients.

**Alternatives considered**:
- **SSE via `StreamingResponse`**: Simpler, works over HTTP. But audio is binary data — SSE requires base64 encoding which adds ~33% overhead on every chunk. Also, SSE is unidirectional: no way for client to send cancel or follow-up request on the same connection.
- **Socket.IO** (existing in codebase): Already used for chat events. But Socket.IO adds protocol overhead (engine.io frames) unsuitable for high-throughput binary streaming, and mixing audio streaming with chat events on the same namespace creates coupling.

**Rationale**: WebSocket supports native binary frames (zero encoding overhead), bidirectional communication (client can send multiple synthesize requests or cancel mid-stream), and FastAPI has built-in support. We use FastAPI's native WebSocket, not Socket.IO, to keep audio streaming isolated from chat event infrastructure.

### D2: MiniMax HTTP SSE → Our WebSocket relay pattern

**Decision**: Our backend consumes MiniMax T2A via HTTP SSE (`stream=true`), decodes hex chunks to binary, and relays them as WebSocket binary frames to the client.

```
Client ←──[WS binary frames]──→ FastAPI ←──[HTTP SSE hex chunks]──→ MiniMax
```

**Alternatives considered**:
- **Direct MiniMax WebSocket proxy** (`wss://api.minimax.io/ws/v1/t2a_v2`): Would expose API key management complexity, requires different protocol handling, and couples our WebSocket lifecycle to MiniMax's.
- **Client polls MiniMax directly**: Exposes API key to client. Not acceptable.

**Rationale**: HTTP SSE from MiniMax is simpler to consume (standard `httpx` streaming), we control the client-facing protocol, and the API key stays server-side. The hex→binary decode cost is negligible.

### D3: Persist audio after stream completion (not during)

**Decision**: During WebSocket streaming, accumulate audio chunks in memory. After the final chunk from MiniMax, combine all chunks → upload to Cloudinary → save to MongoDB → send completion event to client.

**Alternatives considered**:
- **Stream to temp file, then upload**: Adds filesystem I/O, cleanup complexity. For typical TTS audio (< 5MB), in-memory accumulation is fine.
- **Upload chunks progressively**: Cloudinary doesn't support chunked/resumable uploads for small files. Would need S3 multipart upload (not in current stack).

**Rationale**: TTS audio files are typically small (seconds to minutes of MP3 at 128kbps ≈ KB to low MB). In-memory accumulation is simple, fast, and avoids temp file management. If the client disconnects mid-stream, we simply discard — no cleanup needed.

### D4: httpx.AsyncClient for MiniMax (not aiohttp or requests)

**Decision**: Use `httpx.AsyncClient` with connection pooling for all MiniMax API calls.

**Alternatives considered**:
- **`aiohttp`**: Mature async HTTP library but adds another dependency with different API patterns. `httpx` is more "requests-like" and better aligns with FastAPI ecosystem.
- **`requests` in `asyncio.to_thread`**: Pattern used by existing Cloudinary client. Works but wastes a thread per request and doesn't support streaming response iteration natively.

**Rationale**: `httpx` provides native async, SSE streaming via `response.aiter_lines()`, connection pooling, and a familiar API. It's the standard choice for async HTTP in FastAPI projects.

### D5: WebSocket authentication via query parameter

**Decision**: Authenticate WebSocket connections via `token` query parameter: `ws://host/ws/tts?token=<jwt>`.

**Alternatives considered**:
- **First-message auth**: Client sends token as first WS message. Adds protocol complexity and requires connection to be open before auth.
- **Cookie-based**: Current auth is Bearer token (not cookie-based). Would require auth system changes.
- **HTTP header**: Browsers' WebSocket API doesn't support custom headers.

**Rationale**: Query parameter is the standard pattern for browser WebSocket auth. The JWT token is validated on connection upgrade — if invalid, the connection is rejected immediately with close code 4001. The token is not logged (server-side), and HTTPS encrypts the query string in transit.

### D6: Organization context in WebSocket messages (not header)

**Decision**: Since WebSocket doesn't have per-message HTTP headers, the `organization_id` SHALL be included in each synthesize message payload.

**Rationale**: WebSocket connections are long-lived. A user could theoretically switch organization context during a session. Including `organization_id` per message is explicit and avoids stale context. The server validates org membership on each request.

### D7: Separate Voice and TTS routers (not combined)

**Decision**: Two separate routers: `/api/v1/voices` for voice management and `/api/v1/tts` for synthesis and audio file management. WebSocket lives at `/ws/tts`.

**Alternatives considered**:
- **Single `/api/v1/voice` router**: Simpler but mixes voice management concerns with audio generation concerns. Makes the router file very large.

**Rationale**: Voice management (clone, list, delete, preview) is a distinct domain from audio synthesis (generate, stream, manage audio files). Separate routers follow the single-responsibility principle and match the existing pattern where each domain has its own router (images, organizations, users, etc.).

### D8: Cloudinary resource_type="video" for audio

**Decision**: Use Cloudinary's `resource_type="video"` for audio files. This is Cloudinary's documented approach — audio falls under their "video" resource category.

**Rationale**: Cloudinary does not have a separate `resource_type="audio"`. All audio operations (upload, transform, deliver) use `resource_type="video"`. This is well-documented and is the only supported approach. New methods (`upload_audio`, `delete_audio`, `generate_audio_signed_url`) are added to the existing `CloudinaryClient` to encapsulate this detail.

### D9: MongoDB collections: `voices` and `audio_files`

**Decision**: Two new collections with soft-delete pattern (matching existing `images` collection).

**`voices` collection schema**:
```
{
  _id: ObjectId,
  voice_id: string,          // MiniMax voice ID (unique per org)
  name: string,              // Display name
  voice_type: "cloned",      // Enum: only "cloned" stored in DB
  organization_id: string,
  created_by: string,        // User ID
  source_audio_url: string,  // Cloudinary URL
  source_audio_public_id: string,
  language: string | null,
  created_at: datetime,
  deleted_at: datetime | null
}
```
**Indexes**: `{ organization_id: 1, deleted_at: 1 }`, `{ voice_id: 1, organization_id: 1 }` (unique, partial: deleted_at=null)

**`audio_files` collection schema**:
```
{
  _id: ObjectId,
  organization_id: string,
  created_by: string,
  voice_id: string,           // MiniMax voice ID used
  source_text: string,        // Original text input
  audio_url: string,          // Cloudinary URL
  audio_public_id: string,
  duration_ms: int,
  size_bytes: int,
  format: "mp3",
  created_at: datetime,
  deleted_at: datetime | null
}
```
**Indexes**: `{ organization_id: 1, deleted_at: 1 }`, `{ created_by: 1, organization_id: 1, deleted_at: 1 }`

## File Structure

```
app/
├── infrastructure/minimax/
│   ├── __init__.py
│   └── client.py                # MiniMaxClient (httpx.AsyncClient)
│
├── domain/models/
│   ├── voice.py                 # Voice model + VoiceType enum
│   └── audio_file.py            # AudioFile model
│
├── domain/schemas/
│   ├── voice.py                 # Voice request/response schemas
│   └── tts.py                   # TTS request/response schemas
│
├── repo/
│   ├── voice_repo.py            # VoiceRepository
│   └── audio_file_repo.py       # AudioFileRepository
│
├── services/
│   ├── voice/
│   │   ├── __init__.py
│   │   └── voice_service.py     # VoiceService
│   └── tts/
│       ├── __init__.py
│       └── tts_service.py       # TTSService
│
├── api/v1/
│   ├── voices/
│   │   ├── __init__.py
│   │   └── router.py            # REST: /api/v1/voices
│   └── tts/
│       ├── __init__.py
│       ├── router.py            # REST: /api/v1/tts
│       └── ws.py                # WebSocket: /ws/tts
│
├── common/
│   ├── exceptions.py            # ADD: Voice/Audio/MiniMax exceptions
│   ├── repo.py                  # ADD: get_voice_repo, get_audio_file_repo
│   └── service.py               # ADD: get_minimax_client, get_voice_service, get_tts_service
│
└── config/
    └── settings.py              # ADD: MINIMAX_API_KEY
```

## Risks / Trade-offs

**[In-memory audio accumulation may use significant memory for long text]** → For `speech-2.8-hd` at 128kbps, 1 minute of audio ≈ 960KB. Even a 10-minute synthesis ≈ 10MB. This is acceptable for single-user requests. If concurrent streaming becomes a concern in the future, switch to temp file accumulation or streaming upload.

**[MiniMax SSE parsing depends on consistent format]** → MiniMax may change SSE event format between API versions. Mitigation: Pin to `/v1/t2a_v2` endpoint, add integration tests that verify SSE parsing against MiniMax sandbox.

**[WebSocket connection drops lose accumulated audio]** → If the client disconnects after MiniMax has generated most of the audio, the accumulated data is discarded. Mitigation: This is acceptable for MVP. Future enhancement could persist partial audio or use a job queue.

**[Cloudinary upload failure after successful stream]** → Client already received the audio via WebSocket but we fail to persist. Mitigation: Log the error for operational visibility, send error event to client. Client has the audio in browser memory. Future: retry queue for failed uploads.

**[MiniMax rate limits shared across all organizations]** → Single global API key means all orgs share rate limits. Mitigation: Basic error handling surfaces rate limit errors as HTTP 429 / WS error events. Future: per-org rate limiting middleware, or upgrade MiniMax tier.

**[voice_id uniqueness is per-org in our DB but global in MiniMax]** → Two orgs could use the same `voice_id` string, but MiniMax sees them as one voice (same API key). Mitigation: Prefix voice_id with org_id internally when sending to MiniMax (e.g., `{org_id_short}_{user_voice_id}`), while storing the user-facing voice_id in MongoDB. This is an implementation detail for the MiniMax client.

## Migration Plan

1. Add `MINIMAX_API_KEY` to `.env` and deployment environment variables
2. Add `httpx` to `requirements.txt`
3. Deploy code — no database migration needed (MongoDB is schemaless, new collections are created on first write)
4. Create MongoDB indexes for `voices` and `audio_files` collections (can be done via startup script or manually)
5. **Rollback**: Remove the new routers from `api/v1/router.py` and the WebSocket mount from `main.py`. No data migration needed — voices and audio_files collections can remain.

## Open Questions

- **Q1**: Should `voice_id` sent to MiniMax be prefixed with an org identifier to avoid cross-org collision? (Recommended: yes, use `{org_id[:8]}_{voice_id}`)
- **Q2**: Should the WebSocket endpoint be mounted directly on the FastAPI app or via a sub-application? (Recommended: directly on app, since it's a single endpoint)
- **Q3**: Maximum text length for sync generate vs streaming — should they differ? (Current spec: both 10,000 characters)
