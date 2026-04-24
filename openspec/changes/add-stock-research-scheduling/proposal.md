## Why

Stock research reports can only be triggered manually today, which forces users to repeatedly request the same analysis for symbols they monitor. Scheduled research lets users define recurring report generation for Vietnam-listed stocks while preserving the existing asynchronous report lifecycle.

## What Changes

- Add authenticated organization-scoped stock research schedule CRUD APIs.
- Support three schedule types:
  - `every_15_minutes`
  - `daily` at an integer hour
  - `weekly` at an integer hour on one or more weekdays
- Treat configured hours as `Asia/Saigon` business time without exposing timezone in the API.
- Add a scheduled dispatcher invoked by AWS EventBridge Scheduler every 15 minutes through an internal authenticated endpoint.
- Persist schedule occurrences separately from schedule configuration so duplicate EventBridge retries do not create duplicate reports for the same occurrence.
- Allow overlapping report execution across different schedule occurrences.
- Add a Redis-backed stock research worker queue and migrate manual report creation away from FastAPI `BackgroundTasks` to the same worker execution path used by scheduled reports.

## Capabilities

### New Capabilities

- `stock-research-schedules`: User-managed recurring stock research schedules, occurrence dispatch, and idempotent scheduled report creation.

### Modified Capabilities

- None. Existing stock research report API behavior remains asynchronous and organization-scoped; the execution mechanism changes from FastAPI background tasks to Redis worker dispatch.

## Impact

- Affected API modules:
  - `app/api/v1/stock_research/router.py`
  - `app/api/v1/internal/router.py`
  - `app/api/v1/router.py`
- New persistence models, schemas, repositories, and indexes for stock research schedules and schedule runs.
- Stock research reports gain internal scheduled-run linkage fields so scheduled reports can be traced to their source schedule.
- New Redis queue setting for stock research tasks.
- New worker process: `app/workers/stock_research_worker.py`.
- Existing manual report creation will enqueue Redis work instead of using FastAPI `BackgroundTasks`.
- Tests are needed for schedule validation, next-run calculation, idempotent occurrence creation, internal dispatch, manual queue migration, and worker processing.
