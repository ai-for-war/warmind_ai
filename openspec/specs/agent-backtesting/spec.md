# agent-backtesting Specification

## Purpose
TBD - created by archiving change add-agent-backtest-tools. Update Purpose after archive.
## Requirements
### Requirement: Internal backtest runs execute one deterministic daily stock strategy
The system SHALL provide an internal backtest execution capability for AI and
agent workflows that runs exactly one stock symbol per request using daily
price history only. Each run MUST be long-only, MUST use one deterministic
execution model, and MUST reject unsupported scopes such as intraday,
multi-symbol, short-selling, or leverage.

#### Scenario: Run one supported daily backtest
- **WHEN** an internal caller submits a backtest request for one valid stock
  symbol with daily timeframe and a supported template
- **THEN** the system executes exactly one daily backtest run for that symbol
- **AND** the run uses the agreed long-only execution model

#### Scenario: Reject unsupported execution scope
- **WHEN** an internal caller submits a backtest request that asks for
  unsupported scope such as multiple symbols, intraday timeframe, short
  exposure, or leverage
- **THEN** the system rejects the request
- **AND** no backtest run is executed

### Requirement: Backtest runs reuse canonical daily price history from the stock-price layer
The system SHALL source backtest bars through the existing normalized
stock-price history capability so strategy execution operates on canonical
daily OHLCV records. The system MUST validate the symbol before execution and
MUST reject empty or insufficient daily history for the requested backtest
window.

#### Scenario: Load canonical daily bars for a valid request
- **WHEN** an internal caller submits a backtest request for a valid stock
  symbol and date range
- **THEN** the system loads normalized daily bars containing canonical fields
  required for execution
- **AND** the execution engine receives ordered daily backtest bars rather than
  raw upstream payloads

#### Scenario: Reject requests without usable history
- **WHEN** the requested symbol or date range does not produce enough daily
  history to execute the selected template
- **THEN** the system rejects the backtest request with a deterministic error
- **AND** it does not return fabricated metrics or empty placeholder results

### Requirement: V1 strategy input is restricted to fixed templates with explicit parameter validation
The system SHALL support exactly two backtest templates in v1:
`buy_and_hold` and `sma_crossover`. `buy_and_hold` MUST run without strategy
parameters. `sma_crossover` MUST require `fast_window` and `slow_window`, and
the system MUST validate that both are positive and that `fast_window` is less
than `slow_window`.

#### Scenario: Run buy-and-hold without strategy parameters
- **WHEN** an internal caller submits a backtest request with template
  `buy_and_hold`
- **THEN** the system executes the buy-and-hold strategy without requiring
  template parameters
- **AND** the run follows the common execution model shared by v1 templates

#### Scenario: Run SMA crossover with valid windows
- **WHEN** an internal caller submits a backtest request with template
  `sma_crossover`, a positive `fast_window`, and a larger positive
  `slow_window`
- **THEN** the system executes the SMA crossover strategy using those windows
- **AND** signals are generated from the template's moving-average crossover
  rules

#### Scenario: Reject invalid SMA crossover parameters
- **WHEN** an internal caller submits `sma_crossover` with missing,
  non-positive, or inverted window parameters
- **THEN** the system rejects the request
- **AND** the engine does not execute the strategy

### Requirement: V1 execution uses a capital-based long-only model
The system SHALL execute v1 backtests with a capital-based model that defaults
`initial_capital` to `100_000_000` when the caller does not provide an
explicit value. The system MUST use `all_in` position sizing, MUST allow at
most one open long position at a time, MUST ignore repeated buy signals while
already holding, and MUST fill signals on the next bar open.

#### Scenario: Apply default capital and all-in sizing
- **WHEN** an internal caller omits `initial_capital` from a valid backtest
  request
- **THEN** the system uses `100_000_000` as the starting capital
- **AND** position sizing allocates all available capital when entering a new
  position

#### Scenario: Ignore repeated buy signals while holding
- **WHEN** the active strategy generates another buy signal while one long
  position is already open
- **THEN** the system ignores the repeated buy signal
- **AND** it does not open a second position or pyramid into the existing one

#### Scenario: Fill signals on the next bar open
- **WHEN** the strategy generates an entry or exit signal from one completed
  daily bar
- **THEN** the corresponding trade is filled using the next available bar open
- **AND** the system does not use same-bar close execution for that signal

### Requirement: Completed runs return structured backtest outputs for analysis
The system SHALL return successful backtest results with four top-level output
sections: `summary_metrics`, `performance_metrics`, `trade_log`, and
`equity_curve`. `summary_metrics` MUST describe the run context and aggregate
run totals. `performance_metrics` MUST contain derived performance indicators.
`trade_log` MUST contain completed trade records. `equity_curve` MUST contain
time-ordered equity snapshots for the run.

#### Scenario: Return all required result sections
- **WHEN** a backtest run completes successfully
- **THEN** the system returns `summary_metrics`, `performance_metrics`,
  `trade_log`, and `equity_curve`
- **AND** each section follows a stable structured contract suitable for AI
  inspection

#### Scenario: Include completed-trade details in the trade log
- **WHEN** a backtest run produces one or more completed trades
- **THEN** each trade-log entry includes the trade's entry and exit timing,
  prices, position size, invested capital, profit and loss, profit-and-loss
  percentage, and exit reason

#### Scenario: Include per-bar equity snapshots
- **WHEN** a backtest run completes successfully
- **THEN** the equity curve contains time-ordered snapshots across the run
- **AND** each snapshot includes cash, market value, total equity, drawdown
  percentage, and position size for that point in time

### Requirement: Backtest capability remains internal until explicitly exposed to lead-agent tooling
The system SHALL keep the backtest capability internal in this change. The
system MUST NOT register a selectable lead-agent tool or otherwise expose this
capability in the current public lead-agent tool catalog until a later change
explicitly introduces that runtime integration.

#### Scenario: Internal service contract exists without public lead-agent registration
- **WHEN** the application initializes after this change
- **THEN** the backtest capability is available through internal service
  orchestration for future AI integration
- **AND** the current public lead-agent selectable tool catalog does not list a
  backtest tool

