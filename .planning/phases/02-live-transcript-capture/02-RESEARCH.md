# Phase 02: Live Transcript Capture - Research

**Researched:** 2026-03-19
**Domain:** FastAPI + Socket.IO + Deepgram live meeting transcript capture
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### Live transcript behavior
- During an active meeting, users should see transcript text live before the utterance is fully stabilized.
- When provider output is corrected by a later finalized transcript fragment, the current live text should be rewritten in place rather than appended as a correction trail.
- The transcript should be shaped around stable utterances. Once one utterance is considered stable, the next transcript content should begin a new transcript block.
- Frontend scrolling behavior is not locked in this phase discussion and can remain implementation discretion.

### Speaker grouping and labeling
- Transcript storage and presentation should be utterance-first, not speaker-merged. Each stable utterance remains its own transcript item.
- Anonymous speaker labels do not need to remain perfectly stable across an entire meeting session.
- The preferred visible label format is `speaker 1`, `speaker 2`, and so on.
- If diarization is unclear for a captured utterance, the system should still retain that utterance and use a fallback label such as `speaker unknown` rather than dropping transcript text.

### Timestamp fidelity
- Saved transcript items should carry both utterance start and utterance end timestamps.
- The canonical stored timing representation should be milliseconds from meeting start rather than preformatted display strings.
- Timestamp display during the live meeting is not a locked requirement for this phase; the important requirement is durable timing for saved review.
- If provider timing is imperfect, the system should persist best-effort timestamps instead of rejecting otherwise valid transcript content.

### Saved transcript review shape
- Saved transcript review should be a chronological list of utterance items rather than speaker-grouped sections.
- Each saved transcript item should minimally include anonymous speaker label, utterance text, and timestamps.
- Read paths for completed transcripts should be paginated in Phase 2 rather than only returning the full transcript in one fetch.
- Paginated transcript review should default to oldest-first ordering so review reads naturally from meeting start to meeting end.

### Claude's Discretion
- Exact socket or API payload shapes used to emit live transcript updates during an active meeting
- The exact fallback label string for unclear diarization as long as it is anonymous and non-destructive
- Pagination mechanics for completed transcript reads, including page size and cursor/offset style
- Whether transcript persistence uses a meeting-specific utterance store, a linked conversation/message structure, or another meeting-native durable model that does not leak chat semantics publicly

### Deferred Ideas (OUT OF SCOPE)
None - discussion stayed within Phase 2 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRNS-01 | User can view transcript text accumulating during an active meeting session | Use meeting-native socket transcript upsert events driven by provider interim/final fragments and a background listener loop |
| TRNS-02 | User can review the full saved transcript after the meeting ends | Persist stable utterances in MongoDB under a dedicated meeting transcript collection and expose paginated oldest-first REST reads |
| TRNS-03 | User can see transcript segments grouped by anonymous speaker labels such as `speaker 1` and `speaker 2` | Enable Deepgram diarization, derive a dominant speaker per stable utterance, and persist anonymous rendered labels per utterance |
| TRNS-04 | User can see timestamps for saved transcript segments when reviewing a meeting | Persist `start_ms` and `end_ms` as meeting-relative integers on each closed utterance and return them in transcript read schemas |
</phase_requirements>

## Summary

Phase 2 should extend the meeting-native runtime introduced in Phase 1 instead of inventing a new streaming path. The repo already has the hard parts in adjacent code: a Deepgram websocket adapter, fragment-by-fragment transcript assembly logic in `app/services/stt/session.py`, Socket.IO user-room delivery in `app/socket_gateway/server.py`, and durable MongoDB meeting lifecycle storage in `app/repo/meeting_record_repo.py`. What is missing is a meeting-specific transcript lane that consumes provider events, rewrites live partial text in place, closes stable utterances, persists them durably, and exposes transcript read APIs.

