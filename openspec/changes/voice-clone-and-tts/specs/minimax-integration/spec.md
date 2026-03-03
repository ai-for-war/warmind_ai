## ADDED Requirements

### Requirement: MiniMax API configuration
The system SHALL read the MiniMax API key from the environment variable `MINIMAX_API_KEY` via the `Settings` class. The application SHALL fail to start if this variable is not set. The API key SHALL be used as a Bearer token in the `Authorization` header for all MiniMax API requests.

#### Scenario: Valid configuration
- **WHEN** the application starts with `MINIMAX_API_KEY` set in the environment
- **THEN** the MiniMax client is operational and can make authenticated API calls

#### Scenario: Missing API key
- **WHEN** the application starts without `MINIMAX_API_KEY`
- **THEN** the application fails to start with a pydantic-settings validation error

### Requirement: MiniMax HTTP client
The system SHALL provide a `MiniMaxClient` class in `app/infrastructure/minimax/client.py` that wraps all MiniMax API interactions. The client SHALL use `httpx.AsyncClient` with connection pooling, a base URL of `https://api.minimax.io/v1`, and a default timeout of 60 seconds. The client SHALL be instantiated as a singleton via the service factory pattern (matching existing `CloudinaryClient` pattern).

#### Scenario: Client initialization
- **WHEN** the application creates a `MiniMaxClient` instance
- **THEN** it configures an `httpx.AsyncClient` with the API key from settings, base URL, and connection pooling

#### Scenario: Request authentication
- **WHEN** the client makes any API request to MiniMax
- **THEN** the request includes the header `Authorization: Bearer <MINIMAX_API_KEY>` and `Content-Type: application/json`

### Requirement: Upload file to MiniMax
The system SHALL provide a method to upload audio files to the MiniMax File API via `POST https://api.minimax.io/v1/files/upload`. The method SHALL accept file bytes and filename, send as `multipart/form-data` with `purpose: "voice_clone"`, and return the `file_id` (int64) from the response.

#### Scenario: Successful file upload
- **WHEN** the client uploads a 2MB MP3 file to MiniMax
- **THEN** MiniMax returns a `file_id` and the method returns this ID

#### Scenario: Upload failure
- **WHEN** MiniMax returns a non-zero `status_code` in the response
- **THEN** the method raises a `MiniMaxAPIError` with the status code and message from the response

### Requirement: Clone voice via MiniMax
The system SHALL provide a method to clone a voice via `POST https://api.minimax.io/v1/voice_clone`. The method SHALL accept `file_id` (from file upload), `voice_id`, and optional parameters (`need_noise_reduction`, `need_volume_normalization`). It SHALL return the parsed response including optional `demo_audio` URL.

#### Scenario: Successful voice clone
- **WHEN** the client sends a clone request with a valid `file_id` and `voice_id`
- **THEN** MiniMax returns success and the method returns the response with optional preview audio URL

#### Scenario: Clone with noise reduction
- **WHEN** the client sends a clone request with `need_noise_reduction=true`
- **THEN** MiniMax applies noise reduction to the source audio before cloning

#### Scenario: Clone permission denied
- **WHEN** the MiniMax API returns error code 2038 (no cloning permission)
- **THEN** the method raises a `MiniMaxAPIError` indicating account verification is needed

### Requirement: Text-to-audio synchronous synthesis
The system SHALL provide a method to synthesize speech via `POST https://api.minimax.io/v1/t2a_v2` in synchronous mode (`stream=false`). The method SHALL accept `text`, `voice_id`, `model` (default `speech-2.8-hd`), voice settings (`speed`, `vol`, `pitch`, `emotion`), and audio settings (`sample_rate=32000`, `bitrate=128000`, `format=mp3`, `channel=1`). The method SHALL set `language_boost: "auto"` and `output_format: "hex"`. It SHALL decode the hex-encoded audio from the response and return raw MP3 bytes along with metadata (`duration_ms`, `size_bytes`, `usage_characters`).

#### Scenario: Successful sync synthesis
- **WHEN** the client sends a T2A request with text "Hello world" and a valid voice_id
- **THEN** MiniMax returns hex-encoded audio, the method decodes it to bytes, and returns the audio bytes with duration and size metadata

#### Scenario: Synthesis with emotion
- **WHEN** the client sends a T2A request with `emotion: "calm"`
- **THEN** MiniMax synthesizes with the calm emotion applied

