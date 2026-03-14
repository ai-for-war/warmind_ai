## 1. Contracts, configuration, and shared event definitions

- [x] 1.1 Extend `app/config/settings.py` with multichannel interview STT settings for `channels=2`, `multichannel=true`, `endpointing`, `utterance_end_ms`, `keepalive interval`, and interviewer turn-close grace timing
- [x] 1.2 Update `app/common/event_socket.py` with additive interview-specific events for stable utterance closure and text answer delivery while preserving existing STT event names for preview/final/completed/error
- [x] 1.3 Add or update exception types in `app/common/exceptions.py` for invalid channel mapping, invalid interview conversation state, Redis context write failure, async utterance persistence failure, and AI trigger failure
- [x] 1.4 Register repository and service factories in `app/common/service.py` and `app/common/repo.py` for interview session management, Redis context storage, conversation persistence, utterance persistence, and answer generation services

## 2. Multichannel socket payload schemas and normalized event models

- [x] 2.1 Update `app/domain/schemas/stt.py` so `stt:start` requires `conversation_id`, `channels=2`, and a valid `channel_map` for `interviewer` and `user`
- [x] 2.2 Update audio metadata schemas so multichannel `stt:audio` frames keep existing sequence/timestamp fields while validating the new interview stream contract
- [x] 2.3 Extend outbound STT payload schemas so `stt:partial` and `stt:final` remain speaker-aware with channel/source attribution
- [x] 2.4 Add a normalized `stt:utterance_closed` payload schema containing `conversation_id`, `utterance_id`, `source`, `channel`, `text`, `started_at`, `ended_at`, and `turn_closed_at`
- [x] 2.5 Add a text-only interview answer payload schema for AI responses emitted after interviewer turn closure

## 3. Conversation and utterance persistence models

- [x] 3.1 Create or update domain models for `conversation` and `utterance` with explicit `channel_map`, `source`, `channel`, `text`, `status`, `started_at`, `ended_at`, and `turn_closed_at`
- [x] 3.2 Create repositories for conversations and utterances with methods to create conversation records, append stable utterances, and query recent durable utterances for fallback recovery
- [x] 3.3 Add MongoDB indexes needed for conversation lookup and utterance timeline retrieval by `conversation_id`, `created_at`, and `turn_closed_at`
- [x] 3.4 Decide and encode durable status values so only closed stable utterances are stored in MongoDB and open/preview states remain excluded

## 4. Deepgram adapter upgrade for multichannel Listen V1

- [ ] 4.1 Update `app/infrastructure/deepgram/client.py` to open Listen V1 with `channels=2`, `multichannel=true`, `interim_results=true`, `endpointing`, and `utterance_end_ms`
- [ ] 4.2 Verify the pinned Deepgram SDK async usage against current docs and code by using `AsyncDeepgramClient`, `listen.v1.connect`, `start_listening`, `send_media`, and control messages for `KeepAlive` and `Finalize`
- [ ] 4.3 Extend provider event normalization to preserve `channel_index` on partial transcript, final transcript, `SpeechStarted`, `UtteranceEnd`, and finalize-related events
- [ ] 4.4 Implement structured provider logging that captures channel, finality flags, close codes, and provider request metadata without logging raw transcript bodies or audio bytes
- [ ] 4.5 Add a clean separation between provider `Finalize` and `CloseStream` behaviors so the application can flush remaining transcript without tearing down the session prematurely

## 5. In-memory interview session state machine

- [ ] 5.1 Replace the single-stream transcript assembly flow with a conversation-scoped interview session object that owns one Deepgram connection and per-channel open utterance state
- [ ] 5.2 Track open utterances separately for channel `0` and channel `1`, including stable segment buffers, preview text, timestamps, and pending turn-close timers
- [ ] 5.3 Implement preview behavior so `is_final=false` updates emit UI preview events immediately without writing preview state to Redis or MongoDB
- [ ] 5.4 Implement stable segment merge rules so `is_final=true` and `speech_final=true` contribute to the open utterance for the correct channel without closing the turn yet
- [ ] 5.5 Implement turn-close detection so `UtteranceEnd` starts an `800ms` grace timer and any new `SpeechStarted` or transcript activity on that same channel cancels the pending close
- [ ] 5.6 Emit a stable utterance-closed event only when the grace timer expires with no new speech activity for that channel
- [ ] 5.7 Preserve one active interview STT session per socket while supporting both channels inside that session

## 6. Redis stable-context storage

