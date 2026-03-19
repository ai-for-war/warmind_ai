# AI Service

## What This Is

AI Service is an internal modular AI backend built around FastAPI, LangGraph, Socket.IO, MongoDB, and Redis. It already supports authenticated multi-tenant APIs, AI chat/orchestration, media generation, speech features, analytics, and Google Sheets ingestion, and the next major capability is a dedicated AI record flow for meetings.

The AI record flow is not an extension of the interview assistant domain. It is a separate meeting-oriented workflow that can reuse shared STT, socket, queue, and LLM infrastructure where useful, while keeping its own conversation semantics, persistence model, prompts, and summary pipeline so the feature can evolve independently.

## Core Value

Internal teams can stream meeting audio to the service and get a durable transcript plus usable meeting notes without spending time rewriting manual notes afterward.

## Requirements

### Validated

- [x] Users can authenticate, manage user accounts, and operate within organization-scoped API flows - existing
- [x] Internal users can run AI chat and orchestration flows backed by LangGraph/LangChain - existing
- [x] The platform can handle live speech processing over Socket.IO with Deepgram-backed STT session management - existing
- [x] The platform can persist conversation-oriented records and utterance-style data in MongoDB - existing
- [x] The platform can run asynchronous/background processing with Redis queues and worker processes - existing
- [x] The platform can manage voice, text-to-speech, image upload/generation, and related media workflows - existing
- [x] The platform can ingest and analyze Google Sheets-backed data sources for internal workflows - existing

### Active

- [ ] Internal users can start and stop a dedicated AI record meeting session from the frontend by streaming live meeting audio to the backend
- [ ] AI record sessions store the meeting as its own conversation flow, separate from interview-specific models and behaviors
- [ ] The system durably stores full meeting transcripts as utterance/message history for later retrieval
- [ ] The system generates batch-based meeting summaries during an active session instead of invoking AI on every utterance
- [ ] AI record summaries capture short summaries, key points, decisions, action items, notes, and follow-up questions
- [ ] The system stores meeting summaries in a dedicated summary collection linked to the meeting conversation
- [ ] The transcript can label anonymous participants as speaker-style identifiers (for example `speaker 1`, `speaker 2`) without requiring real-name mapping
- [ ] The frontend/client can select supported meeting language values such as `vi` or `en` for transcription

### Out of Scope

- Direct Google Meet bot or platform integration in v1 - frontend-streamed audio is sufficient for the first release
- Real-time AI output for every finalized utterance - batch summarization is preferred to reduce cost/noise and keep the flow practical
- Mapping diarized speakers to real participant identities in v1 - anonymous speaker labels are enough for the first release
- Coupling AI record to the interview domain model - this would slow future development and blur separate product semantics
- Export/sharing workflows for meeting outputs in v1 - first priority is accurate storage and usable in-product review

## Context

This repository is already a brownfield codebase with a documented architecture map under `.planning/codebase/`. The current backend is a layered modular monolith: FastAPI routes feed service objects, services coordinate repositories and infrastructure adapters, LangGraph/LangChain handle AI orchestration, Socket.IO handles realtime delivery, and Redis-backed workers process asynchronous tasks.

The existing speech path is optimized for interview-specific multichannel STT with fixed interviewer/user semantics. That makes it a useful technical reference but the wrong product boundary for meeting recording. AI record should instead be modeled as its own meeting workflow with separate repositories, prompts, storage, and summarization rules, while selectively reusing common infrastructure such as Deepgram live transcription, socket transport, queueing, and LLM invocation patterns.

The user pain is straightforward: internal teams lose time rewriting notes after meetings. The new feature should therefore prioritize durable transcript capture and structured summaries that reduce post-meeting manual work. During the meeting, the system may update summaries in batches; it does not need per-utterance copilot behavior.

Deepgram capabilities are a strong fit for this direction. The latest official docs support `diarize=true` for speaker diarization, `utterances=true` for semantically grouped speech units, and `utterance_end_ms` for gap detection in streaming transcription. That supports anonymous `speaker N` labeling and batch-oriented summarization without requiring fixed two-channel speaker roles.

## Constraints

- **Product boundary**: AI record must be a separate meeting domain, not a thin wrapper over interview flows - this keeps the feature easier to develop and maintain
- **Input model**: v1 audio comes from frontend streaming, not direct meeting-platform integration - this reduces implementation surface and external dependencies
- **User model**: Initial users are internal teams - multi-tenant/auth patterns should still be respected, but UX complexity can stay pragmatic
- **Storage**: Full transcript history and summary history must persist durably - the output cannot be ephemeral because review after the meeting is core value
- **Speaker handling**: Real identity mapping is not required in v1 - diarized anonymous speakers are acceptable
- **Language selection**: Client chooses supported transcription language values such as `vi` or `en` - the backend should not assume one fixed meeting language
- **Processing strategy**: Summary generation should be batch-oriented during the meeting - avoid forcing an LLM call on every utterance
- **Technical environment**: The implementation must fit the current FastAPI + MongoDB + Redis + Socket.IO + Deepgram stack - avoid introducing a parallel architecture without clear need

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Model AI record as a separate meeting workflow | Interview semantics are too specialized and would create accidental coupling | Pending |
| Use frontend-streamed audio for v1 | Fastest path to value without Meet bot/integration complexity | Pending |
| Persist transcripts as meeting conversation messages/utterances | Conversation-style storage matches the way the user wants to view meetings | Pending |
| Store summaries in a dedicated collection | Summary lifecycle differs from transcript lifecycle and should evolve independently | Pending |
| Use batch summarization during live meetings | Reduces noise/cost and better matches note-taking use case | Pending |
| Allow anonymous diarized speakers instead of identity mapping | `speaker 1`, `speaker 2` is good enough for v1 and lowers complexity | Pending |
| Let the client declare transcription language | The service should support meetings in different languages without hardcoding one default | Pending |

---
*Last updated: 2026-03-19 after initialization*
