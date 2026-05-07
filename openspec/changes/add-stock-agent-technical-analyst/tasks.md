## 1. Dependency And Technical Analysis Models

- [ ] 1.1 Add the `ta` dependency to backend dependency files.
- [ ] 1.2 Create technical analyst output schemas for `TechnicalAnalystOutput`, indicator snapshots, trading plans, backtest summaries, signals, risks, and uncertainties.
- [ ] 1.3 Create input schemas for `compute_technical_indicators`, `load_price_history`, and `run_backtest`.
- [ ] 1.4 Add validation helpers that parse structured technical analyst output and reject malformed payloads.

## 2. Indicator Engine And Tool Implementation

- [ ] 2.1 Implement OHLCV loading for technical-analysis tools through `StockPriceService.get_history`.
- [ ] 2.2 Implement `compute_technical_indicators` so it self-loads canonical OHLCV and computes preset indicator sets with `ta`.
- [ ] 2.3 Implement custom indicator configuration for SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, OBV, volume average, and support/resistance inclusion.
- [ ] 2.4 Normalize `ta` outputs into backend-owned structured indicator fields and report unavailable indicators without fabricating values.
- [ ] 2.5 Implement `load_price_history` as optional raw OHLCV inspection using either `length` or `start` with optional `end`.
- [ ] 2.6 Implement `run_backtest` as a wrapper around the existing internal backtest service and registered templates.

## 3. Technical Analyst Runtime

- [ ] 3.1 Create `app/agents/implementations/technical_analyst/` module structure.
- [ ] 3.2 Add technical analyst runtime model builder with stock-agent-compatible runtime config.
- [ ] 3.3 Add technical analyst tool surface exposing only `compute_technical_indicators`, `load_price_history`, and `run_backtest`.
- [ ] 3.4 Add technical analyst system prompt covering `technical_read`, `trading_plan`, daily interval scope, tool usage, and parent-synthesis boundaries.
- [ ] 3.5 Add technical analyst middleware for summarization, tool-output limiting, and bounded tool-error conversion.
- [ ] 3.6 Create `create_technical_analyst_agent` with structured response format and the dedicated tool surface.

## 4. Stock-Agent Delegation Integration

- [ ] 4.1 Extend the stock-agent subagent registry and `DelegatedTaskInput` literal to include `technical_analyst`.
- [ ] 4.2 Add cached technical analyst runtime creation by resolved stock-agent runtime config.
- [ ] 4.3 Route delegated `technical_analyst` tasks through the specialist runtime with minimal isolated payload.
- [ ] 4.4 Preserve recursive delegation guardrails for technical analyst executions.
- [ ] 4.5 Update stock-agent orchestration prompt to describe `technical_analyst` routing rules and examples.
- [ ] 4.6 Update tool descriptions and prompt tests so parent stock agent does not invent unsupported subagent IDs.

## 5. Tests

- [ ] 5.1 Add unit tests for technical indicator input schema variants: `length`, `start`/`end`, preset indicator sets, and custom config.
- [ ] 5.2 Add unit tests for `compute_technical_indicators` using fake stock price history and verifying normalized indicator snapshot output.
- [ ] 5.3 Add unit tests for unavailable indicator reporting when price history is insufficient for a requested indicator.
- [ ] 5.4 Add unit tests for `load_price_history` confirming it returns raw canonical OHLCV and is not required before indicator computation.
- [ ] 5.5 Add unit tests for `run_backtest` confirming supported templates route to the existing backtest service and unsupported scope is rejected.
- [ ] 5.6 Add technical analyst structured output validation tests for `technical_read` and `trading_plan`.
- [ ] 5.7 Add delegation tests proving `technical_analyst` routes to the specialist runtime and unknown IDs remain rejected.
- [ ] 5.8 Add stock-agent prompt/middleware tests confirming technical-analysis routing guidance is present.

## 6. Verification

- [ ] 6.1 Run targeted technical analyst unit tests.
- [ ] 6.2 Run targeted stock-agent delegation and middleware tests.
- [ ] 6.3 Run targeted stock price and backtest tests touched by the technical-analysis tool integration.
- [ ] 6.4 Run OpenSpec validation for `add-stock-agent-technical-analyst`.
