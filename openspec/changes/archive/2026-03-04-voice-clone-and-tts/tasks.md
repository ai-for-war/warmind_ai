## 1. Configuration & Dependencies

- [x] 1.1 Add `httpx` to `requirements.txt`
- [x] 1.2 Add `MINIMAX_API_KEY: str` to `Settings` class in `app/config/settings.py`

## 2. Custom Exceptions

- [x] 2.1 Add `VoiceNotFoundError`, `AudioFileNotFoundError`, `VoiceCloneError`, `InvalidAudioTypeError`, `AudioFileSizeLimitExceededError` to `app/common/exceptions.py`
- [x] 2.2 Add `MiniMaxAPIError`, `MiniMaxRateLimitError`, `MiniMaxStreamError` to `app/common/exceptions.py`

## 3. MiniMax Infrastructure Client

- [x] 3.1 Create `app/infrastructure/minimax/__init__.py`
- [x] 3.2 Implement `MiniMaxClient` in `app/infrastructure/minimax/client.py` with `httpx.AsyncClient` setup, base URL, auth headers, and connection pooling
- [x] 3.3 Implement `upload_file` method — upload audio to MiniMax File API, return `file_id`
- [x] 3.4 Implement `clone_voice` method — invoke MiniMax Voice Clone API with `file_id` and `voice_id`
- [x] 3.5 Implement `synthesize_sync` method — call T2A API with `stream=false`, decode hex response, return MP3 bytes + metadata
- [x] 3.6 Implement `synthesize_stream` method — async generator calling T2A API with `stream=true`, parse SSE events, yield decoded binary audio chunks
- [x] 3.7 Implement `list_voices` method — call MiniMax get_voice API, return parsed voice list
- [x] 3.8 Implement `delete_voice` method — call MiniMax delete_voice API
- [x] 3.9 Add error handling: parse `base_resp.status_code`, map to `MiniMaxAPIError` / `MiniMaxRateLimitError` / `MiniMaxStreamError`
- [x] 3.10 Add timeout configuration: 30s for file upload/clone, 60s for sync T2A, 120s for streaming T2A

## 4. Cloudinary Audio Support

- [x] 4.1 Add `upload_audio` method to `CloudinaryClient` — upload with `resource_type="video"`, `type="authenticated"`, wrapped in `asyncio.to_thread`
- [x] 4.2 Add `generate_audio_signed_url` method to `CloudinaryClient` — signed URL with `resource_type="video"`, wrapped in `asyncio.to_thread`
- [x] 4.3 Add `delete_audio` method to `CloudinaryClient` — destroy with `resource_type="video"`, `invalidate=True`, wrapped in `asyncio.to_thread`

## 5. Domain Models

- [x] 5.1 Create `app/domain/models/voice.py` — `VoiceType` enum, `Voice` model with fields: id, voice_id, name, voice_type, organization_id, created_by, source_audio_url, source_audio_public_id, language, created_at, deleted_at
- [x] 5.2 Create `app/domain/models/audio_file.py` — `AudioFile` model with fields: id, organization_id, created_by, voice_id, source_text, audio_url, audio_public_id, duration_ms, size_bytes, format, created_at, deleted_at

## 6. Domain Schemas

- [x] 6.1 Create `app/domain/schemas/voice.py` — `CloneVoiceRequest`, `PreviewVoiceRequest`, `VoiceRecord`, `SystemVoiceRecord`, `VoiceDetailResponse`, `VoiceListResponse`, `CloneVoiceResponse`
- [x] 6.2 Create `app/domain/schemas/tts.py` — `SynthesizeRequest`, `GenerateAudioRequest`, `AudioFileRecord`, `AudioDetailResponse`, `AudioListResponse`, `GenerateAudioResponse`

## 7. Repositories

- [x] 7.1 Create `app/repo/voice_repo.py` — `VoiceRepository` with methods: create, find_by_id, find_by_id_and_org, find_by_minimax_voice_id, list_by_organization, list_by_creator_and_organization, soft_delete
- [x] 7.2 Create `app/repo/audio_file_repo.py` — `AudioFileRepository` with methods: create, find_by_id, find_by_id_and_org, list_by_organization, list_by_creator_and_organization, soft_delete
- [x] 7.3 Register `get_voice_repo` and `get_audio_file_repo` factories in `app/common/repo.py`

## 8. Voice Service

