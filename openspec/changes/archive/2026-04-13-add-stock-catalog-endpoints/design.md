## Context

The current backend has no stock-catalog module, but the product now needs a
stable API for listing Vietnamese stock symbols, searching by symbol or
company name, and filtering by exchange or group. Research against the current
`vnstock` docs shows that the required data exists in `Listing(source='VCI')`,
but it is exposed as multiple listing methods rather than one ready-made API
contract for the backend.

This change is cross-cutting because it introduces:

- a new external dependency and integration surface (`vnstock`)
- a new persisted MongoDB collection for normalized stock symbol documents
- new authenticated API endpoints
- Redis cache behavior specific to the unfiltered list path
- manual refresh behavior that must not break reads if upstream fetch fails

The product decisions already confirmed for this change are:

- read access follows the existing org-auth request model
- the stock catalog dataset is global and shared, not per organization
- `vnstock` uses `VCI` only for v1
- refresh is manual through a Super Admin API, not a background scheduler
- Redis cache is used only for unfiltered list requests
- filtered requests query MongoDB directly

The existing codebase already has the architectural pieces needed for this
approach:

- FastAPI router aggregation in `app/api/v1/router.py`
- shared auth dependencies in `app/api/deps.py`
- service/repository wiring in `app/common/service.py`
- MongoDB and Redis infrastructure already initialized in `app/main.py`
- an existing pattern for public read APIs plus internal persistence-backed
  query services

## Goals / Non-Goals

**Goals:**
- Add a dedicated stock catalog capability with one read endpoint and one
  manual refresh endpoint
- Persist a normalized stock symbol snapshot in MongoDB keyed by `symbol`
- Support the current product query surface: unfiltered list, `q`,
  `exchange`, and `group`
- Use Redis cache only for unfiltered list responses
- Keep reads stable even if a later manual refresh fails
- Reuse the codebase's current router/service/repo patterns and auth model

**Non-Goals:**
- Add scheduled refresh, worker-driven sync, or Cloud Scheduler integration in
  this phase
- Add `KBS` fallback, source rotation, or multi-provider arbitration
- Add Elasticsearch or a dedicated full-text search subsystem
- Add industry-focused filtering behavior beyond storing future-compatible
  metadata
- Add per-organization stock catalogs or organization-specific snapshots
- Add live `vnstock` calls in the `GET /stocks` request path

## Decisions

### D1: Split the feature into a read path and a manual refresh path

**Decision**: Implement two endpoints only:

- `GET /api/v1/stocks` for authenticated catalog reads
- `POST /api/v1/stocks/refresh` for Super Admin-triggered manual refresh

The read path will never call `vnstock` directly. The refresh path is the only
entry point that talks to `vnstock`.

**Rationale**:
- keeps rate-limit and upstream failure risk off the user-facing read path
- matches the requirement that data should be persisted in MongoDB first
- keeps the contract simple while deferring background sync complexity

**Alternatives considered:**
- **Live fetch in `GET /stocks`**: rejected because it couples API latency and
  reliability to `vnstock` and upstream source behavior
- **Background scheduler first**: rejected because the user explicitly chose
  manual refresh for v1

### D2: Keep the stock catalog global at rest but enforce existing org-auth on reads

**Decision**: Store stock documents in one shared MongoDB collection without
`organization_id`, while keeping `GET /stocks` behind the same
`get_current_active_user + get_current_organization_context` access model used
elsewhere in the app.

**Rationale**:
- stock symbols are global market reference data, not tenant-owned business
  objects
- keeping the existing org-auth model avoids introducing a second read-access
  model into the API surface
- avoids duplicating the same catalog across organizations

**Alternatives considered:**
- **Public unauthenticated endpoint**: rejected because the user chose the
  current org-auth model
- **Persist catalog per organization**: rejected because it wastes storage and
  creates unnecessary multi-tenant complexity for global reference data

### D3: Use a dedicated stock catalog service and repository rather than embedding Mongo queries in routers

**Decision**: Add a dedicated `StockCatalogService` and `StockSymbolRepository`
plus a small `VnstockListingGateway`. The router remains thin and delegates all
query composition, cache usage, and refresh orchestration to the service layer.

Recommended module split:

