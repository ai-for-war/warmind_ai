# Phase 02: Live Transcript Capture - Research

**Researched:** 2026-03-19
**Domain:** Meeting-native live transcript capture on top of Deepgram streaming transcription
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- During an active meeting, users should see transcript text live before the utterance is fully stabilized.
- When provider output is corrected by a later finalized transcript fragment, the current live text should be rewritten in place rather than appended as a correction trail.
- The live transcript should be shaped around transcript blocks. Each block can contain multiple finalized speaker segments plus one draft segment, and the next transcript content should begin a new block after a provider boundary closes the current one.
- Transcript storage and presentation should preserve chronological segment order, not collapse a whole block into one dominant speaker label.
- Anonymous speaker labels do not need to remain perfectly stable across an entire meeting session.
- The preferred visible label format is `speaker 1`, `speaker 2`, and so on.
- If diarization is unclear for a captured segment, the system should still retain that segment and use a fallback label such as `speaker unknown` rather than dropping transcript text.
- Saved transcript items should carry both segment or block start and end timestamps as appropriate for the read model.
- The canonical stored timing representation should be milliseconds from meeting start rather than preformatted display strings.
- Saved transcript review should be a chronological list of transcript items.
- Each saved transcript item should minimally include anonymous speaker label, transcript text, and timestamps.
- Read paths for completed transcripts should be paginated in Phase 2 rather than only returning the full transcript in one fetch.
- Paginated transcript review should default to oldest-first ordering.

### Claude's Discretion
- Exact socket payload shape for live transcript updates
- Exact fallback label string as long as it is anonymous and non-destructive
- Pagination style for completed transcript reads
- Whether persistence uses a dedicated meeting utterance collection or a meeting-native facade over a reusable lower-level primitive

### Deferred Ideas (OUT OF SCOPE)
- Summary generation and summary persistence
- Real identity mapping for speakers
- Meeting history list/detail UX beyond transcript read paths
- Locking frontend scroll behavior
</user_constraints>

<latest_official_docs>
## Latest Official Deepgram Findings

These points were checked directly against Deepgram official docs on 2026-03-19.

### 1. The current streaming transcription path for Nova is still `v1/listen`
- Deepgram docs home separates:
  - `Streaming: Conversational STT for voice agents (Flux)`
  - `Streaming: Transcription (Nova-3)`
- The official streaming transcription API reference for Nova is still the WebSocket endpoint `wss://api.deepgram.com/v1/listen`.
- The latest Python SDK README showcases `listen.v2.connect(...)` for Flux voice-agent streaming, but Nova-3 transcription docs remain on the `v1/listen` streaming reference.

**Planning implication:** do not migrate this meeting transcript phase to `listen.v2` unless the product is explicitly moving to Flux voice-agent semantics. The current repo `listen.v1.connect(...)` path is aligned with the official Nova transcription docs.

### 2. The documented streaming controls we can rely on are clear
The official Nova streaming docs explicitly document:
- `diarize`
- `interim_results`
- `endpointing`
- `utterance_end_ms`
- `vad_events`
- `Finalize`
- `CloseStream`
- `KeepAlive`

**Planning implication:** Phase 2 should be built around these documented controls, not around undocumented assumptions.

### 3. Diarization in live streaming returns word-level `speaker`, not `speaker_confidence`
- Deepgram diarization docs state that for live streaming audio, only `speaker` is returned.
- The streaming API reference also shows `speaker` attached to each word in `channel.alternatives[0].words[]`.

**Planning implication:** speaker grouping should derive from word-level `speaker` values accumulated across a stable utterance. Do not plan around `speaker_confidence` for live streaming.

### 4. `is_final` and `speech_final` mean different things
- Deepgram endpointing/interim docs state:
  - `is_final: false` = interim transcript, may change
  - `is_final: true` = finalized transcript segment
  - `speech_final: true` = pause-based endpoint detected
