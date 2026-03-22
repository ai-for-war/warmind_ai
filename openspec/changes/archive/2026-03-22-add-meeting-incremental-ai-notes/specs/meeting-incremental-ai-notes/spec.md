## ADDED Requirements

### Requirement: Closed meeting utterances are staged as hot note input
The system SHALL stage each closed canonical meeting utterance in Redis-backed
hot state for note generation after the utterance has been queued for
background processing.

#### Scenario: Add a closed utterance to pending note state
- **WHEN** a canonical meeting utterance is closed and queued for background processing
- **THEN** the system stores that utterance in per-meeting pending note state keyed by sequence
- **AND** the system marks that sequence as pending for note generation

#### Scenario: Remove consumed utterances after a batch is processed
- **WHEN** a pending meeting utterance batch is either summarized or explicitly skipped as not note-worthy
- **THEN** the system removes the consumed utterance payloads and sequence markers from Redis hot state

### Requirement: Meeting notes are triggered only from contiguous closed utterance batches
The system SHALL generate incremental meeting notes only from contiguous,
unsummarized closed utterances that belong to the same meeting.

#### Scenario: Trigger note generation after seven contiguous utterances
- **WHEN** there are at least `7` contiguous pending utterances after the last summarized sequence for one meeting
- **THEN** the system generates a note batch for the next `7` utterances in order

#### Scenario: Do not trigger note generation while a streaming meeting has fewer than seven pending utterances
- **WHEN** a meeting is still streaming and fewer than `7` contiguous pending utterances exist after the last summarized sequence
- **THEN** the system MUST NOT generate a note batch yet

#### Scenario: Flush the remaining terminal tail
- **WHEN** a meeting becomes `completed` or `interrupted` and a contiguous pending tail remains after the last summarized sequence
- **THEN** the system generates one final note batch for that remaining tail even if it contains fewer than `7` utterances

### Requirement: Meeting note output is structured and suppresses empty batches
The system SHALL produce note chunks with `key_points`, `decisions`, and
`action_items`. If a processed batch contains nothing note-worthy, the system
MUST NOT persist or emit a note chunk for that batch.

#### Scenario: Persist a structured note chunk
- **WHEN** AI generation returns grounded meeting notes for a processed utterance batch
- **THEN** the system persists a note chunk containing `key_points`, `decisions`, and `action_items`
- **AND** the persisted note chunk records the batch range with `from_sequence` and `to_sequence`

#### Scenario: Skip an empty note batch
- **WHEN** AI generation determines that a processed utterance batch has nothing worth noting
- **THEN** the system MUST NOT persist a meeting note chunk for that batch
- **AND** the system MUST NOT emit a realtime note event for that batch

#### Scenario: Extract explicit owner and due text only when grounded
- **WHEN** an action item in the transcript explicitly names an owner or due phrase
- **THEN** the note chunk includes that value in `owner_text` or `due_text`

#### Scenario: Leave owner_text empty when the transcript does not name one
- **WHEN** an action item is grounded in the transcript but no explicit owner is named
- **THEN** the note chunk stores `owner_text` as `null`

### Requirement: Note chunks are persisted and emitted additively to the meeting creator
The system SHALL persist each created meeting note chunk durably and emit an
additive realtime note event only to the user who created the meeting.

#### Scenario: Emit a created note chunk to the meeting creator
- **WHEN** a meeting note chunk is created successfully
- **THEN** the system emits a realtime note-chunk event to the meeting creator
- **AND** the event payload includes the chunk sequence range and structured note fields

#### Scenario: Backend does not need to emit a merged note snapshot
- **WHEN** multiple note chunks have already been created for the same meeting
- **THEN** the backend emits only the newly created chunk
- **AND** the backend MUST NOT require a server-generated merged note snapshot for each update

### Requirement: Parallel workers must not overlap note batches for the same meeting
The system SHALL serialize note-batch ownership per meeting even when multiple
workers consume queued utterance tasks concurrently.

#### Scenario: Prevent overlapping note batches for one meeting
- **WHEN** multiple workers attempt to summarize pending utterances for the same meeting at the same time
- **THEN** the system grants note-batch ownership to only one worker for the next contiguous sequence range
- **AND** the system MUST NOT persist overlapping note chunks for that same range

#### Scenario: Different meetings can still progress in parallel
- **WHEN** different workers process pending utterances for different meetings
- **THEN** the system allows those meetings to generate note batches independently and in parallel
