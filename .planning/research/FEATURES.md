# Feature Research

**Domain:** internal AI meeting recording and note generation
**Researched:** 2026-03-19
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Full transcript with timestamps | Users want a durable record so they do not need to replay the entire meeting | MEDIUM | This is the audit trail that all summaries depend on |
| Speaker-separated transcript view | Market leaders show transcript grouped by speaker, even when the identity is generic | MEDIUM | Anonymous `speaker 1`, `speaker 2` is acceptable for v1 if identity mapping is not available |
| AI summary with decisions and action items | Official product pages from Otter, Fireflies, and Notta all market this as core value | MEDIUM | This directly addresses the user's manual note-taking pain |
| Ongoing capture during the meeting | Users expect to start recording at the beginning and stop at the end without post-upload friction | MEDIUM | FE streaming is enough for v1; meeting bot integration is not required |
| History/detail review of completed meetings | Users need to reopen old conversations, not just process the current meeting once | LOW | In this product, "history" can stay close to conversation detail semantics |
| Language selection or clear language policy | Transcription quality depends heavily on language configuration | LOW | The user explicitly wants language to be selectable such as `vi` or `en` |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Batch-updated summary during the live session | Users can catch up during the meeting without the noise of per-utterance AI output | MEDIUM | This is a practical middle ground between offline-only notes and hyper-realtime copilots |
| Meeting-native conversation model | Keeps transcript, summary, and future query features coherent without interview-domain baggage | MEDIUM | This is a technical differentiator that protects future velocity |
| Summary snapshots with source transcript lineage | Makes later verification and regeneration safer | MEDIUM | Supports trustworthy note updates instead of opaque summary replacement |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Per-utterance live AI response | Feels "more realtime" | Creates noisy notes, higher cost, and unstable partial conclusions | Summarize on debounced transcript batches |
| Real speaker identity mapping in v1 | Feels more polished | Browser audio usually lacks reliable identity metadata; diarization labels can drift | Show anonymous `speaker N` labels first |
| Direct meeting-bot/platform integration in v1 | Feels like a complete meeting assistant | Adds OAuth, platform APIs, permissions, scheduling, and bot behavior complexity | Use frontend audio streaming first |

## Feature Dependencies

```text
Meeting capture
  -> requires -> Live STT ingest
                   -> requires -> Transcript persistence
                                      -> requires -> Meeting conversation model

Transcript persistence
  -> enables -> Batch summary generation
                   -> enables -> Decisions/action items/follow-up extraction
                   -> enables -> Meeting detail review

Diarization
  -> enhances -> Transcript readability

Meeting history
  -> requires -> Durable transcript + summary storage

Direct platform integrations
  -> conflicts with -> Fast v1 delivery
```

### Dependency Notes

- **Meeting capture requires live STT ingest:** Without a reliable streaming transcription path, there is nothing to summarize.
- **Transcript persistence requires a meeting conversation model:** The user wants meetings treated as conversations, so transcript storage should align with that boundary.
- **Batch summary generation depends on durable transcript state:** Summary quality improves when built from stable transcript chunks rather than volatile interim text.
- **Diarization enhances transcript readability:** It is not enough by itself, but it makes later summary and review much more usable.
- **Direct platform integration conflicts with fast v1 delivery:** It expands scope far beyond the current internal need.

## MVP Definition

### Launch With (v1)

- [ ] Start/stop live meeting capture from the frontend - essential because the product begins when the meeting begins
- [ ] Durable transcript stored as meeting conversation utterances/messages - essential because summary alone is not enough
- [ ] Anonymous speaker-separated transcript rendering - essential for readability without identity mapping
- [ ] Batch-generated summary sections (summary, key points, decisions, action items, notes, follow-up questions) - essential because this is the main user value
- [ ] Dedicated summary collection linked to the meeting conversation - essential because summary lifecycle differs from transcript lifecycle
- [ ] Language selection for supported meeting languages - essential to avoid predictable transcription errors

### Add After Validation (v1.x)

- [ ] Search/QA over past meetings - add once transcript and summary schemas are stable
- [ ] Re-run or regenerate summary with different prompt templates - add once users request alternate meeting formats
- [ ] Export/share flows - add when internal review patterns are clear

### Future Consideration (v2+)

- [ ] Google Meet/Zoom/Teams integrations - defer until the FE streaming workflow proves value
- [ ] Speaker identity mapping - defer until a trustworthy identity source exists
- [ ] Automatic task/CRM/project management sync - defer until action-item quality is proven

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Live meeting capture | HIGH | MEDIUM | P1 |
| Durable full transcript | HIGH | MEDIUM | P1 |
| Anonymous speaker labels | MEDIUM | MEDIUM | P1 |
| Batch summary generation | HIGH | MEDIUM | P1 |
| Decisions and action items extraction | HIGH | MEDIUM | P1 |
| Summary history/snapshots | MEDIUM | MEDIUM | P2 |
| Search/QA on meeting history | MEDIUM | HIGH | P2 |
| Export/share | LOW | MEDIUM | P3 |
| Meeting platform integrations | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Competitor A | Competitor B | Our Approach |
|---------|--------------|--------------|--------------|
| Transcript + speakers | Otter markets live transcription with speaker recognition | Notta markets real-time transcripts with speaker identification and timestamps | Deliver diarized transcript with anonymous speaker labels first |
| Summary + action items | Fireflies markets live notes, action items, and transcripts | Otter markets summaries with decisions, action items, and insights | Make this core v1 output, but generated from our own prompt/schema |
| Live meeting recap | Fireflies markets "summary so far" and live AI notes | Otter markets live summary and instant takeaways | Support batch-updated summaries during the meeting, not token-by-token notes |
| History/detail review | Otter exposes conversation pages with summary and transcript tabs | Notta emphasizes review, sharing, and accessible cloud history | Treat each meeting as a conversation with durable transcript plus summary collection |

## Sources

- https://otter.ai/ - official product page for transcripts, summaries, action items, and meeting history expectations
- https://help.otter.ai/hc/en-us/articles/5093228433687-Conversation-Page-Overview - official help article showing summary + transcript conversation detail pattern
- https://fireflies.ai/product/real-time - official product page for live transcript, notes, and action items
- https://guide.fireflies.ai/articles/5965172749-live-assist-on-fireflies-mobile-app-get-real-time-notes-live-during-meetings - official help article for live recap patterns
- https://www.notta.ai/en/ - official product page for transcript, AI notes, multilingual support, and security expectations
- https://www.notta.ai/en/features/meeting-recording-software - official page for review/storage expectations
- https://www.notta.ai/en/landing-page/meeting-notes - official page for summary/action-item expectations
- User interview context from `.planning/PROJECT.md`

---
*Feature research for: internal AI meeting recording and note generation*
*Researched: 2026-03-19*