The safest architecture is: keep volatile live preview state in the process-local meeting session, persist only stable utterances, and emit meeting-native transcript upsert events keyed by a stable server-generated utterance id. This matches the locked product behavior: the UI can rewrite the current line in place while the saved transcript remains a chronological list of stable utterance items. Do not reuse generic chat messages as the public meeting transcript model. The existing `Message` model has chat roles and `created_at`, but it does not model anonymous speakers, meeting-relative `start_ms` / `end_ms`, or utterance closure semantics cleanly.

Deepgram's current live audio docs still document the `v1/listen` websocket parameters the repo already wraps, and those parameters cover this phase: `interim_results`, `endpointing`, `utterance_end_ms`, `vad_events`, and `diarize`. The current repo does not enable diarization and the meeting runtime does not run a provider listener at all, so planning should focus on adapting the existing STT listener/session pattern into the meeting domain, not on changing providers or redesigning the transport.

**Primary recommendation:** Reuse the current Deepgram + Socket.IO + MongoDB stack, add a meeting transcript assembler around provider final/interim events, persist closed utterances in a dedicated `meeting_transcript_utterances` collection, and expose oldest-first paginated read APIs while keeping live preview socket-driven.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | `0.135.1` (PyPI, 2026-03-01) | HTTP transcript review endpoints and dependency-based auth/org scoping | Already the repo API layer; official router/dependency patterns fit the current composition style |
| `python-socketio` | `5.16.1` (PyPI, 2026-02-06) | Live meeting transcript event delivery | Already owns authenticated user rooms and meeting socket lifecycle |
| `deepgram-sdk` | `6.0.1` (PyPI, 2026-02-24) | Live speech-to-text with interim results, endpointing, utterance-end, and diarization | Existing provider wrapper already isolates the SDK; official live API still supports the needed `v1/listen` feature set |
| `motor` | `3.7.1` (PyPI, 2025-05-14) | Async MongoDB persistence for meeting utterances | Matches all existing repository patterns in the repo |
| `pydantic` | `2.12.5` (PyPI, 2025-11-26) | Typed meeting transcript models and API/socket schemas | Already used across current models/schemas |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic-settings` | `2.13.1` (PyPI, 2026-02-19) | Meeting transcript feature flags and runtime settings | Add meeting transcript tuning knobs beside current `MEETING_STT_*` settings |
| `pytest` | Installed `8.3.5` locally; PyPI latest `9.0.2` (2025-12-06) | Unit/integration validation for transcript assembly and review APIs | Use the installed version for this phase; do not mix a framework upgrade into transcript work |
| `pytest-asyncio` | version not verified from source tree; plugin is installed | Async test support for service/repo/socket flows | Required for async session manager and repository tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Dedicated meeting transcript utterance collection | Reuse `conversations` + `messages` | Reuse looks cheaper, but the current message model does not represent anonymous speakers, meeting-relative timestamps, or utterance closure cleanly |
| Offset pagination (`skip` / `limit`) | Cursor pagination | Cursor pagination scales better later, but offset matches current repo patterns and is sufficient for Phase 2 |
| Server-side fragment assembly using `is_final` + `speech_final` / `UtteranceEnd` | Provider `utterances=true` as the primary live path | `utterances=true` exists, but the current code already has the right partial/final assembly shape and the product needs rewrite-in-place live preview |

**Installation:**
```bash
pip install fastapi python-socketio deepgram-sdk motor pydantic pydantic-settings pytest pytest-asyncio
```

**Version verification:** Verified against official PyPI package metadata on 2026-03-19. Do not turn Phase 2 into a dependency-upgrade phase. The most important caution is `deepgram-sdk`: PyPI current is `6.0.1`, while the freshest Context7 SDK docs available in-session are `v5.3.0`. The repo already wraps the provider behind `app/infrastructure/deepgram/client.py`, so keep the phase scoped to wrapper enhancements and pin/confirm the deployed SDK separately if runtime drift appears.

## Architecture Patterns

### Recommended Project Structure
```text
app/
|-- api/v1/meeting_records/router.py              # Transcript review endpoints
|-- common/event_socket.py                        # Meeting transcript event names
|-- common/repo.py                                # Meeting transcript repo factory
|-- common/service.py                             # Meeting transcript service factory
|-- domain/models/meeting_transcript_utterance.py # Durable utterance storage model
|-- domain/schemas/meeting_transcript.py          # Socket + REST transcript payloads
|-- repo/meeting_transcript_repo.py               # MongoDB transcript persistence
|-- services/meeting/session.py                   # Add transcript assembly state
|-- services/meeting/session_manager.py           # Add collect/reap/listener support
`-- services/meeting/transcript_service.py        # Persistence + read orchestration
```

