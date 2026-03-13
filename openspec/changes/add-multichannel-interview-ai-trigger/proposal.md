## Why

The current live speech-to-text capability is designed for a single mono
browser microphone stream whose main output is partial and final transcript
updates for UI rendering. That shape is not sufficient for the interview
assistant workflow now being targeted.

The new workflow must capture two independent microphones in the same browser
session, preserve speaker identity, keep the UI responsive with preview text,
wait until the interviewer has actually finished a turn before invoking AI, and
avoid persisting unstable partial transcripts. The system also needs a fast
context path for AI responses without making MongoDB part of the realtime
critical path.

## What Changes

- Extend the live speech transcription flow from single-channel mono STT to a
  multichannel browser audio contract where channel identity is mapped
  explicitly to `interviewer` and `user`
- Reuse one authenticated realtime session per conversation while forwarding
  multichannel audio to Deepgram live transcription and normalizing provider
  transcript events back into speaker-aware application events
- Keep UI preview behavior for non-final transcript updates, but store unstable
  transcript state only in process memory rather than Redis or MongoDB
- Define utterance stability around Deepgram transcript finalization plus
  `utterance_end` with an additional `800ms` grace window before a turn is
  considered closed
- Persist only stable utterances, first into Redis for fast context access and
  then asynchronously into MongoDB for durable history
- Trigger AI only after a stable interviewer utterance is closed and already
  available in Redis, using a recent multi-speaker conversation window as
  context
- Keep phase 1 output text-only: the AI response is returned as text and the
  system does not add synthesized speech or downstream non-text orchestration

## Capabilities

### New Capabilities
- `interview-multichannel-ai-trigger`: Capture two-microphone interview audio,
  derive stable speaker-aware utterances, persist stable context, and trigger
  text-only AI responses only after interviewer turn closure

### Modified Capabilities
- `live-speech-transcription`: Evolve the existing capability from
  single-channel transcript streaming toward multichannel, speaker-aware
  interview support with turn-close semantics

## Impact

- **New browser audio contract**: frontend must capture two microphones,
  multiplex them into one multichannel PCM stream, and declare the channel map
  at stream start
- **Updated realtime contract**: outbound preview events remain additive for UI,
  while stable utterance and AI-trigger behavior become conversation-aware and
  speaker-aware
- **New turn-close policy**: `speech_final` and other provider-final transcript
  signals stabilize transcript segments, but AI invocation waits for
  `utterance_end` plus an `800ms` grace period with no new speech on the
  interviewer channel
- **New persistence split**: process memory holds unstable/open utterances,
  Redis stores only stable recent utterances for low-latency context reads, and
  MongoDB stores stable utterances asynchronously for durable history
- **New context path**: AI requests are built from a recent interviewer+user
  utterance window retrieved from Redis rather than from partial transcript
  buffers or full long-history prompt replay
- **Affected code**: `app/socket_gateway/`, `app/services/stt/`,
  `app/infrastructure/deepgram/`, `app/domain/schemas/`, Redis-backed context
  services, conversation/utterance persistence, and the AI invocation layer
- **Operational note**: multichannel interview state remains tied to the app
  instance that owns the socket session, so horizontal scale still requires
  affinity unless session state is externalized later
