## 1. Dependencies, configuration, and shared contracts

- [x] 1.1 Add the official Deepgram Python SDK dependency to `requirements.txt` and pin a tested version instead of leaving the integration on an unbounded latest release
- [x] 1.2 Add `DEEPGRAM_API_KEY`, `DEEPGRAM_MODEL`, `DEEPGRAM_ENDPOINTING_MS`, `DEEPGRAM_UTTERANCE_END_MS`, and `DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS` to `app/config/settings.py`
- [x] 1.3 Add an `STTEvents` group to `app/common/event_socket.py` for `stt:start`, `stt:audio`, `stt:finalize`, `stt:stop`, `stt:started`, `stt:partial`, `stt:final`, `stt:completed`, and `stt:error`
- [x] 1.4 Add STT-specific exception classes to `app/common/exceptions.py` for invalid stream state, unsupported audio format, active-stream conflict, provider connection failure, and stream ownership violations
- [x] 1.5 Register dependency factories in `app/common/service.py` for the Deepgram client wrapper and STT session manager/service

## 2. Socket payload schemas and normalized transcript contract

- [x] 2.1 Create `app/domain/schemas/stt.py` with request payload models for `stt:start`, `stt:audio` metadata, `stt:finalize`, and `stt:stop`
- [x] 2.2 Define validation rules in `stt.py` that enforce phase 1 audio format as `encoding=linear16`, `sample_rate=16000`, and `channels=1`
- [x] 2.3 Define outbound payload models for `stt:started`, `stt:partial`, `stt:final`, `stt:completed`, and `stt:error`
- [x] 2.4 Decide and encode the normalized `stt:final` payload shape, including whether `confidence`, `start_ms`, and `end_ms` are exposed in phase 1
- [x] 2.5 Keep the frontend-facing payloads provider-agnostic so Socket.IO consumers never depend on raw Deepgram event names or raw SDK response types

## 3. Deepgram SDK adapter using official Python SDK

- [x] 3.1 Create `app/infrastructure/deepgram/client.py` as the only module allowed to talk directly to `deepgram-sdk`
- [x] 3.2 Initialize the async SDK client using `AsyncDeepgramClient(api_key=...)`
- [x] 3.3 Implement live connection creation using the current Listen V1 async websocket path from official docs and Context7 (`client.listen.v1.connect(...)`)
- [x] 3.4 Register Deepgram SDK event handlers for at least open, message, close, and error events using the SDK event API
- [x] 3.5 Implement provider start/options wiring for `model=nova-3`, `encoding=linear16`, `sample_rate=16000`, `channels=1`, `interim_results=true`, `vad_events=true`, `endpointing=400`, `utterance_end_ms=1000`, and `language=<client or en>`
- [x] 3.6 Implement audio streaming to Deepgram using the current SDK media send path verified from docs (`send_media(...)` / equivalent tested method for the pinned SDK version)
- [x] 3.7 Implement provider control messages for keepalive and finalize using the current SDK control send path verified from docs (`send_control(KeepAlive/Finalize)` or the pinned-version equivalent)
- [x] 3.8 Normalize SDK responses into an internal provider event model that includes transcript partials, final fragments, speech-started, utterance-end, provider-finalize, close, and error signals
- [x] 3.9 Hide all SDK-specific classes such as `ListenV1SocketClientResponse`, `ListenV1MediaMessage`, and control message types inside the adapter boundary so service code depends only on internal dataclasses or methods
- [x] 3.10 Add explicit logging around provider open/close/error events without logging raw audio or full transcript contents

## 4. STT session state machine and transcript assembly

- [x] 4.1 Create `app/services/stt/session.py` with a stateful `STTSession` object that owns `sid`, `user_id`, `stream_id`, `organization_id`, `language`, provider connection, transcript buffers, and timestamps
- [x] 4.2 Implement an explicit state machine with at least `starting`, `streaming`, `finalizing`, `completed`, and `failed`
- [x] 4.3 Enforce `1 active stream per socket` at the session layer before any provider connection is opened
- [x] 4.4 Bind each stream to the originating socket and reject audio/control events from non-owning sockets
- [x] 4.5 Implement transcript assembly rules so `is_final=false` becomes `stt:partial`, while `speech_final=true` becomes `stt:final`
- [x] 4.6 Decide how to buffer and merge provider-final fragments that are `is_final=true` but not yet `speech_final=true`
- [x] 4.7 Use `UtteranceEnd` only as a secondary flush aid or idle marker, not as the primary commit trigger for transcript finalization
- [x] 4.8 Track last-audio and last-provider-activity timestamps for keepalive and stale-session cleanup
- [x] 4.9 Implement graceful finalize flow so session state does not transition to `completed` until provider final output has been flushed

## 5. Session manager, lifecycle ownership, and cleanup

