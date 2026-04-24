## ADDED Requirements

### Requirement: Stock research schedules are organization-scoped user resources
The system SHALL provide authenticated stock research schedule APIs that require an active user and a valid organization context. A schedule MUST be scoped to the creating user and organization.

#### Scenario: Create a schedule in an organization context
- **WHEN** an authenticated active user creates a stock research schedule with a valid organization context
- **THEN** the system persists the schedule for that user and organization
- **AND** the schedule is not visible outside that user and organization scope

#### Scenario: Reject schedule access outside owner scope
- **WHEN** a user requests a stock research schedule owned by another user or organization
- **THEN** the system MUST reject the request

### Requirement: Users can manage recurring stock research schedules
The system SHALL provide APIs to create, list, read, update, pause, resume, and delete stock research schedules. Deleting a schedule MUST prevent future scheduled occurrences without deleting already-created reports.

#### Scenario: List user schedules
- **WHEN** a user lists stock research schedules in an organization
- **THEN** the system returns only schedules owned by that user in that organization

#### Scenario: Pause a schedule
- **WHEN** a user pauses an active stock research schedule they own
- **THEN** the system marks the schedule as paused
- **AND** future dispatcher runs MUST NOT create scheduled reports for the paused schedule

#### Scenario: Delete a schedule
- **WHEN** a user deletes a stock research schedule they own
- **THEN** the system prevents future scheduled reports for that schedule
- **AND** reports already created by that schedule remain readable through the stock research report APIs

### Requirement: Schedule creation validates symbol, runtime, and schedule shape
The system SHALL validate a schedule's stock symbol against the persisted stock catalog and SHALL validate runtime configuration using the same stock research runtime catalog rules used by manual report creation. The system MUST reject invalid schedule definitions.

#### Scenario: Create every-15-minutes schedule
- **WHEN** a user creates a schedule with type `every_15_minutes` for a valid symbol and runtime config
- **THEN** the system accepts the schedule
- **AND** the schedule definition MUST NOT require an hour or weekdays

#### Scenario: Create daily schedule
- **WHEN** a user creates a schedule with type `daily`, an integer hour from 0 through 23, a valid symbol, and a valid runtime config
- **THEN** the system accepts the schedule

#### Scenario: Create weekly schedule with multiple weekdays
- **WHEN** a user creates a schedule with type `weekly`, one or more weekdays, an integer hour from 0 through 23, a valid symbol, and a valid runtime config
- **THEN** the system accepts the schedule

#### Scenario: Reject invalid schedule shape
- **WHEN** a user creates or updates a schedule with missing required schedule fields, unsupported schedule type, invalid hour, empty weekly weekdays, unknown symbol, or unsupported runtime config
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT persist the invalid schedule definition

### Requirement: Daily and weekly schedule hours use Vietnam business time
The system SHALL interpret daily and weekly schedule hours as `Asia/Saigon` time. The public schedule API MUST NOT require or expose user-selectable timezone configuration.

#### Scenario: Persist next run in UTC
- **WHEN** a user creates a daily schedule for hour `8`
- **THEN** the system computes the next occurrence at `08:00 Asia/Saigon`
- **AND** the system persists `next_run_at` as the equivalent UTC datetime

#### Scenario: Update schedule recalculates next run
- **WHEN** a user updates a schedule's type, hour, weekdays, symbol, runtime config, or active status
- **THEN** the system recalculates future dispatch state from the updated schedule definition

### Requirement: Internal dispatcher creates due scheduled report occurrences
The system SHALL provide an internal API endpoint for AWS EventBridge Scheduler to trigger stock research schedule dispatch. The endpoint MUST require internal API key authentication and MUST process active schedules whose `next_run_at` is due.

#### Scenario: Dispatch due schedule
- **WHEN** the internal dispatcher runs at or after an active schedule's `next_run_at`
- **THEN** the system creates a schedule run for that occurrence
- **AND** the system creates a queued stock research report for the schedule's symbol and runtime config
- **AND** the system enqueues a stock research worker task for that report
- **AND** the system advances the schedule's `next_run_at` to the following occurrence

#### Scenario: Do not dispatch future schedule
- **WHEN** the internal dispatcher runs before a schedule's `next_run_at`
- **THEN** the system MUST NOT create a report for that schedule

#### Scenario: Reject unauthenticated internal dispatch
- **WHEN** a request calls the internal stock research schedule dispatch endpoint without the valid internal API key
- **THEN** the system MUST reject the request

### Requirement: Schedule occurrences are idempotent
The system SHALL prevent duplicate report creation for the same schedule occurrence. Idempotency MUST be based on the combination of schedule id and occurrence datetime.

#### Scenario: Retry same occurrence
- **WHEN** the internal dispatcher is invoked multiple times for the same due schedule occurrence
- **THEN** the system creates at most one stock research report for that schedule occurrence

#### Scenario: Concurrent dispatcher race
- **WHEN** two dispatcher processes attempt to dispatch the same schedule occurrence concurrently
- **THEN** only one process creates the schedule run and report for that occurrence

### Requirement: Different schedule occurrences may overlap
The system SHALL allow separate occurrences of the same schedule to create separate reports even if prior reports are still queued or running.

#### Scenario: Fifteen-minute occurrences overlap
- **WHEN** an `every_15_minutes` schedule has a previous report still running and a later occurrence becomes due
- **THEN** the system creates a new queued report for the later occurrence

#### Scenario: Weekly occurrence overlaps previous occurrence
- **WHEN** a weekly schedule's new configured weekday and hour becomes due while an earlier report from the same schedule is still running
- **THEN** the system creates a new queued report for the new occurrence

### Requirement: Manual and scheduled reports share Redis worker execution
The system SHALL dispatch both manually-created and scheduled stock research reports through a Redis-backed stock research worker queue. The HTTP API MUST return after persisting and enqueueing a queued report and MUST NOT rely on FastAPI `BackgroundTasks` for stock research execution.

#### Scenario: Manual report enqueues worker task
- **WHEN** a user creates a manual stock research report for a valid symbol
- **THEN** the system persists a queued report
- **AND** the system enqueues a stock research worker task for that report
- **AND** the system returns `202 Accepted` without waiting for report completion

#### Scenario: Worker processes queued report
- **WHEN** the stock research worker dequeues a stock research task
- **THEN** the worker processes the report through the stock research service lifecycle
- **AND** terminal report state and notifications follow the existing stock research report behavior

### Requirement: Users can manually trigger one schedule without changing recurring cadence
The system SHALL provide a run-now operation for a user's stock research schedule. Run-now MUST create a report immediately and MUST NOT move the schedule's next recurring occurrence.

#### Scenario: Run schedule now
- **WHEN** a user invokes run-now for a stock research schedule they own
- **THEN** the system creates a queued stock research report using the schedule's current symbol and runtime config
- **AND** the system enqueues the report for worker execution
- **AND** the schedule's `next_run_at` remains based on its recurring cadence
