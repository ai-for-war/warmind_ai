## 1. Backtest contracts and module setup

- [x] 1.1 Create the `app/services/backtest` module structure for data loading, templates, engine, metrics, and orchestration
- [x] 1.2 Add backtest domain schemas for run requests, template parameters, summary metrics, performance metrics, trade-log entries, equity-curve entries, and run responses
- [x] 1.3 Implement request validation for supported scope only: one symbol, daily timeframe, long-only execution, supported template IDs, and default `initial_capital = 100_000_000`

## 2. Data loading and template definitions

- [x] 2.1 Implement a `BacktestDataService` that reuses the existing stock-price history capability to load canonical daily OHLCV bars for a validated symbol and date range
- [x] 2.2 Reject empty or insufficient history before strategy execution begins
- [x] 2.3 Implement the `buy_and_hold` template with no required strategy parameters
- [x] 2.4 Implement the `sma_crossover` template with validated `fast_window` and `slow_window` parameters and crossover signal generation rules

## 3. Execution engine and metrics

- [x] 3.1 Implement the capital-based execution engine with `all_in` sizing, one open long position at a time, ignored repeated buy signals, and next-open fills
- [x] 3.2 Implement end-of-window close behavior so runs return completed trade and equity results
- [x] 3.3 Implement summary-metric and performance-metric calculation for completed runs
- [x] 3.4 Implement structured `trade_log` output with entry, exit, position size, invested capital, PnL, PnL percent, and exit reason
- [x] 3.5 Implement structured `equity_curve` output with per-bar cash, market value, total equity, drawdown percent, and position size

## 4. Internal orchestration and integration boundaries

- [ ] 4.1 Implement the top-level backtest service that orchestrates request validation, data loading, template execution, metrics assembly, and response shaping
- [ ] 4.2 Wire the backtest service into shared internal dependency factories if required by the current application service layout
- [ ] 4.3 Ensure this change does not register a selectable lead-agent tool or otherwise expose the backtest capability in the current public lead-agent tool catalog

## 5. Tests and verification

- [x] 5.1 Add unit tests for request and template-parameter validation, including invalid SMA window combinations
- [x] 5.2 Add deterministic tests for buy-and-hold execution, SMA crossover entry and exit behavior, and ignored repeated buy signals while holding
- [x] 5.3 Add tests for next-open fill timing, end-of-window close behavior, and one-position long-only execution semantics
- [x] 5.4 Add tests for summary metrics, performance metrics, trade-log records, and equity-curve output shapes and values
- [ ] 5.5 Run the relevant backtest and stock-price test suites and resolve any failures introduced by the new capability
