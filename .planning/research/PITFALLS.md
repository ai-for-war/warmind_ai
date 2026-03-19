# Pitfalls Research

**Domain:** internal AI meeting recording and note generation
**Researched:** 2026-03-19
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Reusing the interview domain as the meeting domain

**What goes wrong:**
Meeting logic gets trapped inside `interviewer/user` assumptions, fixed channel maps, and interview-specific prompts.

**Why it happens:**
The existing STT path already works, so it is tempting to clone it instead of defining new meeting semantics.

**How to avoid:**
Create separate meeting models, repos, prompts, and APIs from the start. Reuse only transport/provider utilities and common infrastructure.

**Warning signs:**
New code keeps introducing `interviewer`, `candidate`, or fixed `channel_map` semantics into meeting handlers.

**Phase to address:**
Phase 1 foundation and domain modeling.

---

### Pitfall 2: Treating diarization labels as stable user identity

**What goes wrong:**
The product starts implying that `speaker 1` is a real named participant across the meeting or across meetings, even though diarization only gives anonymous speaker labels.

**Why it happens:**
Teams confuse speaker segmentation with identity resolution.

**How to avoid:**
Keep v1 speaker labels explicitly anonymous. Store them only as meeting-local labels unless there is a separate identity source.

**Warning signs:**
UI copy or database fields start calling diarized speakers "user", "host", or a real person without verified mapping.

**Phase to address:**
Phase 1 schema design and Phase 2 transcript rendering.

---

### Pitfall 3: Summarizing every finalized utterance

**What goes wrong:**
Notes become noisy, repetitive, and expensive, and summary quality gets worse because the model keeps re-summarizing partial context.

**Why it happens:**
Developers reuse a voice-agent mentality where every turn should trigger AI output.

**How to avoid:**
Persist stable transcript first, then trigger summary generation only on debounced transcript batches or explicit checkpoints.

**Warning signs:**
LLM calls scale linearly with every fragment, summaries churn rapidly, and users stop trusting mid-meeting notes.

**Phase to address:**
Phase 3 summary orchestration.

---

### Pitfall 4: Keeping only the summary and not the raw transcript lineage

**What goes wrong:**
Users cannot audit where decisions or action items came from, and later summary fixes become guesswork.

**Why it happens:**
Summary output feels like the only user-visible artifact, so teams under-invest in transcript storage.

**How to avoid:**
Treat transcript utterances as the source of truth and link summary snapshots to transcript positions or source ranges.

**Warning signs:**
Action items cannot point back to transcript context, or summaries cannot be regenerated safely after prompt changes.

**Phase to address:**
Phase 2 persistence and Phase 3 summary storage.

---

### Pitfall 5: Misconfiguring language handling

**What goes wrong:**
Meetings in the wrong language or mixed-language sessions produce missing or degraded transcripts.

**Why it happens:**
The official Deepgram language docs say a fixed `language` value transcribes only that language, but teams often treat it as a harmless hint.

**How to avoid:**
Require an explicit language choice for v1, document the behavior, and keep multilingual handling as a planned follow-up if needed.

**Warning signs:**
Users report that part of a bilingual meeting is missing, or transcript quality collapses after language switches.

**Phase to address:**
Phase 1 session contract design and Phase 4 UX/polish.

---

### Pitfall 6: Forgetting privacy and retention controls for meeting content

**What goes wrong:**
Sensitive transcripts and summaries become visible to the wrong internal users or linger longer than intended.

**Why it happens:**
Teams focus on transcription accuracy and postpone access control/retention because the product starts as "internal only."

**How to avoid:**
Apply existing organization/user scoping rules to meeting artifacts from day one and define deletion/retention behavior early.

**Warning signs:**
Meeting endpoints bypass organization checks, transcripts appear in logs, or there is no clear delete path for meeting data.

