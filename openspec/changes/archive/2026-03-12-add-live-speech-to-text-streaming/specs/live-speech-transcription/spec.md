## Purpose

Define the live browser speech transcription capability that streams microphone
audio over the existing authenticated Socket.IO connection, forwards it to
Deepgram live transcription, and returns partial and final transcript updates
to the frontend in realtime.

## Requirements

### Requirement: Authenticated live STT over the existing Socket.IO channel
The system SHALL provide live speech transcription over the existing authenticated Socket.IO connection. The system MUST NOT require a separate realtime transport for this capability in phase 1.

#### Scenario: Start a live transcription stream over Socket.IO
- **WHEN** an authenticated browser client emits `stt:start` with a valid stream configuration
- **THEN** the backend creates a live STT session bound to that socket connection

#### Scenario: Reject unauthenticated transcription access
- **WHEN** a client without a valid authenticated Socket.IO connection attempts to use STT events
- **THEN** the system refuses to create a live transcription session

### Requirement: PCM16 mono 16kHz browser audio input
The system SHALL accept phase 1 browser audio input as raw `PCM16`, `mono`, `16kHz` audio chunks streamed from the frontend.

#### Scenario: Accept valid PCM stream chunks
- **WHEN** the client emits `stt:audio` chunks for an active stream using `PCM16`, `mono`, `16kHz`
- **THEN** the backend accepts and forwards the audio to the live transcription provider

#### Scenario: Reject unsupported stream format
- **WHEN** the client attempts to start a stream with unsupported encoding, sample rate, or channel configuration
- **THEN** the backend rejects the stream with an STT error response

### Requirement: One active STT stream per socket
The system SHALL allow at most one active speech-to-text stream per socket connection in phase 1.

#### Scenario: Start a first active stream
- **WHEN** a socket with no active STT session emits `stt:start`
- **THEN** the backend starts the stream and marks it as the socket's active session

#### Scenario: Reject a second concurrent stream on the same socket
- **WHEN** a socket with an already active STT session emits another `stt:start`
- **THEN** the backend rejects the new request and keeps the original stream active

### Requirement: Stream ownership is bound to the originating socket
The system SHALL bind each STT stream to the originating socket session and authenticated user context. Audio and control events for a stream MUST only be accepted from the owning socket.

#### Scenario: Accept audio from the owning socket
- **WHEN** the socket that started a stream emits `stt:audio` or `stt:finalize` for that stream
- **THEN** the backend processes the event for the active session

#### Scenario: Reject stream control from a different socket
- **WHEN** another socket attempts to send audio or control events for a stream it does not own
- **THEN** the backend rejects the event and does not route provider audio for that request

### Requirement: Client language is configurable with default English fallback
The system SHALL allow the client to pass a `language` value when starting a stream. If the client omits language, the system SHALL default to `en`.

#### Scenario: Start a stream with an explicit language
- **WHEN** the client includes a supported `language` in `stt:start`
- **THEN** the backend configures the live transcription session with that language

#### Scenario: Start a stream without a language
- **WHEN** the client omits `language` in `stt:start`
- **THEN** the backend configures the stream with default language `en`

### Requirement: Provider-backed live transcription forwarding
The system SHALL forward accepted live audio chunks to Deepgram live transcription and consume provider transcript events for the active stream.

#### Scenario: Forward live audio to Deepgram
- **WHEN** the backend receives valid audio chunks for an active STT session
- **THEN** it streams those bytes to the Deepgram live transcription connection for that session

#### Scenario: Finalize the provider stream
- **WHEN** the client emits `stt:finalize` for an active session
- **THEN** the backend finalizes the provider-side stream and flushes any remaining transcript output before completion

### Requirement: Partial transcript updates are streamed to the frontend
The system SHALL emit realtime partial transcript updates to the frontend while speech is still in progress.

#### Scenario: Emit a partial transcript update
- **WHEN** Deepgram returns an interim transcript result for the active stream
- **THEN** the backend emits `stt:partial` to the owning user connection with the current partial transcript text

#### Scenario: Partial transcript remains non-final
- **WHEN** the backend emits `stt:partial`
- **THEN** the payload identifies the transcript as non-final and not yet committed as end-of-speech

### Requirement: Final transcript segments are emitted when speech is finalized
The system SHALL emit final transcript output when the provider indicates that speech has reached a final boundary.

#### Scenario: Emit final transcript on speech finalization
- **WHEN** Deepgram returns transcript output with a final speech boundary for the active stream
- **THEN** the backend emits `stt:final` with the finalized transcript segment for UI consumption

#### Scenario: Final transcript is stable for UI commit
- **WHEN** the frontend receives `stt:final`
- **THEN** the payload represents a stable transcript segment that can be committed in the UI

### Requirement: Stream lifecycle events are explicit and additive
The system SHALL expose additive STT lifecycle events without changing existing socket routing semantics.

#### Scenario: Stream start is acknowledged
- **WHEN** a new STT session is successfully created
- **THEN** the backend emits `stt:started` for that stream

#### Scenario: Stream completion is signaled
- **WHEN** an active STT session is finalized or stopped cleanly
- **THEN** the backend emits `stt:completed` before session cleanup finishes

#### Scenario: Stream failure is signaled
- **WHEN** the STT session fails due to invalid input, provider failure, or internal processing error
- **THEN** the backend emits `stt:error` for the affected stream

### Requirement: Session cleanup occurs on stop and disconnect
The system SHALL clean up active STT session state when a stream is stopped, completed, fails, or its socket disconnects.

#### Scenario: Stop an active stream explicitly
- **WHEN** the client emits `stt:stop` for an active stream
- **THEN** the backend closes the provider connection and removes the active session state

#### Scenario: Disconnect cleans up the active session
- **WHEN** a socket disconnects while an STT session is active
- **THEN** the backend closes the provider connection and removes the active session state for that socket

### Requirement: Independent clients can transcribe simultaneously
The system SHALL support multiple independent authenticated clients transcribing simultaneously, provided each socket still has at most one active stream.

#### Scenario: Two different sockets transcribe at the same time
- **WHEN** two separate authenticated clients each start their own STT stream
- **THEN** each stream is processed independently and each client receives only its own transcript events

#### Scenario: Same account on two different sockets transcribes independently
- **WHEN** the same authenticated account has two different socket connections and each connection starts a stream
- **THEN** each socket can maintain its own single active STT session independently
