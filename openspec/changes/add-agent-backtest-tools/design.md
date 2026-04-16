## Context

The backend already has normalized stock price history reads for one symbol via
the stock-price stack, but there is no application-owned backtest layer that
can turn those bars into deterministic strategy results for AI workflows.
Today an agent that wants to evaluate a strategy would have to improvise its
own calculations in prompts, which is hard to validate, hard to test, and
likely to drift from one run to another.

This change is cross-cutting because it introduces:

- a new service area under `app/services/backtest`
- internal request/response schemas for backtest execution
- orchestration that depends on the existing stock price history capability
- a template registry plus execution engine and metrics builder
- future agent-tool integration points that must remain stable even before the
  tool is exposed in the lead-agent catalog

The confirmed v1 product decisions are:

- the capability is internal for AI and agent flows only
- one run covers exactly one stock symbol
- timeframe is daily only
- execution is long-only
- position sizing is `all_in`
- only one open position may exist at a time
- repeated buy signals while already holding a position are ignored
- default `initial_capital` is `100_000_000`
- v1 templates are `buy_and_hold` and `sma_crossover`
- outputs must include `summary_metrics`, `performance_metrics`,
  `trade_log`, and `equity_curve`
- Vietnam-market execution rules such as fees, tax, lot-size, settlement, and
  margin are out of scope for now

## Goals / Non-Goals

**Goals:**
- Add a deterministic internal backtest orchestration flow under
  `app/services/backtest`
- Reuse the existing normalized daily price history path instead of duplicating
  upstream quote integration inside the backtest engine
- Keep strategy input narrow in v1 through fixed templates with explicit
  parameter validation
- Standardize one execution model so results remain reproducible across runs
- Return structured outputs that downstream AI code can inspect without
  re-deriving metrics from raw bars

**Non-Goals:**
- Add public HTTP endpoints for backtest execution in this change
- Register backtest tools in the lead-agent selectable tool catalog in this
  change
- Support free-form strategy expressions or natural-language strategy parsing
- Support intraday, multi-symbol, short-selling, leverage, or portfolio
  backtests
- Implement Vietnam-market microstructure rules such as fees, tax, lot-size,
  settlement timing, or margin constraints
- Add optimization, parameter sweeps, or batch comparison runs in v1

## Decisions

### D1: Keep backtest orchestration in a dedicated `app/services/backtest` module tree

**Decision**: Create a dedicated service area under `app/services/backtest`
with separate responsibilities for data loading, template resolution,
execution, metrics, and orchestration.

Recommended module split:

- `app/services/backtest/data_service.py`
- `app/services/backtest/templates.py`
- `app/services/backtest/engine.py`
- `app/services/backtest/metrics.py`
- `app/services/backtest/service.py`

Supporting schemas can live outside that tree in domain schema modules, but
the executable orchestration belongs in `app/services/backtest`.

**Rationale**:
- matches the requested location for business logic
- prevents the existing stock price modules from absorbing simulation concerns
- keeps the future agent-tool wrapper thin because the main orchestration lives
  behind one service boundary

**Alternatives considered:**
- **Add backtest logic under `app/services/stocks`**: rejected because it mixes
  quote retrieval with simulation semantics and makes future expansion harder
- **Add backtest logic directly in agent tooling code**: rejected because the
  engine must remain testable and reusable outside one runtime wrapper

### D2: Reuse the existing stock-price history capability through a dedicated backtest data adapter

**Decision**: The backtest layer will load daily bars through a dedicated
`BacktestDataService` that depends on the existing stock-price stack for symbol
validation, normalized history payloads, and upstream data access. The
backtest engine itself will only see canonical daily bars such as `time`,
`open`, `high`, `low`, `close`, and `volume`.

Recommended flow:

- validate the requested symbol through the existing stock-price path
- request daily history for the supplied date range
- convert the normalized history response into ordered backtest bars
- reject empty or insufficient history before strategy execution

**Rationale**:
- avoids duplicating `vnstock` gateway behavior and symbol-validation logic
- keeps backtest inputs aligned with the backend's canonical daily price format
- lets future improvements in the stock-price layer benefit backtests too

**Alternatives considered:**
- **Call `vnstock` directly from the backtest engine**: rejected because it
  duplicates integration logic and increases drift risk
- **Consume stock-price HTTP endpoints internally**: rejected because in-process
  service reuse is simpler and avoids unnecessary transport coupling

### D3: Restrict v1 strategy input to fixed templates compiled into deterministic signals

**Decision**: V1 accepts only two fixed templates:

- `buy_and_hold`
- `sma_crossover`

Each template owns its own parameter schema and signal generation rules.
`buy_and_hold` needs no strategy parameters. `sma_crossover` requires
`fast_window` and `slow_window`, with validation that both are positive and
`fast_window < slow_window`.

**Rationale**:
- fixed templates are easy to validate, document, and test
- the agreed v1 scope values control and determinism over expressiveness
- template-specific parameter schemas reduce ambiguous agent inputs

**Alternatives considered:**
- **Structured strategy specs in v1**: rejected because they add a parsing and
  validation surface the user explicitly deferred
- **Natural-language strategy parsing**: rejected because it is too unstable for
  a first application-owned backtest engine