- Deepgram explicitly recommends concatenating finalized segments until `speech_final: true` when reconstructing a complete utterance.
- The interim-results docs also show that finalized segments can split and re-boundary speech in ways that do not match the latest interim text one-to-one.

**Planning implication:** the live UI should update one open transcript block in place, but the server must treat transcript truth as an accumulation of finalized segments, not a single final packet.

### 5. `UtteranceEnd` is useful, but it depends on `interim_results`
- The official Utterance End docs state that:
  - `utterance_end_ms` requires `interim_results=true`
  - using a value below `1000ms` offers no benefit because interim results are typically sent every second
- Deepgram end-of-speech guidance says `speech_final=true` and `UtteranceEnd` can be used together, and if both are enabled you may receive one after the other.

**Planning implication:** keep `interim_results=true` for meeting transcript capture, keep `utterance_end_ms >= 1000`, and treat `UtteranceEnd` as an utterance-closure aid rather than the only closure signal.

### 6. `Finalize` and `CloseStream` have different jobs
- Official Finalize docs:
  - `{"type":"Finalize"}` flushes unprocessed audio
  - may yield a response with `from_finalize: true`
  - is not guaranteed to emit that marker if there is not much buffered audio
- Official Close Stream docs:
  - `{"type":"CloseStream"}` instructs Deepgram to finish processing cached data, send responses and metadata, then terminate the socket

**Planning implication:** the safest stop flow for transcript truth is still:
1. send `Finalize`
2. drain final transcript responses
3. persist closed utterances
4. send `CloseStream`
5. wait for terminal metadata/close

### 7. KeepAlive has an important nuance
- Deepgram KeepAlive docs say to send `KeepAlive` every 3-5 seconds to prevent the 10-second inactivity timeout (`NET-0001`).
- The troubleshooting docs add a nuance: `KeepAlive` helps prevent timeouts, but you still need to have sent at least one audio frame; `KeepAlive` alone is not a full substitute for ever sending audio.
- The troubleshooting docs also warn that sending an empty binary frame like `b''` can cause unexpected closures.

**Planning implication:** the current meeting flow can keep its keepalive behavior during silence, but it must never send empty binary payloads and should assume the stream still needs genuine audio frames at least once.

### 8. Reconnects reset timestamps
- Deepgram reconnect guidance states that when a new connection is created, returned timestamps begin again from `00:00:00`, and callers need to maintain an offset if they want a continuous application timeline.

**Planning implication:** if Phase 2 later adds reconnect recovery, meeting-relative timestamps must be normalized in app code rather than trusting raw provider timestamps across connections.

### 9. The `utterances` feature exists in docs, but it is not the safest dependency for this phase
- Deepgram has a dedicated Utterances feature page and marks it available for streaming Nova.
- However, the `v1/listen` streaming API reference we verified for Nova explicitly documents `diarize`, `interim_results`, `endpointing`, `utterance_end_ms`, `vad_events`, and the control messages above, while `utterances` does not appear in that reference page.

**Inference from sources:** this may be a docs/reference gap rather than a feature gap, but for implementation accuracy Phase 2 should not depend on `utterances=true` as a required control. The documented and sufficient baseline is `interim_results + endpointing + utterance_end_ms + diarize`.
</latest_official_docs>

<research_summary>
## Summary

Phase 2 should stay on the current Deepgram Nova streaming path and adapt the existing repo around the official streaming controls that are clearly documented today. The repo already has the right raw building blocks:
- `DeepgramLiveClient` for `v1/listen`
- interview-side fragment assembly patterns in `app/services/stt/session.py`
- Socket.IO user-room delivery in `app/socket_gateway/server.py`
- durable meeting lifecycle storage in `app/repo/meeting_record_repo.py`

What is missing is the meeting-native transcript lane:
- a listener-driven meeting provider event loop
- meeting transcript socket updates keyed by a stable block id
- word-level speaker extraction from Deepgram diarization
- stable transcript block or segment persistence
- paginated transcript read APIs

