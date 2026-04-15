## 1. Schema and query validation foundations

- [x] 1.1 Add stock price domain schemas for history and intraday response envelopes plus canonical raw item payloads under `app/domain/schemas/`
- [x] 1.2 Add request-query schemas for the public v1 contract, including `history` parameters (`start`, `end`, `interval`, `length`) and `intraday` parameters (`page_size`, `last_time`, `last_time_format`)
- [x] 1.3 Implement schema-level validation rules that reject unsupported query combinations such as providing both `start` and `length` or neither of them for history reads

## 2. Upstream quote integration

- [x] 2.1 Create a `VnstockPriceGateway` that wraps `Quote(symbol=..., source='VCI')` and exposes dedicated fetch methods for `history` and `intraday`
- [x] 2.2 Implement DataFrame-like payload conversion helpers in the price gateway so history and intraday responses are returned as plain record lists
- [x] 2.3 Implement endpoint-specific normalization that preserves canonical VCI raw fields for OHLCV history and intraday trade timeseries without speculative aliases
- [x] 2.4 Document and handle the current runtime mismatch between the public `vnstock` quote wrapper and the installed VCI provider behavior near the integration point

## 3. Cache and service orchestration

- [x] 3.1 Create Redis cache helpers for stock price responses keyed by stock symbol, endpoint section, and normalized query variant
- [x] 3.2 Implement a `StockPriceService` that normalizes symbols, validates them against the stock catalog, and orchestrates cache lookup plus upstream fetch on miss
- [x] 3.3 Offload synchronous upstream quote reads through `run_in_threadpool` and map provider or transport failures into deterministic API-facing errors
- [x] 3.4 Implement stale-cache fallback so upstream failures return the latest cached response for the same symbol, endpoint section, and query variant when available
- [x] 3.5 Ensure endpoint-level and query-variant failures remain isolated so one failing history or intraday request does not block later reads for other sections or variants

## 4. API wiring and authorization

- [x] 4.1 Extend the stock API router with authenticated price endpoints under `/api/v1/stocks/{symbol}/prices/history` and `/api/v1/stocks/{symbol}/prices/intraday`
- [x] 4.2 Wire the new price gateway, cache helper, and service into shared dependency factories in `app/common/service.py`
- [x] 4.3 Ensure every stock price endpoint reuses the existing active-user and organization-context dependencies
- [x] 4.4 Ensure endpoint responses expose stable envelope metadata such as `symbol`, `source`, `cache_hit`, and `interval` for history responses

## 5. Tests and verification

- [x] 5.1 Add gateway tests for history and intraday fetches, canonical field preservation, empty payload handling, and runtime-specific parameter behavior
- [x] 5.2 Add service tests for symbol validation before upstream calls, query validation, cache hit and miss behavior, and stale-cache fallback by query variant
- [x] 5.3 Add service or API tests for deterministic error mapping across invalid symbol, invalid query shape, and upstream failure cases
- [x] 5.4 Add API tests for organization-scoped read access across the new stock price routes
- [x] 5.5 Run the relevant stock-service and API test suites and resolve any failures introduced by the new endpoints
