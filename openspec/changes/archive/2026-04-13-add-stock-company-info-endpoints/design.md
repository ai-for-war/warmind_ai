## Context

The current backend already provides a persisted stock-symbol catalog under the
`/stocks` API surface, backed by MongoDB, Redis, and a small `vnstock`
integration for VCI listing data. The product now needs company-detail
endpoints for a selected stock symbol so the frontend can render tab-wise
company views such as overview, shareholders, officers, events, and news.

Research against the current Vnstock docs and the installed runtime shows that
company information for `VCI` is exposed through `Company(source='VCI')` and is
organized by section-oriented methods such as:

- `overview()`
- `shareholders()`
- `officers()`
- `subsidiaries()`
- `affiliate()`
- `events()`
- `news()`
- `reports()`
- `ratio_summary()`
- `trading_stats()`

This change is cross-cutting because it introduces:

- a new external integration path for `vnstock` company information
- multiple new authenticated read endpoints
- a new Redis caching contract for per-symbol company sections
- symbol validation logic that depends on the existing stock catalog
- normalization logic that must track the exact VCI section fields without
  speculative cross-provider aliases

The product decisions already confirmed for this change are:

- reads follow the existing org-auth request model
- company data is exposed through tab-wise endpoints, not one aggregate payload
- `VCI` is the only source in v1
- live upstream requests are acceptable in the read path for this capability
- Redis caching is allowed for company information responses
- the backend should reuse the existing stock catalog to validate symbols

There is one important integration nuance from the current runtime:

- the public Vnstock docs describe `reports()`, `ratio_summary()`, and
  `trading_stats()` for VCI company information
- the installed provider implementation in
  `.venv/Lib/site-packages/vnstock/explorer/vci/company.py` exposes those
  methods
- the higher-level wrapper class in
  `.venv/Lib/site-packages/vnstock/api/company.py` does not declare them
  explicitly even though they are reachable via provider delegation

The implementation therefore needs one isolated gateway layer that documents
that mismatch and optimizes for the currently installed runtime behavior.

## Goals / Non-Goals

**Goals:**
- Add authenticated tab-wise company-information endpoints under the existing
  `/api/v1/stocks/{symbol}/company/*` API surface
- Keep routers thin and place integration, caching, and validation logic in a
  dedicated service layer
- Reuse the existing persisted stock catalog to reject unknown symbols before
  hitting upstream
- Normalize each endpoint to a stable contract derived from the exact VCI
  method scope in use
- Cache company responses per stock symbol and section so repeat reads do not
  always hit upstream
- Serve stale cached responses when upstream fetches fail

**Non-Goals:**
- Add background refresh, snapshot persistence, or MongoDB storage for company
  detail payloads in v1
- Support `KBS`, source rotation, or multi-provider fallback
- Add one aggregate company endpoint that bundles all tabs in a single response
- Add arbitrary query federation, full-text search, or company-detail analytics
- Normalize company payloads into a unified cross-provider schema beyond the
  current VCI runtime path

## Decisions

### D1: Expose company information as dedicated tab-wise read endpoints

**Decision**: Implement separate authenticated GET endpoints under the stock
router:

- `GET /api/v1/stocks/{symbol}/company/overview`
- `GET /api/v1/stocks/{symbol}/company/shareholders`
- `GET /api/v1/stocks/{symbol}/company/officers`
- `GET /api/v1/stocks/{symbol}/company/subsidiaries`
- `GET /api/v1/stocks/{symbol}/company/affiliate`
- `GET /api/v1/stocks/{symbol}/company/events`
- `GET /api/v1/stocks/{symbol}/company/news`
- `GET /api/v1/stocks/{symbol}/company/reports`
- `GET /api/v1/stocks/{symbol}/company/ratio-summary`
- `GET /api/v1/stocks/{symbol}/company/trading-stats`

Only the endpoint-specific section is returned on each request.

**Rationale**:
- matches the confirmed frontend consumption model
- avoids nested pagination and mixed freshness semantics in one aggregate
  payload
- keeps each tab independently cacheable and independently failure-isolated

**Alternatives considered:**
- **One aggregate company endpoint**: rejected because it complicates
  pagination, cache invalidation, and partial failure handling
- **One generic `section` query parameter endpoint**: rejected because
  dedicated routes are clearer in the API surface and easier to type-check