### Pattern 1: Background Listener Owns Provider Event Consumption
**What:** Mirror the existing interview STT pattern: audio handlers only push bytes; a long-lived background task consumes provider events, assembles transcript state, persists stable utterances, and emits user-facing events.

**When to use:** Always for meeting transcript capture. Do not parse provider events inside `meeting_record:audio`.

**Example:**
```python
async def _run_meeting_listener(*, sid: str, user_id: str) -> None:
    while True:
        emitted = await meeting_service.collect_session_events(
            sid=sid,
            wait_for_first=True,
            timeout_seconds=1.0,
        )
        if not emitted:
            emitted = await meeting_service.reap_session(sid)
        await _emit_meeting_session_events(user_id=user_id, events=emitted)
```
Source: local pattern from `app/socket_gateway/server.py` and `app/services/stt/session_manager.py`

### Pattern 2: Stable Utterance ID + Upsert Events for Live Rewrite
**What:** Generate one server-side utterance id when a meeting utterance opens. Emit partial/final updates against that same id so the frontend rewrites in place. Persist the same id when the utterance closes.

**When to use:** For all live transcript updates. This is required by the locked "rewrite in place" behavior.

**Example:**
```python
if not transcript.is_final:
    emit_partial(
        meeting_id=session.meeting_id,
        utterance_id=open_utterance.utterance_id,
        speaker_label=open_utterance.speaker_label,
        text=open_utterance.preview_transcript,
    )
else:
    open_utterance.append_stable(transcript)
    if transcript.speech_final or utterance_end_seen:
        saved = await transcript_repo.append_stable(...)
        emit_committed(meeting_id=session.meeting_id, utterance=saved)
```
Source: Deepgram endpointing/interim-results guidance plus local `app/services/stt/session.py` assembly pattern

### Pattern 3: Durable-Only Persistence for Closed Utterances
**What:** Persist only stable utterances that have crossed a closure boundary. Keep provisional preview text process-local.

**When to use:** Default Phase 2 behavior. It limits write churn and keeps saved review clean.

**Example:**
```python
document = {
    "_id": utterance_id,
    "meeting_id": meeting_id,
    "organization_id": organization_id,
    "sequence": sequence,
    "speaker_label": speaker_label,
    "provider_speaker": provider_speaker,
    "text": text,
    "start_ms": start_ms,
    "end_ms": end_ms,
    "created_at": utcnow,
}
await collection.find_one_and_update(
    {"_id": utterance_id},
    {"$setOnInsert": document},
    upsert=True,
)
```
Source: local repository style from `app/repo/interview_utterance_repo.py` and `app/repo/meeting_record_repo.py`

### Pattern 4: Oldest-First Paginated Review Reads
**What:** Read saved transcript pages in chronological order using `skip` / `limit`, sorted by `start_ms` and a monotonic fallback key such as `sequence`.

**When to use:** Completed meeting review endpoints and active-session durable transcript reads.

**Example:**
```python
cursor = (
    collection.find({"meeting_id": meeting_id, "organization_id": organization_id})
    .sort([("start_ms", 1), ("sequence", 1)])
    .skip(skip)
    .limit(limit)
)
```
Source: local repo pagination style from `app/repo/conversation_repo.py` and `app/repo/message_repo.py`

