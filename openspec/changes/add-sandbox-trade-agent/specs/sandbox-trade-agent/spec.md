## ADDED Requirements

### Requirement: Sandbox trade sessions are organization-scoped user resources
The system SHALL provide authenticated sandbox trade-agent APIs that require an active user and a valid organization context. A sandbox trade session MUST be scoped to the creating user and organization.

#### Scenario: Create a sandbox trade session
- **WHEN** an authenticated active user creates a sandbox trade session with a valid organization context, valid symbol, and valid initial capital
- **THEN** the system persists the session for that user and organization
- **AND** the session is not visible outside that user and organization scope

#### Scenario: Reject access outside owner scope
- **WHEN** a user requests a sandbox trade session owned by another user or organization
- **THEN** the system MUST reject the request

### Requirement: Users can manage sandbox trade sessions
The system SHALL provide APIs to create, list, read, pause, resume, stop, and delete sandbox trade sessions. A session MUST trade exactly one stock symbol.

#### Scenario: List user sandbox trade sessions
- **WHEN** a user lists sandbox trade sessions in an organization
- **THEN** the system returns only sessions owned by that user in that organization
- **AND** the response includes pagination metadata for total count, page, and page size

#### Scenario: Create session with default virtual capital
- **WHEN** a user creates a sandbox trade session without specifying initial capital
- **THEN** the system creates the session with `100000000` VND initial virtual capital
- **AND** the initial available cash equals the initial virtual capital

#### Scenario: Pause an active session
- **WHEN** a user pauses an active sandbox trade session they own
- **THEN** the system marks the session as paused
- **AND** future dispatcher runs MUST NOT enqueue trade ticks for the paused session

#### Scenario: Resume a paused session
- **WHEN** a user resumes a paused sandbox trade session they own
- **THEN** the system marks the session as active
- **AND** the system recalculates the next eligible run time from the current time

#### Scenario: Stop a session
- **WHEN** a user stops a sandbox trade session they own
- **THEN** the system marks the session as stopped
- **AND** the stopped session MUST NOT be resumed or dispatched again

#### Scenario: Delete a session
- **WHEN** a user deletes a sandbox trade session they own
- **THEN** the system prevents future ticks for that session
- **AND** previously persisted tick, order, settlement, and portfolio history remain available only if the API explicitly exposes deleted-session history

### Requirement: Session creation validates symbol and capital
The system SHALL validate sandbox trade session creation before persistence. The stock symbol MUST be validated against the supported stock catalog, and initial capital MUST be a positive VND amount.

#### Scenario: Reject unknown symbol
- **WHEN** a user creates a sandbox trade session with a symbol that is not supported by the stock catalog
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT persist a session

#### Scenario: Reject invalid initial capital
- **WHEN** a user creates a sandbox trade session with zero, negative, or non-numeric initial capital
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT persist a session

#### Scenario: Normalize session symbol
- **WHEN** a user creates a sandbox trade session with lowercase or surrounding whitespace in the symbol
- **THEN** the system persists the symbol in uppercase canonical form

### Requirement: Active sessions run every three minutes during Vietnam continuous trading windows
The system SHALL dispatch active sandbox trade sessions on a 3-minute cadence only on Monday through Friday and only during configured `Asia/Saigon` continuous trading windows. The initial windows SHALL be `09:00-11:30` and `13:00-14:45`.

#### Scenario: Dispatch due session inside trading window
- **WHEN** an active session's `next_run_at` is due during a Monday-Friday continuous trading window
- **THEN** the dispatcher creates or claims one tick occurrence for that session
- **AND** the dispatcher enqueues the tick for worker processing

#### Scenario: Do not dispatch on weekend
- **WHEN** an active session's `next_run_at` is due on Saturday or Sunday in `Asia/Saigon`
- **THEN** the dispatcher MUST NOT enqueue a trade tick for that time
- **AND** the session's next eligible run MUST be moved to the next Monday-Friday trading window

