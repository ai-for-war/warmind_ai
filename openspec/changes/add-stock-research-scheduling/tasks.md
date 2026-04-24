## 1. Persistence Models and Indexes

- [x] 1.1 Add stock research schedule domain models for schedule type, status, weekdays, runtime config snapshot, and UTC `next_run_at`.
- [x] 1.2 Add stock research schedule run domain models for occurrence idempotency with `dispatching`, `queued`, and `enqueue_failed` states.
- [x] 1.3 Add optional stock research report metadata fields for `trigger_type`, `schedule_id`, and `schedule_run_id` while preserving current manual report behavior.
- [x] 1.4 Add Mongo indexes for active due schedules, user organization schedule listing, and unique `(schedule_id, occurrence_at)` schedule runs.

## 2. Schedule Calculation and Validation

- [ ] 2.1 Implement schedule request schemas for `every_15_minutes`, `daily`, and `weekly` definitions.
- [ ] 2.2 Validate schedule definitions, including integer hours from 0 through 23 and one or more weekdays for weekly schedules.
- [ ] 2.3 Implement `Asia/Saigon` next-run calculation for every-15-minutes, daily, and multi-weekday weekly schedules.
- [ ] 2.4 Add unit tests for schedule validation and next-run calculation around before, at, and after due times.

## 3. Repositories and Services

- [ ] 3.1 Add `StockResearchScheduleRepository` with create, find owned, list owned, update, pause/resume, soft delete, and due schedule query methods.
- [ ] 3.2 Add `StockResearchScheduleRunRepository` with occurrence insert, stale dispatch claim, queued mark, enqueue-failed mark, and lookup methods.
- [ ] 3.3 Add `StockResearchScheduleService` for CRUD, run-now, symbol validation, runtime config validation, and next-run persistence.
- [ ] 3.4 Add `StockResearchScheduleDispatcherService` that claims due occurrences idempotently, creates queued reports, enqueues worker tasks, and advances `next_run_at`.

## 4. Redis Worker Execution

- [ ] 4.1 Add `STOCK_RESEARCH_QUEUE_NAME` setting and stock research task payload schema.
- [ ] 4.2 Add stock research queue enqueue helper/service path shared by manual and scheduled report creation.
- [ ] 4.3 Implement `app/workers/stock_research_worker.py` following the existing Redis worker pattern.
- [ ] 4.4 Update manual `POST /stock-research/reports` to enqueue Redis work instead of using FastAPI `BackgroundTasks`.
- [ ] 4.5 Add worker tests for processing queued reports, skipping missing reports, and preserving terminal lifecycle behavior.

## 5. API Endpoints

- [ ] 5.1 Add stock research schedule routes for create, list, read, update, pause/resume or status update, delete, and run-now.
- [ ] 5.2 Wire schedule routes into the v1 router with existing authentication and organization dependencies.
- [ ] 5.3 Add internal API-key-protected endpoint for EventBridge schedule dispatch.
- [ ] 5.4 Add integration tests for schedule CRUD, ownership enforcement, run-now, and internal dispatch authentication.

## 6. Dispatcher Idempotency and Overlap

- [ ] 6.1 Add tests proving repeated dispatcher calls for the same occurrence create at most one report.
- [ ] 6.2 Add tests proving concurrent claim attempts for the same occurrence resolve to a single schedule run.
- [ ] 6.3 Add tests proving later due occurrences can create new reports even when earlier reports are still queued or running.
- [ ] 6.4 Add tests for stale `dispatching` run recovery and enqueue failure recording.

## 7. Documentation and Deployment Notes

- [ ] 7.1 Update environment documentation with `STOCK_RESEARCH_QUEUE_NAME`.
- [ ] 7.2 Document the required AWS EventBridge Scheduler heartbeat: one 15-minute trigger calling the internal dispatch endpoint with the internal API key.
- [ ] 7.3 Document that daily and weekly schedule hours are interpreted as `Asia/Saigon` time.
- [ ] 7.4 Run the relevant unit and integration test suites and fix regressions.