- `app/api/v1/stocks/router.py`
- `app/domain/schemas/stock.py`
- `app/services/stocks/stock_catalog_service.py`
- `app/services/stocks/vnstock_gateway.py`
- `app/repo/stock_symbol_repo.py`

**Rationale**:
- matches the current codebase architecture
- isolates external integration from persistence and HTTP concerns
- keeps auth checks in routers/deps and business behavior in services

**Alternatives considered:**
- **Put refresh logic directly in the router**: rejected because it mixes auth,
  orchestration, external fetch, normalization, and cache invalidation
- **Reuse an unrelated existing analytics/data-query service**: rejected
  because stock catalog semantics are distinct from generic data querying

### D4: Persist one normalized stock-symbol document per symbol

**Decision**: Model the stock catalog as one MongoDB document per stock symbol,
uniquely keyed by `symbol`, with normalized search fields and additive market
metadata required by the API.

Recommended document shape:

```json
{
  "symbol": "FPT",
  "normalized_symbol": "fpt",
  "organ_name": "Công ty Cổ phần FPT",
  "normalized_organ_name": "cong ty co phan fpt",
  "exchange": "HOSE",
  "groups": ["VN30", "VN100"],
  "industry_code": 8300,
  "industry_name": "Technology",
  "source": "VCI",
  "snapshot_at": "2026-04-12T10:15:00Z",
  "updated_at": "2026-04-12T10:15:00Z"
}
```

Recommended indexes:

- unique `symbol`
- `exchange`
- `groups`
- `industry_code`
- `normalized_symbol`
- `normalized_organ_name`

**Rationale**:
- `symbol` is the natural business key for upsert and read APIs
- query use cases are simple enough for document-per-symbol storage
- precomputed normalized fields avoid repeating normalization logic on every
  read

**Alternatives considered:**
- **Store raw upstream payloads only**: rejected because query behavior would
  depend on source-specific fields and require more transformation at read time
- **Store one snapshot document containing all symbols**: rejected because it
  makes filtering and pagination inefficient

### D5: Build the persisted snapshot by merging multiple `vnstock` listing views

**Decision**: The manual refresh implementation will use a small gateway that
assembles the catalog from multiple `Listing(source='VCI')` calls:

- `all_symbols()`
- exchange-specific listing data
- group membership listing data for supported groups
- optional industry metadata from `symbols_by_industries()`

The service will merge these results into one normalized in-memory model before
performing MongoDB upserts.

**Rationale**:
- `vnstock` exposes listing capability as multiple functions rather than one
  all-in-one record source
- separating fetch/normalize/merge keeps the integration testable
- it allows the persisted schema to stay stable even if source response shapes
  vary by method

**Alternatives considered:**
- **Use only `all_symbols()`**: rejected because it does not cover exchange and
  group membership well enough for the target API filters
- **Defer group support and persist only symbol/exchange**: rejected because
  group filtering is already in the committed scope

### D6: Limit v1 filtering to MongoDB-backed query composition with deterministic pagination

**Decision**: `GET /stocks` will support:

- `q`
- `exchange`
- `group`
- `page`
- `page_size`

Filtered reads will use MongoDB directly. Unfiltered reads will use cache if
present, otherwise MongoDB and then cache the result. Pagination stays
page-based in v1 because the dataset size is small and the client contract is
simple.

**Rationale**:
- small catalog size does not justify a more complex search engine
- deterministic page-based reads are sufficient for current UI needs
- aligns with the product decision that cache should only accelerate default
  list reads

**Alternatives considered:**
- **Cache filtered queries too**: rejected because it increases cache-key
  surface and invalidation complexity for little gain in v1
- **Cursor pagination**: rejected because the current scope does not require it

### D7: Use a narrow cache contract for the default list only

**Decision**: Cache only the unfiltered list response in Redis, keyed by page
and page size, with stock-specific key names and explicit invalidation after a
successful refresh.

Recommended key shape:

- `stocks:list:page=<page>:size=<page_size>`

Cache behavior:

- no filters: check Redis first, then Mongo on miss
- any filter present: bypass Redis
- successful refresh: invalidate all `stocks:list:*` keys