### D4: Standardize one capital-based daily execution model for v1

**Decision**: Use one execution model with these rules:

- `initial_capital` defaults to `100_000_000`
- position sizing is `all_in`
- only one long position may be open at a time
- a new buy signal is ignored while already holding
- signals detected from bar `t` are filled on the next bar open (`next_open`)
- if the strategy remains long at the end of the requested window, the engine
  closes that position on the final available bar so the run returns completed
  trade and equity results

**Rationale**:
- `next_open` avoids same-bar look-ahead bias for daily strategies
- `all_in` matches the current one-symbol scope and keeps result interpretation
  simple
- end-of-window closing keeps the output complete and makes summary metrics and
  trade logs easier to consume

**Alternatives considered:**
- **`same_close` execution**: rejected because it is more prone to look-ahead
  bias when signals are derived from the closing bar
- **Partial sizing or pyramiding**: rejected because one-symbol v1 does not need
  the added complexity
- **Leave final positions open**: rejected because incomplete PnL makes result
  consumption and testing harder

### D5: Return a structured result contract optimized for AI analysis

**Decision**: Every successful run returns:

- `summary_metrics`
- `performance_metrics`
- `trade_log`
- `equity_curve`

Recommended contents:

- `summary_metrics`: run metadata such as symbol, template ID, timeframe,
  date range, initial capital, ending equity, and total trades
- `performance_metrics`: derived indicators such as total return,
  annualized return, max drawdown, win rate, profit factor, average win,
  average loss, and expectancy
- `trade_log`: one completed-trade entry with entry/exit timestamps, prices,
  shares, invested capital, PnL, PnL percent, and exit reason
- `equity_curve`: one per-bar series with time, cash, market value, total
  equity, drawdown percent, and position size

**Rationale**:
- AI workflows need both high-level summary and inspectable detail
- separating run metadata from performance metrics keeps outputs easier to scan
- trade log and equity curve allow downstream explanation without rerunning the
  engine

**Alternatives considered:**
- **Return only summary metrics**: rejected because the user explicitly wants
  trade-level and equity-level detail
- **Return raw bars plus recomputation guidance**: rejected because the app
  should own backtest semantics instead of pushing that work back to agents

### D6: Keep the capability internal until the result contract is proven

**Decision**: This change defines the backtest capability and its internal
service contracts, but does not register a selectable lead-agent tool or expose
the capability in the current public lead-agent catalog. Any future agent tool
must wrap the backtest service instead of embedding strategy logic directly in
tool handlers.

**Rationale**:
- matches the requested rollout order: inspect capability first, expose later
- allows the service contract and result shape to settle before prompt-facing
  integration
- keeps this change focused on deterministic backtesting instead of runtime UX

**Alternatives considered:**
- **Expose the tool immediately in lead-agent**: rejected because the user wants
  to review the capability before adding it to the tool surface
- **Skip internal contract design until tool exposure**: rejected because the
  service layer should be stable before runtime integration

## Risks / Trade-offs

**[Daily backtests depend on the correctness and continuity of upstream history data]** -> Mitigation:
reuse the backend's normalized stock-price history path and reject empty or
insufficient datasets before strategy execution.

**[`next_open` fills require one additional bar after a signal]** -> Mitigation:
document the execution model clearly and avoid generating fills when the next
bar does not exist, except for the explicit end-of-window close rule.

**[`all_in` one-position logic limits realism for future strategies]** -> Mitigation:
accept the simplification for one-symbol v1 and isolate execution rules inside
the engine so they can evolve later.

**[Template-specific metric behavior can become ambiguous without explicit result semantics]** -> Mitigation:
define one stable response contract and test deterministic scenarios for both
templates.

**[Delaying lead-agent tool exposure postpones end-to-end runtime validation]** -> Mitigation:
lock the internal service request/response contract now so a future tool wrapper
becomes a thin integration step rather than a redesign.

## Migration Plan

1. Add domain schemas for backtest request, template parameters, trade-log
   entries, equity-curve entries, and response metrics.
2. Add `BacktestDataService` under `app/services/backtest` to load and validate
   canonical daily bars through the existing stock-price path.
3. Add a template registry for `buy_and_hold` and `sma_crossover`, including
   parameter validation and signal-generation helpers.
4. Add the execution engine that manages cash, one open long position, all-in
   sizing, ignored duplicate buy signals, next-open fills, and end-of-window
   close behavior.
5. Add the metrics builder for summary metrics, performance metrics, trade log,
   and equity curve.
6. Add the top-level backtest service that orchestrates request validation,
   data loading, template execution, and response assembly.
7. Wire the service into shared internal dependency factories if required by the
   current application service layout.
8. Add deterministic unit tests for:
   - template parameter validation
   - buy-and-hold execution behavior
   - SMA crossover entry and exit behavior
   - one-position and ignored-repeat-buy semantics
   - next-open execution timing
   - metrics, trade-log, and equity-curve shape and values

**Rollback**

- remove the `app/services/backtest` modules and supporting backtest schemas
- remove any dependency wiring added for the backtest service
- leave the stock-price stack unchanged because it remains independently useful

## Open Questions

- None for the currently agreed v1 scope.
