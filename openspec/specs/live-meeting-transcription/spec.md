## Purpose

Define the live meeting transcription capability that streams authenticated
meeting audio over the existing Socket.IO connection, forwards mono PCM audio
to Deepgram live transcription with diarization, and emits final transcript
updates plus canonical utterance closures for durable meeting transcript
storage.

## Requirements

### Requirement: Meeting transcription sessions run on authenticated Socket.IO connections scoped to an organization
The system SHALL provide realtime meeting transcription on the existing
authenticated Socket.IO connection. Each meeting transcription session MUST be
bound to the initiating user, the initiating socket, and the `organization_id`
provided when the meeting starts.

#### Scenario: Start a valid meeting transcription session
- **WHEN** an authenticated client emits `meeting:start` with a valid `organization_id` and `stream_id`
- **THEN** the system creates a new meeting transcription session bound to that socket
- **AND** the system binds the session to the current user and declared organization

#### Scenario: Reject a start request without authentication or organization context
- **WHEN** an unauthenticated client or a client without a valid `organization_id` attempts to emit `meeting:start`
- **THEN** the system MUST reject creation of the meeting transcription session

### Requirement: Meetings are created as durable transcript sessions with an optional title
The system SHALL create a durable `meeting` record when a meeting
transcription session starts. The record MUST store at least
`organization_id`, `created_by`, `stream_id`, lifecycle state, and an optional
title.

#### Scenario: Create a meeting without a title
- **WHEN** the client starts meeting transcription without providing a title
- **THEN** the system MUST still create the `meeting` record
- **AND** the meeting title MUST be stored as empty or `null`

#### Scenario: Create a meeting with a provided title
- **WHEN** the client starts meeting transcription with a valid title
- **THEN** the system creates the `meeting` record
- **AND** the system stores that title with the meeting record

### Requirement: Meeting input audio is PCM16 16kHz mono
The system SHALL accept browser audio streamed using the same transmission
style as the current interview flow, but for meeting phase 1 the audio MUST be
raw `PCM16`, `16kHz`, `1-channel`.

#### Scenario: Accept a valid meeting audio chunk
- **WHEN** the client emits `meeting:audio` for an active session with audio encoded as `PCM16`, `16kHz`, `1-channel`
- **THEN** the system accepts that chunk and continues transcript processing

#### Scenario: Reject unsupported audio configuration
- **WHEN** the client attempts to start or send meeting audio with the wrong encoding, sample rate, or channel count
- **THEN** the system MUST reject the request with an appropriate meeting transcription error

### Requirement: Each socket has at most one active meeting transcription session
The system SHALL allow at most one active meeting transcription session per
socket in phase 1.

#### Scenario: Start the first meeting session on a socket
- **WHEN** a socket without an active meeting transcription session emits `meeting:start`
- **THEN** the system starts the new session and marks it as the active session for that socket

#### Scenario: Reject a second meeting session on the same socket
- **WHEN** a socket that already has an active meeting transcription session emits another `meeting:start`
- **THEN** the system MUST reject the new request
- **AND** the system MUST keep the original active session unchanged

### Requirement: Stream ownership is bound to the initiating socket
The system SHALL bind all meeting transcription audio events and control
events to the socket that created the session. Audio or control events for a
stream MUST only be accepted from the socket that owns that stream.

#### Scenario: Accept audio and finalize from the owning socket
- **WHEN** the socket that created the meeting emits `meeting:audio` or `meeting:finalize` for the correct `stream_id`
- **THEN** the system processes the request for the corresponding active session

#### Scenario: Reject control events from another socket
- **WHEN** a different socket attempts to send audio or finalize for a `stream_id` it does not own
- **THEN** the system MUST reject that request
- **AND** the system MUST NOT change the state of the original session

### Requirement: The system uses Deepgram live transcription with diarization for mixed mono audio
The system SHALL forward valid meeting audio to Deepgram live transcription.
For meeting phase 1, the system MUST configure the provider to process mixed
`1-channel` audio and return enough word-level data to identify speakers.

#### Scenario: Forward meeting audio to the provider
- **WHEN** the system receives a valid audio chunk for an active meeting session
- **THEN** the system streams that chunk to the meeting session's Deepgram live transcription connection

#### Scenario: Keep word-level speaker information for a meeting session
- **WHEN** Deepgram returns final transcript data for active meeting audio
- **THEN** the system MUST retain the word-level speaker data needed to determine the speaker for each word in the session's realtime buffer

### Requirement: Frontend only receives final realtime transcript updates and closed utterances
The system SHALL stream realtime meeting transcript updates to the frontend in
phase 1 using only final transcript fragments and closed utterances. The
system MUST NOT emit partial transcript updates for meetings.

