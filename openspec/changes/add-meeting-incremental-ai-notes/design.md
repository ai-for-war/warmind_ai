## Context

The codebase already has a live meeting transcription capability that:

- owns the provider connection in process-local meeting sessions
- builds canonical `messages[]` from Deepgram diarized final words
- emits transcript events over the existing authenticated Socket.IO channel
- persists `meeting_utterance` directly from the realtime session path

That flow is sufficient for transcript capture, but it does not support
incremental AI notes and keeps durable utterance persistence on the live audio
critical path. The new change introduces a second layer of behavior on top of
meeting transcription:

- closed utterances must be handed off to background processing
- note generation must happen only after `7` contiguous unsummarized utterances
  or on terminal flush
- note output must be structured as `key_points`, `decisions`, and
  `action_items`
- empty note batches must be consumed without persisting or emitting anything
- the user who created the meeting must receive additive note chunk events in
  realtime
- Redis should hold unsummarized hot state so workers do not rebuild batch
  context from MongoDB on every trigger

This is a cross-cutting change because it affects:

- `app/services/meeting/` session semantics
- Redis queue and hot-state usage
- worker topology and realtime worker emits
- new durable note-chunk persistence
- lifecycle coordination at `completed` and `interrupted`

## Goals / Non-Goals

**Goals:**
- Remove durable meeting utterance persistence from the realtime critical path
- Keep canonical utterance assembly inside the live meeting session
- Persist closed utterances asynchronously from queued work
- Generate incremental structured meeting notes from contiguous utterance
  batches of size `7`
- Flush the remaining pending tail only when a meeting becomes `completed` or
  `interrupted`
- Use Redis as the fast source of pending unsummarized utterances
- Support scaling to multiple workers without overlapping note ranges for the
  same meeting
- Persist note chunks durably and emit only the newly created chunk to the
  meeting creator

**Non-Goals:**
- Reintroduce idle-time flush logic for partial tails while the meeting is still
  streaming
- Generate one server-side merged note snapshot on every update
- Infer an action item owner from diarization speaker identity when no explicit
  owner name appears in transcript text
- Guarantee exactly-once queue delivery in phase 1
- Externalize process-local live meeting session ownership or remove sticky
  routing requirements
- Normalize `due_text` into a concrete datetime field in phase 1

## Decisions

### D1: Keep canonical utterance assembly in the realtime session, but move persistence downstream

**Decision**: `MeetingSession` remains responsible for buffering final words,
grouping them into canonical `messages[]`, assigning the next meeting-local
`sequence`, and emitting `meeting:utterance_closed`. It no longer performs the
durable Mongo write itself. Instead, it emits a closed-utterance payload that
`MeetingSessionManager` enqueues for worker-side persistence and note handling.

**Alternatives considered:**
- **Move raw word grouping to the worker**: reduces session responsibility, but
  leaks live-session state into async workers and requires passing larger,
  noisier payloads downstream
- **Keep synchronous utterance persistence and only async AI notes**: safer
  short term, but does not remove DB work from the realtime path and no longer
  matches the chosen product direction

**Rationale**: Canonicalization depends on live in-memory utterance state and
provider timing. Persistence and note generation do not. Splitting at the
closed canonical utterance boundary keeps the live path small without moving
session-only logic into workers.

### D2: Use a queue-first async pipeline for both utterance persistence and note generation

**Decision**: Each closed meeting utterance is enqueued immediately. A meeting
worker consumes that task, persists the utterance durably, stores the hot note
input in Redis, and attempts note generation.

**Alternatives considered:**
- **Background `asyncio` tasks inside the app process**: simpler locally, but
  tied to app instance lifecycle and not suitable for independent worker scale
- **Persist first, queue later**: reduces loss risk, but keeps DB writes in the
  live path and weakens the benefit of the worker split

**Rationale**: The product accepts best-effort queue semantics in phase 1.
Queue-first gives the cleanest separation between realtime ingestion and
background work, and it aligns with existing Redis queue and worker patterns
already present in the repo.

### D3: Redis hot state stores only unsummarized meeting utterances

**Decision**: Redis stores only the pending note window for each meeting, not
the full meeting history. Once a batch is consumed, its utterances are removed
from Redis. MongoDB remains the durable source for transcript and note history.

**Per-meeting Redis keys:**
- `meeting:{meeting_id}:note_state` as a hash
  - `created_by_user_id`
  - `organization_id`
  - `status`
  - `last_summarized_sequence`
  - `final_sequence` optional
- `meeting:{meeting_id}:pending_sequences` as a sorted set
  - member = sequence string
  - score = numeric sequence
