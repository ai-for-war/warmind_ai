---
phase: 3
slug: summary-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 3 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | none - pytest defaults only |
| **Quick run command** | `pytest tests/unit -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30-45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit -q`
- **After every plan wave:** Run `pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | SUMM-01, SUMM-07 | unit | `pytest tests/unit/repo/test_meeting_summary_repo.py -q` | no (W0) | pending |
| 03-01-02 | 01 | 1 | SUMM-01 | unit | `pytest tests/unit/services/test_meeting_summary_service.py -q` | no (W0) | pending |
| 03-01-03 | 01 | 1 | SUMM-01, SUMM-07 | unit | `pytest tests/unit/test_meeting_summary_worker.py -q` | no (W0) | pending |
| 03-02-01 | 02 | 2 | SUMM-01 | integration | `pytest tests/integration/socket_gateway/test_meeting_record_summary_socket.py -q` | no (W0) | pending |
| 03-02-02 | 02 | 2 | SUMM-07 | integration | `pytest tests/integration/socket_gateway/test_meeting_record_summary_socket.py -q` | no (W0) | pending |
| 03-02-03 | 02 | 2 | SUMM-01, SUMM-07 | regression | `pytest -q` | yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/repo/test_meeting_summary_repo.py` - durable summary storage, stale write rejection, and latest-version retrieval
- [ ] `tests/unit/services/test_meeting_summary_service.py` - debounce thresholding, summary state transitions, and language/prompt guardrails
- [ ] `tests/unit/test_meeting_summary_worker.py` - queue task execution, idempotent processing, retry/error handling, and final promotion behavior
- [ ] `tests/integration/socket_gateway/test_meeting_record_summary_socket.py` - meeting summary socket lifecycle from updating to ready/final-ready

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live summary keeps the last good content visible while a new batch is processing | SUMM-01 | Requires frontend rendering confirmation | Start a meeting, wait for one live summary, continue speaking until another summary batch triggers, and confirm the existing summary remains visible with only a light updating state |
| Final summary reuses the same UI surface instead of swapping to a different panel | SUMM-07 | Requires observing UX continuity | Stop a meeting after at least one live summary exists, verify the current summary remains visible during finalization, then confirm the same panel moves to final-ready |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
