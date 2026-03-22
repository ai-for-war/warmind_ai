## MODIFIED Requirements

### Requirement: Utterance ổn định chỉ được đóng khi provider phát tín hiệu utterance_end
The system SHALL treat a meeting utterance as stable only when the provider
emits `utterance_end` for the accumulated final transcript region. At that
moment, the system MUST allocate the next meeting-local sequence, emit the
canonical closed utterance payload, and enqueue that utterance for asynchronous
background persistence and note processing.

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

### Requirement: Durable storage của utterance chỉ lưu dữ liệu transcript đã chuẩn hóa
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

### Requirement: Kết thúc phiên phải flush transcript cuối và đánh dấu trạng thái terminal phù hợp
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