- [ ] 6.1 Create a Redis-backed context store service that writes only closed stable utterances to a recent ordered utterance window per conversation
- [ ] 6.2 Define the Redis value shape for a stable utterance so it includes `utterance_id`, `conversation_id`, `source`, `channel`, `text`, and turn timing fields
- [ ] 6.3 Implement timeline-ordered append and bounded trimming of recent utterances so AI context reads stay fast and bounded
- [ ] 6.4 Store stable conversation metadata such as `channel_map` in Redis when the interview session starts or when the first stable utterance is persisted
- [ ] 6.5 Add fallback behavior so Redis read failures surface clearly and do not silently corrupt AI context assembly

## 7. Async MongoDB persistence for stable utterances

- [ ] 7.1 Implement an asynchronous persistence path that writes a closed stable utterance to MongoDB after Redis write succeeds
- [ ] 7.2 Ensure interviewer and user utterances both persist through the same async path, with no special-case skip for user utterances
- [ ] 7.3 Add retry/backfill handling or explicit failure reporting for MongoDB persistence failures that occur after Redis already contains the stable utterance
- [ ] 7.4 Ensure MongoDB persistence is not on the critical path for interviewer AI trigger latency

## 8. Interview AI trigger and context builder

- [ ] 8.1 Create an interview answer service that triggers only when a closed stable utterance belongs to `interviewer`
- [ ] 8.2 Implement a Redis-first context builder that loads a bounded recent window of stable interviewer and user utterances in timeline order
- [ ] 8.3 Ensure the just-closed interviewer utterance is always included in the AI context window used for answer generation
- [ ] 8.4 Exclude prior AI answers from the phase 1 context assembly path
- [ ] 8.5 Emit a text-only answer event back to the frontend after successful AI generation
- [ ] 8.6 Handle AI provider/service failures without breaking the live interview session or losing the already-closed stable utterance

## 9. Socket.IO server integration

- [ ] 9.1 Update `app/socket_gateway/server.py` so `stt:start` accepts the multichannel interview contract and creates a conversation-scoped session
- [ ] 9.2 Update `stt:audio` handling so binary multichannel audio frames are validated and forwarded without changing the authenticated Socket.IO transport model
- [ ] 9.3 Update session event emission so `stt:partial`, `stt:final`, and `stt:utterance_closed` include speaker-aware channel/source context
- [ ] 9.4 Keep organization-aware payload enrichment on all interview STT and AI answer events
- [ ] 9.5 Ensure disconnect, explicit stop, and explicit finalize clean up the provider session, cancel pending close timers, and remove process-local open utterance state
- [ ] 9.6 Add keepalive scheduling in the session listener loop so `KeepAlive` is sent every `3-5s` during silence while the interview session remains active

## 10. Access control, recovery, and operational safety

- [ ] 10.1 Reuse authenticated socket ownership checks so only the owning socket can stream audio or control the active interview session
- [ ] 10.2 Validate that invalid or conflicting `channel_map` input cannot start a session and cannot remap speaker roles mid-stream
- [ ] 10.3 Ensure premature provider close, timeout, or reconnect failure transitions the session into a clear error state without persisting unstable partial transcript state
- [ ] 10.4 Document and encode sticky-session assumptions so multichannel interview state is not expected to survive cross-instance rebalance
- [ ] 10.5 Ensure Deepgram `Finalize` is used only for explicit session flush behavior and not as a substitute for normal utterance turn closure

## 11. Verification and implementation readiness

- [ ] 11.1 Add schema tests for multichannel `stt:start` validation, including `channels=2`, valid `channel_map`, and rejection of missing or duplicate speaker-role mappings
- [ ] 11.2 Add adapter tests for multichannel Deepgram event normalization, especially preservation of `channel_index`, `speech_final`, `UtteranceEnd`, and `SpeechStarted`
- [ ] 11.3 Add session tests for preview emission, stable segment merge, grace-timer cancellation, and stable utterance closure after `UtteranceEnd + 800ms`
- [ ] 11.4 Add Redis context-store tests to verify only closed stable utterances are written and preview/partial transcript state is never stored
- [ ] 11.5 Add async persistence tests to verify closed interviewer and user utterances are both written to MongoDB after Redis success
- [ ] 11.6 Add AI trigger tests to verify only interviewer utterance closure triggers answer generation and that the context window includes both interviewer and user turns
- [ ] 11.7 Add socket integration tests for the end-to-end flow: start multichannel session -> preview events -> final segment events -> utterance closed -> Redis write -> interviewer answer event
- [ ] 11.8 Run manual verification with real or simulated two-mic browser audio for interviewer and user channels, including silence gaps, resumed speech before `800ms`, explicit finalize, stop, and disconnect handling