### Anti-Patterns to Avoid
- **Reusing `Message` as the meeting transcript model:** It forces chat semantics onto meetings and hides required speaker/timestamp fields in ad hoc metadata.
- **Appending correction lines instead of rewriting the current utterance:** This violates a locked product decision and makes the live transcript noisy.
- **Closing Deepgram immediately after `finalize()`:** The current `MeetingSession._stop_internal()` does this today; for transcript capture it risks losing tail-end final results.
- **Using `speech_final` alone as utterance truth:** Official Deepgram guidance says long utterances can emit multiple `is_final: true` fragments before `speech_final: true`.
- **Dropping utterances when diarization is unclear:** Phase 2 explicitly requires non-destructive fallback labeling.
- **Assuming HTTP can always see current live preview state:** Process-local session state still requires sticky routing; volatile preview belongs on sockets unless you add shared session storage.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Speaker separation in mono meeting audio | Custom VAD + clustering heuristics | Deepgram `diarize=true` and `words[].speaker` | Diarization is a provider capability already documented for single-channel audio |
| Live utterance stabilization | Ad hoc append-only string matcher | Deepgram `is_final` + `speech_final` / `UtteranceEnd` plus the existing STT fragment-assembly pattern | This is the documented way to reconstruct complete utterances without missing mid-utterance final fragments |
| New realtime transport for transcript updates | Separate WebSocket stack | Existing Socket.IO gateway and per-user rooms | Auth, user routing, and org-aware emit already exist |
| Full-transcript response blobs | One giant transcript document | Mongo utterance collection with paginated reads | Phase 2 explicitly wants paginated review and utterance-first presentation |

**Key insight:** The only custom logic Phase 2 should add is the meeting-domain translation layer between provider events and durable utterance records. Speaker diarization, partial/final transcript behavior, and websocket transport are already solved elsewhere in the stack or by the provider.

## Common Pitfalls

### Pitfall 1: Losing the Last Utterance on Stop
**What goes wrong:** The repo's current meeting stop flow calls `finalize()` and `close()` back-to-back inside `MeetingSession._stop_internal()`, then marks the meeting complete.
**Why it happens:** That lifecycle was sufficient for Phase 1, which did not need transcript truth.
**How to avoid:** Move stop semantics to the listener-driven model used by STT: request finalize, drain provider finals, persist any final closed utterances, then close and mark completed.
**Warning signs:** Last spoken sentence is missing or truncated in saved transcripts, especially when the user stops immediately after talking.

### Pitfall 2: Misassembling Long Utterances
**What goes wrong:** Only the last finalized fragment is kept, or the utterance closes too early.
**Why it happens:** Deepgram can emit multiple `is_final: true` segments before `speech_final: true`.
**How to avoid:** Concatenate finalized fragments until `speech_final: true` or `UtteranceEnd` closes the utterance, exactly like the current interview STT session pattern.
**Warning signs:** Long sentences are split unnaturally or saved with missing middle text.

### Pitfall 3: Wrong Anonymous Speaker Labels
**What goes wrong:** The label for a saved utterance reflects only the last word's speaker, or flips unpredictably across fragments.
**Why it happens:** Diarization comes back at word level, not as a ready-made stable meeting label for your domain.
**How to avoid:** Compute the dominant speaker for the closed utterance from accumulated word-level speaker ids, persist both the provider speaker key and rendered anonymous label, and fall back to `speaker unknown` if confidence is too weak.
**Warning signs:** A single utterance contains mixed labels or saved speaker labels change every fragment.

### Pitfall 4: Coupling Transcript Review to Process-Local Live State
**What goes wrong:** Active transcript review breaks across refreshes or multi-instance routing.
**Why it happens:** Meeting sessions are process-local, and the repo currently warns that live STT flows require sticky-session routing.
**How to avoid:** Treat sockets as the source of volatile preview and Mongo as the source of durable review. If you expose active REST reads, scope them to persisted closed utterances unless you intentionally add shared session storage.
**Warning signs:** Active-session transcript API returns inconsistent results across requests while the socket UI continues to work.

### Pitfall 5: Letting Test Infrastructure Drift Hide Regressions
**What goes wrong:** Planning assumes existing meeting/STT tests exist because `__pycache__` files are present, but `pytest tests -q` currently reports `no tests ran`.
**Why it happens:** Source test files are missing from the workspace even though cached artifacts remain.
**How to avoid:** Add transcript-focused unit/integration tests in Wave 0 and add explicit pytest async-loop configuration.
**Warning signs:** Planner references nonexistent test files or the suite stays green only because nothing is collected.