#### Scenario: Text exceeding MiniMax limit
- **WHEN** the client sends text exceeding 10,000 characters
- **THEN** the method raises a validation error before making the API call

#### Scenario: Rate limit exceeded
- **WHEN** MiniMax returns error code 1002 (rate limit exceeded)
- **THEN** the method raises a `MiniMaxRateLimitError`

### Requirement: Text-to-audio streaming synthesis
The system SHALL provide an async generator method to synthesize speech via `POST https://api.minimax.io/v1/t2a_v2` in streaming mode (`stream=true`). The method SHALL use the same parameters as sync synthesis. It SHALL parse the SSE response stream, decode each hex-encoded audio chunk, and yield raw bytes. The method SHALL set `stream_options.exclude_aggregated_audio: true` to avoid receiving duplicate data in the final event.

#### Scenario: Successful streaming synthesis
- **WHEN** the client sends a streaming T2A request
- **THEN** the method yields binary audio chunks as they arrive from MiniMax, each decoded from hex

#### Scenario: Final chunk detection
- **WHEN** MiniMax sends an SSE event with `data.status=2` (completed)
- **THEN** the method yields the final audio chunk (if present) and stops iteration

#### Scenario: Stream interruption
- **WHEN** the MiniMax SSE connection drops unexpectedly mid-stream
- **THEN** the method raises a `MiniMaxStreamError` and stops yielding

#### Scenario: Empty chunk handling
- **WHEN** MiniMax sends an SSE event with empty audio data
- **THEN** the method skips the empty chunk and continues waiting for the next event

### Requirement: List voices from MiniMax
The system SHALL provide a method to list voices via `POST https://api.minimax.io/v1/get_voice`. The method SHALL accept `voice_type` parameter (`system`, `voice_cloning`, `voice_generation`, or `all`). It SHALL return the parsed list of voices with their `voice_id`, `voice_name`, `description`, and `created_time`.

#### Scenario: List all system voices
- **WHEN** the client sends a list request with `voice_type: "system"`
- **THEN** MiniMax returns the catalog of 300+ system voices

#### Scenario: List cloned voices
- **WHEN** the client sends a list request with `voice_type: "voice_cloning"`
- **THEN** MiniMax returns only the voices cloned under the current API key

### Requirement: Delete voice from MiniMax
The system SHALL provide a method to delete a cloned voice via `POST https://api.minimax.io/v1/delete_voice`. The method SHALL accept `voice_type` (`voice_cloning`) and `voice_id`. It SHALL return the deletion confirmation.

#### Scenario: Successful voice deletion
- **WHEN** the client sends a delete request for a cloned voice
- **THEN** MiniMax deletes the voice and returns confirmation

#### Scenario: Delete non-existent voice
- **WHEN** the client sends a delete request for a voice_id that does not exist on MiniMax
- **THEN** MiniMax returns an error and the method raises `MiniMaxAPIError`

### Requirement: MiniMax error handling
The system SHALL define custom exception classes for MiniMax API errors: `MiniMaxAPIError` (general API error with status code and message), `MiniMaxRateLimitError` (error codes 1002 and 1039), and `MiniMaxStreamError` (streaming connection failures). All exceptions SHALL extend the application's base `AppException` class.

#### Scenario: General API error mapping
- **WHEN** MiniMax returns `base_resp.status_code: 1000` with message "Unknown error"
- **THEN** the client raises `MiniMaxAPIError` with status_code=502, containing the original MiniMax error code and message

#### Scenario: Rate limit error mapping
- **WHEN** MiniMax returns `base_resp.status_code: 1002`
- **THEN** the client raises `MiniMaxRateLimitError` with status_code=429

#### Scenario: Authentication error mapping
- **WHEN** MiniMax returns `base_resp.status_code: 1004`
- **THEN** the client raises `MiniMaxAPIError` with status_code=502, detail indicating a provider authentication failure (not exposing the internal API key issue)

### Requirement: MiniMax request timeout
The system SHALL enforce a 60-second default timeout for synchronous T2A requests and a 120-second timeout for streaming T2A requests. File upload and voice clone operations SHALL use a 30-second timeout.

#### Scenario: Sync request timeout
- **WHEN** MiniMax takes longer than 60 seconds to respond to a sync T2A request
- **THEN** the client raises a `MiniMaxAPIError` with detail indicating a timeout

#### Scenario: Streaming connection timeout
- **WHEN** MiniMax takes longer than 120 seconds without sending any SSE events
- **THEN** the client raises a `MiniMaxStreamError`
