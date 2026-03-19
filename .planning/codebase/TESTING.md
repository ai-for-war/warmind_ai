# Testing Patterns

**Analysis Date:** 2026-03-19

## Test Framework

**Runner:**
- `pytest` is declared in `requirements.txt`.
- `pytest-asyncio` is declared in `requirements.txt`, which matches the repo's async-heavy service and worker code under `app/services/` and `app/workers/`.
- `hypothesis` is declared in `requirements.txt`, but no committed source file imports it.
- Config: Not detected. `pytest.ini`, `pyproject.toml`, `tox.ini`, `.coveragerc`, and `tests/conftest.py` are not present.

**Assertion Library:**
- Native `pytest` assertions are the only detectable assertion style. No alternate assertion library is declared in `requirements.txt` or referenced by committed source files.

**Run Commands:**
```bash
pytest
# Watch mode: Not detected
# Coverage: Not detected (`pytest-cov` and `.coveragerc` are absent)
```

## Test File Organization

**Location:**
- Tests live in a separate top-level `tests/` tree rather than co-locating with source code.
- Current committed structure only contains package markers: `tests/__init__.py`, `tests/unit/__init__.py`, and `tests/integration/__init__.py`.
- No readable `test_*.py` or `*_test.py` modules are currently checked in.

**Naming:**
- The last recorded pytest node IDs in `.pytest_cache/v/cache/nodeids` use the pattern `tests/unit/test_<module>.py::test_<behavior>`.
- Examples from `.pytest_cache/v/cache/nodeids`: `tests/unit/test_stt_session.py::test_partial_transcript_emits_speaker_aware_preview` and `tests/unit/test_image_generation_worker.py::test_run_once_dispatches_without_waiting_for_previous_task`.

**Structure:**
```text
tests/
├── __init__.py
├── unit/
│   └── __init__.py
└── integration/
    └── __init__.py
```

## Test Structure

**Suite Organization:**
```text
# No committed test implementation files are currently readable.
# Historical local node IDs in `.pytest_cache/v/cache/nodeids` show this pattern:
tests/unit/test_stt_session.py::test_partial_transcript_emits_speaker_aware_preview
tests/unit/test_interview_context_store.py::test_append_closed_utterance_trims_window_and_stores_metadata
tests/unit/test_socket_payload_contract.py::test_enrich_socket_payload_serializes_datetime_values
```

**Patterns:**
- Setup pattern: Not detected in committed test source. No `tests/conftest.py` or shared setup helpers exist.
- Teardown pattern: Not detected in committed test source.
- Assertion pattern: Not directly inspectable because the repo does not include readable test bodies.

## Mocking

**Framework:** Not detected in committed test source.

**Patterns:**
```text
# Not detected: no readable mocking examples are checked in.
# The missing historical unit tests targeted boundary-heavy modules such as:
# `app/infrastructure/deepgram/client.py`
# `app/workers/image_generation_worker.py`
# `app/services/stt/context_store.py`
```

**What to Mock:**
- No checked-in policy exists. Based on current architecture, future unit tests should mock external boundaries created through `app/common/service.py` and `app/common/repo.py`: `RedisClient`, `MongoDB`, `CloudinaryClient`, `MiniMaxClient`, `DeepgramLiveClient`, queue adapters, and Socket.IO gateways under `app/socket_gateway/`.

**What NOT to Mock:**
- Keep pure validation and stateful domain logic unmocked where possible. Good candidates are `app/services/ai/pipeline_validator.py`, `app/services/stt/session.py`, `app/common/socket_payload_contract.py`, and schema validation in `app/domain/schemas/stt.py`.

## Fixtures and Factories

**Test Data:**
```text
# Not detected: there is no `tests/conftest.py`, no `tests/fixtures/`, and no factory module.
# Historical node IDs show behavior-focused cases such as:
tests/unit/test_interview_context_store.py::test_get_recent_utterances_surfaces_invalid_cached_payloads
tests/unit/test_deepgram_client.py::test_sanitize_exception_message_redacts_authorization_token
```

**Location:**
- Not detected. Only `tests/unit/` and `tests/integration/` package directories are present.

## Coverage

**Requirements:** None enforced. No coverage target, no `pytest-cov` dependency, and no coverage configuration file are checked in.

**View Coverage:**
```bash
# Not detected: no coverage command or config is checked in
```

## Test Types

**Unit Tests:**
- Intended location exists at `tests/unit/`.
- Historical pytest cache entries in `.pytest_cache/v/cache/nodeids` show prior unit focus on `app/services/stt/session.py`, `app/services/stt/context_store.py`, `app/workers/image_generation_worker.py`, `app/infrastructure/deepgram/client.py`, `app/common/socket_payload_contract.py`, and normalization helpers in `app/services/voice/voice_service.py`.

**Integration Tests:**
- Intended location exists at `tests/integration/`.
- No readable integration test modules are committed.
- `.pytest_cache/v/cache/nodeids` does not currently list any integration test node IDs.

**E2E Tests:**
- Not used. No end-to-end test directory, browser test framework, or corresponding configuration files are detected.

## Common Patterns

**Async Testing:**
```text
# No committed async test example is available.
# Async-heavy targets that future pytest tests should cover include:
# `app/services/stt/session.py`
# `app/services/stt/context_store.py`
# `app/workers/image_generation_worker.py`
# `app/infrastructure/minimax/client.py`
```

**Error Testing:**
```text
# Cached node IDs indicate behavior-style error assertions such as:
tests/unit/test_interview_context_store.py::test_get_conversation_metadata_surfaces_read_failures
tests/unit/test_deepgram_client.py::test_sanitize_exception_message_redacts_authorization_token
tests/unit/test_image_generation_worker.py::test_run_once_dispatches_without_waiting_for_previous_task
```

---

*Testing analysis: 2026-03-19*
