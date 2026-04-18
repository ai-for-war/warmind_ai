## MODIFIED Requirements

### Requirement: Backtest runs reuse canonical daily price history from the stock-price layer
The system SHALL source backtest bars through the existing normalized
stock-price history capability so strategy execution operates on canonical
daily OHLCV records. The system MUST validate the symbol before execution and
MUST reject empty or insufficient daily history for the requested backtest
window. For templates that depend on lookback indicators, the system MUST load
enough pre-window history to satisfy the template's warmup requirement before
the first tradable bar in the requested window.

#### Scenario: Load canonical daily bars with warmup for a lookback template
- **WHEN** an internal caller submits a backtest request for a valid stock
  symbol, a date range, and a template that requires warmup history
- **THEN** the system loads normalized daily bars that include both pre-window
  warmup bars and tradable bars for the requested window
- **AND** only bars within the requested backtest window are eligible for
  signal execution, trade fills, and reported outputs

#### Scenario: Reject requests without enough warmup or tradable history
- **WHEN** the requested symbol and date range do not produce enough daily
  history to satisfy the selected template's warmup and tradable-bar
  requirements
- **THEN** the system rejects the backtest request with a deterministic error
- **AND** it does not return fabricated metrics or empty placeholder results

### Requirement: V1 strategy input is restricted to fixed templates with explicit parameter validation
The system SHALL support exactly three backtest templates in v1:
`buy_and_hold`, `sma_crossover`, and `ichimoku_cloud`. `buy_and_hold` MUST run
without strategy parameters. `sma_crossover` MUST require `fast_window` and
`slow_window`, and the system MUST validate that both are positive and that
`fast_window` is less than `slow_window`. `ichimoku_cloud` MUST require
positive `tenkan_window`, `kijun_window`, `senkou_b_window`,
`displacement`, and `warmup_bars`, and the system MUST validate that
`tenkan_window < kijun_window < senkou_b_window` and that `warmup_bars` is at
least `senkou_b_window + displacement`.

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

#### Scenario: Run Ichimoku with valid template parameters
- **WHEN** an internal caller submits a backtest request with template
  `ichimoku_cloud` and valid Tenkan, Kijun, Senkou B, displacement, and
  warmup parameters
- **THEN** the system executes the Ichimoku strategy using those values
- **AND** signals are generated from the template's aligned cloud and
  confirmation rules

#### Scenario: Reject invalid Ichimoku parameters
- **WHEN** an internal caller submits `ichimoku_cloud` with missing,
  non-positive, misordered, or insufficient warmup parameters
- **THEN** the system rejects the request
- **AND** the engine does not execute the strategy

## ADDED Requirements

### Requirement: Ichimoku template uses aligned trend-following entry and exit rules
The system SHALL implement `ichimoku_cloud` as a deterministic trend-following
template for the existing long-only daily backtest engine. The template MUST
emit a buy signal only when the completed bar closes above the aligned cloud,
the aligned cloud is bullish, a bullish Tenkan/Kijun crossover occurs on that
completed bar, and the Chikou confirmation rule is satisfied relative to price
`displacement` bars back. The template MUST emit a sell signal when the
completed bar closes below the aligned cloud, or when a bearish Tenkan/Kijun
crossover occurs on a completed bar that also closes below Kijun.

#### Scenario: Emit a bullish Ichimoku entry signal
- **WHEN** a completed tradable bar closes above the aligned cloud
- **AND** the aligned cloud is bullish
- **AND** Tenkan crosses above Kijun on that bar
- **AND** the Chikou confirmation rule is satisfied
- **THEN** the template emits one buy signal for that completed bar

#### Scenario: Emit a bearish Ichimoku exit signal on cloud breakdown
- **WHEN** a completed tradable bar closes below the aligned cloud
- **THEN** the template emits one sell signal for that completed bar

#### Scenario: Emit a bearish Ichimoku exit signal on crossover and Kijun loss
- **WHEN** a completed tradable bar produces a bearish Tenkan/Kijun crossover
- **AND** that same bar closes below Kijun
- **THEN** the template emits one sell signal for that completed bar

### Requirement: Ichimoku template evaluates warning conditions without forcing execution
The system SHALL evaluate warning conditions for `ichimoku_cloud` so the
template can distinguish weakening trend conditions from confirmed exit
conditions. Warning evaluation MUST NOT create additional trades by itself.

#### Scenario: Warning state does not create an exit by itself
- **WHEN** a completed tradable bar triggers an Ichimoku warning condition
- **AND** no confirmed Ichimoku sell condition is met
- **THEN** the template does not emit a sell signal for that bar
- **AND** the current position remains governed by the existing execution model