#### Scenario: Do not dispatch outside trading windows
- **WHEN** an active session's `next_run_at` is due outside `09:00-11:30` and `13:00-14:45` in `Asia/Saigon`
- **THEN** the dispatcher MUST NOT enqueue a trade tick for that time
- **AND** the session's next eligible run MUST be moved to the next configured trading window

#### Scenario: Advance next run after processed tick
- **WHEN** a session tick reaches a terminal state
- **THEN** the system advances the session's `next_run_at` by the configured 3-minute cadence to the next eligible trading time

### Requirement: Tick dispatch is idempotent
The system SHALL prevent duplicate tick execution for the same sandbox trade session occurrence. Tick idempotency MUST be based on the combination of session id and tick datetime.

#### Scenario: Retry same tick occurrence
- **WHEN** the dispatcher is invoked multiple times for the same due session occurrence
- **THEN** the system creates at most one tick record for that session occurrence
- **AND** the system enqueues at most one worker task that can execute the occurrence

#### Scenario: Concurrent dispatcher race
- **WHEN** two dispatcher processes attempt to claim the same session occurrence concurrently
- **THEN** only one process owns execution of that occurrence
- **AND** no duplicate sandbox fills are created for that occurrence

#### Scenario: Recover stale claimed tick
- **WHEN** a tick remains in a non-terminal claimed state past the configured lock expiration
- **THEN** a later dispatcher or worker recovery pass MAY reclaim the tick
- **AND** the reclaimed tick MUST still produce at most one set of sandbox execution side effects

### Requirement: Worker skips ticks without fresh market data
The system SHALL fetch a current market-data snapshot before invoking the trade agent. If no fresh usable latest price is available for the session symbol, the tick MUST be recorded as skipped and the agent MUST NOT be called.

#### Scenario: Skip tick when market data is unavailable
- **WHEN** the worker processes a due tick and cannot obtain a usable latest price for the session symbol
- **THEN** the system marks the tick as skipped with reason `NO_FRESH_MARKET_DATA`
- **AND** the system MUST NOT call the trade agent
- **AND** the system MUST NOT create a sandbox order

#### Scenario: Use market data in agent context
- **WHEN** the worker obtains a fresh market-data snapshot for the session symbol
- **THEN** the system includes the snapshot in the trade-agent input
- **AND** the system records the snapshot or a deterministic summary with the tick for auditability

### Requirement: Trade agent returns structured autonomous decisions
The system SHALL invoke a trade agent that autonomously returns a structured decision for each processable tick. The allowed actions MUST be `BUY`, `SELL`, and `HOLD`.

#### Scenario: Accept valid hold decision
- **WHEN** the trade agent returns a valid structured decision with action `HOLD`
- **THEN** the system records the decision on the tick
- **AND** the system MUST NOT create a sandbox order

#### Scenario: Accept valid buy or sell decision for execution validation
- **WHEN** the trade agent returns a valid structured decision with action `BUY` or `SELL`
- **THEN** the system records the decision on the tick
- **AND** the system passes the decision to sandbox execution validation

#### Scenario: Reject invalid agent decision shape
- **WHEN** the trade agent returns malformed output, an unsupported action, or invalid quantity fields
- **THEN** the system marks the tick as rejected with reason `INVALID_AGENT_DECISION`
- **AND** the system MUST NOT create a sandbox order

### Requirement: Sandbox execution enforces mechanical trading constraints
The system SHALL validate each structured trade decision before execution. Sandbox execution MUST be long-only and MUST NOT allow buys beyond available cash or sells beyond sellable quantity.

#### Scenario: Execute buy with sufficient available cash
- **WHEN** the agent returns a valid buy decision whose estimated cost is less than or equal to available cash
- **THEN** the system creates a sandbox buy order and fill at the selected sandbox execution price
- **AND** available cash decreases by the filled value
- **AND** pending securities settlement is created for the purchased quantity

