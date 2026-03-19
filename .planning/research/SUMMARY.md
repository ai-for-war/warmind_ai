# Project Research Summary

**Project:** AI Service
**Domain:** internal AI meeting recording and note generation
**Researched:** 2026-03-19
**Confidence:** HIGH

## Executive Summary

This is a meeting recording and AI note-generation product inside an existing FastAPI-based internal AI platform. The right approach is not to extend the interview assistant domain, but to build a meeting-specific workflow that reuses the current realtime, provider, queue, and auth infrastructure while keeping its own storage, summary logic, and API contracts.

Research points strongly toward a transcript-first architecture. Official Deepgram docs support live diarization, utterance grouping, and streaming gap detection, which makes anonymous speaker-separated transcripts practical without relying on fixed interviewer/user roles. Market signals from Otter, Fireflies, and Notta also show that users expect transcript, summary, decisions, and action items to be first-class outputs rather than optional extras.

The main risk is accidental coupling: if the team reuses interview schemas or summarizes every utterance, the feature will become noisy, expensive, and hard to evolve. The mitigation is to define a separate meeting domain, persist stable transcript utterances as the source of truth, and generate structured summary snapshots in debounced batches.

## Key Findings

### Recommended Stack

The best stack is mostly the one already in the repo: FastAPI, Socket.IO, MongoDB, Redis, and the existing LLM abstraction, with Deepgram as the live STT provider. The important change is architectural, not infrastructural: use Deepgram diarization plus utterance grouping for one mixed meeting stream, and keep summary generation inside the application domain rather than delegating the product contract to provider-native summarization.

**Core technologies:**
- FastAPI 0.135.1: control plane and read APIs inside the existing modular monolith
- python-socketio 5.16.1: live meeting stream transport and frontend updates
- Deepgram streaming STT: diarization, utterances, punctuation, and gap detection for meeting transcript assembly
- MongoDB + Motor/PyMongo: durable meeting conversations, utterances, and summary snapshots
- Redis 7.2.1: debounced summary jobs and realtime backplane
- OpenAI via the existing abstraction: structured meeting summaries, decisions, action items, and follow-up extraction

### Expected Features

Research indicates that transcript, speaker-separated readability, summary, and action items are baseline expectations. The strongest market pattern is that users do not want to re-read the whole transcript to recover decisions or next steps.

**Must have (table stakes):**
- Full transcript with timestamps
- Speaker-separated transcript view
- Summary with decisions and action items
- Ongoing meeting capture from the start of the meeting
- Durable meeting history/detail review
- Language selection or a clear language policy

**Should have (competitive):**
- Batch-updated "summary so far" during the meeting
- Meeting-native summary snapshots with clear transcript lineage

**Defer (v2+):**
- Meeting bot/platform integrations
- Real speaker identity mapping
- Automatic downstream task/CRM sync

### Architecture Approach

The recommended architecture is a meeting-specific domain on top of shared platform infrastructure. The live path should convert stable transcript chunks into persisted meeting utterances, then hand off debounced summary work to a background worker that updates a dedicated meeting summary collection. This separates the immutable transcript log from the derived summary projection and keeps the live socket path lightweight.

**Major components:**
1. Meeting socket/API boundary - start/stop streaming and load meeting detail/history
2. Meeting session manager - own live transcript batching and provider interaction
3. Meeting repositories - store conversations, utterances, and summaries separately from interview data
4. Summary queue/worker - generate structured summaries outside the live STT loop
5. Read model/UI contract - expose transcript plus summary in a conversation-style meeting view

### Critical Pitfalls

1. **Interview-domain reuse** - avoid by creating meeting-native models and repos from phase 1
2. **Diarization treated as real identity** - avoid by keeping anonymous `speaker N` labels in v1
3. **Per-utterance summarization** - avoid with debounced batch summary jobs
4. **Summary without transcript lineage** - avoid by storing transcript as source of truth and linking summary snapshots to transcript state
5. **Language misconfiguration** - avoid with explicit language selection and a documented multilingual policy

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Meeting Domain Foundation
**Rationale:** Product boundaries have to be correct before any transcript or summary code starts accumulating.
**Delivers:** Meeting-specific models, schemas, event names, and repositories.
**Addresses:** Separate AI record from interview semantics.
**Avoids:** Interview-domain coupling and speaker-role lock-in.

