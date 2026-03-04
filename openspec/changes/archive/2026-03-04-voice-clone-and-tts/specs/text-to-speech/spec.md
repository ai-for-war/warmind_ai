## ADDED Requirements

### Requirement: Synthesize speech via WebSocket streaming
The system SHALL provide a WebSocket endpoint at `/ws/tts` that accepts a JSON message with `action: "synthesize"`, `text` (1-10,000 characters), `voice_id`, and optional parameters (`speed`, `volume`, `pitch`, `emotion`). The system SHALL authenticate the user via a `token` query parameter. Upon receiving a synthesize message, the system SHALL call MiniMax T2A API with `stream=true` and `model=speech-2.8-hd`, relay decoded binary audio chunks to the client as WebSocket binary frames, accumulate all chunks, and after the final chunk: upload the complete MP3 to Cloudinary, store metadata in the `audio_files` MongoDB collection, and send a JSON completion message with the `audio_id` and `audio_url`. The WebSocket connection SHALL remain open for subsequent requests.

#### Scenario: Successful streaming synthesis
- **WHEN** an authenticated user connects to `ws://host/ws/tts?token=<jwt>` and sends `{"action": "synthesize", "text": "Hello world", "voice_id": "commander-voice-01"}`
- **THEN** the system streams binary audio frames to the client as MiniMax returns them, then sends a JSON message `{"event": "completed", "audio_id": "<id>", "audio_url": "<cloudinary_url>", "duration_ms": <ms>, "size_bytes": <bytes>}` after persisting the audio

#### Scenario: Streaming with voice parameters
- **WHEN** a user sends `{"action": "synthesize", "text": "Important briefing", "voice_id": "system-voice-01", "speed": 0.8, "pitch": 2, "emotion": "calm"}`
- **THEN** the system passes all parameters to MiniMax T2A API and streams the resulting audio

#### Scenario: Multiple sequential requests on same connection
- **WHEN** a user sends a synthesize request, receives the completed event, then sends another synthesize request on the same WebSocket connection
- **THEN** the system processes the second request and streams audio for it as well

#### Scenario: Invalid token on WebSocket connect
- **WHEN** a client connects to `/ws/tts` with an invalid or expired JWT token
- **THEN** the system closes the WebSocket with code 4001 and reason "Authentication failed"

#### Scenario: Missing organization context
- **WHEN** an authenticated user sends a synthesize request without an `organization_id` field in the message
- **THEN** the system sends a JSON error message `{"event": "error", "detail": "organization_id is required"}` without closing the connection

#### Scenario: Text exceeds maximum length
- **WHEN** a user sends a synthesize request with text exceeding 10,000 characters
- **THEN** the system sends a JSON error message `{"event": "error", "detail": "Text must not exceed 10,000 characters"}`

#### Scenario: Invalid voice_id
- **WHEN** a user sends a synthesize request with a voice_id that does not exist in MiniMax or in the organization's cloned voices
- **THEN** the system sends a JSON error message `{"event": "error", "detail": "Voice not found"}`

#### Scenario: MiniMax streaming failure mid-stream
- **WHEN** the MiniMax SSE stream fails partway through (network error, timeout)
- **THEN** the system sends a JSON error message `{"event": "error", "detail": "Synthesis failed"}`, does NOT persist partial audio, and the connection remains open for retry

#### Scenario: Client disconnects during streaming
- **WHEN** the client disconnects the WebSocket while audio chunks are being streamed
- **THEN** the system cancels the MiniMax stream, discards accumulated chunks, and does NOT persist audio

#### Scenario: Cloudinary upload fails after stream completes
- **WHEN** audio streaming completes successfully but Cloudinary upload fails
- **THEN** the system sends a JSON error message `{"event": "error", "detail": "Audio storage failed"}` and logs the error for operational visibility

### Requirement: Generate speech synchronously
The system SHALL provide a `POST /api/v1/tts/generate` endpoint that accepts JSON with `text` (1-10,000 characters), `voice_id`, and optional parameters (`speed`, `volume`, `pitch`, `emotion`). The system SHALL call MiniMax T2A API synchronously with `model=speech-2.8-hd` and `output_format=hex`, decode the hex response into MP3 bytes, upload to Cloudinary, store metadata in the `audio_files` MongoDB collection, and return the audio record with a signed Cloudinary URL (2-hour expiry).

#### Scenario: Successful sync generation
- **WHEN** an authenticated user sends `POST /api/v1/tts/generate` with `{"text": "Mission briefing content", "voice_id": "commander-voice-01"}`
- **THEN** the system generates audio via MiniMax, uploads to Cloudinary, stores metadata (voice_id, source_text, audio_url, audio_public_id, duration_ms, size_bytes, format=mp3, organization_id, created_by), and returns HTTP 201 with the audio record and signed URL

#### Scenario: Generation with custom parameters
- **WHEN** a user sends a generate request with `speed: 1.5`, `pitch: -3`, `emotion: "happy"`
- **THEN** the system passes all parameters to MiniMax T2A API and returns the generated audio

#### Scenario: Empty text
- **WHEN** a user sends a generate request with empty text
- **THEN** the system returns HTTP 422 with validation error

