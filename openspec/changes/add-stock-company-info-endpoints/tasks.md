## 1. Schema and validation foundations

- [x] 1.1 Add stock company domain schemas for section-specific response envelopes and item payloads under `app/domain/schemas/`
- [x] 1.2 Extend the stock symbol repository with a symbol existence lookup used to validate requested company symbols before upstream reads
- [x] 1.3 Define request-query schemas for section filters that are required in v1, including `officers.filter_by` and `subsidiaries.filter_by`

## 2. Upstream company integration

- [x] 2.1 Create a `VnstockCompanyGateway` that wraps `Company(symbol=..., source='VCI')` and exposes one fetch method per supported company-information section
- [x] 2.2 Implement DataFrame-like payload conversion helpers in the company gateway so each section can be returned as plain dictionaries or lists
- [x] 2.3 Document and handle the current runtime mismatch between the public `vnstock` wrapper and the installed VCI provider methods near the integration point
- [x] 2.4 Implement section-specific normalization that preserves canonical VCI fields without speculative cross-provider aliases

## 3. Cache and service orchestration

- [x] 3.1 Create Redis cache helpers for company-information responses keyed by stock symbol, section, and supported filter variants
- [x] 3.2 Implement a `StockCompanyService` that normalizes symbols, validates them against the stock catalog, and orchestrates cache lookup plus upstream fetch on miss
- [x] 3.3 Implement stale-cache fallback so upstream failures return the latest cached response for the same symbol and section when available
- [x] 3.4 Ensure section-level failures remain isolated so one failing company tab does not block later reads for other tabs

## 4. API wiring and authorization

- [x] 4.1 Extend the stock API router with authenticated tab-wise company-information endpoints under `/api/v1/stocks/{symbol}/company/*`
- [x] 4.2 Wire the new company gateway, cache helper, and service into shared dependency factories in `app/common/service.py`
- [x] 4.3 Ensure every company-information endpoint reuses the existing active-user and organization-context dependencies
- [x] 4.4 Ensure endpoint responses expose stable envelope metadata such as `symbol`, `source`, `fetched_at`, and `cache_hit`

## 5. Tests and verification

- [ ] 5.1 Add gateway and service tests for section fetches, canonical field preservation, and symbol validation before upstream calls
- [ ] 5.2 Add cache behavior tests covering cache hit, cache miss, and stale-cache fallback for company-information endpoints
- [ ] 5.3 Add API tests for organization-scoped read access across the new company-information routes
- [ ] 5.4 Add API or service tests for section-specific filters on officers and subsidiaries plus endpoint-level failure isolation
