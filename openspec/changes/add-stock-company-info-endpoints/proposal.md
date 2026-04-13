## Why

The backend currently exposes a persisted stock-symbol catalog, but it does not
yet provide company-detail endpoints for a selected stock. The product now
needs a stable backend contract for company overview, governance, ownership,
events, news, and related tabs without pushing `vnstock` VCI integration logic
into clients.

## What Changes

- Add authenticated tab-wise company-information endpoints under the existing
  stock API surface for one selected stock symbol
- Use `vnstock` company information with source `VCI` only for v1
- Support dedicated read endpoints for company overview, major shareholders,
  officers, subsidiaries, affiliates, events, news, reports, ratio summary, and
  trading stats
- Allow live upstream reads in the request path, backed by Redis caching per
  symbol and graceful stale-cache fallback when upstream fetch fails
- Reuse the existing persisted stock catalog to validate symbols and preserve
  the current org-auth access model

## Capabilities

### New Capabilities
- `stock-company-info`: provide authenticated tab-wise company-information
  endpoints backed by `vnstock` VCI with backend normalization and per-symbol
  caching

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds authenticated `GET /api/v1/stocks/{symbol}/company/*`
  endpoints for tab-wise company data reads
- **Affected code**: new router, schemas, service, cache helper, and `vnstock`
  company gateway modules under `app/api/v1/`, `app/domain/schemas/`, and
  `app/services/`, plus dependency wiring in shared service factories
- **Dependencies**: relies on the current `vnstock` integration with source
  `VCI` for company-information methods
- **Caching**: introduces Redis caching for company-information responses per
  symbol and endpoint section
- **Data layer**: reuses the existing stock catalog for symbol validation; does
  not introduce a new MongoDB snapshot for company-detail payloads in v1
