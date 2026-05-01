## 1. Domain Models, Schemas, and Indexes

- [x] 1.1 Add sandbox trade session domain models and API schemas for create, update, lifecycle actions, list, read, and status responses.
- [x] 1.2 Add tick, structured decision, sandbox order, position, settlement, and portfolio snapshot domain models and response schemas.
- [x] 1.3 Add enum values for session status, tick status, action, order side, order status, settlement asset type, and settlement status.
- [x] 1.4 Add MongoDB indexes for organization-scoped session listing, active due-session lookup, unique `(session_id, tick_at)` ticks, session order history, session settlement lookup, and latest portfolio snapshots.

## 2. Repositories and Session Services

- [x] 2.1 Add repositories for sandbox trade sessions, ticks, orders, positions, settlements, and portfolio snapshots.
- [x] 2.2 Implement session creation with symbol validation, uppercase normalization, default `100000000` VND virtual capital, and initial cash/position state.
- [x] 2.3 Implement organization-scoped session list, read, pause, resume, stop, and delete service methods.
- [x] 2.4 Implement history read service methods for ticks, orders, settlements, current position, and latest portfolio state.

## 3. Trading Calendar and Tick Scheduling

- [ ] 3.1 Add settings for sandbox trade-agent cadence, queue name, worker poll interval, and Vietnam continuous trading windows.
- [ ] 3.2 Implement `Asia/Saigon` weekday and trading-window eligibility checks for `09:00-11:30` and `13:00-14:45`.
- [ ] 3.3 Implement next-eligible-run calculation for active sessions, weekend skipping, lunch-break skipping, and end-of-day rollover.
- [ ] 3.4 Implement idempotent due-session dispatch that creates or claims one tick per `(session_id, tick_at)` and enqueues a worker task.
- [ ] 3.5 Implement stale tick claim recovery without allowing duplicate sandbox execution side effects.

## 4. Market Data Snapshot

- [ ] 4.1 Add a market-data snapshot service that uses the existing stock price/intraday read path for the session symbol.
- [ ] 4.2 Define and implement freshness validation for latest usable price during a trading window, based on verified runtime behavior of the existing provider integration.
- [ ] 4.3 Persist market-data snapshot details or deterministic summaries with each processable tick.
- [ ] 4.4 Mark ticks as `skipped` with `NO_FRESH_MARKET_DATA` without calling the agent when no fresh price is available.

## 5. Trade Agent Runtime

- [ ] 5.1 Add a sandbox trade-agent system prompt that receives market data, available cash, sellable quantity, pending settlements, recent decisions, and current portfolio state.
- [ ] 5.2 Add structured decision schema validation for `BUY`, `SELL`, and `HOLD` decisions.
- [ ] 5.3 Implement trade-agent invocation for processable ticks using the existing model/runtime patterns where appropriate.
- [ ] 5.4 Record valid decisions on ticks and reject malformed or unsupported decisions with `INVALID_AGENT_DECISION`.

## 6. Sandbox Execution and T+2 Settlement

- [ ] 6.1 Implement weekday-only T+2 settlement date calculation in `Asia/Saigon` with no holiday calendar.
- [ ] 6.2 Apply due cash and securities settlements before building each tick's agent input.
- [ ] 6.3 Implement long-only buy validation against available cash and sell validation against sellable quantity.
- [ ] 6.4 Implement sandbox buy fills that reduce available cash immediately and create pending securities settlement.
- [ ] 6.5 Implement sandbox sell fills that reduce sellable quantity immediately and create pending cash settlement.
- [ ] 6.6 Implement rejected execution outcomes for insufficient cash, insufficient sellable quantity, and outside trading window.
- [ ] 6.7 Persist portfolio snapshots after completed, skipped, rejected, and failed ticks.

## 7. Worker and API Wiring

- [ ] 7.1 Add Redis task payload schema and queue helper for sandbox trade-agent tick tasks.
- [ ] 7.2 Add sandbox trade-agent worker that dispatches due sessions, processes tick tasks, advances `next_run_at`, and records terminal tick states.
- [ ] 7.3 Add authenticated API routes for session create, list, read, pause, resume, stop, delete, tick history, order history, settlement history, and current portfolio state.
- [ ] 7.4 Wire sandbox trade-agent routes into the v1 API router with existing authentication and organization dependencies.
- [ ] 7.5 Add optional internal dispatch endpoint only if the deployment path requires an external trigger instead of worker polling.

## 8. Tests and Verification

- [ ] 8.1 Add unit tests for session schema validation, symbol normalization, default capital, and ownership enforcement.
- [ ] 8.2 Add unit tests for trading-window checks and next-run calculation across morning, lunch break, afternoon, end of day, Friday, Saturday, and Sunday.
- [ ] 8.3 Add unit tests for T+2 weekday settlement, including Friday-to-Tuesday settlement.
- [ ] 8.4 Add unit tests for execution constraints: sufficient cash buy, insufficient cash rejection, sufficient sellable sell, unsettled security sell rejection, and outside-window rejection.
- [ ] 8.5 Add worker tests for idempotent tick dispatch, concurrent claim behavior, stale claim recovery, skipped market-data ticks, valid hold decisions, valid trade decisions, and invalid agent output.
- [ ] 8.6 Add API integration tests for session CRUD, lifecycle transitions, history reads, and organization scope isolation.
- [ ] 8.7 Run the relevant unit and integration test suites and fix regressions.

## 9. Documentation

- [ ] 9.1 Document sandbox trade-agent environment settings and worker startup requirements.
- [ ] 9.2 Document MVP trading assumptions: Monday-Friday only, no holidays, continuous trading windows only, no ATO/ATC, one symbol per session, long-only, and no real broker integration.
- [ ] 9.3 Document T+2 sandbox settlement behavior and the difference between available cash, pending cash, sellable quantity, and pending securities.
