## ADDED Requirements

### Requirement: Upload audio files to Cloudinary
The `CloudinaryClient` SHALL provide an `upload_audio` method that uploads audio file bytes to Cloudinary using `resource_type="video"` (Cloudinary's resource type for audio/video files) and `type="authenticated"`. The method SHALL accept `file_bytes`, `filename`, `folder`, and `org_id` parameters, matching the signature pattern of the existing `upload` method. The method SHALL be wrapped in `asyncio.to_thread()` to prevent blocking the event loop.

#### Scenario: Successful audio upload
- **WHEN** the service calls `upload_audio` with MP3 bytes and organization context
- **THEN** Cloudinary stores the file under `{org_id}/{folder}` with `resource_type="video"` and `type="authenticated"`, and returns the upload result including `public_id`

#### Scenario: Non-blocking audio upload
- **WHEN** `upload_audio` is called
- **THEN** the Cloudinary SDK call executes via `asyncio.to_thread()`, not blocking the FastAPI event loop

### Requirement: Generate signed URL for audio files
The `CloudinaryClient` SHALL provide a `generate_audio_signed_url` method that generates a time-limited signed URL for authenticated audio files. The method SHALL use `resource_type="video"` (matching the upload resource type) and accept `public_id` and `expiry_seconds` (default 7200). The method SHALL be wrapped in `asyncio.to_thread()`.

#### Scenario: Signed URL for audio file
- **WHEN** the service calls `generate_audio_signed_url` with an audio file's `public_id`
- **THEN** Cloudinary returns a signed URL valid for the specified duration with `resource_type="video"` and `type="authenticated"`

#### Scenario: Expired audio signed URL
- **WHEN** a client uses an audio signed URL that was generated more than 2 hours ago
- **THEN** Cloudinary returns HTTP 401 (token expired)

### Requirement: Delete audio files from Cloudinary
The `CloudinaryClient` SHALL provide a `delete_audio` method that deletes an audio file from Cloudinary and invalidates the CDN cache. The method SHALL use `resource_type="video"` and `invalidate=True`. The method SHALL be wrapped in `asyncio.to_thread()`.

#### Scenario: Successful audio deletion
- **WHEN** the service calls `delete_audio` with a valid audio `public_id`
- **THEN** Cloudinary deletes the audio file, invalidates CDN cache, and returns `{"result": "ok"}`

#### Scenario: Delete non-existent audio
- **WHEN** the service calls `delete_audio` with a `public_id` that does not exist
- **THEN** Cloudinary returns `{"result": "not found"}`
