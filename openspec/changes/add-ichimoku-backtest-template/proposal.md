## Why

The backtest stack currently supports only `buy_and_hold` and
`sma_crossover`, which leaves the product without a trend-following template
that matches how many discretionary stock traders evaluate regime, momentum,
and confirmation together. The backend needs an Ichimoku-based template so
users can backtest a widely used multi-signal strategy through the existing
daily long-only engine without inventing custom logic outside the product.

## What Changes

- Add a new `ichimoku_cloud` backtest template for daily stock backtests
- Define explicit Ichimoku template parameters for Tenkan, Kijun, Senkou B,
  displacement, and warmup history
- Extend the internal backtest flow to load pre-window warmup bars so
  Ichimoku signals can be calculated without distorting the first tradable bars
- Add deterministic Ichimoku entry, exit, and warning logic aligned to the
  current long-only `next_open` execution model
- Expose the new template and parameter metadata through the public backtest
  template catalog and run-request validation
- Keep the execution scope unchanged in v1: one symbol, daily bars, long-only,
  one open position, all-in sizing, and next-open fills

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `agent-backtesting`: expand the supported template catalog to include an
  Ichimoku-based strategy, define its parameter validation, and require
  warmup-history handling for indicators that depend on pre-window bars
- `backtest-api`: expose the Ichimoku template in the public template catalog
  and accept its parameter contract in the synchronous FE-facing backtest run
  API

## Impact

- **Affected code**: internal backtest schemas, template registry, signal
  generation logic, data-loading behavior for warmup history, public backtest
  API schemas, and template presenters
- **Affected APIs**: the `/api/v1/backtests/templates` catalog and public run
  request validation will add one new template and parameter set
- **Data dependencies**: reuses the existing vnstock-backed daily price history
  path, but will use pre-window lookback loading to satisfy Ichimoku warmup
  requirements
- **Execution behavior**: preserves the current long-only engine contract while
  adding a more complex trend-confirmation strategy on top of it
- **Testing**: requires deterministic tests for warmup loading, Ichimoku signal
  generation, schema validation, and FE template-catalog presentation
