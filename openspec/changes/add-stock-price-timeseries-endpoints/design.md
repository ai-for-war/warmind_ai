## Context

The current backend already provides a persisted stock-symbol catalog under the
`/stocks` API surface and authenticated company-information endpoints for one
selected stock symbol. The product now needs price-timeseries endpoints so the
frontend can render historical charts and intraday trade views without pushing
`vnstock` VCI integration details into clients.

Research against the current `vnstock` docs and the installed runtime shows
that stock price data for `VCI` is exposed through `Quote(source='VCI')` and is
organized around two methods relevant to this change:

- `history()` for historical OHLCV data
- `intraday()` for intraday trade timeseries

This change is cross-cutting because it introduces:

- a new external integration path for `vnstock` quote data
- multiple new authenticated read endpoints
- a new Redis caching contract for per-symbol, per-query timeseries responses
- symbol validation logic that depends on the existing stock catalog
- normalization logic that must track the exact VCI runtime fields without
  speculative cross-provider aliases

The product decisions already confirmed for this change are:

- reads follow the existing org-auth request model
- the capability is limited to symbols already present in the shared stock
  catalog
- `VCI` is the only source in v1
- the API surface exposes both `history` and `intraday`
- responses return raw normalized timeseries only, without backend-derived
  analytics
- live upstream reads are acceptable in the request path when cache misses

There are two important integration nuances from the current runtime:

- the installed provider implementation in
  `.venv/lib/python3.12/site-packages/vnstock/explorer/vci/quote.py` exposes the
  VCI runtime path we actually depend on:
  - `history(start, end, interval, show_log, count_back, floating, length)`
  - `intraday(page_size, last_time, last_time_format, show_log)`
- the higher-level wrapper in
  `.venv/lib/python3.12/site-packages/vnstock/api/quote.py` advertises a wider
  surface, including `page` for `intraday()` and backward-compatible aliases
  like `resolution`, but those do not represent the exact VCI provider contract
  we want to expose publicly

The implementation therefore needs one isolated gateway layer that documents
runtime-vs-wrapper differences and optimizes for the currently installed VCI
behavior.

## Goals / Non-Goals

**Goals:**
- Add authenticated stock price endpoints under the existing
  `/api/v1/stocks/{symbol}/prices/*` API surface
- Keep routers thin and place validation, cache policy, normalization, and
  upstream integration in a dedicated service layer
- Reuse the existing persisted stock catalog to reject unknown symbols before
  hitting upstream
- Normalize each endpoint to a stable contract derived from the exact VCI quote
  method scope in use
- Return raw timeseries only, with stable envelope metadata and canonical item
  fields
- Cache responses per stock symbol, endpoint section, and normalized query
  variant so repeat reads do not always hit upstream
- Serve stale cached responses when upstream quote fetches fail

**Non-Goals:**
- Add MongoDB snapshot persistence or background refresh for price timeseries in
  v1
- Support `KBS`, source rotation, or multi-provider fallback
- Expose indices, futures, CW, or other symbols outside the current stock
  catalog boundary
- Add backend-derived analytics, summary metrics, or aggregate statistics in
  price responses
- Expose the full raw `vnstock` parameter surface such as public `count_back`,
  `resolution`, or `page`
- Add websocket streaming, push updates, or price-depth endpoints in this phase

## Decisions

### D1: Expose price data as two dedicated read endpoints under the stock router

**Decision**: Implement two authenticated GET endpoints under the existing
stock router:

- `GET /api/v1/stocks/{symbol}/prices/history`
- `GET /api/v1/stocks/{symbol}/prices/intraday`

Only the endpoint-specific payload is returned on each request.

Recommended response envelopes:

- history response: `symbol`, `source`, `cache_hit`, `interval`,
  `items`
- intraday response: `symbol`, `source`, `cache_hit`, `items`

**Rationale**:
- matches the confirmed frontend consumption model
- keeps `history` and `intraday` independently cacheable and independently
  failure-isolated
- avoids mixing different freshness, pagination, and query semantics into one
  payload

**Alternatives considered:**
- **One aggregate price endpoint**: rejected because it would combine two data
  shapes with different query contracts and cache behavior
- **Expose this capability as `/quote/*`**: rejected because `prices/*` is
  clearer in the API surface and more consistent with product terminology

### D2: Reuse the company-info service pattern with a dedicated price gateway and cache helper

**Decision**: Add a dedicated stock-price module split that mirrors the working
company-information pattern:

- `app/domain/schemas/stock_price.py`
- `app/services/stocks/price_gateway.py`
- `app/services/stocks/price_cache.py`
- `app/services/stocks/price_service.py`
- `app/api/v1/stocks/router.py` (extended)
- `app/common/service.py` (dependency wiring)

