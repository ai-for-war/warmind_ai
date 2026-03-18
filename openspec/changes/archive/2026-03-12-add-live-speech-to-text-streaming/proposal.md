## Why

The platform already supports real-time Socket.IO delivery and audio-oriented AI workflows, but it cannot yet transcribe a user's live speech from the browser microphone into partial and final text updates. The product needs a low-latency speech-to-text path that fits the current FastAPI + Socket.IO architecture, keeps provider credentials on the backend, and gives the frontend stable streaming transcript updates without introducing a second realtime transport.

## What Changes

- Add a new live speech-to-text streaming capability that accepts browser microphone audio over the existing authenticated Socket.IO connection
- Standardize phase 1 browser audio input on `AudioWorklet` output encoded as `PCM16`, `mono`, `16kHz`, with frontend frames in the `20-40ms` range
- Reuse the current Socket.IO server to manage per-socket STT sessions, enforce `1 active stream per socket`, and forward audio to Deepgram live transcription
- Stream Deepgram partial and final transcript events back to the same authenticated user channel for immediate UI rendering
- Introduce an internal Deepgram live client plus STT session manager/service layer to own stream lifecycle, transcript assembly, finalization, keepalive, and cleanup
- Add additive socket event contracts for STT lifecycle events such as `started`, `partial`, `final`, `completed`, and `error`
- Allow the client to pass `language` per stream, with backend defaulting to `en` when omitted
- Keep phase 1 focused on UI transcript delivery only, without downstream agent orchestration, transcript persistence, diarization, or multi-speaker analysis

## Capabilities

### New Capabilities
- `live-speech-transcription`: Start, stream, finalize, and stop authenticated live browser speech transcription with realtime partial and final transcript events delivered over Socket.IO

### Modified Capabilities
- None

## Impact

- **New realtime contract**: additive Socket.IO inbound events for `stt:start`, `stt:audio`, `stt:finalize`, and `stt:stop`, plus outbound events for `stt:started`, `stt:partial`, `stt:final`, `stt:completed`, and `stt:error`
- **New backend stateful path**: per-socket STT session management layered on top of the existing `python-socketio` server
- **New infrastructure client**: Deepgram live transcription websocket wrapper for streaming raw PCM audio and receiving transcript events
- **New configuration**: Deepgram API key and live transcription defaults such as model, endpointing, utterance end timing, and keepalive behavior
- **Affected code**: `app/socket_gateway/`, `app/common/event_socket.py`, `app/config/settings.py`, `app/domain/schemas/`, `app/services/`, `app/infrastructure/`, and dependency/config wiring in common factory modules
- **Operational constraint**: stream affinity remains tied to the app instance handling the socket connection, so future horizontal scaling will require sticky sessions or a dedicated stateful STT session layer
- **Non-goals for phase 1**: transcript storage, downstream workflow triggering, speaker diarization, provider failover, and concurrent multiple active streams on the same socket
