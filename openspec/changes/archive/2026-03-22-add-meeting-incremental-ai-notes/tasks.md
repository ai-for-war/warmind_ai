## 1. Meeting Note Persistence

- [x] 1.1 Add durable model and schema definitions for `meeting_note_chunks` with `key_points`, `decisions`, and `action_items`
- [x] 1.2 Create `meeting_note_chunk` repository methods and unique indexes for `(meeting_id, from_sequence, to_sequence)`
- [x] 1.3 Update meeting utterance repository/indexing to guarantee idempotent writes by `(meeting_id, sequence)`

## 2. Realtime Meeting Session Changes

- [x] 2.1 Update `MeetingSession` to allocate `sequence` at utterance close time and emit a canonical closed-utterance payload without writing Mongo inline
- [x] 2.2 Update `MeetingSessionManager` to enqueue closed meeting utterances for background persistence and note processing
- [x] 2.3 Update meeting finalize/disconnect handling to enqueue terminal note-flush work with `final_sequence` while allowing `completed` and `interrupted` to finish before background drain completes

## 3. Redis Hot State And Locking

- [x] 3.1 Add meeting note Redis helpers for `note_state`, `pending_sequences`, and `pending_utterances`
- [x] 3.2 Store canonical pending utterance payloads in Redis with precomputed text suitable for prompt assembly
- [x] 3.3 Add a per-meeting Redis summary lock with token-based acquire/release semantics for multi-worker safety

## 4. Background Worker And Note Generation

- [x] 4.1 Add a meeting note queue payload contract for `utterance_closed` and `meeting_terminal` tasks
- [x] 4.2 Implement a meeting note worker that persists queued utterances and stages unsummarized state in Redis
- [x] 4.3 Implement contiguous batch selection rules for `7` utterances plus terminal tail flush based on `final_sequence`
- [x] 4.4 Implement AI note generation and structured parsing for `key_points`, `decisions`, and `action_items` with `owner_text` and `due_text`
- [x] 4.5 Implement empty-batch handling that advances the summarized watermark and removes consumed Redis state without persisting or emitting a note chunk
- [x] 4.6 Persist note chunks idempotently and clean up consumed Redis state after each processed batch

## 5. Realtime Note Delivery And Service Wiring

- [x] 5.1 Add additive meeting note event constants and payload schemas for note chunk creation
- [x] 5.2 Emit note chunk events from the worker only to the meeting creator using the existing worker socket gateway
- [x] 5.3 Wire meeting note queue, Redis helpers, repositories, and worker dependencies into the shared service factory/container

## 6. Verification

- [ ] 6.1 Add unit tests for contiguous batch selection, terminal tail flush, and empty-batch watermark advancement
- [ ] 6.2 Add unit tests for Redis lock behavior and idempotent note/utterance persistence under duplicate task processing
- [ ] 6.3 Add integration-style tests for `utterance_end -> enqueue -> worker persist -> note emit` and `completed/interrupted -> terminal flush`
- [ ] 6.4 Run targeted verification to confirm the meeting transcript flow still emits realtime transcript events correctly while note generation happens asynchronously