#### Scenario: Reject buy with insufficient available cash
- **WHEN** the agent returns a buy decision whose estimated cost exceeds available cash
- **THEN** the system rejects the decision with reason `INSUFFICIENT_AVAILABLE_CASH`
- **AND** the system MUST NOT create a filled sandbox order

#### Scenario: Execute sell with sufficient sellable quantity
- **WHEN** the agent returns a valid sell decision whose quantity is less than or equal to sellable quantity
- **THEN** the system creates a sandbox sell order and fill at the selected sandbox execution price
- **AND** sellable quantity decreases by the filled quantity
- **AND** pending cash settlement is created for the proceeds

#### Scenario: Reject sell of unsettled or unavailable securities
- **WHEN** the agent returns a sell decision whose quantity exceeds sellable quantity
- **THEN** the system rejects the decision with reason `INSUFFICIENT_SELLABLE_QUANTITY`
- **AND** the system MUST NOT create a filled sandbox order

#### Scenario: Reject trade outside trading window
- **WHEN** a worker attempts to execute a buy or sell outside the configured trading windows
- **THEN** the system rejects the decision with reason `OUTSIDE_TRADING_WINDOW`
- **AND** the system MUST NOT create a filled sandbox order

### Requirement: Sandbox settlement follows weekday T+2
The system SHALL simulate T+2 settlement for sandbox securities and cash using Monday through Friday as settlement days. Holiday calendars MUST NOT be used in this phase.

#### Scenario: Buy settlement makes securities sellable on T plus two weekdays
- **WHEN** a buy order fills on trade date `T`
- **THEN** the purchased quantity remains pending
- **AND** the purchased quantity becomes sellable on the second weekday after `T`

#### Scenario: Sell settlement makes cash available on T plus two weekdays
- **WHEN** a sell order fills on trade date `T`
- **THEN** the sale proceeds remain pending cash
- **AND** the sale proceeds become available cash on the second weekday after `T`

#### Scenario: Apply due settlements before agent decision
- **WHEN** the worker starts processing a tick
- **THEN** the system applies all due pending settlements for the session before building the agent input
- **AND** the agent input reflects updated available cash and sellable quantity

#### Scenario: Friday trade settles on Tuesday
- **WHEN** a buy or sell order fills on Friday
- **THEN** the related settlement date is the following Tuesday

### Requirement: Portfolio state is persisted after every terminal tick
The system SHALL persist a portfolio snapshot after every completed, skipped, rejected, or failed tick. Snapshots MUST include enough state to inspect virtual cash, pending settlements, position quantity, latest valuation, and equity.

#### Scenario: Persist snapshot after completed trade tick
- **WHEN** a tick completes after a buy, sell, or hold decision
- **THEN** the system persists a portfolio snapshot linked to the session and tick
- **AND** the snapshot includes available cash, pending cash, total quantity, sellable quantity, pending quantity, latest price, market value, and equity

#### Scenario: Persist snapshot after skipped tick
- **WHEN** a tick is skipped because no fresh market data is available
- **THEN** the system persists a portfolio snapshot linked to the skipped tick
- **AND** the snapshot preserves the latest known portfolio accounting state

### Requirement: Users can inspect sandbox trading history
The system SHALL provide authenticated APIs for reading a session's tick history, sandbox orders, pending and settled settlements, current position, and portfolio snapshots.

#### Scenario: Read session tick history
- **WHEN** a user requests tick history for a sandbox trade session they own
- **THEN** the system returns ticks for that session ordered by tick time
- **AND** the response supports pagination

#### Scenario: Read sandbox orders
- **WHEN** a user requests sandbox orders for a sandbox trade session they own
- **THEN** the system returns only orders linked to that session
- **AND** each order includes status and rejection reason when applicable

#### Scenario: Read current portfolio state
- **WHEN** a user requests the current portfolio state for a sandbox trade session they own
- **THEN** the system returns current cash, pending cash, position quantity, sellable quantity, pending quantity, latest snapshot, and pending settlements