The router remains thin and delegates orchestration to `StockPriceService`.
`VnstockPriceGateway` wraps `Quote(symbol=..., source='VCI')` and converts
DataFrame-like payloads into plain dictionaries. `StockPriceCache` owns Redis
key construction and serialization.

**Rationale**:
- aligns with the existing stock-company implementation already in the repo
- isolates third-party integration behavior in one place
- makes cache policy, error mapping, and normalization testable without HTTP
  transport concerns

**Alternatives considered:**
- **Call `vnstock` directly in the router or service only**: rejected because it
  would mix orchestration, cache policy, and payload adaptation
- **Reuse `company_cache` or `company_gateway` directly**: rejected because
  price data has different query-variant semantics, item shapes, and TTL needs

### D3: Keep the public query contract narrower than the full vnstock runtime surface

**Decision**: Expose only the public query parameters needed for the agreed v1
product scope.

Public `history` query contract:

- `start`
- `end`
- `interval`
- `length`

Public `intraday` query contract:

- `page_size`
- `last_time`
- `last_time_format`

Contract rules:

- `history` requires exactly one of:
  - explicit range mode: `start` with optional `end`
  - lookback mode: `length`
- requests that provide both `start` and `length`, or neither, are rejected
- `count_back` is not exposed publicly in v1 even though the provider supports
  it internally
- `page` is not exposed for `intraday` even though the wrapper advertises it,
  because the exact VCI provider path does not use it
- backward-compatible wrapper aliases such as `resolution` are not exposed in
  the backend API contract

**Rationale**:
- keeps the backend contract stable and easy to document
- avoids leaking wrapper-specific or backward-compatibility behavior into the
  public API
- reduces cache-key permutations and validation ambiguity

**Alternatives considered:**
- **Expose the entire vnstock parameter surface immediately**: rejected because
  it would couple the API contract to a broader and less stable wrapper surface
- **Hide lookback mode and require only `start`/`end`**: rejected because the
  product explicitly wants practical historical exploration flows, and `length`
  is part of the confirmed scope

### D4: Normalize responses to canonical raw VCI timeseries fields only

**Decision**: Normalize each endpoint to a stable response envelope with
endpoint-specific raw item fields derived from the exact VCI runtime output.

Recommended canonical fields:

- `history` items: `time`, `open`, `high`, `low`, `close`, `volume`
- `intraday` items: `time`, `price`, `volume`, `match_type`, `id`

Normalization behavior:

- convert DataFrame-like outputs to plain record lists
- collapse missing numeric/string cells such as `NaN` to `None` where needed
- preserve the canonical VCI field names already materialized by the provider
- serialize time values through Pydantic/FastAPI as stable datetime strings
- do not append derived metrics such as return percentages, max/min summaries,
  average volume, or trend labels

Recommended gateway behavior:

- accept only the exact allowed fields per endpoint
- return `[]` for empty list-like payloads rather than inventing placeholder
  records
- document any observed runtime mismatch close to the gateway code when docs and
  installed behavior differ

**Rationale**:
- keeps the backend contract close to the confirmed product need and to the VCI
  runtime path we depend on
- avoids speculative aliasing across providers
- keeps the frontend free to compute chart-level analytics without the backend
  owning those semantics in v1

**Alternatives considered:**
- **Return raw DataFrame-like payloads directly**: rejected because the API
  should not expose pandas-oriented transport details
- **Add summary blocks beside raw items**: rejected because the user explicitly
  scoped v1 to raw timeseries only

### D5: Validate symbols against the shared stock catalog and offload upstream calls to a threadpool

**Decision**: Before calling upstream quote methods, the service validates that
the requested symbol exists in the existing persisted stock catalog via
`StockSymbolRepository.exists_by_symbol()`. The service normalizes the path
parameter to uppercase and rejects unknown symbols before any `vnstock` request
is sent.

The service will also offload gateway reads to `run_in_threadpool`, following
the existing `StockCompanyService` pattern, because `vnstock` quote methods are
synchronous and perform blocking network and pandas work.

**Rationale**:
- avoids unnecessary upstream calls for invalid symbols
- reuses the backend's authoritative symbol universe
- keeps validation out of routers and gateway internals
- prevents blocking the async request path during cold reads and cache misses

**Alternatives considered:**
- **Trust any symbol and defer validation to upstream**: rejected because it
  wastes upstream calls and creates inconsistent error behavior
- **Call `vnstock` directly on the event loop**: rejected because the library is
  synchronous and would add avoidable latency coupling under load

### D6: Cache by symbol, section, and normalized query variant, with stale fallback

