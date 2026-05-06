## Context

The codebase already has stock price reads, intraday data contracts, backtest concepts, lead-agent runtime patterns, MongoDB persistence, and Redis worker execution patterns. The sandbox trade agent is a different product capability from stock research scheduling: it is a stateful paper-trading session that wakes every 3 minutes during Vietnam continuous trading hours and simulates orders against virtual cash and positions.

The user-confirmed scope is intentionally narrow:

- one session trades one symbol
- default virtual capital is `100,000,000 VND`
- sessions run until the user pauses, stops, or deletes them
- sessions only run Monday through Friday
- no holiday calendar
- only continuous trading windows are supported in phase 1: `09:00-11:30` and `13:00-14:45` in `Asia/Saigon`
- the agent makes autonomous decisions
- there is no real broker integration
- T+2 settlement must be simulated
- market data unavailability skips a tick instead of calling the agent
- phase 1 is backend API, persistence, and worker execution

## Goals / Non-Goals

**Goals:**

- Provide organization-scoped CRUD and lifecycle APIs for sandbox trade-agent sessions.
- Run due active sessions every 3 minutes during configured Vietnam trading windows.
- Use a durable worker path for tick execution instead of API-process background work.
- Persist every tick outcome, including skipped ticks, agent decisions, accepted/rejected orders, settlements, and portfolio snapshots.
- Require the trade agent to return a structured `BUY`, `SELL`, or `HOLD` decision.
- Validate decisions in backend execution code before creating sandbox fills.
- Simulate long-only T+2 settlement for both bought securities and sold cash proceeds.
- Keep implementation independent from the stock research schedule dispatcher and stock research report lifecycle.

**Non-Goals:**

- Real broker, exchange, custody, or clearing integration.
- Holiday calendar support.
- ATO or ATC auction simulation.
- Short selling, margin, derivatives, or multi-symbol portfolios.
- Default risk controls such as max drawdown, max order percentage, or max trades per day.
- UI screens or new socket contracts in phase 1.
- Backtesting historical strategy performance.

## Decisions

### D1: Model sandbox trading as sessions, not reports or research schedules

**Decision:** Add a new sandbox trade-agent module with its own session, tick, order, position, settlement, and portfolio records. Do not reuse stock research schedules as the persistence model.

**Rationale:** Stock research schedules create independent report jobs. Trade-agent sessions are long-lived portfolio simulations with mutable cash, positions, pending settlements, and tick history. Reusing report scheduling would couple unrelated lifecycles and make T+2 settlement awkward.

**Alternatives considered:**

- Reuse stock research scheduling: rejected because research occurrences are stateless report generation, while paper trading needs portfolio state.
- Extend backtest APIs: rejected because backtests run over historical bars in one request, while this capability runs incrementally during market hours.

### D2: Use a dedicated due-session dispatcher plus Redis worker execution

**Decision:** Add an internal trade-agent dispatch path that claims due active sessions and enqueues trade-agent tick tasks to Redis. A worker executes the tick and advances `next_run_at`.

**Rationale:** A 3-minute cadence does not fit the existing 15-minute stock research heartbeat. A dedicated dispatcher keeps the capability independent and avoids long-running work inside the API process.

The dispatcher can be implemented as either:

- a worker-side polling loop that runs every 30-60 seconds, or
- an internal endpoint triggered by infrastructure more frequently than every 3 minutes.

Phase 1 should prefer the worker-side polling loop unless deployment already has a simple reliable trigger for sub-3-minute cadence.

**Alternatives considered:**

- In-process FastAPI background tasks: rejected because active sessions must survive API restarts and multi-instance deployments.
- Per-session cloud schedules: rejected because CRUD, idempotency, and operational debugging would be spread across infrastructure and MongoDB.
- Reuse the 15-minute EventBridge heartbeat: rejected because the requirement is 3-minute ticking.

### D3: Store idempotent ticks separately from sessions

**Decision:** Store one tick record per `(session_id, tick_at)` and enforce uniqueness on that pair. Tick states should include at least `dispatching`, `running`, `completed`, `skipped`, `failed`, and `rejected`.

**Rationale:** The dispatcher or worker may retry. A unique tick occurrence prevents duplicate agent decisions and duplicate sandbox fills for the same scheduled wake-up.

The session owns configuration and current scheduling state. Ticks own execution history and auditable inputs/outputs.

### D4: Compute trading windows in `Asia/Saigon` and exclude weekends only

**Decision:** The system uses `Asia/Saigon` for trading-time checks. Sessions may tick only Monday-Friday inside `09:00-11:30` or `13:00-14:45`. No holiday calendar is included.

**Rationale:** This matches the confirmed MVP. Skipping holidays is intentionally out of scope. If a weekday is a market holiday or provider data is stale/unavailable, the worker records a skipped tick.

**Alternatives considered:**

