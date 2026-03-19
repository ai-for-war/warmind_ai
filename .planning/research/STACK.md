# Stack Research

**Domain:** internal AI meeting recording and note generation
**Researched:** 2026-03-19
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | 0.135.1 | REST control plane and read APIs | Already established in the codebase, fits the existing service/repository architecture, and keeps the new meeting flow inside the current backend rather than creating a second app |
| python-socketio | 5.16.1 | Live audio/control transport between frontend and backend | The repo already uses Socket.IO for realtime flows, so meeting capture can reuse proven connection/auth/event patterns |
| Deepgram streaming STT (Nova docs current) | API current | Live transcription with diarization, utterances, punctuation, and gap detection | Official docs support `diarize=true`, `utterances=true`, and `utterance_end_ms`, which matches the need for anonymous speaker labels and batch-oriented meeting summarization |
| MongoDB via Motor/PyMongo | motor 3.7.1 / pymongo 4.16.0 | Durable storage for meeting conversations, utterances, and summary snapshots | The platform already persists document-style conversational data in MongoDB, which is a good fit for append-heavy transcripts and evolving summary projections |
| Redis | 7.2.1 | Queueing summary jobs, transient batch state, and realtime fan-out | Existing queue and pub/sub infrastructure already relies on Redis; batch summary generation should reuse it instead of inventing another worker stack |
| OpenAI through the existing LLM abstraction | langchain-openai 1.1.10 | Structured meeting summarization and follow-up extraction | Custom prompts and summary schemas are more flexible than provider-native one-shot summarization and work better with multilingual/internal product requirements |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| LangGraph | 1.0.10 | Multi-step summary or refinement flow | Use if summary generation grows beyond a single prompt into checkpointed summarization, refinement, or verification |
| Pydantic | 2.12.5 | Request, event, and storage contracts | Use for separate meeting schemas instead of reusing interview-specific STT payloads |
| pydantic-settings | 2.13.1 | Feature flags and provider settings | Use for meeting-specific knobs such as batch window size, summary debounce, language policy, and retention behavior |
| pytest / pytest-asyncio | 9.0.2 / 1.3.0 | Unit and async integration testing | Use to lock down meeting session lifecycle, transcript persistence, summary batching, and access-control behavior |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Deepgram Playground | Verify diarization and utterance behavior against real samples | Useful for tuning `diarize`, `utterances`, `punctuate`, and `utterance_end_ms` before hard-coding defaults |
| Existing worker scripts | Run background summary workers locally | Prefer extending the current Redis worker model instead of adding another scheduler just for meetings |
| Existing `.planning/codebase/*` docs | Brownfield architecture guardrails | Keep the meeting flow aligned with the repo's modular monolith conventions |

## Installation

```bash
# Reuse the existing Python environment and dependency set
pip install -r requirements.txt

# No separate meeting-specific package manager is needed
# Extend existing FastAPI, Deepgram, Redis, and LLM integrations
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Deepgram diarization on one streamed audio source | Fixed two-channel speaker mapping | Only use fixed channels when the source truly provides isolated per-speaker channels; browser-captured meeting audio usually does not |
| Custom LLM summary pipeline in the application domain | Deepgram `summarize=v2` | Acceptable only for simple English-only one-shot summaries of completed recordings; not ideal for multilingual or custom structured meeting outputs |
| Meeting-specific Mongo collections/models | Reusing interview conversation and utterance collections | Only acceptable if the meeting product is intentionally the same domain as interview, which the user explicitly rejected |
| Redis-backed batch jobs | Calling the LLM on every finalized utterance | Only acceptable for very short voice-agent loops; meeting note generation is better served by batched summarization |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Interview-specific 2-channel schemas as the primary meeting contract | They hard-code `interviewer/user` semantics that do not match meetings and will slow future changes | Create meeting-native schemas and repos, then reuse only shared infrastructure |
| Provider-native summarization as the main product summary path | Deepgram summary is one short summary across all channels and its docs say v2 is not supported for non-English languages | Keep summarization in the app so prompts, schema, and language policy stay under product control |
| Per-utterance AI calls | High cost, noisy partial outputs, and weak note quality during long meetings | Buffer transcript changes and summarize in debounced batches |

## Stack Patterns by Variant

**If the frontend sends one mixed meeting stream:**
- Use Deepgram diarization with utterance grouping
- Because speaker separation is semantic, not channel-based

**If a later source provides isolated channels per participant:**
- Use multichannel transcription first, then optionally combine with diarization
- Because channels and speakers solve different problems

**If meetings may contain mixed languages:**
- Either require a user-selected language or move to multilingual model settings
- Because the official language docs state a fixed `language` value will ignore other languages in the stream

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI 0.135.1 | Pydantic 2.12.5 | Already validated in the codebase |
| LangChain 1.2.10 | LangGraph 1.0.10 | Existing AI orchestration stack in the repo |
| motor 3.7.1 | pymongo 4.16.0 | Existing persistence combination in the repo |
| python-socketio 5.16.1 | Redis 7.2.1 | Current realtime/backplane stack already uses both |

## Sources

- `.planning/codebase/STACK.md` - current repo stack and pinned versions
- `.planning/codebase/ARCHITECTURE.md` - current runtime architecture and integration boundaries
- https://developers.deepgram.com/docs/diarization - verified live diarization behavior and speaker labeling
- https://developers.deepgram.com/docs/utterances - verified utterance grouping and diarization-friendly formatting
- https://developers.deepgram.com/docs/utterance-end - verified server-side gap detection for streaming batch windows
- https://developers.deepgram.com/docs/multichannel-vs-diarization - verified when to use diarization vs multichannel
- https://developers.deepgram.com/docs/language - verified language parameter behavior and multilingual caveat
- https://developers.deepgram.com/docs/summarization - verified limitations of provider-native summary output

---
*Stack research for: internal AI meeting recording and note generation*
*Researched: 2026-03-19*