**Decision**: Use Redis caching in front of live upstream reads. Keys are built
from the normalized symbol, endpoint section, and a deterministic query-variant
string. If an upstream request fails and cached data for that exact variant
exists, the service returns stale cache instead of failing the request.

Recommended key shape:

- `stocks:prices:<symbol>:history:interval=<interval>:start=<start>:end=<end>`
- `stocks:prices:<symbol>:history:interval=<interval>:length=<length>`
- `stocks:prices:<symbol>:intraday:page_size=<page_size>:last_time=<last_time>:last_time_format=<last_time_format>`

Recommended cache policy:

- normalize symbols to uppercase before key generation
- normalize absent optional values consistently in the variant builder so
  semantically identical requests share one key
- use shorter TTLs for intraday than for history because intraday data changes
  more frequently
- keep history and intraday cache namespaces separate even for the same symbol

**Rationale**:
- repeated reads for popular symbols should not always hit upstream
- exact query-variant keys avoid stale cross-contamination between different
  history windows or intraday cursors
- stale fallback improves resilience without introducing persistent snapshots

**Alternatives considered:**
- **No cache**: rejected because it would expose every repeat read to upstream
  latency and availability
- **Cache only by symbol and endpoint**: rejected because different ranges and
  cursors would overwrite one another and return incorrect payloads

### D7: Map validation and upstream failures into predictable API behavior

**Decision**: Keep failure handling explicit and endpoint-local.

Recommended behavior:

- invalid symbol: `404`
- request-shape or schema validation errors: `422`
- provider errors caused by invalid user-supplied time values or incompatible
  query combinations: `422`
- upstream availability, transport, or unexpected normalization failures:
  `502`, unless stale cache exists for the same variant

The service must not silently replace failures with empty data on cache misses.
Failures remain scoped to the requested endpoint and query variant.

**Rationale**:
- gives clients deterministic behavior for the most common failure classes
- preserves operational visibility when upstream is unhealthy
- matches the existing section-level isolation pattern already used for company
  data

**Alternatives considered:**
- **Always return empty arrays on upstream failure**: rejected because it hides
  real operational issues and corrupts client assumptions
- **Treat every upstream error as `500`**: rejected because many query issues are
  actually client-correctable and should remain distinguishable from transport
  failures

## Risks / Trade-offs

**[The installed vnstock wrapper and the VCI provider expose slightly different quote surfaces]** -> Mitigation:
optimize for the currently installed VCI runtime, document mismatches near the
gateway, and keep the public API contract narrower than the wrapper surface.

**[Live upstream reads can be slow or intermittently unavailable on cold cache misses]** -> Mitigation:
cache per symbol and query variant, offload reads to a threadpool, and return
stale cache when available.

**[Cache keys multiply as history windows and intraday cursors vary]** -> Mitigation:
keep the public query surface narrow, normalize variants deterministically, and
set endpoint-appropriate TTLs.

**[Without MongoDB persistence, cache cold-start still depends on upstream]** -> Mitigation:
accept this trade-off for v1 simplicity and add persistence only if traffic or
reliability requirements justify it later.

**[Provider-side intraday behavior can vary by market session state]** -> Mitigation:
propagate explicit validation/upstream errors when no stale cache exists and
avoid inventing synthetic fallback data.

## Migration Plan

1. Add domain schemas for history and intraday query params, item payloads, and
   response envelopes.
2. Add `VnstockPriceGateway` for `Quote(source='VCI')` reads and
   DataFrame-to-dict conversion.
3. Add a dedicated Redis cache helper for stock-price responses keyed by
   symbol, section, and query variant.
4. Reuse `StockSymbolRepository.exists_by_symbol()` for request validation.
5. Add `StockPriceService` to orchestrate:
   - symbol normalization and validation
   - query normalization
   - cache lookup
   - upstream fetch on miss via threadpool
   - normalization into response schemas
   - stale-cache fallback on upstream failure
   - deterministic error mapping
6. Extend the stock router with `/stocks/{symbol}/prices/history` and
   `/stocks/{symbol}/prices/intraday` endpoints while reusing the existing
   org-auth dependencies.
7. Wire the new gateway, cache, and service into `app/common/service.py`.
8. Add tests for:
   - organization-scoped read access
   - invalid symbol rejection before upstream calls
   - history query validation and intraday query validation
   - cache hit/miss behavior by query variant
   - stale-cache fallback on upstream failure
   - gateway normalization of canonical history and intraday fields
   - endpoint-level and query-variant failure isolation

**Rollback**

- remove the new price routes from the stock router
- remove the new service/gateway/cache wiring
- leave Redis keys to expire naturally or invalidate the `stocks:prices:*`
  namespace
- keep the existing stock catalog unchanged because it remains independently
  useful

## Open Questions

- None for the currently agreed v1 scope.
