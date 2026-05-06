## Why

The backend currently exposes Vietnamese stock catalog, company, and price APIs,
but it does not provide financial statement data for a selected stock symbol.
The product needs a stable API contract for KBS-backed financial reports so
clients can analyze income statement, balance sheet, cash flow, and ratio data
without coupling directly to `vnstock` DataFrame behavior.

## What Changes

- Add authenticated stock financial report read endpoints under the existing
  stock API surface for one selected stock symbol
- Use `vnstock` `Finance(source="KBS")` only for this financial report
  capability
- Support separate report reads for income statement, balance sheet, cash
  flow, and financial ratios
- Return a stable row-oriented response envelope with `item`, `item_id`, and
  dynamic period values nested under `values`
- Return `404` when a requested symbol is valid but KBS does not return report
  data for the requested report type and period
- Reuse the existing stock catalog to validate symbols before upstream KBS
  reads
- Add Redis caching per symbol, report type, and period with stale-cache
  fallback when upstream KBS fetches fail
- Keep hierarchy metadata such as `item_en`, `unit`, `levels`, and
  `row_number` out of the v1 public response because the installed `vnstock`
  runtime does not reliably expose those fields for all KBS report methods
- Do not add an aggregate endpoint that fetches all financial report types in
  one request

## Capabilities

### New Capabilities

- `stock-financial-reports`: provide authenticated KBS-backed financial report
  endpoints for a stock symbol with stable row/value normalization, symbol
  validation, no provider fallback, and per-query caching

### Modified Capabilities

- None.

## Impact

- **Affected APIs**: adds authenticated
  `GET /api/v1/stocks/{symbol}/financial-reports/{report_type}` reads with a
  `period` query parameter
- **Affected code**: new schemas, service, cache helper, and `vnstock` finance
  gateway modules under `app/domain/schemas/` and `app/services/stocks/`, plus
  router and shared service factory wiring
- **Dependencies**: relies on the currently installed `vnstock` KBS finance
  integration
- **Caching**: introduces Redis caching for financial report responses per
  symbol, report type, and period
- **Data layer**: reuses the existing persisted stock catalog for symbol
  validation and does not add MongoDB persistence for financial report payloads
  in v1
