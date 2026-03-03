## Why

The platform needs voice synthesis capabilities so that users can convert text into spoken audio using either built-in system voices or custom-cloned voices. This enables tactical audio briefings, multi-language announcements, and personalized voice communication within organizations. MiniMax is the chosen API provider, offering high-quality multilingual TTS with voice cloning at production scale.

## What Changes

- Add MiniMax API integration as a new infrastructure client (`infrastructure/minimax/`) for voice cloning and text-to-speech
- Add voice cloning capability: users upload audio files to clone a voice, source audio stored on Cloudinary, voice metadata stored in MongoDB
- Add text-to-speech with two modes:
  - **WebSocket streaming**: real-time audio playback via binary WebSocket frames, with automatic persistence (Cloudinary + MongoDB) after stream completes
  - **Sync generation**: blocking request that returns a download URL after audio is generated and persisted
- Add voice management endpoints (list system + cloned voices, get detail, delete, preview)
- Add generated audio file management endpoints (list, get with signed URL, delete)
- Add `MINIMAX_API_KEY` to application settings
- Extend Cloudinary client to support audio uploads (`resource_type="video"`)
- Voice and audio resources are organization-scoped with 3-tier permission model (super admin > org admin > owner)

## Capabilities

### New Capabilities
- `voice-cloning`: Upload audio to MiniMax to create custom voice clones, store source audio on Cloudinary, manage cloned voices (CRUD) with organization-scoped ownership and 3-tier access control
- `text-to-speech`: Convert text to speech using MiniMax T2A API with both WebSocket streaming (real-time binary audio) and sync generation modes, persist all generated audio to Cloudinary with metadata in MongoDB
- `minimax-integration`: Infrastructure client wrapping MiniMax API for file upload, voice cloning, voice listing/deletion, and T2A synthesis (streaming SSE and sync)

### Modified Capabilities
- `image-upload`: Cloudinary client extended to support audio file uploads via `resource_type="video"` and audio-specific signed URL generation

## Impact

- **New API endpoints**: 10 new endpoints across `/api/v1/voices` (5 REST) and `/api/v1/tts` (1 WebSocket + 4 REST)
- **New infrastructure**: `app/infrastructure/minimax/client.py` — HTTP client using `httpx.AsyncClient`
- **New domain models**: `Voice`, `AudioFile` in `app/domain/models/`
- **New repositories**: `VoiceRepository`, `AudioFileRepository` in `app/repo/`
- **New services**: `VoiceService`, `TTSService` in `app/services/`
- **Modified files**: `config/settings.py` (add `MINIMAX_API_KEY`), `common/repo.py` (add factories), `common/service.py` (add factories), `common/exceptions.py` (add voice/audio errors), `infrastructure/cloudinary/client.py` (add audio support), `api/v1/router.py` (mount new routers)
- **New dependency**: `httpx` for async HTTP client to MiniMax API
- **MongoDB collections**: `voices`, `audio_files`