**Primary recommendation:** implement meeting transcript capture around official Deepgram streaming primitives that are explicitly documented now: `interim_results`, `endpointing`, `utterance_end_ms`, `diarize`, `Finalize`, `CloseStream`, and `KeepAlive`. Do not make `utterances=true` a required assumption for Phase 2.
</research_summary>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Listener-driven provider event consumption
**What:** mirror the existing interview STT architecture where audio handlers only push bytes and a background listener drains provider events.

**Why it fits:** transcript truth depends on receiving post-finalize results before the session is closed.

### Pattern 2: Stable block id for live rewrite-in-place
**What:** open one server-side transcript block, emit repeated updates for that same `block_id`, and return the full current block snapshot on every update.

**Why it fits:** this matches the product requirement that live transcript text be rewritten in place while still allowing finalized content to accumulate within the current block.

### Pattern 3: Word-level diarization projected into finalized block segments
**What:** split finalized transcript fragments by word-level `speaker` changes, keep the resulting speaker-tagged segments in chronological order, and render `speaker {n+1}` or `speaker unknown` per segment.

**Why it fits:** official docs confirm live streaming only gives word-level `speaker`, so multi-speaker UI support must be application-derived from those word boundaries.

### Pattern 4: Durable-only persistence for finalized transcript segments
**What:** persist only finalized transcript content with `start_ms` / `end_ms`, not partial preview text.

**Why it fits:** official docs show interim text may change and finalized segments may split boundaries. Saved review should be stable, chronological, and clean.

### Pattern 5: HTTP review over durable data, socket updates over volatile data
**What:** keep active volatile preview on sockets and expose saved/active durable transcript pages via REST.

**Why it fits:** meeting sessions are process-local, but saved transcript review must survive reconnects and later support history screens.

### Anti-Patterns to Avoid
- Reusing interview channel roles or `conversation_id` as public meeting transcript fields
- Planning around live `speaker_confidence` for streaming diarization
- Treating a single `is_final:true` response as the whole utterance
- Calling `CloseStream` immediately without draining post-finalize results
- Sending empty binary audio packets
- Depending on `utterances=true` as a mandatory streaming control without runtime verification
</architecture_patterns>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Dropping the last words on stop
**What goes wrong:** the current Phase 1 meeting stop flow finalizes and closes too eagerly.
**Why it happens:** lifecycle-only code did not need transcript truth.
**How to avoid:** switch to finalize -> drain -> persist -> close.

### Pitfall 2: Misreading Deepgram flags
**What goes wrong:** `is_final` is treated as "utterance finished".
**Why it happens:** the names are easy to conflate.
**How to avoid:** treat `is_final` as finalized segment accuracy and `speech_final` / `UtteranceEnd` as closure signals.

### Pitfall 3: Incorrect speaker grouping
**What goes wrong:** the runtime collapses a whole block into one dominant speaker and loses speaker alternation inside the block.
**Why it happens:** live diarization is word-level.
**How to avoid:** keep finalized fragments split by speaker change and emit them as ordered segments within the same block.

### Pitfall 4: Over-relying on KeepAlive
**What goes wrong:** the app assumes KeepAlive alone is enough forever.
**Why it happens:** the keepalive page is easy to read without the troubleshooting nuance.
**How to avoid:** keep sending KeepAlive during silence, but still ensure the stream has carried real audio and never send empty binary frames.

### Pitfall 5: Planning against the wrong Deepgram API generation
**What goes wrong:** the team tries to migrate to `listen.v2` because it appears in the latest SDK README.
**Why it happens:** the README foregrounds Flux voice-agent streaming.
**How to avoid:** keep Nova-3 transcription on the official `v1/listen` path for this phase.
</common_pitfalls>