- [x] 8.1 Create `app/services/voice/__init__.py`
- [x] 8.2 Implement `VoiceService.clone_voice` — validate audio file (magic bytes, size), upload source audio to Cloudinary, upload to MiniMax, clone voice, save metadata to MongoDB
- [x] 8.3 Implement `VoiceService.list_voices` — fetch system voices from MiniMax + cloned voices from MongoDB (filtered by role/org), return combined response
- [x] 8.4 Implement `VoiceService.get_voice` — fetch voice metadata with 3-tier access control, return with signed URL for source audio
- [x] 8.5 Implement `VoiceService.delete_voice` — 3-tier access control, soft-delete MongoDB, delete from MiniMax, delete source audio from Cloudinary
- [x] 8.6 Implement `VoiceService.preview_voice` — call MiniMax T2A sync with max 200-char text, return raw MP3 bytes (no persistence)
- [x] 8.7 Register `get_minimax_client` and `get_voice_service` factories in `app/common/service.py`

## 9. TTS Service

- [x] 9.1 Create `app/services/tts/__init__.py`
- [x] 9.2 Implement `TTSService.synthesize_stream` — validate voice access, call MiniMax streaming T2A, yield binary chunks, accumulate, upload to Cloudinary after completion, save metadata to MongoDB, return completion info
- [x] 9.3 Implement `TTSService.generate_audio` — validate voice access, call MiniMax sync T2A, upload to Cloudinary, save metadata, return audio record with signed URL
- [x] 9.4 Implement `TTSService.get_audio` — fetch audio metadata with 3-tier access control, return with signed URL
- [x] 9.5 Implement `TTSService.list_audio` — paginated list with role-based filtering (admin sees all, user sees own)
- [x] 9.6 Implement `TTSService.delete_audio` — 3-tier access control, soft-delete MongoDB, delete from Cloudinary
- [x] 9.7 Register `get_tts_service` factory in `app/common/service.py`

## 10. Voice API Router

- [x] 10.1 Create `app/api/v1/voices/__init__.py`
- [x] 10.2 Implement `POST /api/v1/voices/clone` endpoint — accept multipart/form-data (audio file + name + voice_id), call VoiceService.clone_voice
- [x] 10.3 Implement `GET /api/v1/voices` endpoint — call VoiceService.list_voices with role resolution
- [x] 10.4 Implement `GET /api/v1/voices/{voice_id}` endpoint — call VoiceService.get_voice with role resolution
- [x] 10.5 Implement `DELETE /api/v1/voices/{voice_id}` endpoint — call VoiceService.delete_voice with role resolution
- [x] 10.6 Implement `POST /api/v1/voices/{voice_id}/preview` endpoint — call VoiceService.preview_voice, return audio/mpeg response

## 11. TTS API Router

- [x] 11.1 Create `app/api/v1/tts/__init__.py`
- [x] 11.2 Implement `POST /api/v1/tts/generate` endpoint — accept JSON, call TTSService.generate_audio
- [x] 11.3 Implement `GET /api/v1/tts/audio` endpoint — call TTSService.list_audio with pagination and role resolution
- [x] 11.4 Implement `GET /api/v1/tts/audio/{audio_id}` endpoint — call TTSService.get_audio with role resolution
- [x] 11.5 Implement `DELETE /api/v1/tts/audio/{audio_id}` endpoint — call TTSService.delete_audio with role resolution

## 12. TTS Streaming on Shared Socket Connection

- [x] 12.1 Reuse existing shared Socket.IO connection (no dedicated `/ws/tts` endpoint)
- [x] 12.2 Implement HTTP trigger endpoint to start async TTS streaming and return `request_id`
- [x] 12.3 Implement streaming relay in TTS service layer - call `TTSService.synthesize_stream` and emit chunk events to `user:{user_id}` room
- [x] 12.4 Emit completion event with persisted audio metadata (`audio_id`, `signed_url`, `duration_ms`, `size_bytes`)
- [x] 12.5 Emit structured error event for validation/provider/storage failures without disconnecting socket
- [x] 12.6 Add `request_id` correlation in started/chunk/completed/error events

## 13. Router Registration & App Wiring

- [x] 13.1 Register voice router and TTS router in `app/api/v1/router.py`
- [x] 13.2 Reuse existing shared Socket.IO app mount in `app/main.py` (no dedicated TTS socket mount)

## 14. Verification

- [x] 14.1 Verify all new endpoints respond correctly with valid auth and org context
- [x] 14.2 Verify 3-tier access control works for voice and audio CRUD operations
- [x] 14.3 Verify shared-socket streaming delivers chunk events and completion event
- [x] 14.4 Verify audio files persist to Cloudinary and metadata saves to MongoDB after both streaming and sync generation
