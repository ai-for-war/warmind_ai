## 1. Schema And API Contract

- [x] 1.1 Add stock financial report query, enum, item, and response schemas for report type, period, ordered periods, row `values`, and `cache_hit`
- [x] 1.2 Validate supported report types `income-statement`, `balance-sheet`, `cash-flow`, and `ratio`
- [x] 1.3 Validate supported periods `quarter` and `year`, defaulting omitted period to `quarter`

## 2. KBS Gateway

- [x] 2.1 Add `VnstockFinancialReportGateway` for `Finance(symbol=..., source="KBS")`
- [x] 2.2 Map each public report type to the exact KBS finance method used by the runtime
- [x] 2.3 Convert DataFrame-like payloads into ordered rows with `item`, `item_id`, and period-keyed `values`
- [x] 2.4 Normalize missing numeric cells such as NaN to `None`
- [x] 2.5 Document the runtime mismatch around `display_mode` and hierarchy metadata near the KBS integration point

## 3. Caching And Service

- [x] 3.1 Add a Redis cache helper for financial report responses keyed by symbol, report type, and period
- [x] 3.2 Add `StockFinancialReportService` to validate symbols through the stock catalog before upstream reads
- [x] 3.3 Implement cache hit, upstream fetch on miss, successful response caching, and same-variant stale-cache fallback
- [x] 3.4 Return `404` when a valid symbol has no KBS rows for the requested report type and period
- [x] 3.5 Map invalid request inputs to client errors and unexpected upstream/runtime failures to gateway errors when no stale cache exists

## 4. Routing And Dependency Wiring

- [x] 4.1 Wire the financial report cache, gateway, and service factories in `app/common/service.py`
- [x] 4.2 Extend the stock router with `GET /api/v1/stocks/{symbol}/financial-reports/{report_type}`
- [x] 4.3 Reuse the existing active-user and organization-context dependencies for the new endpoint
- [x] 4.4 Return the normalized financial report response from the router without adding aggregate all-report behavior

## 5. Tests

- [ ] 5.1 Add schema tests for report type, period defaults, unsupported period rejection, and response validation
- [ ] 5.2 Add gateway tests for report-method mapping, DataFrame conversion, period ordering, NaN normalization, and unsupported payload rejection
- [ ] 5.3 Add service tests for symbol normalization, unknown symbol rejection before upstream calls, cache hits, cache writes, stale fallback, empty-data `404`, and cache variant isolation
- [ ] 5.4 Add router tests for authenticated organization access, request validation, successful response shape, and no aggregate fetch behavior
- [ ] 5.5 Run the focused stock financial report test suite and any existing stock service/router tests affected by the change
