## Context

The current backend already exposes Vietnamese stock data under the `/stocks`
API surface:

- persisted stock catalog backed by the existing stock symbol repository
- VCI company information endpoints with section-level caching
- VCI/KBS price timeseries endpoints with source-aware caching

It does not yet expose financial statement data for a stock symbol. Vnstock
documentation recommends KBS for detailed financial reports, and the installed
runtime (`vnstock 4.0.2`) exposes KBS financial reports through
`Finance(symbol=..., source="KBS")` methods:

- `income_statement(period=...)`
- `balance_sheet(period=...)`
- `cash_flow(period=...)`
- `ratio(period=...)`

KBS returns a DataFrame whose rows are financial statement line items and whose
periods are dynamic columns. The stable columns available through the normal
runtime path are `item` and `item_id`; period columns vary by requested period
and available upstream data.

Important runtime mismatch:

- the public docs describe `display_mode=all` returning hierarchy metadata such
  as `item_en`, `unit`, `levels`, and `row_number`
- in the installed `vnstock 4.0.2` runtime, `display_mode` and
  `include_metadata` are not reliably accepted through the normal wrapper path
  for `income_statement`, `balance_sheet`, and `cash_flow`
- `ratio` currently accepts those fields, but the endpoint contract must be
  consistent across all report types

This change therefore treats hierarchy metadata as out of scope for v1 and
keeps the public response shape focused on financial line items and period
values.

## Goals / Non-Goals

**Goals:**

- Add authenticated KBS-backed financial report read endpoints under
  `/api/v1/stocks/{symbol}`
- Support one report type per request:
  `income-statement`, `balance-sheet`, `cash-flow`, and `ratio`
- Support `period=quarter` and `period=year`
- Reuse the existing stock catalog to validate symbols before hitting KBS
- Normalize KBS DataFrame rows into a stable API envelope with `periods` and
  `items[].values`
- Return `404` for valid symbols when KBS returns no rows for the requested
  report type and period
- Cache successful responses by symbol, report type, and period
- Return stale cache for the same symbol/report/period when upstream KBS fails

**Non-Goals:**

- Support VCI or automatic provider fallback for this capability
- Add an aggregate endpoint that fetches all report types at once
- Add hierarchy metadata such as `item_en`, `unit`, `levels`, or `row_number`
  to the v1 response
- Add MongoDB persistence or background refresh for financial report payloads
- Return official issuer filing PDFs or full disclosure documents; this API
  returns the processed KBS/vnstock financial report table
- Add derived analytics, summaries, or cross-report calculations

## Decisions

### D1: Use one generic report endpoint with a report-type path parameter

**Decision**: Add one authenticated endpoint:

- `GET /api/v1/stocks/{symbol}/financial-reports/{report_type}?period=quarter`

Supported `report_type` values:

- `income-statement`
- `balance-sheet`
- `cash-flow`
- `ratio`

Supported `period` values:

- `quarter`
- `year`

**Rationale**:

- report types share the same envelope and service/cache behavior
- a path enum keeps the API compact while preserving report-level isolation
- one report per request avoids mixed partial failures and slow aggregate reads

**Alternatives considered:**

- **Four separate route functions with separate paths**: workable, but mostly
  duplicates the same validation, caching, and response envelope behavior
- **One aggregate `/financial-reports` endpoint**: rejected because the user
  explicitly does not want all reports fetched together

### D2: Use KBS only and do not expose a source query parameter

**Decision**: The gateway always calls `Finance(symbol=..., source="KBS")`.
The public API does not expose `source`.

**Rationale**:

- the user explicitly chose KBS and rejected VCI for this capability
- adding `source` now invites unsupported provider behavior and cache variants
- no provider fallback keeps data lineage predictable

**Alternatives considered:**

- **Expose `source=KBS|VCI` like price endpoints**: rejected because VCI is out
  of scope and has a different report shape
- **Automatic fallback from KBS to VCI**: rejected because it can return mixed
  provider data under the same endpoint contract

### D3: Normalize dynamic period columns under `values`

**Decision**: Return each row as:

```json
{
  "item": "Tiền và các khoản tương đương tiền",
  "item_id": "cash_and_cash_equivalents",
  "values": {
    "2026-Q1": 63589689844,
    "2025-Q4": 58696689844
  }
}
```

The response envelope includes the period order:

```json
{
  "symbol": "VCI",
  "source": "KBS",
  "report_type": "balance_sheet",
  "period": "quarter",
  "periods": ["2026-Q1", "2025-Q4"],
  "cache_hit": false,
  "items": []
}
```

**Rationale**:

- KBS period labels are dynamic and may include suffixes such as `2025-Q4_1`
- `values` keeps the API schema stable even when period columns change
- `periods` preserves the upstream display/order contract for clients

**Alternatives considered:**

- **Return raw DataFrame records with period keys at row root**: rejected
  because it makes the row schema dynamic and harder to type
- **Normalize period labels into a strict year/quarter object**: rejected for
  v1 because the runtime can return duplicate/suffixed labels that should not
  be collapsed without product rules

### D4: Do not expose hierarchy metadata in v1

**Decision**: v1 returns only `item`, `item_id`, and `values` for each row.
It does not return `item_en`, `unit`, `levels`, or `row_number`.

**Rationale**:

- those fields require `display_mode=all` in the documented path
- the installed runtime does not reliably accept that mode for all report
  methods through normal public calls