### D2: Keep live upstream reads in the request path, with cache in front of them

**Decision**: Company-information reads will call `vnstock` on demand when no
valid cached response exists. Redis is used as a per-symbol, per-section cache.
If upstream fails and cached data exists, the service returns stale cache.

Recommended key shape:

- `stocks:company:<symbol>:overview`
- `stocks:company:<symbol>:shareholders`
- `stocks:company:<symbol>:officers:filter=<filter_by>`
- `stocks:company:<symbol>:subsidiaries:filter=<filter_by>`
- `stocks:company:<symbol>:affiliate`
- `stocks:company:<symbol>:events`
- `stocks:company:<symbol>:news`
- `stocks:company:<symbol>:reports`
- `stocks:company:<symbol>:ratio-summary`
- `stocks:company:<symbol>:trading-stats`

**Rationale**:
- company details are naturally symbol-specific and requested on demand
- a single VCI company read path is acceptable for this scope
- caching provides latency improvement and protects upstream from repeated
  reads on popular symbols
- stale fallback improves resilience without introducing snapshot storage

**Alternatives considered:**
- **Persist company data in MongoDB first**: rejected for v1 because it would
  require expensive symbol-wide refresh orchestration and a larger write model
- **No cache**: rejected because repeated tab reads would unnecessarily hit
  upstream and expose more latency variance to clients

### D3: Reuse the existing stock catalog as the validation boundary

**Decision**: Before calling upstream company methods, the service validates
that the requested symbol exists in the existing persisted stock catalog. The
service normalizes the path parameter to uppercase and rejects unknown symbols
before any `vnstock` request is sent.

Recommended repository addition:

- `exists_by_symbol(symbol: str) -> bool`

**Rationale**:
- avoids unnecessary upstream calls for invalid symbols
- reuses the backend's authoritative symbol universe
- keeps validation logic local to the stock domain instead of scattering it in
  routers or gateway code

**Alternatives considered:**
- **Trust any symbol and defer validation to upstream**: rejected because it
  wastes upstream calls and leads to inconsistent error behavior
- **Keep an in-memory allowlist only**: rejected because the persisted stock
  catalog already exists and is the better boundary

### D4: Introduce a dedicated company gateway instead of calling vnstock directly from the service

**Decision**: Add a dedicated `VnstockCompanyGateway` that wraps
`Company(symbol=..., source='VCI')` and exposes one method per section. This
gateway converts DataFrame-like payloads into plain dictionaries and lists,
documents the runtime mismatch around provider-exposed methods, and preserves
canonical VCI field names.

Recommended module split:

- `app/services/stocks/company_gateway.py`
- `app/services/stocks/company_cache.py`
- `app/services/stocks/company_service.py`
- `app/domain/schemas/stock_company.py`
- `app/api/v1/stocks/router.py` (extended)

**Rationale**:
- isolates third-party integration behavior in one place
- aligns with the existing listing gateway pattern already used by the stock
  catalog
- allows targeted tests for upstream conversion, stale fallback, and error
  handling

**Alternatives considered:**
- **Call `vnstock` directly in the service**: rejected because the service
  would mix orchestration, cache policy, and upstream payload adaptation
- **Call provider internals directly instead of the public Company wrapper**:
  rejected because it increases coupling to the package layout

### D5: Normalize responses by section, not into one flattened company document

**Decision**: The backend will use endpoint-specific response schemas:

- snapshot responses for `overview`, `ratio-summary`, and `trading-stats`
- list responses for `shareholders`, `officers`, `subsidiaries`, `affiliate`,
  `events`, `news`, and `reports`

Every response should include stable envelope metadata such as:

- `symbol`
- `source`
- `fetched_at`
- `cache_hit`

The item fields themselves remain section-specific and aligned to VCI.

**Rationale**:
- the upstream data is already segmented by business meaning
- a flattened all-sections schema would create sparse payloads and couple
  unrelated tabs together
- section-specific schemas keep the contract explicit and closer to frontend
  usage

**Alternatives considered:**
- **One normalized company document**: rejected because the sections differ too
  much in shape and cardinality
- **Return raw DataFrame-like records without an envelope**: rejected because
  it misses traceability metadata such as source and cache status

### D6: Keep filtering and pagination narrow and endpoint-specific in v1

**Decision**: Only the filters already required by VCI methods are exposed in
v1:

