# Requirements: AI Service

**Defined:** 2026-03-19
**Core Value:** Internal teams can stream meeting audio to the service and get a durable transcript plus usable meeting notes without spending time rewriting manual notes afterward.

## v1 Requirements

### Meetings

- [ ] **MEET-01**: User can start a dedicated AI record meeting session from the frontend when a meeting begins
- [ ] **MEET-02**: User can stop an active AI record meeting session at any time and receive finalized meeting outputs
- [ ] **MEET-03**: User can choose a supported transcription language such as `vi` or `en` before or when starting the meeting session

### Transcript

- [ ] **TRNS-01**: User can view transcript text accumulating during an active meeting session
- [ ] **TRNS-02**: User can review the full saved transcript after the meeting ends
- [ ] **TRNS-03**: User can see transcript segments grouped by anonymous speaker labels such as `speaker 1` and `speaker 2`
- [ ] **TRNS-04**: User can see timestamps for saved transcript segments when reviewing a meeting

### Summaries

- [ ] **SUMM-01**: User can see an in-progress short meeting summary that updates in batches during an active meeting
- [ ] **SUMM-02**: User can review key points extracted from the meeting transcript
- [ ] **SUMM-03**: User can review decisions extracted from the meeting transcript
- [ ] **SUMM-04**: User can review action items extracted from the meeting transcript
- [ ] **SUMM-05**: User can review meeting notes extracted from the meeting transcript
- [ ] **SUMM-06**: User can review follow-up questions extracted from the meeting transcript
- [ ] **SUMM-07**: User can review the finalized summary after the meeting ends

### History

- [ ] **HIST-01**: User can view a history list of saved meetings they are allowed to access
- [ ] **HIST-02**: User can open a saved meeting and review its transcript and latest summary outputs

## v2 Requirements

### Search and Recall

- **QARY-01**: User can search across past meeting transcripts and summaries
- **QARY-02**: User can ask follow-up questions against a stored meeting transcript

### Integrations

- **INTG-01**: User can create meeting records from direct Google Meet or other meeting-platform integrations
- **INTG-02**: User can sync meeting outputs to downstream task or project systems

### Identity and Sharing

- **IDEN-01**: User can map diarized speakers to real participant identities
- **SHAR-01**: User can export or share meeting transcript and summary outputs

## Out of Scope

| Feature | Reason |
|---------|--------|
| Direct Google Meet bot/platform integration in v1 | FE-streamed audio is the chosen first release path |
| Real participant identity mapping in v1 | Anonymous diarized speakers are enough for the first release |
| Per-utterance AI summary updates | Batch summarization is the chosen quality/cost tradeoff |
| Export/share workflows in v1 | Core value is transcript + summary capture and review first |
| Search/QA over historical meetings in v1 | Useful, but not required to validate the first release |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MEET-01 | Phase 1 | Pending |
| MEET-02 | Phase 1 | Pending |
| MEET-03 | Phase 1 | Pending |
| TRNS-01 | Phase 2 | Pending |
| TRNS-02 | Phase 2 | Pending |
| TRNS-03 | Phase 2 | Pending |
| TRNS-04 | Phase 2 | Pending |
| SUMM-01 | Phase 3 | Pending |
| SUMM-02 | Phase 4 | Pending |
| SUMM-03 | Phase 4 | Pending |
| SUMM-04 | Phase 4 | Pending |
| SUMM-05 | Phase 4 | Pending |
| SUMM-06 | Phase 4 | Pending |
| SUMM-07 | Phase 3 | Pending |
| HIST-01 | Phase 5 | Pending |
| HIST-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-03-19*
*Last updated: 2026-03-19 after roadmap mapping*