- a consistent contract across all report types is more important than exposing
  partial metadata

**Alternatives considered:**

- **Use provider internals or unwrapped functions to force metadata**: rejected
  because it couples production code to decorator internals and package layout
- **Expose metadata only for `ratio`**: rejected because it creates an uneven
  contract by report type
- **Hard-code fallback aliases for metadata fields**: rejected because there is
  no concrete evidence of multiple field names in the exact supported runtime
  path

### D5: Validate symbols through the existing stock catalog

**Decision**: The service normalizes the path symbol to uppercase and validates
it using the existing stock symbol repository before calling KBS.

**Rationale**:

- avoids unnecessary upstream calls for unknown symbols
- matches the existing stock company and price endpoint patterns
- keeps the stock catalog as the backend's symbol validation boundary

**Alternatives considered:**

- **Let KBS validate symbols**: rejected because upstream errors are less
  predictable and waste external calls
- **Add a separate KBS symbol catalog**: rejected for v1 because the current
  catalog is already accepted for validation

### D6: Return 404 for empty KBS report data

**Decision**: If the symbol exists but the selected KBS report method returns
an empty DataFrame or no valid rows for the requested period, the service
returns `404`.

**Rationale**:

- the user explicitly selected `404`
- empty data for a valid report request is semantically "not found" for this
  API
- clients can distinguish "no report exists" from "report exists with empty
  numeric cells"

**Alternatives considered:**

- **Return `200` with `items=[]`**: rejected by product decision
- **Map all upstream no-data exceptions to `502`**: rejected because no data is
  not necessarily an upstream failure

### D7: Add a dedicated gateway, cache helper, and service

**Decision**: Follow existing stock service layering:

```text
router
  -> StockFinancialReportService
      -> StockSymbolRepository
      -> StockFinancialReportCache
      -> VnstockFinancialReportGateway
          -> vnstock.Finance(source="KBS")
```

Recommended modules:

- `app/domain/schemas/stock_financial_report.py`
- `app/services/stocks/financial_report_gateway.py`
- `app/services/stocks/financial_report_cache.py`
- `app/services/stocks/financial_report_service.py`
- extend `app/api/v1/stocks/router.py`
- extend `app/common/service.py`

**Rationale**:

- keeps routers thin
- isolates third-party DataFrame conversion in one gateway
- matches established cache/service patterns for company and price data
- makes runtime mismatch comments local to the integration point

**Alternatives considered:**

- **Call `vnstock` directly from the router**: rejected because it mixes auth,
  validation, caching, and upstream conversion
- **Reuse company cache/service classes**: rejected because financial report
  cache variants differ by report type and period

### D8: Cache by symbol, report type, and period with stale fallback

**Decision**: Use Redis keys scoped to the exact request variant.

Recommended key shape:

- `stocks:financial-reports:<SYMBOL>:<report_type>:period=<period>`

Recommended TTL:

- 86400 seconds for both yearly and quarterly report responses in v1

If upstream KBS fails and a cached response exists for the same symbol, report
type, and period, return that cached response with `cache_hit=true`.

**Rationale**:

- financial report data changes slowly relative to price/intraday data
- cache variants must not mix report types or periods
- stale fallback improves availability without adding MongoDB snapshots

**Alternatives considered:**

- **No cache**: rejected because report reads can be slow and repeated client
  reads should not always hit KBS
- **Persist report snapshots in MongoDB**: rejected for v1 due additional
  refresh, versioning, and storage model complexity

## Risks / Trade-offs

**[KBS docs and runtime differ for metadata exposure]** -> Mitigation: do not
expose metadata in v1; document the mismatch near the gateway; use only fields
verified in the normal runtime path.

**[KBS period labels are dynamic and can include duplicate suffixes]** ->
Mitigation: preserve provider period labels exactly in `periods` and `values`
instead of inventing normalization rules.

**[Live KBS reads can fail or be slow]** -> Mitigation: cache successful
responses and return stale cache for the same request variant when upstream
fails.

**[Empty KBS data can be ambiguous]** -> Mitigation: apply the explicit product
decision that valid-symbol/no-report data returns `404`, while upstream
transport or unexpected runtime failures map to gateway errors.

**[Financial rows are not official disclosure filings]** -> Mitigation: keep
the contract framed as processed KBS/vnstock financial report data, not issuer
filing documents.

## Migration Plan

1. Add financial report schemas for query params, response envelope, report
   type enum, period enum, and row items.
2. Add `VnstockFinancialReportGateway` to call KBS `Finance` methods and
   convert DataFrame-like payloads into normalized rows.
3. Add `StockFinancialReportCache` for Redis get/set using symbol, report type,
   and period variants.
4. Add `StockFinancialReportService` for symbol validation, cache lookup,
   threadpool upstream fetch, empty-data handling, stale fallback, and error
   mapping.
5. Extend the stock router with the financial report endpoint while reusing the
   current active-user and organization-context dependencies.
6. Wire gateway, cache, and service factories in `app/common/service.py`.
7. Add focused unit tests for schema validation, gateway conversion, service
   cache/stale behavior, empty-data `404`, and router integration.

**Rollback**

- remove the financial report route from the stock router
- remove service factory wiring and new financial report modules
- let Redis keys under `stocks:financial-reports:*` expire naturally
- no MongoDB migration is required

## Open Questions

- None for v1. Hierarchy metadata can be revisited in a later change after the
  supported `vnstock` runtime path for all report methods is verified.