**Phase to address:**
Phase 2 persistence/API design and Phase 4 review flows.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse interview collections for meetings | Ships initial prototype faster | Locks the meeting domain to the wrong semantics and migration pain later | Never, given the user's explicit boundary |
| Recompute the whole summary from scratch every batch | Simple first implementation | High cost and inconsistent summary drift on long meetings | Acceptable only for very early internal prototypes |
| Keep summary only, no snapshots | Fewer documents to manage | No audit trail, weak recovery, harder prompt iteration | Rarely acceptable |
| Push full transcript to the client on every update | Easy frontend implementation | Poor performance as meetings grow | Acceptable only for very short test sessions |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Deepgram live STT | Assuming diarization equals named participants | Treat diarization labels as anonymous, meeting-local speaker ids |
| Deepgram language config | Hard-coding one language and expecting mixed-language support | Require explicit language or plan multilingual model support |
| Redis summary queue | Enqueuing a new summary job for every fragment | Debounce by conversation id and make jobs idempotent |
| LLM summary generation | Trusting a single free-form summary blob | Generate a structured summary contract with separate fields for decisions, actions, and follow-ups |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-summary regeneration on every batch | Queue lag, high LLM cost, unstable notes | Incremental or checkpoint-aware summarization | Medium-length meetings and above |
| Unbounded in-memory transcript buffers | Socket worker memory keeps growing during long calls | Persist stable utterances quickly and page transcript reads | Long meetings or many concurrent sessions |
| Shipping huge transcript payloads repeatedly | Slow UI refresh and large websocket/API payloads | Send deltas for live updates and paginate history/detail reads | As soon as transcripts exceed a few thousand words |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Meeting endpoints skip organization/user scoping | Data leaks across teams | Reuse current auth + org dependency checks on all meeting reads/writes |
| Logging raw transcript/audio metadata indiscriminately | Sensitive discussion appears in logs | Reduce logging to operational metadata and redact transcript content from logs |
| No delete/retention path for meetings | Compliance and trust problems | Define retention/deletion behavior early, even if manual first |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing unstable partial notes as final truth | Users lose trust in the feature | Label live notes as in-progress and keep final summary explicit |
| Overstating diarized speaker identity | Users misread the transcript | Keep labels generic and meeting-local |
| Forcing users to read the whole transcript to find decisions | Core pain remains unsolved | Make decisions and action items first-class summary sections |

## "Looks Done But Isn't" Checklist

- [ ] **Meeting capture:** It records audio, but disconnect/finalize/stop recovery is verified for long sessions.
- [ ] **Transcript persistence:** It stores text, but timestamps, speaker labels, and ordering are correct.
- [ ] **Summary generation:** It produces notes, but action items and decisions are linked to the underlying meeting context.
- [ ] **Meeting detail:** It renders one meeting, but old meetings can still be loaded safely without giant payloads.
- [ ] **Access control:** It works for one user, but organization/user scoping is enforced on every read path.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Interview-domain coupling | HIGH | Freeze schema growth, create meeting-native collections/models, backfill or migrate existing prototypes |
| Summary churn/noise | MEDIUM | Introduce debounce rules, snapshot versioning, and structured prompts |
| Missing transcript lineage | HIGH | Reconstruct from stored utterances if possible, then add summary source cursors immediately |
| Wrong language handling | MEDIUM | Reprocess stored audio/transcript source when possible and expose language choice more clearly |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Interview-domain coupling | Phase 1 | Meeting schemas/repos contain no interview-specific roles |
| Diarization identity confusion | Phase 1 | UI/API contracts expose anonymous speaker labels only |
| Over-eager summary generation | Phase 3 | LLM call rate is batch-based, not utterance-based |
| Missing transcript lineage | Phase 2 and Phase 3 | Summary records reference transcript state or source range |
| Language misconfiguration | Phase 1 and Phase 4 | Session contract and UI enforce explicit language policy |
| Privacy/retention gaps | Phase 2 and Phase 4 | Meeting reads obey auth/org checks and retention behavior is documented |

## Sources

- `.planning/PROJECT.md` - product boundary and user intent
- `.planning/codebase/ARCHITECTURE.md` - brownfield constraints
- https://developers.deepgram.com/docs/diarization - speaker-label behavior
- https://developers.deepgram.com/docs/language - language restriction behavior
- https://developers.deepgram.com/docs/utterance-end - gap detection behavior for batching
- https://developers.deepgram.com/docs/summarization - provider summary limitations
- Official product/help pages from Otter, Fireflies, and Notta for market expectations on transcript, summary, and meeting history

---
*Pitfalls research for: internal AI meeting recording and note generation*
*Researched: 2026-03-19*