#### Scenario: MiniMax API failure
- **WHEN** the MiniMax T2A API returns an error
- **THEN** the system returns HTTP 502 with detail indicating the synthesis provider failed

#### Scenario: Generate without organization context
- **WHEN** a user sends a generate request without the `X-Organization-ID` header
- **THEN** the system returns HTTP 400

### Requirement: List generated audio files
The system SHALL provide a `GET /api/v1/tts/audio` endpoint that returns a paginated list of generated audio files scoped to the user's current organization. Access control SHALL follow the 3-tier permission model: super admin and org admin see all audio in the organization, regular users see only their own.

#### Scenario: List audio with default pagination
- **WHEN** an authenticated user requests `GET /api/v1/tts/audio` with org context
- **THEN** the system returns the first page of audio files (default limit 20) belonging to that organization, sorted by `created_at` descending

#### Scenario: List audio with pagination parameters
- **WHEN** a user requests `GET /api/v1/tts/audio?skip=10&limit=5`
- **THEN** the system returns audio files 11-15, with total count in the response

#### Scenario: Regular user sees only their own audio
- **WHEN** a regular org member requests `GET /api/v1/tts/audio`
- **THEN** the system returns only audio files created by that user within the organization

#### Scenario: Org admin sees all audio in organization
- **WHEN** an org admin requests `GET /api/v1/tts/audio`
- **THEN** the system returns all audio files in the organization regardless of creator

#### Scenario: Empty result
- **WHEN** a user requests audio files for an organization with no generated audio
- **THEN** the system returns an empty list with `total: 0`

### Requirement: Get audio file detail
The system SHALL provide a `GET /api/v1/tts/audio/{audio_id}` endpoint that returns audio metadata and a signed Cloudinary URL (2-hour expiry). Access control SHALL follow the 3-tier permission model.

#### Scenario: Owner retrieves their audio
- **WHEN** the user who generated an audio file requests `GET /api/v1/tts/audio/{audio_id}`
- **THEN** the system returns the audio metadata and a 2-hour signed Cloudinary URL

#### Scenario: Org admin retrieves any audio in their org
- **WHEN** an org admin requests an audio file generated by another member
- **THEN** the system returns the audio metadata with signed URL

#### Scenario: Regular user attempts to access another user's audio
- **WHEN** a regular org member requests an audio file generated by another user
- **THEN** the system returns HTTP 403

#### Scenario: Audio not found
- **WHEN** a user requests an audio ID that does not exist or has been soft-deleted
- **THEN** the system returns HTTP 404

#### Scenario: Audio from different organization
- **WHEN** a user who is a member of Org-A requests an audio file from Org-B
- **THEN** the system returns HTTP 404 (not 403, to avoid revealing existence)

### Requirement: Delete audio file
The system SHALL provide a `DELETE /api/v1/tts/audio/{audio_id}` endpoint. Deletion SHALL be permitted only for: the audio creator, an org admin, or a super admin. Deletion SHALL soft-delete the MongoDB record and delete the audio binary from Cloudinary with CDN cache invalidation.

#### Scenario: Owner deletes their own audio
- **WHEN** the user who generated an audio file sends `DELETE /api/v1/tts/audio/{audio_id}`
- **THEN** the system sets `deleted_at` on the MongoDB record, calls Cloudinary destroy with `invalidate=True` and `resource_type="video"`, and returns HTTP 204

#### Scenario: Org admin deletes another user's audio
- **WHEN** an org admin sends `DELETE /api/v1/tts/audio/{audio_id}` for audio generated by another member
- **THEN** the system deletes the audio and returns HTTP 204

#### Scenario: Super admin deletes any audio
- **WHEN** a super admin sends `DELETE /api/v1/tts/audio/{audio_id}` for any audio in any organization
- **THEN** the system deletes the audio and returns HTTP 204

#### Scenario: Regular user attempts to delete another user's audio
- **WHEN** a regular org member attempts to delete audio generated by another user
- **THEN** the system returns HTTP 403

#### Scenario: Delete non-existent audio
- **WHEN** a user attempts to delete an audio ID that does not exist
- **THEN** the system returns HTTP 404

### Requirement: TTS audio settings
The system SHALL use the following default audio settings for all TTS operations: format `mp3`, sample rate `32000` Hz, bitrate `128000`, mono channel (1). These defaults SHALL be applied consistently across streaming, sync, and preview modes.

#### Scenario: Default audio settings applied
- **WHEN** a user sends a TTS request without specifying audio settings
- **THEN** the system generates MP3 audio at 32kHz sample rate, 128kbps bitrate, mono channel

### Requirement: TTS multilingual support
The system SHALL support multilingual text-to-speech by passing `language_boost: "auto"` to MiniMax T2A API. This enables automatic language detection for the input text across 40+ supported languages.

#### Scenario: Vietnamese text synthesis
- **WHEN** a user sends a TTS request with Vietnamese text
- **THEN** MiniMax auto-detects Vietnamese and synthesizes with correct pronunciation

#### Scenario: English text synthesis
- **WHEN** a user sends a TTS request with English text
- **THEN** MiniMax auto-detects English and synthesizes with correct pronunciation

#### Scenario: Mixed-language text
- **WHEN** a user sends a TTS request containing both English and Vietnamese text
- **THEN** MiniMax handles both languages in the output audio