- `meeting:{meeting_id}:pending_utterances` as a hash
  - field = sequence string
  - value = serialized utterance payload including `messages[]` and `flat_text`

**Alternatives considered:**
- **Rebuild every note batch from MongoDB**: simpler durability story, but adds
  avoidable query cost and increases worker contention on the database
- **Store the full transcript timeline in Redis**: faster reads, but larger
  memory footprint and unnecessary once a batch has already been consumed

**Rationale**: The worker only needs the unsummarized contiguous tail. Keeping
just that hot set in Redis minimizes DB reads while keeping memory bounded.

### D4: Note generation uses fixed contiguous batches of seven utterances plus terminal tail flush

**Decision**: The worker summarizes only the next contiguous unsummarized batch
after `last_summarized_sequence`.

**Batch rules:**
- If there are at least `7` contiguous pending utterances, summarize exactly the
  next `7`
- If fewer than `7` exist and the meeting is still `streaming`, do nothing
- If fewer than `7` exist and the meeting is `completed` or `interrupted`,
  summarize the entire remaining contiguous tail only after Redis contains all
  sequences through `final_sequence`

**Alternatives considered:**
- **Rolling window summaries**: gives more context continuity, but causes note
  overlap and makes client-side merging and idempotency much harder
- **Idle-time flush**: improves responsiveness for sparse meetings, but adds a
  scheduler and more race conditions; it was explicitly deferred

**Rationale**: Fixed disjoint batches keep note ranges deterministic, make
idempotency practical, and match the product decision to drop idle flush while
preserving terminal flush.

### D5: Empty note batches still advance the watermark

**Decision**: If AI determines that a processed batch contains nothing worth
noting, the worker does not persist or emit a note chunk, but it still advances
`last_summarized_sequence` and removes the batch from Redis pending state.

**Alternatives considered:**
- **Keep empty batches pending for a later attempt**: may produce more context
  later, but breaks deterministic batch ownership and can cause repeated
  summarization of the same range
- **Persist explicit empty note records**: adds noise to durable history and
  frontend logic without user value

**Rationale**: The batch boundary is a processing contract, not a promise that
every batch yields visible notes. Advancing the watermark prevents rework and
keeps the system moving forward deterministically.

### D6: Use per-meeting distributed locking only for summary ownership

**Decision**: Multiple workers may persist utterances for the same meeting, but
only one worker may own note-batch selection and summarization at a time. This
is enforced with a Redis lock:

- key: `lock:meeting:{meeting_id}:note_summary`
- acquire via `SET key token NX EX ttl`
- release via compare-and-delete using the same token

The lock covers:
- reading `last_summarized_sequence`
- selecting the next contiguous batch
- invoking AI
- inserting the note chunk
- advancing the watermark
- deleting consumed Redis pending state

**Alternatives considered:**
- **Single worker process for all meeting notes**: simplest coordination, but
  blocks horizontal scale
- **Lock all utterance persistence too**: stronger ordering, but unnecessary if
  persistence is idempotent and significantly reduces throughput

**Rationale**: The overlap risk exists at note-range selection, not at durable
utterance writes. Narrow summary locking preserves parallelism across meetings
and keeps worker coordination focused on the critical race.

### D7: Durable writes must be idempotent by meeting-local identity

**Decision**: Mongo writes for queued utterances and note chunks must be
idempotent.

**Proposed durable models:**

`meeting_utterances`
```json
{
  "_id": "utterance_id",
  "meeting_id": "string",
  "sequence": 12,
  "messages": [{ "speaker_index": 0, "speaker_label": "speaker_1", "text": "..." }],
  "created_at": "datetime"
}
```

`meeting_note_chunks`
```json
{
  "_id": "note_id",
  "meeting_id": "string",
  "from_sequence": 8,
  "to_sequence": 14,
  "key_points": ["..."],
  "decisions": ["..."],
  "action_items": [
    {
      "text": "Prepare the report",
      "owner_text": "Minh",
      "due_text": "next Friday"
    }
  ],
  "created_at": "datetime"
}
```

**Indexes:**
- `meeting_utterances`: unique `(meeting_id, sequence)`
- `meeting_note_chunks`: unique `(meeting_id, from_sequence, to_sequence)`

**Alternatives considered:**
- **Rely only on queue semantics for uniqueness**: insufficient once multiple
  workers or retries exist
- **Use one mutable aggregate note document per meeting**: easier reads, but
  harder retries and worse client merge semantics

**Rationale**: The system does not guarantee exactly-once queue delivery, so
idempotent storage is mandatory. Chunk-level note persistence matches the
frontend decision to merge note chunks client-side.

### D8: Terminal meeting completion does not wait for background note drain

