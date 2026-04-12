## 1. Setup and persistence foundations

- [x] 1.1 Add `vnstock` to the backend dependency set and ensure the application environment can import it
- [x] 1.2 Add stock catalog domain schemas for list query params, list response items, paginated response envelope, and manual refresh response
- [x] 1.3 Create a `stock_symbols` repository with MongoDB upsert, paginated unfiltered reads, filtered reads, and count support
- [x] 1.4 Add MongoDB indexes for `stock_symbols` covering unique `symbol`, `exchange`, `groups`, and normalized search fields

## 2. Upstream integration and normalization

- [x] 2.1 Create a `VnstockListingGateway` that fetches stock listing data from `Listing(source='VCI')`
- [x] 2.2 Implement normalization helpers that map upstream listing fields into the persisted stock-symbol document shape
- [x] 2.3 Implement group membership assembly for the v1-supported stock groups and merge that data into the normalized snapshot
- [x] 2.4 Implement manual refresh persistence flow that upserts normalized symbol documents without deleting the previous snapshot first

## 3. Service and cache behavior

- [x] 3.1 Create a `StockCatalogService` that orchestrates manual refresh, unfiltered reads, filtered reads, and cache invalidation
- [x] 3.2 Implement Redis cache helpers for unfiltered stock-list responses keyed by page and page size
- [x] 3.3 Implement `GET /stocks` service behavior so unfiltered requests use cache and filtered requests query MongoDB directly
- [x] 3.4 Implement refresh error handling so failed refresh attempts leave the last successful persisted snapshot readable

## 4. API wiring and authorization

- [x] 4.1 Add a new FastAPI router for `GET /api/v1/stocks` using active-user and organization-context dependencies
- [x] 4.2 Add a new FastAPI endpoint `POST /api/v1/stocks/refresh` protected by `require_super_admin`
- [x] 4.3 Register the stock router in the v1 router aggregation and wire the stock catalog service into shared service factories
- [x] 4.4 Ensure read responses expose the persisted catalog fields needed for list, search, exchange filter, and group filter behavior

## 5. Tests and verification

- [x] 5.1 Add repository and service tests for unfiltered pagination, `q` filtering, `exchange` filtering, and `group` filtering
- [x] 5.2 Add service tests that verify unfiltered requests use cache while filtered requests bypass cache
- [x] 5.3 Add API tests for org-auth read access and Super Admin-only refresh authorization
- [x] 5.4 Add refresh-path tests that verify successful upsert behavior and preservation of the previous snapshot when refresh fails
