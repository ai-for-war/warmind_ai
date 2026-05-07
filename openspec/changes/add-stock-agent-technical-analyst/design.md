## Context

The stock agent already runs as a dedicated LangChain/LangGraph runtime with stock-agent-specific prompts, middleware, tools, checkpointing, and typed delegation infrastructure. The current codebase also has canonical stock price history through `StockPriceService`, normalized OHLCV schemas, and an internal deterministic backtest service with fixed templates.

The existing event analyst establishes the specialist-subagent pattern: a dedicated runtime, fixed tool surface, structured output, and parent stock-agent synthesis. Technical analysis should follow the same pattern instead of using the generic worker or letting the LLM infer indicators from raw price text.

Important constraints:

- The technical analyst must support Vietnam-listed equities only, consistent with stock agent scope.
- Phase one supports daily interval `1D`.
- Indicator computation must use canonical OHLCV from the stock price layer and must not call `vnstock` directly.
- The user explicitly wants the agent to control `length` or `start`/`end` selection rather than backend-enforced business limits.
- `load_price_history` is optional inspection only; `compute_technical_indicators` is self-contained and loads its own price history.
- The technical analyst may use the existing backtest service, but it must not execute arbitrary model-generated strategy code.

## Goals / Non-Goals

**Goals:**

- Add `technical_analyst` as a preset stock-agent subagent.
- Add a dedicated technical analyst runtime with prompt, middleware, tools, and structured response validation.
- Compute technical indicators deterministically with the `ta` library.
- Support both preset indicator sets and custom indicator configuration.
- Support two output modes:
  - `technical_read` for chart state and evidence.
  - `trading_plan` for entry zone, stop loss, targets, risk/reward, invalidation, and backtest context.
- Expose a backtest tool to the technical analyst that reuses the existing internal backtest service and fixed templates.
- Keep parent stock agent responsible for final user-facing synthesis and all-factor recommendation labels.

**Non-Goals:**

- Do not add public REST endpoints for technical analysis in this change.
- Do not change public stock price or backtest APIs.
- Do not support intraday, weekly, or monthly technical analysis in phase one.
- Do not add TA-Lib native dependency.
- Do not allow the LLM to run arbitrary Python strategy code for backtesting.
- Do not make `load_price_history` a required precursor to indicator computation.
- Do not persist technical-analysis reports as a new durable artifact in this change.

## Decisions

### Decision 1: Create a dedicated `technical_analyst` specialist runtime

The stock-agent registry will be extended with a new preset `technical_analyst` ID. The executor will route this ID to a cached technical analyst runtime, mirroring the event analyst integration pattern.

Rationale:

- Technical analysis has a distinct tool surface and structured output contract.
- Reusing `general_worker` would leave indicator and trading-plan behavior prompt-driven and hard to test.
- A specialist runtime lets the parent stock agent delegate technical work without losing responsibility for final synthesis.

Alternatives considered:

- Add technical-analysis instructions to the parent stock agent only: rejected because indicator computation and backtest interpretation need a bounded specialist contract.
- Add a generic stock-analysis tool to the parent: rejected because it grows the parent tool surface and makes routing harder to test.

### Decision 2: Use `ta` for phase-one indicator computation

The indicator engine will use the `ta` Python library on Pandas-backed OHLCV data. The dependency provides common trend, momentum, volatility, and volume indicators without TA-Lib native installation complexity.

Rationale:

- The project already uses Pandas/Numpy in the local locked dependency set.
- `ta` covers the phase-one indicator set: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, OBV, and related volume features.
- Avoiding TA-Lib reduces deployment complexity because TA-Lib requires a native core library.

Alternatives considered:

- TA-Lib: rejected for phase one due to native dependency complexity.
- `pandas-ta-classic`: deferred because it is attractive for broad indicator coverage but should be evaluated separately before being made core backend infrastructure.
- Hand-written indicators only: rejected because `ta` gives a maintained implementation for common indicators while still keeping the tool deterministic and testable.

### Decision 3: Make `compute_technical_indicators` self-contained

