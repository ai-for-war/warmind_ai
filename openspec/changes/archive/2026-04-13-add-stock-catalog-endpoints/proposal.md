## Why

The backend currently has no dedicated stock-symbol catalog capability, but the
product now needs a stable way to list Vietnamese stock symbols, search by
symbol or company name, and filter by exchange or grouping without sending live
`vnstock` requests on every user query.

Research on the current `vnstock` docs shows the required data can be assembled
from `Listing(source='VCI')`, but search for Vietnamese symbols is not exposed
as one first-class endpoint. We need an internal catalog endpoint backed by
MongoDB so the API contract is stable, query behavior is predictable, and
upstream rate-limit risk stays off the request path.

## What Changes

- Add a new stock catalog capability that stores normalized symbol metadata in
  MongoDB and exposes one authenticated `GET /stocks` endpoint for listing and
  filtering stock symbols
- Add a manual authenticated `POST /stocks/refresh` endpoint for Super Admins
  to fetch the latest stock-symbol snapshot from `vnstock` using the `VCI`
  source and upsert it into the backend catalog
- Support query patterns needed by the current product scope: unfiltered list,
  search by `q`, filter by `exchange`, filter by `group`, and future-compatible
  filtering by industry metadata
- Cache only unfiltered stock-list responses in Redis, while filtered requests
  continue to query MongoDB directly
- Keep the stock catalog global at the data layer while preserving the
  codebase's existing org-auth request model for read endpoints

## Capabilities

### New Capabilities

- `stock-symbol-catalog`: provide a backend-managed stock symbol catalog with
  manual refresh from `vnstock` VCI, normalized MongoDB persistence, unfiltered
  list caching, and authenticated API access for listing, searching, and
  filtering symbols

### Modified Capabilities

- None.

## Impact

- **Affected APIs**: adds `GET /api/v1/stocks` for org-authenticated reads and
  `POST /api/v1/stocks/refresh` for Super Admin-triggered manual refresh
- **Affected code**: new router, schemas, service, repository, and `vnstock`
  gateway modules under `app/api/v1/`, `app/domain/schemas/`, `app/services/`,
  and `app/repo/`, plus dependency wiring in shared service factories and v1
  router aggregation
- **Data layer**: introduces a MongoDB collection for normalized stock-symbol
  documents and related indexes for symbol, exchange, group, and search fields
- **Caching**: introduces Redis caching for unfiltered list responses only, with
  cache invalidation during manual refresh
- **Dependencies**: adds `vnstock` as a backend integration dependency and
  relies on the documented `VCI` listing source for richer market metadata
