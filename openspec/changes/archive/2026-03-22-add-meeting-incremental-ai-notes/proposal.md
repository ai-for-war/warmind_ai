## Why

The current meeting transcription flow is optimized for emitting canonical
utterances directly from the realtime session, but it does not produce
incremental AI notes during the meeting and keeps persistence on the critical
path of the live socket flow.

The product now needs structured meeting notes to appear incrementally while a
meeting is in progress, based on closed utterance batches, without blocking the
live transcription path. This requires a queue-backed worker flow, fast
transient state for unsummarized utterances, and a durable note history that
can be replayed later.

## What Changes

- Add an incremental meeting note workflow that consumes closed meeting
  utterances asynchronously and generates structured note chunks with
  `key_points`, `decisions`, and `action_items`
- Trigger meeting note generation only when there are at least `7` contiguous
  unsummarized utterances, or when the meeting reaches a terminal state and the
  remaining tail must be flushed
- Persist generated note chunks durably so the meeting note timeline can be
  viewed again after the live session ends
- Emit additive realtime socket events for newly created note chunks to the
  user who created the meeting, while letting the frontend merge note chunks
  client-side
- Move stable meeting utterance persistence off the realtime critical path by
  enqueueing closed utterances for worker-side persistence and note generation
- Keep unsummarized meeting utterance state in Redis for fast batch assembly and
  terminal flush coordination instead of repeatedly rebuilding note context from
  MongoDB
- Add per-meeting summary locking so multiple workers can scale horizontally
  without generating overlapping note batches for the same meeting

## Capabilities

### New Capabilities
- `meeting-incremental-ai-notes`: Build incremental structured meeting notes
  from closed utterance batches, persist note chunks, and emit realtime note
  updates during an active meeting

### Modified Capabilities
- `live-meeting-transcription`: Adjust meeting utterance lifecycle semantics so
  closed utterances are enqueued for asynchronous persistence and note
  processing, while terminal meeting completion may occur before background note
  work fully drains

## Impact

- **New worker flow**: add a meeting-specific queue consumer that persists
  canonical utterances, assembles unsummarized contiguous batches, invokes AI,
  persists note chunks, and emits note events
- **New Redis hot state**: add per-meeting pending utterance storage, sequence
  tracking, and summary coordination state so batch selection can be resolved
  without querying MongoDB on every trigger
- **New locking requirement**: add a per-meeting distributed summary lock in
  Redis so multiple workers can safely process different meetings in parallel
  without double-summarizing the same sequence range
- **New persistence**: add durable storage and indexes for meeting note chunks,
  plus idempotent utterance/note writes keyed by meeting and sequence range
- **Updated realtime contract**: add an additive outbound event for new meeting
  note chunks while preserving the existing transcript-oriented meeting socket
  flow
- **Affected code**: `app/services/meeting/`, `app/socket_gateway/`,
  `app/common/event_socket.py`, `app/common/service.py`,
  `app/infrastructure/redis/`, `app/workers/`, `app/domain/models/`,
  `app/domain/schemas/`, and `app/repo/`