- [x] 5.1 Create `app/services/stt/session_manager.py` keyed by socket ID, with exactly one active `STTSession` per socket
- [x] 5.2 Add APIs on the manager for `start_session`, `push_audio`, `finalize_session`, `stop_session`, and `handle_disconnect`
- [x] 5.3 Ensure `disconnect` always closes the Deepgram connection and removes the in-memory session
- [x] 5.4 Add bounded buffering and queue-guard behavior so backend memory cannot grow unbounded if frontend sends faster than the provider path can consume
- [x] 5.5 Add inactivity timeout handling for sessions that open but never receive enough audio, or receive audio and then stall without finalize/stop
- [x] 5.6 Decide whether inactivity timeout auto-finalizes first or hard-closes first, and encode that policy in the manager
- [x] 5.7 Keep the manager implementation process-local and document that horizontal scale requires sticky sessions for inbound socket affinity

## 6. Socket.IO server integration

- [x] 6.1 Register `stt:start`, `stt:audio`, `stt:finalize`, and `stt:stop` handlers in `app/socket_gateway/server.py`
- [x] 6.2 Load `user_id` from the saved Socket.IO session so STT ownership reuses the existing authenticated socket context
- [x] 6.3 Validate each inbound control event before handing it to the session manager, including active-session existence and stream ownership
- [x] 6.4 Accept binary audio payloads over the current Socket.IO connection without base64 encoding
- [x] 6.5 Emit normalized outbound STT events through the existing `gateway.emit_to_user(...)` pattern so the implementation remains consistent with chat/TTS
- [x] 6.6 Preserve additive `organization_id` enrichment on all outbound STT events when organization context is known
- [x] 6.7 Decide and implement how `organization_id` is resolved for STT events on the socket path if the current socket session stores only `user_id`

## 7. Deepgram behavior verification based on official docs

- [x] 7.1 Verify the pinned SDK version's exact async Listen V1 method names against official docs and code examples before final implementation, because current docs surface both `start_listening/send_media/send_control` and lower-level `start/send/keep_alive/finalize/finish` patterns
- [x] 7.2 Verify which event enum values and payload classes are actually emitted for Listen V1 transcript events in the pinned SDK version
- [x] 7.3 Verify how `speech_final`, `is_final`, `from_finalize`, and `UtteranceEnd.last_word_end` appear in real provider responses for `nova-3`
- [x] 7.4 Verify whether `language` values should be validated locally or passed through to Deepgram and surfaced as provider errors
- [x] 7.5 Verify official Deepgram guidance for keepalive interval and finalize timing for a raw PCM browser stream
- [x] 7.6 Verify recovery guidance for transient provider/network failures and explicitly decide what phase 1 will not support, especially around replay/resume and backlog recovery

## 8. Frontend-backend contract alignment for browser AudioWorklet input

- [x] 8.1 Write or update internal implementation notes for the expected browser contract: `AudioWorklet` produces PCM16 mono 16kHz frames and client emits them as binary Socket.IO messages
- [x] 8.2 Define the `stt:start` payload required from frontend, including `stream_id`, `language`, `encoding`, `sample_rate`, and `channels`
- [x] 8.3 Define the `stt:audio` metadata contract, including `stream_id`, `sequence`, and optional `timestamp_ms`
- [x] 8.4 Decide whether the backend requires monotonically increasing sequence numbers and how it reacts to missing or duplicate audio frames
- [x] 8.5 Document that phase 1 only supports `1 active stream / socket`, so frontend must stop/finalize before starting a new stream on the same connection

## 9. Observability, safety, and failure handling

- [ ] 9.1 Add structured logs for stream lifecycle transitions: start requested, provider connected, partial emitted, final emitted, finalize requested, completed, failed, and disconnected
- [ ] 9.2 Expose enough error metadata in `stt:error` for UI troubleshooting without leaking provider internals or sensitive transcript content
- [ ] 9.3 Avoid logging raw PCM bytes, raw provider payloads containing full transcript text, or provider auth details
- [ ] 9.4 Decide how to surface provider close-before-finalize cases to the UI so the frontend can distinguish clean completion from failure
- [ ] 9.5 Add defensive cleanup so partially opened provider sessions are closed if Socket.IO handler exceptions occur mid-start

## 10. Tests and implementation verification

- [ ] 10.1 Add unit tests for `stt:start` validation, especially unsupported encoding/sample-rate/channels and duplicate active-stream attempts
- [ ] 10.2 Add unit tests for transcript assembly logic covering interim updates, final fragments, `speech_final`, and `UtteranceEnd` behavior
- [ ] 10.3 Add unit tests for session manager lifecycle transitions across `start -> streaming -> finalize -> completed`, `start -> failed`, and disconnect cleanup
- [ ] 10.4 Add adapter tests or integration tests around the Deepgram wrapper using mocks/fakes so SDK event mapping is verified without requiring live provider calls in CI
- [ ] 10.5 Add socket integration tests ensuring binary `stt:audio` events are accepted and normalized transcript events are emitted to the correct `user:{user_id}` room
- [ ] 10.6 Manually verify the happy path with a browser AudioWorklet stream: connect -> start -> partials -> finals -> finalize -> completed
- [ ] 10.7 Manually verify edge cases: second `stt:start` on same socket, wrong stream ownership, disconnect during active stream, idle keepalive behavior, and provider-side error propagation
- [ ] 10.8 Manually verify two independent browser clients can transcribe simultaneously without transcript cross-talk
