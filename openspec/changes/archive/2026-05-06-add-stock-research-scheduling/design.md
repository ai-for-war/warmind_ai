## Context

Stock research reports are currently accepted through `POST /stock-research/reports`, persisted as queued reports, and processed with FastAPI `BackgroundTasks`. That works for manual requests but is not durable across API process restarts and does not give scheduled execution a safe worker path.

The codebase already has a stronger pattern for recurring and long-running work: an internal API endpoint receives a cloud scheduler trigger, persists or enqueues work, and a Redis-backed worker process performs execution. Stock research scheduling should reuse that pattern instead of adding in-process scheduling to the API server.

## Goals / Non-Goals

**Goals:**

- Let users create, read, update, pause, delete, and manually trigger recurring stock research schedules inside their authenticated organization context.
- Support `every_15_minutes`, `daily`, and `weekly` schedules, with weekly schedules allowing multiple weekdays.
- Interpret daily and weekly configured hours as `Asia/Saigon` time without exposing timezone in the public API.
- Use AWS EventBridge Scheduler as a heartbeat that calls one internal endpoint every 15 minutes.
- Persist schedule configuration separately from schedule occurrence history.
- Guarantee idempotency for a single schedule occurrence while allowing overlapping reports from different occurrences.
- Move manual report processing to the same Redis worker queue used by scheduled reports.

**Non-Goals:**

- Per-user AWS EventBridge schedules.
- User-selectable timezones.
- Minute-level daily or weekly configuration.
- Preventing overlap between different schedule occurrences.
- Provider-level retry semantics for failed research generation beyond the existing report lifecycle.

## Decisions

### Use EventBridge Scheduler as a 15-minute heartbeat

The deployment should create one AWS EventBridge Scheduler schedule that calls `POST /api/v1/internal/trigger-stock-research-schedules` every 15 minutes with the internal API key. The application owns all user schedule state in MongoDB.

Alternatives considered:
- Per-user EventBridge schedules: rejected because CRUD, authorization, idempotency, and debugging would be split between AWS and MongoDB.
- In-process APScheduler: rejected because API restarts and multi-instance deployments can miss or duplicate jobs.
- Separate hourly and 15-minute triggers: rejected because one 15-minute dispatcher can handle all schedule types using `next_run_at <= now`.

### Store minimal schedule state

`stock_research_schedules` should store only configuration and dispatch state needed to find the next due occurrence:

- user and organization scope
- symbol
- resolved runtime config
- schedule type
- hour and weekdays when required
- status
- `next_run_at`
- timestamps

It should not store `last_report_id` or `last_run_at`. Those are derived from schedule runs or reports and would add consistency concerns without a current requirement.

### Store schedule occurrences for idempotency

`stock_research_schedule_runs` should store each due occurrence with a unique index on `(schedule_id, occurrence_at)`. The dispatcher must create or claim a run before creating the report. This prevents duplicate reports when EventBridge retries the same trigger or when two dispatcher instances race.

Run states should distinguish at least:

- `dispatching`
- `queued`
- `enqueue_failed`

If a dispatcher crashes after creating a `dispatching` run but before queueing work, a later dispatcher can recover stale `dispatching` runs according to a lock expiration timestamp.

### Use Asia/Saigon as the fixed business timezone

The API should not expose timezone. Daily and weekly hours are interpreted in `Asia/Saigon`, then converted to UTC for `next_run_at` and `occurrence_at` persistence. This keeps Mongo queries simple and avoids dependence on server/container local timezone.

Next-run calculation should use Python `zoneinfo.ZoneInfo("Asia/Saigon")` internally. Even though Vietnam does not currently use daylight saving time, using IANA timezone semantics avoids hard-coding offsets in scheduling logic.

### Use Redis worker execution for both manual and scheduled reports

Manual report creation should continue to return `202 Accepted` after persisting a queued report, but it should enqueue `stock_research_tasks` instead of using FastAPI `BackgroundTasks`. Scheduled dispatch should create the same queued report shape and enqueue the same task shape. `StockResearchWorker` then calls `StockResearchService.process_report`.

This gives both trigger sources the same lifecycle behavior, logging, process isolation, and deployment model.

### Allow overlap, prevent duplicate occurrences

The system should allow different occurrences of the same schedule to enqueue reports even when previous reports are still running. The only dedupe boundary is one `(schedule_id, occurrence_at)` pair.

## Risks / Trade-offs

- EventBridge delivery delay -> The dispatcher uses `next_run_at <= now`, so delayed ticks still dispatch due work.
- EventBridge retry duplicate -> The unique `(schedule_id, occurrence_at)` run key prevents duplicate reports for the same occurrence.
- Dispatcher crash mid-dispatch -> Run-level `dispatching` state plus lock expiration allows later recovery.
- Large due backlog -> The dispatcher should process due schedules in bounded batches and can be called again on the next 15-minute tick.
- Worker unavailable -> Reports remain queued and Redis queue depth exposes backlog; the API process is not responsible for long-running execution.
- Manual flow migration changes execution timing -> API behavior remains asynchronous, but tests must cover enqueue behavior so the old `BackgroundTasks` dependency does not remain.

## Migration Plan

1. Add Mongo models, repositories, and indexes for schedules and schedule runs.
2. Add report metadata fields for `trigger_type`, `schedule_id`, and `schedule_run_id` while keeping existing manual report responses backward compatible unless explicitly exposed.
3. Add stock research Redis queue settings and worker.
4. Change manual report creation to enqueue Redis work after persisting the queued report.
5. Add schedule CRUD and run-now APIs.
6. Add the internal dispatcher endpoint for EventBridge.
7. Deploy the worker process.
8. Configure one AWS EventBridge Scheduler heartbeat to call the internal endpoint every 15 minutes.

Rollback can disable the EventBridge heartbeat and stop the stock research worker. Manual API compatibility should remain intact, but manual report execution would require either keeping the worker available or temporarily restoring the old BackgroundTasks path.