**Rationale**:
- exactly matches the requirement already chosen by the user
- keeps invalidation simple and reliable
- avoids stale or fragmented filtered caches

**Alternatives considered:**
- **Single cache key only for page 1**: simpler, but too narrow if the default
  list UI supports pagination
- **No cache in v1**: rejected because the user explicitly wants cache for the
  unfiltered path

### D8: Make refresh failure non-destructive

**Decision**: A manual refresh must not delete the last successful snapshot
before the new snapshot is prepared. The refresh flow will build normalized
records first and then upsert them. If upstream fetching or normalization
fails, existing persisted documents remain readable.

**Rationale**:
- matches the spec requirement to preserve the last successful snapshot
- avoids a broken read API during operator-triggered refresh attempts
- simpler than implementing transactional replacement semantics across large
  batches

**Alternatives considered:**
- **Delete and fully replace**: rejected because any mid-refresh failure would
  create avoidable downtime for reads
- **Write to a shadow collection and swap aliases**: more robust, but heavier
  than needed for this phase

### D9: Restrict refresh to Super Admin and keep read endpoint in org-auth scope

**Decision**: Reuse `require_super_admin` for `POST /stocks/refresh` and reuse
the existing organization context dependency for `GET /stocks`.

**Rationale**:
- refresh is an administrative operation that changes a shared global catalog
- the chosen auth split cleanly separates operator actions from normal product
  reads
- requires no new security model beyond existing dependencies

**Alternatives considered:**
- **Internal API key refresh only**: rejected because the user explicitly
  selected Super Admin JWT
- **Org Admin refresh**: rejected because the dataset is global, not
  organization-owned

## Risks / Trade-offs

**[VCI changes response shape or endpoint behavior]** -> Mitigation: isolate
all upstream calls in `VnstockListingGateway`, keep normalization defensive,
and let refresh fail without impacting the last successful snapshot.

**[Group membership assembly requires multiple upstream calls]** -> Mitigation:
keep an explicit supported group list in configuration or service constants and
merge results deterministically during refresh.

**[Case-insensitive regex search may degrade if the dataset grows]** ->
Mitigation: normalize searchable fields up front and keep the v1 search surface
small; add stronger indexing or full-text search only if query volume grows.

**[Cache keys become stale after manual refresh]** -> Mitigation: invalidate
all `stocks:list:*` keys after a successful refresh and never cache filtered
results.

**[Global dataset plus org-auth may look semantically inconsistent]** ->
Mitigation: document clearly that authorization governs API access while the
catalog itself remains shared reference data.

**[Manual-only refresh can leave stale market metadata]** -> Mitigation:
surface `snapshot_at` in responses so operators and clients can see catalog
freshness until scheduled sync is introduced later.

## Migration Plan

1. Add `vnstock` as a dependency and introduce a small gateway wrapper for
   `Listing(source='VCI')`.
2. Add a new MongoDB collection and indexes for `stock_symbols`.
3. Add repository methods for:
   - upsert by symbol
   - paginated unfiltered reads
   - filtered reads by `q`, `exchange`, and `group`
   - cache invalidation support at the service layer
4. Add domain request/response schemas for stock list and manual refresh
   responses.
5. Add `StockCatalogService` to orchestrate:
   - manual refresh fetch/normalize/upsert
   - cached unfiltered reads
   - direct Mongo filtered reads
6. Add a new FastAPI router and register it in the v1 aggregate router.
7. Extend shared service wiring in `app/common/service.py`.
8. Add tests for:
   - org-auth read access
   - Super Admin refresh authorization
   - unfiltered cache hit/miss behavior
   - filtered queries bypassing cache
   - refresh preserving existing data on failure

**Rollback**

- remove the new router registration
- remove service wiring for the stock catalog feature
- stop calling the refresh endpoint
- leave persisted stock documents in MongoDB because they are additive and do
  not affect existing features

## Open Questions

- Which stock groups must be supported in v1 refresh and filtering beyond the
  obvious baseline such as `VN30` and `VN100`?
- Should `q` use only case-insensitive matching in v1, or do we also want
  accent-insensitive normalization for Vietnamese company names in the first
  implementation?
- Should the read response expose `snapshot_at` only at the envelope level or
  also per item?
