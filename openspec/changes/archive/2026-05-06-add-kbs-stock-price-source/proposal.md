## Why

Stock price timeseries currently hard-codes `vnstock` source `VCI`, which prevents callers from using the documented `KBS` source for environments or workflows where KBS is preferred. Adding explicit source selection lets the backend support both documented providers while keeping VCI as the default behavior.

## What Changes

- Add an explicit stock price source selection to history and intraday reads, defaulting to `VCI`.
- Support `KBS` as an additional `vnstock.Quote` source for both `history()` and `intraday()`.
- Keep cache entries isolated by source so VCI and KBS responses cannot collide.
- Preserve source-specific query behavior: VCI intraday supports `last_time` and `last_time_format`; KBS intraday does not.
- Adjust intraday response validation to allow KBS string trade identifiers while continuing to support VCI numeric identifiers.
- Do not add automatic provider fallback in this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `stock-price-timeseries`: Stock price timeseries APIs can explicitly use `VCI` or `KBS` instead of requiring VCI only.

## Impact

- API query contract for `GET /stocks/{symbol}/prices/history` and `GET /stocks/{symbol}/prices/intraday` gains an optional `source` parameter.
- Stock price response schema expands source values from `VCI` to `VCI` or `KBS`.
- Intraday item `id` expands from numeric-only to numeric or string to match documented KBS payloads.
- Gateway construction, cache variant generation, service validation, and tests need updates.
- No new third-party dependency is expected; this uses the existing `vnstock` package.
