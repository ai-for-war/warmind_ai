# Roadmap: AI Service

## Overview

This roadmap takes the existing AI platform from brownfield speech infrastructure to a dedicated AI record meeting workflow. The sequence protects the product boundary first, then establishes transcript truth, then layers summary generation and structured meeting insights on top, and only after that adds durable meeting review/history flows.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Meeting Domain Foundation** - Create the dedicated AI record domain, session lifecycle, and language-aware meeting start/stop flow
- [x] **Phase 2: Live Transcript Capture** - Deliver stable transcript ingest, persistence, timestamps, and anonymous speaker grouping
- [ ] **Phase 3: Summary Foundation** - Add debounced batch summary generation during the meeting and finalize summary output at session end
- [ ] **Phase 4: Structured Meeting Insights** - Expand summaries into key points, decisions, action items, notes, and follow-up questions
- [ ] **Phase 5: Meeting History and Review** - Deliver meeting history/detail review on top of durable transcript and summary storage

## Phase Details

### Phase 1: Meeting Domain Foundation
**Goal**: Users can start and stop a dedicated AI record meeting session with explicit language selection, using meeting-specific contracts that are independent from interview flows.
**Depends on**: Nothing (first phase)
**Requirements**: [MEET-01, MEET-02, MEET-03]
**Success Criteria** (what must be TRUE):
  1. User can start a dedicated AI record session from the frontend without touching interview-specific roles or payloads.
  2. User can stop an active AI record session and the backend cleanly finalizes the meeting workflow.
  3. User can choose a supported transcription language such as `vi` or `en` when starting a meeting.
**Plans**: 2 plans

Plans:
- [x] 01-01: Define meeting-native models, schemas, repos, and event contracts
- [x] 01-02: Implement session lifecycle, auth/org scoping, and language-aware meeting start/stop flow

### Phase 2: Live Transcript Capture
**Goal**: Users can view and later review a full saved meeting transcript with timestamps and anonymous speaker grouping.
**Depends on**: Phase 1
**Requirements**: [TRNS-01, TRNS-02, TRNS-03, TRNS-04]
**Success Criteria** (what must be TRUE):
  1. User can see transcript text accumulate during an active meeting session.
  2. User can review the saved full transcript after the meeting ends.
  3. Transcript segments are grouped by anonymous speaker labels such as `speaker 1`, `speaker 2`.
  4. Saved transcript segments include timestamps suitable for later review.
**Plans**: 2 plans

Plans:
- [x] 02-01: Adapt live STT ingest to meeting transcript assembly with diarization and utterance closure
- [x] 02-02: Persist meeting utterances and expose transcript read paths for active and completed sessions

### Phase 3: Summary Foundation
**Goal**: Users receive a short batch-updated meeting summary during the session and a finalized summary when the meeting ends.
**Depends on**: Phase 2
**Requirements**: [SUMM-01, SUMM-07]
**Success Criteria** (what must be TRUE):
  1. User can see an in-progress short summary that updates in batches during a meeting.
  2. User can see a finalized summary after the meeting ends.
  3. Summary generation is driven by stable transcript batches rather than per-utterance AI calls.
**Plans**: 2 plans

Plans:
- [ ] 03-01: Build debounced summary triggering and queue/worker orchestration
- [ ] 03-02: Implement finalized and in-progress short-summary generation with dedicated summary storage

### Phase 4: Structured Meeting Insights
**Goal**: Users can review structured meeting outputs beyond the short summary, including decisions and follow-up work.
**Depends on**: Phase 3
**Requirements**: [SUMM-02, SUMM-03, SUMM-04, SUMM-05, SUMM-06]
**Success Criteria** (what must be TRUE):
  1. User can review key points extracted from the meeting transcript.
  2. User can review decisions and action items extracted from the meeting transcript.
  3. User can review notes and follow-up questions extracted from the meeting transcript.
**Plans**: 2 plans

Plans:
- [ ] 04-01: Design structured summary schema and prompt contract for meeting insights
- [ ] 04-02: Generate and persist key points, decisions, action items, notes, and follow-up questions

### Phase 5: Meeting History and Review
**Goal**: Users can reopen saved meetings through a history view and review transcript plus summary outputs safely.
**Depends on**: Phase 4
**Requirements**: [HIST-01, HIST-02]
**Success Criteria** (what must be TRUE):
  1. User can view a history list of saved meetings they are allowed to access.
  2. User can open a saved meeting and review its transcript and latest summary outputs.
  3. Meeting history and detail views respect existing authorization boundaries.
**Plans**: 2 plans

Plans:
- [ ] 05-01: Implement meeting history list and detail APIs on top of conversation and summary stores
- [ ] 05-02: Finalize review experience, pagination/access control, and persistence hardening

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Meeting Domain Foundation | 2/2 | Complete | 2026-03-19 |
| 2. Live Transcript Capture | 2/2 | Complete | 2026-03-20 |
| 3. Summary Foundation | 0/2 | Not started | - |
| 4. Structured Meeting Insights | 0/2 | Not started | - |
| 5. Meeting History and Review | 0/2 | Not started | - |