**Decision**: After provider finalize/close handling is complete, the live
meeting session may transition the meeting to `completed` or `interrupted`
before workers finish persisting the remaining utterances or generating the
final note chunk. The session must enqueue terminal work together with
`final_sequence` so workers know exactly when the terminal tail is complete.

**Alternatives considered:**
- **Block terminal completion until workers finish**: stronger end-to-end
  completion semantics, but keeps background variability on the realtime path
- **Drop terminal tail note flushing entirely**: simpler, but loses the last
  partial chunk of note-worthy conversation

**Rationale**: The product explicitly accepts eventual note completion after the
meeting has ended. Passing `final_sequence` preserves determinism for terminal
flush without extending the live session lifecycle.

### D9: Note output is a new additive realtime event scoped to the meeting creator

**Decision**: Add a new outbound event, e.g. `meeting:note:created`, emitted
only to the meeting creator. The event payload contains only the newly created
note chunk, not a merged note snapshot.

**Alternatives considered:**
- **Embed notes into `meeting:utterance_closed`**: conflates transcript closure
  with asynchronous note creation and breaks event semantics
- **Emit note events to all listeners in the organization**: broader fan-out,
  but not aligned with current product requirements

**Rationale**: Notes and utterance closure are different stages of processing.
Keeping note chunks as a separate additive event preserves a clean contract and
matches the frontend plan to merge note chunks locally.

### D10: Action item owner extraction is transcript-grounded text only

**Decision**: `action_items[]` stores:
- `text`
- `owner_text`
- `due_text`

`owner_text` is set only when the transcript explicitly names one, such as
`"Minh làm bản báo cáo nhé"`. If the transcript does not name an owner,
`owner_text` remains `null`. The system does not derive owner identity from
`speaker_label`.

**Alternatives considered:**
- **Infer owner from diarized speaker**: convenient, but not grounded enough and
  contradicts the product decision
- **Drop action item owner entirely**: simpler, but loses high-value structure
  when names are spoken explicitly

**Rationale**: The system should capture named owners when the transcript truly
contains them, but avoid misleading attribution from diarization labels.

## Risks / Trade-offs

**[Queue-first handoff can lose work if a worker crashes after dequeue]** ->
Mitigation: accept best-effort semantics in phase 1, make Mongo writes
idempotent, and keep task logging/metrics visible for operational debugging.

**[Terminal event can arrive before the last utterance task is processed]** ->
Mitigation: include `final_sequence` in terminal work and only flush the
terminal tail once Redis contains a contiguous range through that sequence.

**[Multiple workers can re-run the same note batch after partial failure]** ->
Mitigation: protect batch ownership with a per-meeting lock and enforce unique
Mongo indexes on note chunk ranges.

**[Redis hot state can become stale if cleanup is missed]** -> Mitigation:
delete consumed batches immediately and add TTL safety to per-meeting note-state
keys so orphaned state ages out.

**[Dropping idle flush reduces note freshness for sparse meetings]** ->
Mitigation: keep the simpler batch model for phase 1 and rely on terminal flush
to capture the remaining tail.

**[Action item owner extraction can miss implied owners]** -> Mitigation:
prefer grounded correctness over inferred ownership; leave `owner_text=null`
when names are not explicit.

## Migration Plan

1. Add new durable model, schema, and repository support for meeting note
   chunks plus unique indexes for utterance and note idempotency.
2. Extend meeting socket events and payload schemas with additive note-chunk
   realtime output.
3. Update `MeetingSession` and `MeetingSessionManager` so closed utterances are
   sequenced, emitted, and enqueued rather than durably persisted inline.
4. Add Redis-backed note state helpers for pending utterance payloads,
   summarized-sequence tracking, and per-meeting summary locks.
5. Add a meeting note worker that:
   - persists queued utterances
   - stages them in Redis
   - summarizes the next eligible contiguous batch
   - persists note chunks
   - emits realtime note events
   - performs terminal tail flush when `final_sequence` is fully available
6. Verify end-to-end behavior for:
   - batching at `7` contiguous utterances
   - no note emission for empty batches
   - terminal tail flush on `completed` and `interrupted`
   - no overlapping note ranges under concurrent workers
7. Roll out with worker processes enabled after the app path can enqueue
   meeting-note tasks successfully.

**Rollback**
- stop the meeting note worker
- disable meeting note enqueue and emit wiring
- keep existing transcript capture behavior
- leave additive note-chunk data in MongoDB untouched if already written

## Open Questions

- Should Redis hot note state be wrapped in a meeting-specific helper service,
  or kept inside the worker/session manager layer for phase 1?
- Does the frontend need an explicit “note processing finished” signal after
  terminal flush, or is additive chunk delivery alone sufficient?
