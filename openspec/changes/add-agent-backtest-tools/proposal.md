## Why

The backend now has normalized stock price history and intraday reads, but the
AI stack still lacks a controlled way to evaluate trading ideas against that
data. The product needs an internal backtest capability so agents can run
repeatable stock-strategy evaluations without inventing their own calculations
or exposing unstable strategy logic directly in prompts.

## What Changes

- Add an internal backtest service under `app/services/backtest` for
  single-symbol, daily, long-only backtests
- Support fixed strategy templates in v1 instead of free-form strategy logic
- Ship two v1 templates: `buy_and_hold` and `sma_crossover`
- Standardize one capital-based execution model with default
  `initial_capital = 100_000_000`, `all_in` position sizing, and one open
  position at a time
- Return structured backtest outputs with `summary_metrics`,
  `performance_metrics`, `trade_log`, and `equity_curve`
- Keep the capability internal for AI and agent workflows first; do not add it
  to the public lead-agent selectable tool catalog in this change

## Capabilities

### New Capabilities
- `agent-backtesting`: provide an internal stock backtest capability for AI and
  agent workflows using daily price history, fixed strategy templates, a stable
  execution model, and structured result outputs

### Modified Capabilities
- None.

## Impact

- **Affected code**: new backtest modules under `app/services/backtest`, new
  request/response schemas for backtest execution, and dependency wiring for
  internal orchestration
- **Data dependencies**: reuses the existing stock price history capability and
  normalized daily OHLCV data already sourced from `vnstock` through the stock
  price layer
- **AI integration**: introduces internal contracts suitable for future agent
  tools, but intentionally stops short of registering them in the lead-agent
  tool catalog during this change
- **Execution scope**: v1 is limited to one stock symbol per run, daily
  timeframe only, long-only execution, `all_in` sizing, and no Vietnam-market
  microstructure rules such as fees, tax, lot-size, or settlement constraints
- **Testing**: requires deterministic tests for template behavior, order
  execution assumptions, metrics calculation, and structured result shapes