## Code Examples

Verified patterns from official sources and current repo conventions:

### Deepgram Fragment Assembly for Complete Utterances
```python
if result.is_final:
    utterance_buffer.append(result.transcript)

if result.speech_final:
    complete_utterance = " ".join(utterance_buffer)
    utterance_buffer.clear()
```
Source: https://developers.deepgram.com/docs/understand-endpointing-interim-results

### Meeting Transcript Repo Query in Oldest-First Order
```python
async def list_by_meeting(
    self,
    *,
    meeting_id: str,
    organization_id: str,
    skip: int = 0,
    limit: int = 100,
) -> list[MeetingTranscriptUtterance]:
    cursor = (
        self.collection.find(
            {"meeting_id": meeting_id, "organization_id": organization_id}
        )
        .sort([("start_ms", 1), ("sequence", 1)])
        .skip(skip)
        .limit(limit)
    )
    return [MeetingTranscriptUtterance(**doc) async for doc in cursor]
```
Source: local repo pattern from `app/repo/message_repo.py` and phase decision for oldest-first pagination

### Meeting-Native Router with Existing Auth + Org Dependencies
```python
router = APIRouter(prefix="/meeting-records", tags=["meeting-records"])


@router.get("/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: str,
    current_user: User = Depends(get_current_active_user),
    context: OrganizationContext = Depends(get_current_organization_context),
    service: MeetingTranscriptService = Depends(get_meeting_transcript_service),
):
    return await service.get_transcript_page(
        meeting_id=meeting_id,
        user_id=current_user.id,
        organization_id=context.organization_id,
    )
```
Source: FastAPI router/dependency pattern plus local `app/api/deps.py`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed interview roles on channels `0` and `1` | Single-channel meeting audio with speaker diarization | Phase 1 product boundary, Phase 2 implementation | Meeting transcript logic must stop depending on interview channel-role assumptions |
| Append-only live transcript corrections | Upsert/rewrite the current utterance in place | Locked in `02-CONTEXT.md` on 2026-03-19 | Socket payloads need stable utterance ids, not fire-and-forget text lines |
| Lifecycle-only meeting stop | Finalize, drain provider finals, persist, then close | Current Deepgram live transcription guidance | Prevents tail-loss in saved transcript capture |
| Generic chat storage reuse | Dedicated utterance-first meeting transcript storage | Recommended for Phase 2 | Preserves speaker labels and meeting-relative timestamps without chat leakage |

**Deprecated/outdated:**
- Using `MeetingSession._stop_internal()` as-is for transcript truth: it was acceptable for lifecycle-only Phase 1, but it is not safe for transcript durability.
- Reusing public `stt:*` or interview event names for meetings: it breaks the meeting-native boundary established in Phases 1 and 2.
- Treating cached pytest artifacts as proof of current coverage: the source files are absent and `pytest tests -q` currently finds no runnable tests.

## Open Questions

1. **Should the active transcript REST endpoint include volatile in-flight preview text or only persisted closed utterances?**
   - What we know: current live preview state is process-local; persisted stable utterances can be read safely from MongoDB.
   - What's unclear: whether product expectations include page refresh/reconnect restoring the current partial line during an active meeting.
   - Recommendation: define active REST reads as durable-only in Phase 2 and keep provisional preview socket-only unless a shared live-state store is explicitly added.

