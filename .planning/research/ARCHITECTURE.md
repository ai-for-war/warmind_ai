# Architecture Research

**Domain:** internal AI meeting recording and note generation
**Researched:** 2026-03-19
**Confidence:** HIGH

## Standard Architecture

### System Overview

```text
+--------------------------------------------------------------+
| Client                                                       |
| - audio capture                                              |
| - meeting start/stop controls                                |
| - transcript and summary view                                |
+---------------------------+----------------------------------+
                            |
                            v
+--------------------------------------------------------------+
| Realtime/API boundary                                         |
| - Socket.IO meeting stream events                             |
| - REST endpoints for meeting read/detail/history              |
+---------------------------+----------------------------------+
                            |
                            v
+--------------------------------------------------------------+
| Meeting application layer                                     |
| - meeting session manager                                     |
| - transcript assembler                                        |
| - summary batch orchestrator                                  |
| - access control + organization scoping                       |
+------------------+-----------------------+-------------------+
                   |                       |
                   v                       v
+------------------------+     +--------------------------------+
| External speech layer  |     | Background AI layer            |
| - Deepgram live STT    |     | - Redis queue                  |
| - diarization          |     | - summary worker               |
| - utterances/gap       |     | - LLM summary prompt pipeline  |
+------------------------+     +--------------------------------+
                   \                       /
                    \                     /
                     v                   v
+--------------------------------------------------------------+
| Persistence                                                   |
| - meeting_conversations                                       |
| - meeting_utterances                                          |
| - meeting_summaries                                           |
+--------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Meeting socket gateway | Accept stream lifecycle events and audio frames | New meeting-specific events layered on top of the current Socket.IO server and auth model |
| Meeting session manager | Own one active meeting stream, batching windows, and provider interaction | Separate service from interview session management, even if shared utilities are reused |
| Transcript persistence | Store stable utterances/messages and meeting metadata | Mongo repositories dedicated to meeting conversations and utterances |
| Summary batch orchestrator | Decide when enough stable transcript changed to trigger summary work | Redis-backed enqueue/debounce logic keyed by meeting conversation id |
| Summary worker | Generate or update structured meeting notes | LLM-backed worker that reads transcript chunks and upserts summary snapshots |
| Meeting read API | Serve transcript, summary, and history back to the frontend | REST endpoints with organization/user authorization checks |

## Recommended Project Structure

```text
app/
|-- api/
|   `-- v1/
|       `-- meetings/
|           |-- router.py
|           `-- schemas.py
|-- services/
|   `-- meeting_record/
|       |-- session_manager.py
|       |-- transcript_service.py
|       |-- summary_service.py
|       `-- batch_policy.py
|-- repo/
|   |-- meeting_conversation_repo.py
|   |-- meeting_utterance_repo.py
|   `-- meeting_summary_repo.py
|-- domain/
|   |-- models/
|   |   |-- meeting_conversation.py
|   |   |-- meeting_utterance.py
|   |   `-- meeting_summary.py
|   `-- schemas/
|       |-- meeting_stream.py
|       `-- meeting_summary.py
|-- prompts/
|   `-- system/
|       `-- meeting_summary.py
`-- workers/
    `-- meeting_summary_worker.py
```

### Structure Rationale

- **`services/meeting_record/`:** Keeps the new product domain separate from interview-specific services while still living inside the same application layer.
- **`repo/meeting_*`:** Prevents accidental schema leakage from interview collections and makes retention/index tuning meeting-specific.
- **`domain/models/` + `domain/schemas/`:** Preserves the repo's existing domain contract split.
- **`workers/meeting_summary_worker.py`:** Keeps heavy summary generation out of the live Socket.IO loop.

## Architectural Patterns

### Pattern 1: Separate meeting domain over shared infrastructure

**What:** Reuse Deepgram, Redis, auth, sockets, and LLM providers, but create meeting-native models, repos, prompts, and APIs.
**When to use:** When two product flows share plumbing but have different business semantics.
**Trade-offs:** Slightly more code up front, but far less accidental coupling later.

**Example:**
```python
meeting_session = MeetingSessionManager(
    deepgram_client_factory=make_live_stt_client,
    meeting_conversation_repo=get_meeting_conversation_repo(),
    meeting_utterance_repo=get_meeting_utterance_repo(),
    summary_scheduler=get_meeting_summary_scheduler(),
)
```

### Pattern 2: Transcript log plus summary projection