- `officers`: `filter_by=working|resigned|all`
- `subsidiaries`: `filter_by=all|subsidiary`

All other sections are returned using the upstream default shape in v1. The
initial design does not add backend-owned pagination or custom filtering for
`news`, `events`, or `reports` unless implementation confirms that the runtime
path already requires it.

**Rationale**:
- avoids inventing behavior not yet demanded by the current product scope
- keeps v1 close to the existing VCI section contracts
- reduces normalization and cache-key complexity

**Alternatives considered:**
- **Add generic pagination to every list endpoint immediately**: rejected
  because it adds non-trivial contract surface before the product needs it
- **Add backend-side search/filtering within company sections**: rejected
  because it is outside the current requirement set

### D7: Isolate failures at the requested section and tolerate section-specific gaps

**Decision**: Failures are handled per endpoint section. If a section has a
cache miss and upstream fails, only that endpoint request fails. If a cached
response exists, the service returns stale data. Known unstable sections such
as `subsidiaries` must use the same policy rather than causing failures in
unrelated tabs.

**Rationale**:
- tab-wise UI tolerates section-level freshness differences much better than
  page-wide failures
- upstream section stability is not uniform
- section isolation is a direct benefit of the tab-wise API design

**Alternatives considered:**
- **Fail the whole company feature when any section is unstable**: rejected
  because it harms availability for otherwise healthy tabs
- **Silently return empty data for every upstream failure**: rejected because
  it hides operational issues and makes debugging harder than stale-cache
  fallback plus explicit errors

## Risks / Trade-offs

**[VCI response shape changes per section]** -> Mitigation: isolate all
upstream access in `VnstockCompanyGateway`, preserve canonical field mapping by
section, and add comments near the integration when docs and runtime differ.

**[The installed vnstock wrapper and provider expose slightly different method surfaces]** -> Mitigation:
optimize for the currently installed runtime, document the mismatch in the
gateway, and add tests around the sections used by the backend.

**[Live upstream reads can be slower or intermittently unavailable]** ->
Mitigation: cache per symbol and section, return stale cache on upstream
failure, and keep routers out of the integration path.

**[Cache keys multiply as sections and filters grow]** -> Mitigation: keep v1
filters narrow and use explicit key builders per endpoint section.

**[Known unstable sections such as subsidiaries may behave inconsistently]** ->
Mitigation: treat each section independently, allow stale fallback, and avoid
coupling one section's availability to another.

**[Without persisted company snapshots, cold reads still depend on upstream]** ->
Mitigation: accept this trade-off for v1 simplicity and add persistence only if
traffic or reliability requirements justify it later.

## Migration Plan

1. Add domain schemas for company-information envelopes and section-specific
   items.
2. Add `VnstockCompanyGateway` for `Company(source='VCI')` section reads and
   DataFrame-to-dict conversion.
3. Add a dedicated Redis cache helper for company-information responses keyed
   by symbol and section.
4. Extend `StockSymbolRepository` with a symbol existence lookup for request
   validation.
5. Add `StockCompanyService` to orchestrate:
   - symbol normalization and validation
   - cache lookup
   - upstream fetch on miss
   - normalization into response schemas
   - stale-cache fallback on upstream failure
6. Extend the stock router with `/stocks/{symbol}/company/*` endpoints while
   reusing the existing org-auth dependencies.
7. Wire the new gateway, cache, and service into `app/common/service.py`.
8. Add tests for:
   - organization-scoped read access
   - invalid symbol rejection before upstream calls
   - cache hit/miss behavior
   - stale-cache fallback on upstream failure
   - section-specific filters for officers and subsidiaries
   - endpoint-level failure isolation

**Rollback**

- remove the new company-information routes from the stock router
- remove the new service/gateway/cache wiring
- leave Redis keys to expire naturally or invalidate the `stocks:company:*`
  namespace
- keep the existing stock catalog unchanged because it remains independently
  useful

## Open Questions

- Should `news`, `events`, and `reports` expose backend-owned pagination in v1,
  or should the first implementation return the upstream default payload size?
- Should the stale-cache responses surface an explicit freshness flag beyond
  `cache_hit`, such as `stale=true`?
- Do we want a single short-lived overview aggregation endpoint later that
  combines `overview`, `ratio-summary`, and `trading-stats` for the first tab,
  or should the backend stay strictly tab-wise?
