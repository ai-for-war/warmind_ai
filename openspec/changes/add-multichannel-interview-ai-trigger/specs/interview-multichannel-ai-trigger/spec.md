## ADDED Requirements

### Requirement: Speaker-aware interview conversations exist as first-class realtime sessions
The system SHALL support a realtime interview conversation that binds one authenticated browser session, one live multichannel speech transcription session, and one explicit channel-to-speaker mapping for `interviewer` and `user`.

#### Scenario: Start an interview conversation with channel mapping
- **WHEN** an authenticated client starts an interview conversation with a valid `conversation_id` and a valid `channel_map`
- **THEN** the system creates a conversation-scoped live session
- **AND** the system binds each declared channel to exactly one speaker role for the duration of that session

#### Scenario: Reject an invalid channel map
- **WHEN** a client starts an interview conversation with missing, duplicate, or unsupported speaker-role channel assignments
- **THEN** the system MUST reject the request with an error

### Requirement: Stable utterances are derived from speaker-specific realtime transcript events
The system SHALL derive stable utterances separately for the `interviewer` and the `user` from the multichannel speech transcription stream.

#### Scenario: Build a stable utterance from finalized transcript segments
- **WHEN** the system receives finalized transcript segments for one speaker channel in an active interview conversation
- **THEN** the system merges those stable segments into that channel's open utterance

#### Scenario: Keep speaker utterances isolated by channel
- **WHEN** finalized transcript segments arrive on different channels in the same interview conversation
- **THEN** the system MUST maintain separate open utterance state for each speaker channel

### Requirement: Interview turn closure requires provider gap detection plus application grace
The system SHALL close a speaker utterance only after provider gap detection is followed by an additional `800ms` application grace period with no new speech activity on the same channel.

#### Scenario: Close an utterance after silence persists
- **WHEN** the system receives `utterance_end` for a speaker channel
- **AND** no new speech-started or transcript event arrives for that channel during the next `800ms`
- **THEN** the system closes the current utterance for that speaker

#### Scenario: Cancel turn closure when speech resumes
- **WHEN** the system receives `utterance_end` for a speaker channel
- **AND** new speech-started or transcript activity arrives for that same channel before `800ms` elapses
- **THEN** the system MUST cancel the pending close action
- **AND** the system MUST continue the existing open utterance instead of closing it

### Requirement: Only stable closed utterances are persisted
The system SHALL persist only stable closed utterances. The system MUST NOT persist unstable preview or partial transcript state to Redis or MongoDB.

#### Scenario: Persist a closed interviewer utterance
- **WHEN** an interviewer utterance becomes closed
- **THEN** the system writes the stable utterance to Redis
- **AND** the system asynchronously writes the stable utterance to MongoDB

#### Scenario: Persist a closed user utterance
- **WHEN** a user utterance becomes closed
- **THEN** the system writes the stable utterance to Redis
- **AND** the system asynchronously writes the stable utterance to MongoDB

#### Scenario: Do not persist partial transcript state
- **WHEN** a transcript update is still partial or preview-only
- **THEN** the system MUST NOT write that transcript state to Redis
- **AND** the system MUST NOT write that transcript state to MongoDB

### Requirement: Redis is the low-latency source for recent stable interview context
The system SHALL store a recent ordered window of stable closed interviewer and user utterances in Redis for realtime context retrieval.

#### Scenario: Add a closed utterance to the recent context window
- **WHEN** a stable utterance is closed
- **THEN** the system adds that utterance to the recent conversation window in Redis in timeline order

#### Scenario: Read context from Redis for a live interview
- **WHEN** the system needs conversation context for an active interview workflow
- **THEN** the system reads the recent stable utterance window from Redis instead of rebuilding context from partial in-memory transcript state

### Requirement: AI is triggered only by a closed interviewer utterance
The system SHALL trigger AI only after a stable interviewer utterance is closed and available in Redis.

#### Scenario: Trigger AI after interviewer turn closes
- **WHEN** an interviewer utterance becomes closed and has been written to Redis
- **THEN** the system triggers AI generation for that interview conversation

#### Scenario: Do not trigger AI after user turn closes
- **WHEN** a user utterance becomes closed
- **THEN** the system MUST persist the stable utterance
- **AND** the system MUST NOT trigger AI generation for that event

### Requirement: AI context is built from recent stable interviewer and user utterances
The system SHALL build AI context from a bounded recent window of stable interviewer and user utterances in the same conversation.

#### Scenario: Include both speakers in the AI context window
- **WHEN** the system triggers AI after an interviewer turn closes
- **THEN** the context MUST include the just-closed interviewer utterance
- **AND** the context MUST include recent stable interviewer and user utterances that precede it in the same conversation

#### Scenario: Exclude prior AI answers from the phase 1 context window
- **WHEN** the system builds context for AI in phase 1
- **THEN** the system MUST NOT require previous AI answers to be included in that context window

### Requirement: Interview AI output is text-only in phase 1
The system SHALL return the interview assistant result as text only.

#### Scenario: Emit a text answer after interviewer trigger
- **WHEN** AI generation completes successfully for a closed interviewer utterance
- **THEN** the system emits a text response to the frontend for that interview conversation

#### Scenario: Do not synthesize speech in phase 1
- **WHEN** the system generates an interview assistant response
- **THEN** the system MUST NOT require text-to-speech output as part of that workflow
