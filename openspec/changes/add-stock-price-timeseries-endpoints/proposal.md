## Why

The backend currently exposes stock-symbol catalog and company-information
endpoints, but it does not yet provide a stable API for historical price
timeseries. The product now needs authenticated backend endpoints for charting
and price exploration without pushing `vnstock` VCI integration details into
clients.

## What Changes

- Add authenticated stock price timeseries endpoints under the existing stock
  API surface for one selected stock symbol
- Use `vnstock` quote data with source `VCI` only for v1
- Support dedicated read endpoints for historical OHLCV data and intraday trade
  timeseries
- Return raw normalized timeseries payloads only in v1, without backend-derived
  analytics or summary statistics
- Reuse the existing persisted stock catalog to validate symbols, preserve the
  current org-auth access model, and back the read path with Redis caching plus
  stale-cache fallback when upstream fetches fail

## Capabilities

### New Capabilities
- `stock-price-timeseries`: provide authenticated stock price history and
  intraday timeseries endpoints backed by `vnstock` VCI, symbol validation via
  the shared stock catalog, backend normalization, and per-symbol caching

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds authenticated `GET /api/v1/stocks/{symbol}/prices/history`
  and `GET /api/v1/stocks/{symbol}/prices/intraday` endpoints for stock price
  timeseries reads
- **Affected code**: new router handlers, schemas, service, cache helper, and
  `vnstock` quote gateway modules under `app/api/v1/`,
  `app/domain/schemas/`, and `app/services/`, plus dependency wiring in shared
  service factories
- **Dependencies**: relies on the current `vnstock` integration with source
  `VCI` for quote history and intraday methods
- **Caching**: introduces Redis caching for stock price timeseries responses per
  symbol, endpoint section, and normalized query variant
- **Data layer**: reuses the existing stock catalog for symbol validation; does
  not introduce a new MongoDB persistence layer for price timeseries in v1