`compute_technical_indicators` will accept stock target, `1D` interval, price-history query fields, and indicator configuration. It will call `StockPriceService.get_history`, convert the canonical OHLCV response into a DataFrame, compute indicators, derive support/resistance, and return a structured technical snapshot.

Supported price-history query shapes:

- `length` lookback-style reads.
- `start` with optional `end` explicit time range.

The tool will support both:

- preset `indicator_set` values such as `core`, `trend`, `momentum`, `volatility`, `volume`, and `custom`;
- optional `config` for custom windows and included indicator families when `indicator_set` is `custom`.

Rationale:

- The agent should pass intent and parameters, not large OHLCV payloads through tool context.
- Loading inside the tool keeps computation reproducible and avoids multi-tool data handoff errors.
- Using the existing stock price layer preserves symbol validation, provider behavior, cache usage, and canonical field normalization.

Alternatives considered:

- Require `load_price_history` first and pass bars into `compute_technical_indicators`: rejected because it bloats tool-call context and makes the agent responsible for data plumbing.
- Let the LLM compute indicators from raw OHLCV: rejected because it is not deterministic or testable.

### Decision 4: Keep `load_price_history` as optional raw data inspection

`load_price_history` will expose the same history query shape as the indicator tool, but it returns raw canonical OHLCV records only. It is available when the technical analyst wants to inspect recent candles or debug data quality, but indicator computation does not depend on it.

Rationale:

- Raw OHLCV inspection can be useful for candle-level interpretation.
- Separating inspection from computation keeps the main indicator tool simpler for agent routing.

### Decision 5: Add two technical analyst modes

The structured response will include `mode`.

`technical_read` returns chart-state evidence:

- trend
- momentum
- volatility state
- support/resistance
- volume confirmation
- signals
- risks
- uncertainties
- indicator snapshot

`trading_plan` adds action-oriented technical fields:

- entry zone
- stop loss
- target 1 and target 2
- risk/reward
- `invalidated_if`
- backtest summary when the agent runs backtest evidence

Rationale:

- Users who ask "chart the nao" should not receive unsolicited entry/stop/target numbers.
- Users who ask for a setup, buy zone, stop loss, target, or strategy validation need actionable technical-plan fields.
- This keeps the subagent subordinate to the parent while still returning machine-readable plan components.

### Decision 6: Reuse internal backtest service through a technical analyst tool

The technical analyst gets `run_backtest`, which wraps existing internal backtest service behavior. The agent may choose supported templates and parameters. The backend continues to validate the request against registered templates.

Rationale:

- Existing backtest code already enforces daily, long-only, fixed-template execution.
- Technical analyst should not invent strategy execution logic.
- Backtest output can improve `trading_plan` evidence without changing public APIs.

Alternatives considered:

- Always run backtest for every technical analysis: rejected because it adds unnecessary latency and can distract from simple chart-read requests.
- Let the LLM simulate backtests: rejected because it is non-deterministic and not auditable.

## Risks / Trade-offs

- **Risk: Agent passes a short or unusual history query for requested indicators** -> Mitigation: the tool returns computed indicators plus skipped/insufficient-data metadata where applicable instead of fabricating values.
- **Risk: `ta` output column naming or NaN behavior leaks into the agent contract** -> Mitigation: normalize all indicator outputs into backend-owned Pydantic schemas and keep raw library names internal.
- **Risk: Backtest results are overinterpreted as predictive certainty** -> Mitigation: prompt and output contract frame backtest as historical evidence only, with uncertainties and invalidation conditions.
- **Risk: Technical analyst overlaps with parent recommendation responsibility** -> Mitigation: prompt states that final all-factor recommendation belongs to the parent stock agent.
- **Risk: Adding another specialist increases runtime compile/cache overhead** -> Mitigation: cache compiled technical analyst runtimes by stock-agent runtime config, same as worker and event analyst patterns.
- **Risk: Active preset-subagent change has not been archived yet** -> Mitigation: implement this change on top of the current code and align with the existing registry pattern; archive order should preserve both subagent additions.
