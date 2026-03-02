## ADDED Requirements

### Requirement: Clone voice from uploaded audio
The system SHALL allow authenticated users to clone a voice by uploading an audio file via `POST /api/v1/voices/clone` using `multipart/form-data`. The request SHALL include the audio file, a display `name`, and a unique `voice_id` (8-256 characters, starting with a letter, allowing letters/digits/hyphens/underscores). The system SHALL validate the audio file, upload the source audio to Cloudinary (`resource_type="video"`), upload the file to MiniMax File API, invoke MiniMax Voice Clone API, and store voice metadata in the `voices` MongoDB collection. The voice SHALL be scoped to the user's current organization.

#### Scenario: Successful voice clone
- **WHEN** an authenticated user with org membership uploads a valid 30-second MP3 file with `name: "Commander Voice"` and `voice_id: "commander-voice-01"` to `POST /api/v1/voices/clone`
- **THEN** the system validates the file, uploads the source audio to Cloudinary, uploads the file to MiniMax, clones the voice, stores metadata in MongoDB (voice_id, name, voice_type=cloned, organization_id, created_by, source_audio_url, source_audio_public_id), and returns HTTP 201 with the voice record and optional preview URL

#### Scenario: Audio file too short
- **WHEN** a user uploads an audio file shorter than 10 seconds
- **THEN** the system returns HTTP 400 with detail indicating the audio must be at least 10 seconds

#### Scenario: Audio file too long
- **WHEN** a user uploads an audio file longer than 5 minutes
- **THEN** the system returns HTTP 400 with detail indicating the audio must not exceed 5 minutes

#### Scenario: Unsupported audio format
- **WHEN** a user uploads a file that is not MP3, M4A, or WAV (detected by magic bytes)
- **THEN** the system returns HTTP 400 with detail indicating the audio format is not supported

#### Scenario: Audio file exceeds size limit
- **WHEN** a user uploads an audio file larger than 20MB
- **THEN** the system returns HTTP 413 with detail indicating the file exceeds the 20MB limit

#### Scenario: Duplicate voice_id within organization
- **WHEN** a user attempts to clone a voice with a `voice_id` that already exists (non-deleted) in the same organization
- **THEN** the system returns HTTP 409 with detail indicating the voice_id is already in use

#### Scenario: Invalid voice_id format
- **WHEN** a user provides a `voice_id` that does not match the pattern `^[a-zA-Z][a-zA-Z0-9_-]{7,255}$`
- **THEN** the system returns HTTP 422 with validation error detail

#### Scenario: Clone without organization context
- **WHEN** a user sends a clone request without the `X-Organization-ID` header
- **THEN** the system returns HTTP 400

#### Scenario: MiniMax API failure during clone
- **WHEN** the MiniMax Voice Clone API returns an error (e.g., rate limit, authentication failure)
- **THEN** the system returns HTTP 502 with detail indicating the voice cloning provider failed, and the source audio already uploaded to Cloudinary SHALL be cleaned up

### Requirement: Validate audio file using magic bytes
The system SHALL validate uploaded audio files by reading magic bytes using `python-magic`, NOT by trusting the client-provided `Content-Type` header. The system SHALL accept only: `audio/mpeg` (MP3), `audio/mp4`/`audio/x-m4a` (M4A), `audio/wav`/`audio/x-wav` (WAV).

#### Scenario: Valid MP3 detected by magic bytes
- **WHEN** a user uploads an MP3 file and magic bytes confirm `audio/mpeg`
- **THEN** the system accepts the file and proceeds

#### Scenario: Spoofed audio file rejected
- **WHEN** a user uploads a non-audio file renamed to `.mp3` but magic bytes indicate `application/pdf`
- **THEN** the system returns HTTP 400 with detail indicating the detected MIME type is not a supported audio format

### Requirement: List voices
The system SHALL provide a `GET /api/v1/voices` endpoint that returns both MiniMax system voices and organization-scoped cloned voices. System voices SHALL be fetched from MiniMax API. Cloned voices SHALL be queried from MongoDB filtered by organization. The response SHALL separate system voices and cloned voices into distinct lists.

#### Scenario: List all voices with cloned voices present
- **WHEN** an authenticated user requests `GET /api/v1/voices` with org context, and the organization has 3 cloned voices
- **THEN** the system returns a response with `system_voices` (from MiniMax), `cloned_voices` (3 items from MongoDB), and `total_cloned: 3`

#### Scenario: List voices with no cloned voices
- **WHEN** a user requests voices for an organization with no cloned voices
- **THEN** the system returns `system_voices` (from MiniMax), `cloned_voices: []`, and `total_cloned: 0`