2. **What exact Deepgram SDK version is pinned in deployment?**
   - What we know: official PyPI current is `deepgram-sdk 6.0.1` as of 2026-02-24, while the best in-session SDK docs available via Context7 are `v5.3.0`.
   - What's unclear: whether deployment is already on a 6.x build or still effectively using the older wrapper contract.
   - Recommendation: verify and pin the runtime version before implementation, but do not expand Phase 2 into a major SDK migration unless verification shows the current wrapper is already broken.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 8.3.5` with `pytest-asyncio` plugin present |
| Config file | none - see Wave 0 |
| Quick run command | `pytest tests/unit/services/test_meeting_transcript_assembler.py -q` |
| Full suite command | `pytest tests -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-01 | Live transcript text accumulates during an active meeting | integration | `pytest tests/integration/socket_gateway/test_meeting_transcript_socket.py -q` | NO - Wave 0 |
| TRNS-02 | Completed meeting returns saved paginated transcript review | integration | `pytest tests/integration/api/test_meeting_transcript_api.py -q` | NO - Wave 0 |
| TRNS-03 | Stable utterances carry anonymous speaker labels | unit | `pytest tests/unit/services/test_meeting_transcript_assembler.py -q` | NO - Wave 0 |
| TRNS-04 | Saved utterances persist `start_ms` / `end_ms` for review | unit | `pytest tests/unit/repo/test_meeting_transcript_repo.py -q` | NO - Wave 0 |

### Sampling Rate
- **Per task commit:** targeted pytest command for the changed service/repo/socket file
- **Per wave merge:** `pytest tests -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/services/test_meeting_transcript_assembler.py` - covers TRNS-01 and TRNS-03 fragment assembly, rewrite-in-place, diarization fallback
- [ ] `tests/unit/repo/test_meeting_transcript_repo.py` - covers TRNS-02 and TRNS-04 oldest-first pagination and timestamp persistence
- [ ] `tests/integration/socket_gateway/test_meeting_transcript_socket.py` - covers live meeting transcript socket flow
- [ ] `tests/integration/api/test_meeting_transcript_api.py` - covers completed transcript review endpoints and org scoping
- [ ] `tests/conftest.py` - shared async repo/socket fixtures
- [ ] `pytest.ini` or `pyproject.toml` - set `asyncio_default_fixture_loop_scope=function` to remove the current `pytest-asyncio` deprecation warning

## Sources

### Primary (HIGH confidence)
- `/deepgram/deepgram-python-sdk/v5.3.0` via Context7 - SDK websocket/event handling patterns
- `/fastapi/fastapi/0.128.0` via Context7 - `APIRouter` and dependency-injection patterns
- https://developers.deepgram.com/reference/speech-to-text/listen-streaming - current `v1/listen` websocket API, query parameters, control messages, and word-level `speaker`
- https://developers.deepgram.com/docs/understand-endpointing-interim-results - `is_final` / `speech_final` behavior and utterance assembly guidance
- https://developers.deepgram.com/docs/multichannel-vs-diarization - diarization vs multichannel guidance for speaker grouping
- https://developers.deepgram.com/docs/utterances - current utterance feature semantics and interaction with diarization
- https://pypi.org/pypi/fastapi/json - current version `0.135.1`, uploaded 2026-03-01
- https://pypi.org/pypi/python-socketio/json - current version `5.16.1`, uploaded 2026-02-06
- https://pypi.org/pypi/motor/json - current version `3.7.1`, uploaded 2025-05-14
- https://pypi.org/pypi/deepgram-sdk/json - current version `6.0.1`, uploaded 2026-02-24
- https://pypi.org/pypi/pydantic/json - current version `2.12.5`, uploaded 2025-11-26
- https://pypi.org/pypi/pydantic-settings/json - current version `2.13.1`, uploaded 2026-02-19

### Secondary (MEDIUM confidence)
- Local code inspection:
  - `app/services/stt/session.py`
  - `app/services/stt/session_manager.py`
  - `app/infrastructure/deepgram/client.py`
  - `app/socket_gateway/server.py`
  - `app/services/meeting/session.py`
  - `app/services/meeting/session_manager.py`
  - `app/services/meeting/meeting_service.py`
  - `app/repo/meeting_record_repo.py`
  - `app/repo/interview_utterance_repo.py`
  - `app/api/deps.py`
  - `app/infrastructure/database/mongodb.py`

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing libraries are explicit in the repo and current package versions were verified against PyPI
- Architecture: MEDIUM - extension points are clear, but active-session REST semantics and SDK runtime pinning still need one implementation decision each
- Pitfalls: HIGH - most risks are directly visible in current code or documented by Deepgram

**Research date:** 2026-03-19
**Valid until:** 2026-03-26