<validation_architecture>
## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` |
| Config file | add one if async test collection needs tightening |
| Quick run command | `pytest tests/unit -q` |
| Full suite command | `pytest -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-01 | live transcript block updates rewrite in place | integration | `pytest tests/integration/socket_gateway/test_meeting_record_socket.py -q` | planned |
| TRNS-02 | completed transcript is durably reviewable | integration | `pytest tests/integration/api/test_meeting_transcript_api.py -q` | planned |
| TRNS-03 | utterances carry anonymous speaker labels | unit | `pytest tests/unit/test_meeting_transcript_session.py -q` | planned |
| TRNS-04 | saved utterances persist `start_ms` and `end_ms` | unit | `pytest tests/unit/repo/test_meeting_transcript_repo.py -q` | planned |

### Wave 0 Gaps
- [ ] `tests/unit/test_meeting_transcript_session.py`
- [ ] `tests/unit/repo/test_meeting_transcript_repo.py`
- [ ] `tests/unit/services/test_meeting_transcript_service.py`
- [ ] `tests/integration/socket_gateway/test_meeting_record_socket.py`
- [ ] `tests/integration/api/test_meeting_transcript_api.py`

**Planning implication:** treat transcript test creation as first-class work. Cached `__pycache__` files are not proof of runnable source coverage.
</validation_architecture>

<open_questions>
## Open Questions

1. **Should active REST transcript reads include volatile preview text or only persisted closed utterances?**
   - Recommendation: durable-only for Phase 2; keep volatile preview socket-only.

2. **Should we normalize speaker labels by first-seen speaker id or by provider numeric id directly?**
   - Recommendation: persist both `speaker_key` and rendered `speaker_label`; render `speaker {n+1}` for UI, keep provider key internal even when one block contains multiple speakers.

3. **Do we want reconnect recovery in this phase?**
   - Recommendation: no. But if it is added later, timestamp offsetting must be handled in application code because Deepgram restarts timestamps from zero on a new connection.
</open_questions>

<sources>
## Sources

### Official Deepgram Docs
- Docs home: https://developers.deepgram.com/home
- Streaming transcription API reference (`v1/listen`): https://developers.deepgram.com/reference/speech-to-text/listen-streaming
- Diarization: https://developers.deepgram.com/docs/diarization
- Configure endpointing and interim results: https://developers.deepgram.com/docs/understand-endpointing-interim-results
- Utterance End: https://developers.deepgram.com/docs/utterance-end
- Using interim results: https://developers.deepgram.com/docs/using-interim-results
- Finalize: https://developers.deepgram.com/docs/finalize
- Close Stream: https://developers.deepgram.com/docs/close-stream
- KeepAlive: https://developers.deepgram.com/docs/audio-keep-alive
- Streaming troubleshooting: https://developers.deepgram.com/docs/stt-troubleshooting-websocket-data-and-net-errors
- Reconnect / timeout recovery: https://developers.deepgram.com/docs/recovering-from-connection-errors-and-timeouts-when-live-streaming-audio
- Streaming feature overview: https://developers.deepgram.com/docs/stt-streaming-feature-overview
- Utterances: https://developers.deepgram.com/docs/utterances
- Official Python SDK repo: https://github.com/deepgram/deepgram-python-sdk

### Local Code / Repo Context
- `app/infrastructure/deepgram/client.py`
- `app/services/stt/session.py`
- `app/services/stt/session_manager.py`
- `app/services/meeting/session.py`
- `app/services/meeting/session_manager.py`
- `app/services/meeting/meeting_service.py`
- `app/socket_gateway/server.py`
- `app/repo/meeting_record_repo.py`
- `.planning/phases/02-live-transcript-capture/02-CONTEXT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
</sources>

<metadata>
## Metadata

**Confidence breakdown:**
- Official streaming controls and semantics: HIGH
- Repo alignment with official Nova streaming path: HIGH
- `utterances=true` as a mandatory dependency: LOW, so excluded from the recommendation

**Research date:** 2026-03-19
**Docs checked:** 2026-03-19
**Valid until:** re-check before implementation if Deepgram changes the streaming reference or SDK examples
</metadata>