#### Scenario: Regular user sees only their own cloned voices
- **WHEN** a regular org member (not admin) requests `GET /api/v1/voices`
- **THEN** the system returns all system voices plus only the cloned voices created by that user within the organization

#### Scenario: Org admin sees all cloned voices in organization
- **WHEN** an org admin requests `GET /api/v1/voices`
- **THEN** the system returns all system voices plus all cloned voices in the organization, regardless of creator

#### Scenario: Super admin sees all cloned voices in organization
- **WHEN** a super admin requests `GET /api/v1/voices` with an org context
- **THEN** the system returns all system voices plus all cloned voices in the specified organization

### Requirement: Get voice detail
The system SHALL provide a `GET /api/v1/voices/{voice_id}` endpoint that returns voice metadata. For cloned voices, it SHALL also return a signed Cloudinary URL (2-hour expiry) for the source audio. Access control SHALL follow the 3-tier permission model.

#### Scenario: Owner retrieves their cloned voice
- **WHEN** the user who created a cloned voice requests `GET /api/v1/voices/{voice_id}`
- **THEN** the system returns the voice metadata including a 2-hour signed URL for the source audio

#### Scenario: Org admin retrieves any cloned voice in their org
- **WHEN** an org admin requests a cloned voice created by another member in the same organization
- **THEN** the system returns the voice metadata with signed URL

#### Scenario: Regular user attempts to access another user's voice
- **WHEN** a regular org member requests a cloned voice created by another user
- **THEN** the system returns HTTP 403

#### Scenario: Voice not found
- **WHEN** a user requests a voice ID that does not exist or has been soft-deleted
- **THEN** the system returns HTTP 404

### Requirement: Delete cloned voice
The system SHALL provide a `DELETE /api/v1/voices/{voice_id}` endpoint. Deletion SHALL be permitted only for: the voice creator, an org admin, or a super admin. Deletion SHALL soft-delete the MongoDB record, delete the voice from MiniMax API, and delete the source audio from Cloudinary with CDN cache invalidation.

#### Scenario: Owner deletes their own voice
- **WHEN** the user who created a voice sends `DELETE /api/v1/voices/{voice_id}`
- **THEN** the system sets `deleted_at` on the MongoDB record, calls MiniMax delete voice API, calls Cloudinary destroy for the source audio, and returns HTTP 204

#### Scenario: Org admin deletes another user's voice
- **WHEN** an org admin sends `DELETE /api/v1/voices/{voice_id}` for a voice created by another member
- **THEN** the system deletes the voice and returns HTTP 204

#### Scenario: Super admin deletes any voice
- **WHEN** a super admin sends `DELETE /api/v1/voices/{voice_id}` for any voice in any organization
- **THEN** the system deletes the voice and returns HTTP 204

#### Scenario: Regular user attempts to delete another user's voice
- **WHEN** a regular org member attempts to delete a voice created by another user
- **THEN** the system returns HTTP 403

#### Scenario: Delete non-existent voice
- **WHEN** a user attempts to delete a voice ID that does not exist
- **THEN** the system returns HTTP 404

#### Scenario: System voice cannot be deleted
- **WHEN** a user attempts to delete a system voice ID
- **THEN** the system returns HTTP 400 with detail indicating system voices cannot be deleted

### Requirement: Preview voice
The system SHALL provide a `POST /api/v1/voices/{voice_id}/preview` endpoint that synthesizes a short sample text (max 200 characters) using the specified voice and returns the audio bytes directly as an `audio/mpeg` response. Preview audio SHALL NOT be persisted to Cloudinary or MongoDB. Both system voices and cloned voices SHALL be previewable.

#### Scenario: Preview a cloned voice
- **WHEN** a user sends `POST /api/v1/voices/{voice_id}/preview` with `{"text": "Hello, this is a test."}` for a cloned voice they own
- **THEN** the system calls MiniMax T2A sync API, decodes the hex audio response, and returns the raw MP3 bytes with `Content-Type: audio/mpeg`

#### Scenario: Preview a system voice
- **WHEN** a user sends a preview request with a valid MiniMax system voice ID
- **THEN** the system calls MiniMax T2A sync API and returns the raw MP3 bytes

#### Scenario: Preview text too long
- **WHEN** a user sends a preview request with text exceeding 200 characters
- **THEN** the system returns HTTP 400 with detail indicating preview text must not exceed 200 characters

#### Scenario: Preview of non-existent voice
- **WHEN** a user sends a preview request for a voice ID that does not exist in MiniMax
- **THEN** the system returns HTTP 404