**What:** Treat transcript utterances as the immutable event log and summaries as a derived projection.
**When to use:** When users need both raw evidence and condensed notes.
**Trade-offs:** More storage, but much better debuggability and safer summary regeneration.

**Example:**
```python
await meeting_utterance_repo.append(stable_utterance)
await meeting_summary_repo.upsert_snapshot(
    conversation_id=conversation_id,
    transcript_cursor=latest_utterance_id,
    summary=structured_summary,
)
```

### Pattern 3: Debounced batch summarization

**What:** Summarize after a stable transcript window changes enough, not after every fragment.
**When to use:** Long-form meetings where note quality matters more than instant token streaming.
**Trade-offs:** Slight delay before notes update, but much better signal-to-noise ratio and lower cost.

## Data Flow

### Request Flow

```text
User starts meeting
    ->
Socket start event
    ->
Meeting session manager
    ->
Deepgram live stream
    ->
Stable utterance closes
    ->
Persist meeting utterance
    ->
Enqueue/debounce summary batch
    ->
Summary worker + LLM
    ->
Upsert meeting summary snapshot
    ->
REST/socket read path updates UI
```

### State Management

```text
Live state:
- active socket session
- current open utterance buffers
- debounce timers / pending summary work

Durable state:
- meeting conversation metadata
- stable utterances
- summary snapshots / latest summary view
```

### Key Data Flows

1. **Capture flow:** Frontend streams audio, backend converts provider results into stable meeting utterances.
2. **Summary flow:** Stable transcript changes trigger debounced summary work that writes summary projections.
3. **Review flow:** Frontend loads meeting detail from conversation, utterance, and summary stores.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-1k internal meetings | Current modular monolith is enough; optimize for correctness and storage shape first |
| 1k-100k meetings | Add stronger batching, transcript pagination, and summary snapshot compaction; monitor Redis queue pressure and provider cost |
| 100k+ meetings | Consider separating summary workers and transcript read models, but only after real bottlenecks appear |

### Scaling Priorities

1. **First bottleneck:** LLM summary cost and queue latency - fix with debounce rules, incremental snapshots, and capped summary frequency.
2. **Second bottleneck:** Transcript retrieval size - fix with utterance pagination, detail endpoints, and summary-first UI loading.

## Anti-Patterns

### Anti-Pattern 1: One "conversation" schema for every speech feature

**What people do:** Reuse the interview conversation model because it already exists.
**Why it's wrong:** Meeting semantics diverge immediately once speaker roles, summaries, history, and follow-ups differ.
**Do this instead:** Keep common infrastructure shared, but define meeting-specific domain models and repos.

### Anti-Pattern 2: Summary generation inside the live STT loop

**What people do:** Call the LLM every time a final fragment arrives.
**Why it's wrong:** It increases latency, cost, and note instability while making disconnect recovery harder.
**Do this instead:** Persist stable transcript first, then summarize in a debounced background path.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Deepgram | Live streaming STT with diarization, utterances, punctuation, and gap detection | Use diarization for mixed speaker streams; do not force multichannel assumptions on browser capture |
| OpenAI via existing abstraction | Structured summary generation | Keep prompt/schema ownership inside the application rather than outsourcing the product contract |
| Redis | Queue, debounce, and fan-out infrastructure | Reuse current worker/backplane patterns already present in the repo |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `socket_gateway` <-> `services/meeting_record` | direct service calls + normalized events | Reuse auth/session patterns but keep event names and payloads meeting-specific |
| `services/meeting_record` <-> `repo/meeting_*` | direct repository access | Avoid writing meeting data into interview repos |
| `workers/meeting_summary_worker` <-> `repo/meeting_*` | queue payloads + repo reads/writes | Make summary jobs idempotent so retries are safe |

## Sources

- `.planning/codebase/ARCHITECTURE.md` - current layered architecture and runtime boundaries
- `.planning/codebase/STRUCTURE.md` - current repo organization
- `.planning/PROJECT.md` - product boundary and user pain
- https://developers.deepgram.com/docs/diarization - speaker labeling behavior
- https://developers.deepgram.com/docs/utterances - utterance grouping
- https://developers.deepgram.com/docs/utterance-end - streaming gap detection for batch windows
- https://developers.deepgram.com/docs/multichannel-vs-diarization - design guidance for meeting audio shape

---
*Architecture research for: internal AI meeting recording and note generation*
*Researched: 2026-03-19*