#### Scenario: Emit a final transcript fragment to the frontend
- **WHEN** Deepgram returns a final transcript fragment for an active meeting session
- **THEN** the system emits the corresponding realtime final event to the frontend so the UI can display it immediately

#### Scenario: Do not emit partial transcript for meetings
- **WHEN** the provider returns an interim or partial transcript for a meeting session
- **THEN** the system MUST NOT emit a partial transcript event for the meeting capability

### Requirement: Stable utterances close only when the provider emits utterance_end
The system SHALL treat a meeting utterance as stable only when the provider
emits `utterance_end` for the accumulated final transcript region. At that
moment, the system MUST allocate the next meeting-local sequence, emit the
canonical closed utterance payload, and enqueue that utterance for
asynchronous background persistence and note processing.

#### Scenario: Close and enqueue an utterance when provider emits utterance_end
- **WHEN** the system has accumulated final words for an open meeting utterance
- **AND** Deepgram emits `utterance_end` for that transcript region
- **THEN** the system closes the current utterance
- **AND** the system assigns the next `sequence` for that meeting
- **AND** the system emits the canonical closed utterance payload
- **AND** the system enqueues the utterance for asynchronous persistence and downstream note processing

#### Scenario: Do not enqueue a stable utterance before utterance_end
- **WHEN** the system has only received final transcript fragments but has not yet received `utterance_end`
- **THEN** the system MUST NOT enqueue a stable meeting utterance task

### Requirement: Meeting utterances are stored as speaker-grouped messages
The system SHALL build `messages[]` for each `meeting_utterance` by grouping
consecutive final words that belong to the same speaker. Each message MUST
contain `speaker_index`, `speaker_label`, and `text`.

#### Scenario: Create one message when consecutive words belong to the same speaker
- **WHEN** consecutive final words within an utterance all belong to the same speaker
- **THEN** the system groups those words into one message in `messages[]`

#### Scenario: Split into multiple messages when the speaker changes within an utterance
- **WHEN** the speaker changes inside the same closed utterance
- **THEN** the system MUST create multiple messages in the original order
- **AND** each message MUST keep the provider `speaker_index`
- **AND** each message MUST provide a `speaker_label` in the form `speaker_<n>` for frontend use

### Requirement: Durable utterance storage keeps only normalized transcript data
The system SHALL persist each `meeting_utterance` asynchronously from the
queued closed-utterance payload, using only normalized transcript data for
product behavior. Durable records MUST still reference `meeting_id`, keep a
monotonic `sequence`, and store only `messages[]` plus record timestamps.

#### Scenario: Persist a queued canonical meeting utterance asynchronously
- **WHEN** a queued closed meeting utterance task is processed successfully
- **THEN** the system writes one durable `meeting_utterance` record containing `meeting_id`, `sequence`, `messages[]`, and record timestamps

#### Scenario: Do not duplicate a meeting utterance on retry or concurrent processing
- **WHEN** the same queued closed meeting utterance is processed more than once because of retries or concurrent workers
- **THEN** the system MUST NOT create more than one durable `meeting_utterance` record for that meeting sequence

#### Scenario: Do not store audio or noncanonical transcript payloads durably
- **WHEN** the system persists meeting transcript data from queued utterance work
- **THEN** the system MUST NOT store audio
- **AND** the system MUST NOT store raw word payloads
- **AND** the system MUST NOT store partial transcript data
- **AND** the system MUST NOT store a flat transcript field at the `meeting_utterance` record level

### Requirement: Terminal session handling flushes final transcript and sets the correct terminal state
The system SHALL end a meeting transcription session by attempting to flush the
final provider transcript before cleanup. After terminal transcript handling is
finished, the system MUST mark the meeting with the appropriate terminal state
without waiting for background utterance persistence or note-drain work to
fully complete.

#### Scenario: Finalize a meeting without waiting for background note drain
- **WHEN** a client emits `meeting:finalize` for an active meeting session
- **THEN** the system finalizes the provider-side stream
- **AND** the system flushes any remaining final transcript output
- **AND** the system enqueues any remaining closed utterance and terminal note-flush work
- **AND** the system marks the meeting as `completed` without waiting for background note work to finish

#### Scenario: Disconnect transitions the meeting to interrupted while background work continues
- **WHEN** a socket disconnects while a meeting session is still active
- **THEN** the system MUST attempt to finalize the provider stream before cleanup
- **AND** the system MUST enqueue any remaining closed utterance and terminal note-flush work
- **AND** the system MUST mark the meeting as `interrupted` without waiting for background note work to finish

#### Scenario: Emit a failure signal when the session cannot continue
- **WHEN** the meeting transcription session fails because of invalid input, provider failure, or internal processing failure
- **THEN** the system MUST emit a realtime error signal for the meeting
- **AND** the system MUST mark the meeting with the appropriate failed terminal state
