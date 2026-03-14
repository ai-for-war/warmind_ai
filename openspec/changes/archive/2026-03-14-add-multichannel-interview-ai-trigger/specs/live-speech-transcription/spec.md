## REMOVED Requirements

### Requirement: PCM16 mono 16kHz browser audio input
**Reason**: The browser audio contract for this workflow is no longer single-channel mono. It is replaced by an explicit multichannel interview capture contract.
**Migration**: Clients MUST update `stt:start` to declare `channels=2` and `channel_map`, and MUST send multichannel `PCM16` `16kHz` audio instead of mono audio.

## MODIFIED Requirements

### Requirement: Authenticated live STT over the existing Socket.IO channel
The system SHALL provide live speech transcription over the existing authenticated Socket.IO connection. The system MUST NOT require a separate realtime transport for this capability in phase 1. For interview multichannel sessions, the client MUST declare a valid conversation-scoped stream configuration at `stt:start`.

#### Scenario: Start a live transcription stream over Socket.IO
- **WHEN** an authenticated browser client emits `stt:start` with a valid multichannel stream configuration
- **THEN** the backend creates a live STT session bound to that socket connection

#### Scenario: Reject unauthenticated transcription access
- **WHEN** a client without a valid authenticated Socket.IO connection attempts to use STT events
- **THEN** the system refuses to create a live transcription session

### Requirement: One active STT stream per socket
The system SHALL allow at most one active live speech transcription session per socket connection in this phase, including multichannel interview sessions.

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

### Requirement: Provider-backed live transcription forwarding
The system SHALL forward accepted live audio chunks to Deepgram live transcription and consume provider transcript events for the active stream. For interview multichannel sessions, the provider transcript events MUST preserve channel identity.

#### Scenario: Forward live audio to Deepgram
- **WHEN** the backend receives valid audio chunks for an active STT session
- **THEN** it streams those bytes to the Deepgram live transcription connection for that session

#### Scenario: Preserve transcript channel identity
- **WHEN** Deepgram returns transcript events for a multichannel session
- **THEN** the backend preserves channel identity while normalizing those events for application processing

#### Scenario: Finalize the provider stream
- **WHEN** the client emits `stt:finalize` for an active session
- **THEN** the backend finalizes the provider-side stream and flushes any remaining transcript output before completion

### Requirement: Partial transcript updates are streamed to the frontend
The system SHALL emit realtime partial transcript updates to the frontend while speech is still in progress. Partial transcript updates are preview-only and MUST NOT be treated as persisted stable utterances.

#### Scenario: Emit a partial transcript update
- **WHEN** Deepgram returns an interim transcript result for the active stream
- **THEN** the backend emits `stt:partial` to the owning user connection with the current partial transcript text

#### Scenario: Partial transcript remains non-final
- **WHEN** the backend emits `stt:partial`
- **THEN** the payload identifies the transcript as non-final and not yet committed as end-of-speech

#### Scenario: Partial transcript remains volatile
- **WHEN** the backend emits `stt:partial`
- **THEN** the system MUST treat that payload as preview-only state rather than persisted transcript state

### Requirement: Final transcript segments are emitted when speech is finalized
The system SHALL emit final transcript output when the provider indicates that speech has reached a final boundary. For multichannel sessions, final transcript segments MUST remain attributed to the correct channel and speaker role.

#### Scenario: Emit final transcript on speech finalization
- **WHEN** Deepgram returns transcript output with a final speech boundary for the active stream
- **THEN** the backend emits `stt:final` with the finalized transcript segment for UI consumption

#### Scenario: Final transcript is stable for UI commit
- **WHEN** the frontend receives `stt:final`
- **THEN** the payload represents a stable transcript segment that can be committed in the UI

#### Scenario: Final transcript is speaker-aware
- **WHEN** the backend emits `stt:final` for a multichannel session
- **THEN** the payload remains attributable to the correct channel and speaker role

### Requirement: Stream lifecycle events are explicit and additive
The system SHALL expose additive STT lifecycle events without changing existing socket routing semantics.

#### Scenario: Stream start is acknowledged
- **WHEN** a new STT session is successfully created
- **THEN** the backend emits `stt:started` for that stream

#### Scenario: Stable utterance closure is signaled
- **WHEN** a speaker utterance becomes closed after the configured turn-close logic completes
- **THEN** the backend emits an additive utterance-closed event for that stream

#### Scenario: Stream completion is signaled
- **WHEN** an active STT session is finalized or stopped cleanly
- **THEN** the backend emits `stt:completed` before session cleanup finishes

#### Scenario: Stream failure is signaled
- **WHEN** the STT session fails due to invalid input, provider failure, or internal processing error
- **THEN** the backend emits `stt:error` for the affected stream

## ADDED Requirements

### Requirement: PCM16 multichannel 16kHz browser audio input
The system SHALL accept phase 1 interview browser audio input as raw `PCM16`, `16kHz`, `2-channel` audio chunks streamed from the frontend.

#### Scenario: Accept valid multichannel stream chunks
- **WHEN** the client emits `stt:audio` chunks for an active stream using `PCM16`, `16kHz`, and `2` channels
- **THEN** the backend accepts and forwards the audio to the live transcription provider

#### Scenario: Reject unsupported multichannel stream format
- **WHEN** the client attempts to start a multichannel stream with unsupported encoding, sample rate, or channel configuration
- **THEN** the backend rejects the stream with an STT error response

### Requirement: Channel-to-speaker mapping is declared at stream start
The system SHALL require interview multichannel clients to declare the mapping between audio channels and speaker roles when the stream starts.

#### Scenario: Start a multichannel stream with a valid channel map
- **WHEN** the client emits `stt:start` with `channels=2` and a valid `channel_map` for `interviewer` and `user`
- **THEN** the backend accepts the stream and binds each channel to the declared speaker role

#### Scenario: Reject a multichannel stream without a valid channel map
- **WHEN** the client emits `stt:start` for an interview multichannel stream without a valid `channel_map`
- **THEN** the backend rejects the request with an error

### Requirement: Stable utterance closure is derived from provider gap detection plus application grace
The system SHALL derive stable speaker utterance closure from provider gap detection followed by an additional `800ms` grace period with no new speech activity on the same channel.

#### Scenario: Close a speaker utterance after silence persists
- **WHEN** the backend receives `utterance_end` for a speaker channel
- **AND** no new speech or transcript activity arrives for that same channel during the next `800ms`
- **THEN** the backend closes the speaker utterance as stable

#### Scenario: Continue the current utterance when speech resumes
- **WHEN** the backend receives `utterance_end` for a speaker channel
- **AND** new speech or transcript activity arrives for that same channel before `800ms` elapses
- **THEN** the backend keeps the utterance open instead of closing it
