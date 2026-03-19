---
phase: 1
slug: meeting-domain-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 1 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | none - pytest defaults only |
| **Quick run command** | `pytest tests/unit -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit -q`
- **After every plan wave:** Run `pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | MEET-01, MEET-03 | grep | `Select-String -Path app/config/settings.py,app/common/event_socket.py,app/common/exceptions.py -Pattern "MEETING_SUPPORTED_LANGUAGES|class MeetingRecordEvents|UnsupportedMeetingLanguageError"` | yes | pending |
| 01-01-02 | 01 | 1 | MEET-01, MEET-03 | unit | `pytest tests/unit/domain/test_meeting_record_schema.py -q` | no (W0) | pending |
| 01-01-03 | 01 | 1 | MEET-01 | unit | `pytest tests/unit/repo/test_meeting_record_repo.py -q` | no (W0) | pending |
| 01-02-01 | 02 | 2 | MEET-01, MEET-02, MEET-03 | unit | `pytest tests/unit/services/test_meeting_service.py -q` | no (W0) | pending |
| 01-02-02 | 02 | 2 | MEET-01, MEET-02 | integration | `pytest tests/integration/socket_gateway/test_meeting_record_socket.py -q` | no (W0) | pending |
| 01-02-03 | 02 | 2 | MEET-01, MEET-02, MEET-03 | regression | `pytest -q` | yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/domain/test_meeting_record_schema.py` - schema validation coverage for explicit organization_id, default language, and allowlist rejection
- [ ] `tests/unit/repo/test_meeting_record_repo.py` - repository lifecycle transition coverage
- [ ] `tests/unit/services/test_meeting_service.py` - service coverage for org membership, duplicate active start, and ownership rules
- [ ] `tests/integration/socket_gateway/test_meeting_record_socket.py` - socket happy-path and failure-path coverage

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Frontend waits for `meeting_record:started` before streaming audio | MEET-01 | Current repo does not include the frontend client | Start a socket client, send `meeting_record:start`, confirm audio is not sent until the ready payload containing `meeting_id` is received |
| Client UX reflects `meeting_record:stopping` before terminal completion | MEET-02 | Requires observing the frontend event sequence | Trigger stop on an active meeting and verify the UI shows a non-terminal stopping state before the final completed state |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