- Official exchange holiday calendar: more accurate but explicitly not needed.
- Server-local timezone: rejected because runtime environment timezone should not affect business logic.

### D5: Treat market data freshness as a hard precondition

**Decision:** Each tick must fetch a market-data snapshot before calling the agent. If there is no fresh usable latest price for the session symbol, the tick is recorded as `skipped` with reason `NO_FRESH_MARKET_DATA`, no agent call is made, and no order is created.

**Rationale:** The agent should not spend tokens or place decisions against stale or absent prices. This also covers weekday holidays without maintaining a holiday calendar.

The implementation should define freshness relative to the current trading window and provider timestamp behavior discovered in the existing stock price service. If provider timestamps are inconsistent, document the runtime-observed behavior near the integration point and optimize for the installed runtime.

### D6: Require structured agent decisions and validate before execution

**Decision:** The trade agent must return a validated structured decision. A minimal decision shape is:

```json
{
  "action": "BUY",
  "quantity_type": "shares",
  "quantity_value": 100,
  "reason": "...",
  "confidence": 0.72
}
```

Allowed actions are `BUY`, `SELL`, and `HOLD`. Execution code validates the decision before creating an order or fill.

**Rationale:** The backend must not parse free-form text to infer trading actions. Structured decisions make tests, rejection reasons, and audit trails possible.

Phase 1 has no default risk caps, but the backend still enforces mechanical sandbox constraints:

- buys cannot exceed available cash
- sells cannot exceed sellable quantity
- pending T+2 securities are not sellable
- pending T+2 cash is not available for buys
- positions are long-only
- orders are rejected outside trading windows

### D7: Simulate T+2 settlement with a ledger

**Decision:** Add settlement records for securities and cash. Before each tick decision, apply all due settlements for the session.

Assumptions for phase 1:

- `T` is the matched sandbox order date in `Asia/Saigon`
- T+2 counts Monday-Friday only
- no holiday adjustments
- buy fills reduce available cash immediately and create pending securities that become sellable on T+2
- sell fills reduce sellable securities immediately and create pending cash that becomes available on T+2
- no cash advance and no margin

**Rationale:** A ledger keeps settlement auditable and avoids hiding pending assets inside aggregate fields only.

### D8: Portfolio snapshots are append-only audit records

**Decision:** After each completed, skipped, or rejected tick, persist a portfolio snapshot containing cash, pending cash, total quantity, sellable quantity, pending quantity, latest price, market value, total equity, realized PnL, and unrealized PnL when calculable.

**Rationale:** Users and tests need to inspect how the sandbox evolved over time. Snapshots also prevent expensive recomputation from all orders for routine reads.

### D9: Keep UI and socket integration out of the initial contract

**Decision:** Phase 1 exposes backend APIs for session state and history. Socket emission may reuse an existing notification pattern only if it does not create new API/socket requirements.

**Rationale:** The core risk is correctness of autonomous decisioning, execution constraints, and settlement. UI can be layered after the state model is stable.

## Risks / Trade-offs

- Weekday-only calendar can tick on Vietnamese holidays -> Skip when market data is unavailable or stale and record `NO_FRESH_MARKET_DATA`.
- LLM output may be invalid or unsafe -> Require structured output validation and reject invalid decisions without execution.
- Agent may repeatedly request impossible trades -> Persist rejection reasons and include current cash, sellable quantity, and pending settlements in the next prompt.
- Provider market data timestamps may be inconsistent -> Verify runtime behavior before implementing freshness checks and document any mismatch near the integration point.
- Worker crash after claiming a tick -> Use tick state and stale claim recovery so a later worker can retry safely.
- Duplicate dispatch attempts -> Unique `(session_id, tick_at)` prevents duplicate fills.
- No default risk controls -> Mechanical constraints prevent impossible sandbox accounting, but users can still lose virtual capital through agent decisions.
- T+2 without holidays is not market-accurate on holidays -> Accepted MVP trade-off based on user scope.

## Migration Plan

1. Add domain schemas and models for sandbox trade-agent sessions, ticks, decisions, orders, positions, settlements, and portfolio snapshots.
2. Add MongoDB repositories and indexes, including unique tick occurrence and settlement lookup indexes.
3. Add session service APIs for CRUD, pause, resume, stop, delete, and history reads.
4. Add trading calendar/window and T+2 settlement calculation services.
5. Add market-data snapshot service using existing stock price reads.
6. Add structured trade-agent prompt/runtime and decision validation.
7. Add sandbox execution service for settlement application, decision validation, fills, orders, positions, settlements, and snapshots.
8. Add Redis queue, dispatcher, and worker for due session ticks.
9. Add tests for validation, scheduling, market-window checks, settlement, execution constraints, idempotency, and worker lifecycle.

Rollback can stop the trade-agent worker and disable the dispatcher. Existing stock research, backtest, and stock price APIs are unaffected because this change introduces a new capability rather than modifying their contracts.