### Phase 2: Live Transcript Capture and Persistence
**Rationale:** Summary quality depends on stable transcript data, so the source-of-truth log comes before AI note generation.
**Delivers:** FE stream ingest, Deepgram diarization path, stable meeting utterance persistence, and meeting detail retrieval.
**Uses:** Deepgram diarization/utterances plus Mongo persistence.
**Implements:** Meeting session manager and transcript log architecture.

### Phase 3: Batch Summary Pipeline
**Rationale:** Once transcript data is trustworthy, batch summarization can generate the product's core value.
**Delivers:** Structured summary generation, decisions/action items extraction, summary collection, and summary snapshots.
**Uses:** Redis queue plus LLM prompt pipeline.
**Implements:** Debounced summary orchestration and summary projection storage.

### Phase 4: Review Experience and Operational Hardening
**Rationale:** The feature is only useful if users can reopen meetings, trust access control, and review notes efficiently.
**Delivers:** Meeting detail/history APIs, summary/transcript review shape, retention/access-control hardening, and language-policy polish.
**Uses:** Existing auth/org boundaries and read-model pagination.
**Implements:** Durable review experience and production-readiness safeguards.

### Phase Ordering Rationale

- Transcript capture comes before AI note generation because summaries need a trustworthy source of truth.
- Domain separation comes before both because the wrong schema boundary becomes expensive immediately.
- Review/history comes after persistence and summary projection because it depends on both durable stores being in place.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Deepgram event-shape adaptation for meeting-specific speaker segmentation and transcript assembly
- **Phase 3:** Prompt design and snapshot strategy for decisions/action items/follow-up extraction

Phases with standard patterns (skip research-phase):
- **Phase 1:** Meeting-native domain modeling inside the existing FastAPI modular monolith
- **Phase 4:** Standard access-control and pagination patterns inside the current backend

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Backed by current codebase plus official Deepgram docs |
| Features | HIGH | Strong alignment between user pain and official product pages from meeting-note tools |
| Architecture | HIGH | Mostly an application-boundary decision inside an already mapped codebase |
| Pitfalls | HIGH | Driven by the user's constraints plus official provider behavior |

**Overall confidence:** HIGH

### Gaps to Address

- Mixed-language live meetings: decide whether v1 is explicit-language-only or needs multilingual model behavior during planning
- Summary snapshot policy: decide whether to store only latest + snapshots or every batch version during planning

## Sources

### Primary (HIGH confidence)
- `.planning/codebase/ARCHITECTURE.md` - current system boundaries
- `.planning/codebase/STACK.md` - current stack versions
- https://developers.deepgram.com/docs/diarization - live speaker labeling
- https://developers.deepgram.com/docs/utterances - utterance grouping
- https://developers.deepgram.com/docs/utterance-end - streaming batch timing
- https://developers.deepgram.com/docs/multichannel-vs-diarization - audio-shape decision guidance
- https://developers.deepgram.com/docs/language - language parameter behavior
- https://developers.deepgram.com/docs/summarization - provider-native summary limits

### Secondary (MEDIUM confidence)
- https://otter.ai/ - market baseline for transcript, summary, decisions, and history
- https://help.otter.ai/hc/en-us/articles/5093228433687-Conversation-Page-Overview - summary + transcript detail-view pattern
- https://fireflies.ai/product/real-time - live notes/action-items expectations
- https://guide.fireflies.ai/articles/5965172749-live-assist-on-fireflies-mobile-app-get-real-time-notes-live-during-meetings - "summary so far" and live recap patterns
- https://www.notta.ai/en/ - multilingual and summary expectations
- https://www.notta.ai/en/features/meeting-recording-software - storage/review expectations

### Tertiary (LOW confidence)
- None

---
*Research completed: 2026-03-19*
*Ready for roadmap: yes*
