## ADDED Requirements

### Requirement: Technical analyst provides structured technical evidence
The system SHALL provide a dedicated `technical_analyst` subagent for Vietnam-listed equity technical analysis. The technical analyst MUST return a structured synthesis-ready technical evidence package and MUST NOT produce the parent stock agent's final all-factor investment recommendation.

#### Scenario: Complete technical read
- **WHEN** the technical analyst receives a delegated objective asking for chart state, technical trend, indicators, support, resistance, momentum, volatility, or volume confirmation
- **THEN** the system returns a structured result with `mode` set to `technical_read`
- **AND** the result includes trend, momentum, volatility state, support levels, resistance levels, technical signals, risks, uncertainties, and indicator evidence
- **AND** the result does not include unsolicited entry zone, stop loss, or target fields as a trading plan

#### Scenario: Complete trading plan
- **WHEN** the technical analyst receives a delegated objective asking for entry, stop loss, target, buy zone, setup, risk/reward, or technical trading plan
- **THEN** the system returns a structured result with `mode` set to `trading_plan`
- **AND** the result includes entry zone, stop loss, target levels, risk/reward, invalidation condition, and relevant technical evidence
- **AND** the result keeps final all-factor recommendation responsibility with the parent stock agent

### Requirement: Technical indicators are computed deterministically from canonical price history
The system SHALL provide a `compute_technical_indicators` tool for the technical analyst. The tool MUST load canonical OHLCV history through the existing stock price service, MUST compute indicators with the `ta` library, and MUST NOT require the agent to call `load_price_history` first or pass raw OHLCV bars into the tool.

#### Scenario: Compute indicators from lookback length
- **WHEN** the technical analyst calls `compute_technical_indicators` with a stock symbol, interval `1D`, a `length` value, and an indicator set
- **THEN** the tool loads historical OHLCV data through the stock price service using that lookback-style history query
- **AND** the tool computes the requested technical indicators from the loaded canonical bars
- **AND** the tool returns a structured technical indicator snapshot

#### Scenario: Compute indicators from explicit date range
- **WHEN** the technical analyst calls `compute_technical_indicators` with a stock symbol, interval `1D`, a `start` value, optional `end` value, and an indicator set
- **THEN** the tool loads historical OHLCV data through the stock price service using that explicit time range
- **AND** the tool computes the requested technical indicators from the loaded canonical bars
- **AND** the tool returns a structured technical indicator snapshot

#### Scenario: Indicator computation does not depend on raw history inspection
- **WHEN** the technical analyst calls `compute_technical_indicators` without a previous `load_price_history` call
- **THEN** the tool still loads the required OHLCV history internally
- **AND** the tool completes indicator computation when upstream data is available

### Requirement: Indicator tool supports preset sets and custom configuration
The `compute_technical_indicators` tool SHALL support preset indicator sets and custom indicator configuration. The phase-one presets MUST include at least `core`, `trend`, `momentum`, `volatility`, `volume`, and `custom`. The `core` set MUST include moving averages, momentum, volatility, volume, and support/resistance evidence.

#### Scenario: Compute core preset
- **WHEN** the technical analyst calls `compute_technical_indicators` with `indicator_set` set to `core`
- **THEN** the tool computes the phase-one core indicator package
- **AND** the package includes SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, OBV, volume average, and support/resistance evidence when enough data is available

#### Scenario: Compute custom configuration
- **WHEN** the technical analyst calls `compute_technical_indicators` with `indicator_set` set to `custom` and a custom configuration
- **THEN** the tool computes indicators according to the supplied custom windows and included indicator families
- **AND** the tool returns results under the same structured technical indicator snapshot contract

#### Scenario: Report unavailable indicator values
- **WHEN** the loaded price history is insufficient for one or more requested indicators
- **THEN** the tool reports which indicators could not be computed
- **AND** the tool MUST NOT fabricate missing indicator values

### Requirement: Raw price history inspection is optional
The system SHALL provide a `load_price_history` tool for optional raw OHLCV inspection by the technical analyst. This tool MUST use the existing stock price service and MUST expose the stock price history query shape of either `length` or `start` with optional `end`.

#### Scenario: Inspect raw history by length
- **WHEN** the technical analyst calls `load_price_history` with a stock symbol, interval `1D`, and a `length` value
- **THEN** the tool returns canonical OHLCV records for that lookback-style history query

#### Scenario: Inspect raw history by range
- **WHEN** the technical analyst calls `load_price_history` with a stock symbol, interval `1D`, a `start` value, and optional `end` value
- **THEN** the tool returns canonical OHLCV records for that explicit time range

#### Scenario: Indicator computation skips raw inspection
- **WHEN** the technical analyst does not need raw candle inspection
- **THEN** it can skip `load_price_history`
- **AND** it can still use `compute_technical_indicators` as the primary analysis tool

### Requirement: Technical analyst can run deterministic backtests
The system SHALL provide a `run_backtest` tool for the technical analyst that reuses the existing internal backtest service and registered templates. The tool MUST NOT execute arbitrary strategy code generated by the model.

#### Scenario: Run supported backtest template
- **WHEN** the technical analyst calls `run_backtest` with one valid stock symbol, daily timeframe, a supported template, and valid template parameters
- **THEN** the tool executes the request through the existing internal backtest service
- **AND** the tool returns structured summary and performance evidence suitable for technical analyst synthesis

#### Scenario: Reject unsupported backtest scope
- **WHEN** the technical analyst calls `run_backtest` with unsupported scope such as intraday timeframe, multiple symbols, unsupported template, or arbitrary strategy code
- **THEN** the tool rejects the request through deterministic validation
- **AND** no unsupported backtest execution occurs

### Requirement: Technical analysis uses daily interval in phase one
The technical analyst SHALL support interval `1D` in phase one. The technical analyst MUST NOT claim support for intraday, weekly, or monthly technical-analysis execution until those intervals are explicitly introduced.

#### Scenario: Use daily interval
- **WHEN** the technical analyst runs phase-one indicator computation or backtest evidence
- **THEN** it uses daily interval `1D`

#### Scenario: Unsupported interval requested
- **WHEN** a delegated objective or tool call asks technical analysis to execute on an unsupported interval
- **THEN** the technical analyst states the interval limitation or returns a bounded unsupported-scope outcome
- **AND** it does not silently substitute another interval as if it matched the user's request
