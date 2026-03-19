---
phase: 2
slug: live-transcript-capture
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 2 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | none - pytest defaults only |
| **Quick run command** | `pytest tests/unit -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit -q`
- **After every plan wave:** Run `pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TRNS-01, TRNS-03, TRNS-04 | unit | `pytest tests/unit/test_deepgram_live_client.py -q` | yes | pending |
| 02-01-02 | 01 | 1 | TRNS-01, TRNS-03 | unit | `pytest tests/unit/test_meeting_transcript_session.py -q` | no (W0) | pending |
| 02-01-03 | 01 | 1 | TRNS-01, TRNS-03 | integration | `pytest tests/integration/socket_gateway/test_meeting_record_socket.py -q` | no (W0) | pending |
| 02-02-01 | 02 | 2 | TRNS-02, TRNS-04 | unit | `pytest tests/unit/repo/test_meeting_transcript_repo.py -q` | no (W0) | pending |
| 02-02-02 | 02 | 2 | TRNS-02, TRNS-04 | unit | `pytest tests/unit/services/test_meeting_transcript_service.py -q` | no (W0) | pending |
| 02-02-03 | 02 | 2 | TRNS-01, TRNS-02, TRNS-03, TRNS-04 | integration | `pytest tests/integration/api/test_meeting_transcript_api.py -q` | no (W0) | pending |
| 02-02-04 | 02 | 2 | TRNS-01, TRNS-02, TRNS-03, TRNS-04 | regression | `pytest -q` | yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_meeting_transcript_session.py` - meeting transcript assembly coverage for live rewrites, diarization fallback, and utterance closure
- [ ] `tests/unit/repo/test_meeting_transcript_repo.py` - durable meeting utterance persistence and pagination coverage
- [ ] `tests/unit/services/test_meeting_transcript_service.py` - transcript read-path, auth scope, and active/completed retrieval coverage
- [ ] `tests/integration/socket_gateway/test_meeting_record_socket.py` - live transcript event emission and stop/finalize transcript flush coverage
- [ ] `tests/integration/api/test_meeting_transcript_api.py` - transcript review endpoint ordering, pagination, and timestamp coverage

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live UI rewrites the current utterance instead of appending correction trails | TRNS-01 | Requires observing the client rendering behavior during provider partial/final churn | Start a meeting, speak a sentence with evolving interim results, and confirm the UI replaces the active utterance text in place rather than adding duplicate rows |
| Saved transcript review shows anonymous speaker labels and readable timestamps in chronological order | TRNS-02, TRNS-03, TRNS-04 | Backend tests can validate payloads, but frontend rendering still needs a human check | Open a completed meeting in the client, confirm transcript rows appear oldest-first with `speaker N` labels and formatted timestamps sourced from stored millisecond values |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
