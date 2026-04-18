## Context

The backtest stack already provides a stable daily long-only engine, a
template registry, and a public FE-facing backtest API, but the supported
template catalog stops at `buy_and_hold` and `sma_crossover`. Adding an
Ichimoku strategy is cross-cutting because it changes internal template
validation, signal generation, data-loading behavior, and the public template
catalog.

The main technical constraints are:

- Ichimoku requires pre-window history so the first tradable bar is not
  distorted by incomplete Tenkan, Kijun, Senkou, and Chikou calculations
- The current backtest engine consumes `buy` and `sell` signals only and fills
  them on the next bar open
- The current stock-price contract supports `start/end` or `length`, but the
  internal schema does not allow combining `end` with `length`, which makes a
  pure count-back fetch unsuitable for historical backtests ending in the past
- Ichimoku cloud alignment must avoid lookahead bias by comparing each tradable
  bar to the cloud displayed for that same bar rather than to raw unshifted
  spans

## Goals / Non-Goals

**Goals:**
- Add one deterministic Ichimoku template that fits the current daily
  `long_only` / `next_open` engine
- Load enough pre-window history to compute Ichimoku indicators correctly
  before `date_from`
- Keep trade execution and metrics restricted to the requested backtest window
- Expose the new template and parameter metadata through the public backtest
  API
- Keep the implementation easy to test with deterministic unit tests

**Non-Goals:**
- Add short-selling, partial exits, pyramiding, or same-bar execution
- Introduce full textbook Ichimoku discretionary behavior such as multiple
  optional entry variants or manual chart interpretation
- Redesign the stock-price API around `count_back` / `length` semantics in this
  change
- Add trading fees, taxes, lot-size rules, or settlement constraints
- Expose warning-state outputs as a new public API surface in this change

## Decisions

### D1: Add Ichimoku as a new fixed template instead of a general indicator DSL

**Decision**: Extend the existing template registry with a third fixed template,
`ichimoku_cloud`, rather than opening the backtest system to arbitrary
indicator combinations.

**Rationale**:
- matches the current architecture, where each template produces deterministic
  `buy` / `sell` signals for the shared engine
- keeps request validation explicit and testable
- avoids a much larger design around composable strategy rules

**Alternatives considered:**
- **Generic indicator-expression engine**: rejected because it would expand
  product scope far beyond one strategy template
- **Agent-generated free-form Ichimoku logic**: rejected because the current
  backtest product intentionally uses fixed templates, not prompt-defined
  execution logic

### D2: Use a trend-following Ichimoku variant for v1

**Decision**: Implement Ichimoku as a trend-following strategy with:

- bullish entry only when price is above the aligned cloud
- bullish cloud confirmation (`span_a > span_b`)
- bullish Tenkan/Kijun crossover trigger
- Chikou-style confirmation approximated deterministically from current price
  relative to the price series `displacement` bars back
- bearish exit on either cloud breakdown or bearish Tenkan/Kijun reversal with
  Kijun loss
- warning-state evaluation that marks weakening trend conditions without
  directly executing a trade

**Rationale**:
- aligns better with common Ichimoku best practice for stock trend following
  than buying weak crosses below the cloud
- fits the current long-only engine
- separates early warning logic from actual entry/exit execution

**Alternatives considered:**
- **Counter-trend entry below cloud**: rejected because it is a weaker signal
  and more prone to noise in a long-only stock backtest
- **Full discretionary Ichimoku rule set including every textbook variation**:
  rejected because it is harder to validate and explain in a fixed-template
  product

### D3: Load warmup history by expanding the request start date

**Decision**: Implement warmup loading by shifting the upstream `start` date
backward far enough to cover the configured warmup bars, then split the
 normalized result into:

- warmup bars used only for indicator calculation
- tradable bars that fall within `date_from..date_to`

The engine and metrics builder continue to operate only on tradable bars.

**Rationale**:
- works with the current `StockPriceHistoryQuery` contract, which uses
  `start/end` for historical windows
- avoids changing the stock-price API to support `end + length` in this change
- keeps run outputs aligned exactly to the requested backtest window

**Alternatives considered:**
- **Use `length` / `count_back` directly**: rejected for v1 because the current
  internal stock-price schema does not allow pairing `end` with `length`, which
  would make historical windows ambiguous
- **Compute indicators without warmup bars**: rejected because the first
  tradable bars would be distorted or unusable for Ichimoku

### D4: Keep warmup bars non-tradable and non-reportable

**Decision**: Warmup bars SHALL never produce fills, equity-curve points, or
trade-log entries. Template logic may inspect them, but signals must be emitted
only for tradable bars within the requested backtest window.

**Rationale**:
- preserves the meaning of `date_from..date_to` for the user
- avoids inflated trade counts or equity history outside the requested window
- makes metrics comparable across templates

**Alternatives considered:**
- **Allow trading during warmup once indicators are available**: rejected
  because it changes the requested evaluation window

### D5: Treat cloud alignment as a first-class implementation concern

**Decision**: The Ichimoku template will construct aligned cloud values for each
tradable bar and compare price to that aligned cloud. It MUST NOT compare price
to raw unshifted Senkou A/B values from the same bar index.

**Rationale**:
- raw same-index Senkou comparisons are not faithful to how Ichimoku cloud is
  interpreted and risk accidental lookahead or misaligned signals
- explicit alignment keeps the strategy semantics explainable and testable

**Alternatives considered:**
- **Use raw Senkou values at the same index**: rejected because it changes the
  strategy semantics and no longer represents standard Ichimoku cloud logic

## Risks / Trade-offs

**[Expanded start date still returns too few bars due to holidays or sparse
history]** -> Mitigation: validate both warmup sufficiency and tradable-bar
availability after normalization, then return a deterministic error.

**[Cloud alignment is implemented incorrectly and introduces lookahead bias]**
-> Mitigation: isolate alignment logic inside the template and cover it with
unit tests that assert entry/exit bars for fixed synthetic datasets.

**[Warning logic becomes dead code because it is not yet exposed publicly]** ->
Mitigation: keep warning evaluation encapsulated and covered by tests, while
limiting the v1 public contract to entry/exit behavior and template metadata.

**[Exposing too many Ichimoku knobs makes FE forms noisy]** -> Mitigation: keep
the parameter set limited to windows, displacement, and warmup; use backend
defaults in the template catalog.

## Migration Plan

1. Extend internal backtest schemas and template IDs to include
   `ichimoku_cloud`.
2. Add Ichimoku template parameter validation and default metadata.
3. Update backtest data loading to fetch and separate warmup bars from tradable
   bars.
4. Implement aligned Ichimoku calculations and deterministic entry / exit /
   warning evaluation.
5. Expose the new template in the public backtest template catalog and public
   request validation.
6. Add unit and integration tests for warmup handling, template validation,
   signal generation, and FE template presentation.

**Rollback**

- remove the `ichimoku_cloud` template from internal and public catalogs
- revert warmup-aware backtest data loading to the previous direct
  `date_from..date_to` fetch path
- keep existing backtest history and result contracts unchanged because this
  change is additive to the template catalog

## Open Questions

- Should warning-state output remain internal only in v1, or should a later
  change expose it as structured diagnostics in the run response?
- Should `warmup_bars` remain FE-configurable after first release, or should a
  later cleanup move it to a backend-owned template default only?
