## Why

Stock agent currently has a typed subagent registry with a generic worker and an event analyst, but technical analysis still has no dedicated specialist. This leaves chart interpretation, indicator computation, trading-plan construction, and backtest evidence either generic or prompt-driven instead of deterministic and testable.

This change adds a dedicated technical analyst subagent that computes indicators from canonical stock price history, returns structured technical evidence to the parent stock agent, and supports trading-plan analysis with backtest context when the user asks for entry, stop, target, setup, or strategy validation.

## What Changes

- Add a preset `technical_analyst` subagent to the stock-agent delegation registry.
- Create a dedicated technical analyst runtime with its own prompt, tool surface, middleware, and structured output contract.
- Add technical-analysis tools:
  - `compute_technical_indicators`: self-contained indicator tool that loads canonical OHLCV history through the stock price layer and computes indicators with the `ta` Python library.
  - `load_price_history`: optional raw OHLCV inspection tool; it is not required before indicator computation.
  - `run_backtest`: technical analyst tool that delegates deterministic strategy evaluation to the existing backtest service.
- Support two analyst modes:
  - `technical_read`: trend, momentum, volatility, support/resistance, volume confirmation, risks, and uncertainties.
  - `trading_plan`: entry zone, stop loss, targets, risk/reward, invalidation condition, and backtest summary when relevant.
- Support `1D` as the phase-one interval.
- Support both preset indicator sets and custom indicator configuration in `compute_technical_indicators`.
- Add `ta` as the technical indicator dependency.
- Update stock-agent orchestration guidance so the parent routes chart, indicator, setup, technical trend, entry, stop, target, and technical backtest tasks to `technical_analyst`.

## Capabilities

### New Capabilities

- `stock-technical-analysis`: Dedicated technical analyst behavior, tool contracts, indicator computation, trading-plan output, and backtest usage for Vietnam-listed equities.

### Modified Capabilities

- `stock-agent-runtime`: Extend stock-agent typed delegation to support the preset `technical_analyst` subagent and route technical-analysis subtasks to it.

## Impact

- **Affected code**:
  - `app/agents/implementations/stock_agent/delegation.py`
  - `app/agents/implementations/stock_agent/tools.py`
  - `app/agents/implementations/stock_agent/tool_catalog.py`
  - `app/agents/implementations/stock_agent/middleware/orchestration.py`
  - `app/prompts/system/stock_agent.py`
  - new `app/agents/implementations/technical_analyst/` module
  - technical-analysis service/helper modules if the indicator engine is separated from the agent tools
- **Dependencies**:
  - Add `ta` for deterministic indicator computation on Pandas-backed OHLCV data.
- **Runtime behavior**:
  - Parent stock agent remains responsible for final user-facing synthesis and recommendation labels.
  - Technical analyst returns a synthesis-ready structured evidence package, not a final all-factor recommendation.
  - Indicator computation uses canonical stock price history through the existing stock price layer; it must not call `vnstock` directly.
  - Backtesting reuses the existing backtest service and registered templates; the agent does not execute arbitrary strategy code.
- **Public API**:
  - No stock-agent conversation endpoint changes are required.
  - No public stock price or backtest API changes are required for the phase-one agent integration.
