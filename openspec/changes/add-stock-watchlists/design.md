## Context

The backend already exposes authenticated stock catalog and stock detail APIs,
with the stock catalog persisted globally in MongoDB and guarded by the
existing `active user + organization context` request model. The product now
needs personalized saved-stock behavior so one user can keep multiple named
watchlists inside one organization and return to those symbols quickly.

This change is cross-cutting because it introduces:

- new user-owned MongoDB data models under the stocks domain
- new authenticated CRUD APIs under the existing stock API surface
- read-time composition between personalized watchlist data and the shared
  stock catalog
- future extension points for alerts, backtests, and other user-specific stock
  workflows

Product decisions already confirmed for this change are:

- watchlists are scoped by `user + organization`
- one user can create multiple named watchlists
- watchlist names must be unique per `user + organization`
- one symbol can exist in multiple watchlists, but only once per watchlist
- watchlist item ordering is based on newest `saved_at` first
- the API surface uses dedicated watchlist endpoints
- watchlist item reads must merge the latest persisted stock catalog data
- v1 includes full watchlist CRUD and item add/remove operations

The existing codebase already provides the architectural pieces needed for this
approach:

- FastAPI router aggregation in `app/api/v1/router.py`
- auth and organization guards in `app/api/deps.py`
- shared repo/service wiring in `app/common/repo.py` and
  `app/common/service.py`
- a persisted stock catalog repository in `app/repo/stock_symbol_repo.py`
- established service/repository layering for stock capabilities

## Goals / Non-Goals

**Goals:**
- Add a dedicated stock watchlist capability under the existing authenticated
  stock API surface
- Persist watchlists and watchlist items as user-owned, organization-scoped
  MongoDB documents
- Support watchlist create, list, rename, delete, add symbol, remove symbol,
  and list items behavior
- Merge watchlist items with the latest stock catalog metadata at read time
- Keep the data model extensible for later stock-personalization features

**Non-Goals:**
- Add portfolio accounting, position sizing, PnL, or transaction tracking
- Add notifications, alerts, scheduled jobs, or background recalculation
- Add user-defined item ordering beyond newest-saved-first
- Add snapshot persistence of stock metadata on watchlist items in v1
- Add cross-organization watchlist sharing or organization-wide shared
  watchlists
- Add `is_saved` personalization flags to the existing stock catalog endpoint

## Decisions

### D1: Model watchlists and watchlist items as separate collections

**Decision**: Introduce two MongoDB collections:

- `stock_watchlists`
- `stock_watchlist_items`

Recommended shapes:

```json
{
  "_id": "watchlist_id",
  "user_id": "user-1",
  "organization_id": "org-1",
  "name": "Watchlist A",
  "normalized_name": "watchlist a",
  "created_at": "2026-04-17T08:00:00Z",
  "updated_at": "2026-04-17T08:00:00Z"
}
```

```json
{
  "_id": "item_id",
  "watchlist_id": "watchlist_id",
  "user_id": "user-1",
  "organization_id": "org-1",
  "symbol": "FPT",
  "normalized_symbol": "fpt",
  "saved_at": "2026-04-17T08:10:00Z",
  "updated_at": "2026-04-17T08:10:00Z"
}
```

Recommended indexes:

- unique `(user_id, organization_id, normalized_name)` on `stock_watchlists`
- unique `(watchlist_id, normalized_symbol)` on `stock_watchlist_items`
- index `(watchlist_id, saved_at desc)` on `stock_watchlist_items`
- optional index `(user_id, organization_id)` on both collections for later
  personalized stock workflows

**Rationale**:
- watchlists and watchlist items have different lifecycle and query patterns
- list-items and item-level uniqueness become straightforward
- the model stays extensible for later per-item alert or annotation metadata

**Alternatives considered:**
- **Embed items inside one watchlist document**: rejected because item growth is
  unbounded and item-level sort/update/remove behavior becomes clumsier
- **Embed watchlists inside `users`**: rejected because the feature is scoped by
  `user + organization`, not just user, and later stock-personalization
  features would outgrow the user document quickly

### D2: Keep stock metadata out of watchlist storage and merge latest catalog data at read time

**Decision**: Persist only watchlist identity and saved symbol references.
Watchlist item reads will join against the latest persisted stock catalog by
`symbol` when building responses.

Read flow:

1. validate the requested watchlist belongs to `current_user + organization`
2. load paginated or full watchlist items sorted by `saved_at desc`
3. collect the symbols from those items
4. bulk read the current active stock catalog entries for those symbols
5. merge item metadata with the latest catalog metadata in the response

**Rationale**:
- the latest catalog remains the single source of truth for stock metadata
- watchlist item reads reflect refreshed market-reference data automatically
- avoids stale denormalized stock metadata inside personalized collections

**Alternatives considered:**
- **Persist `saved_snapshot` on each item**: rejected because the user chose
  latest-catalog merge semantics instead of save-time snapshots
- **Call upstream stock providers during watchlist reads**: rejected because the
  existing stock catalog already isolates upstream dependencies from user-facing
  list reads

### D3: Duplicate `user_id` and `organization_id` onto watchlist items

**Decision**: Store `user_id` and `organization_id` on both watchlists and
watchlist items, even though they are derivable from the parent watchlist.

**Rationale**:
- keeps future scans and queries for user/org-scoped stock data cheap
- simplifies later extension to alerts or background jobs without requiring an
  extra lookup through the parent watchlist
- makes integrity checks and admin diagnostics easier

**Alternatives considered:**
- **Store only `watchlist_id` on items**: rejected because it saves little data
  but weakens future query flexibility

### D4: Expose a dedicated watchlist router under the stocks namespace

**Decision**: Add dedicated authenticated endpoints under
`/api/v1/stocks/watchlists`:

- `POST /stocks/watchlists`
- `GET /stocks/watchlists`
- `PATCH /stocks/watchlists/{watchlist_id}`
- `DELETE /stocks/watchlists/{watchlist_id}`
- `GET /stocks/watchlists/{watchlist_id}/items`
- `POST /stocks/watchlists/{watchlist_id}/items`
- `DELETE /stocks/watchlists/{watchlist_id}/items/{symbol}`

All endpoints will require `get_current_active_user` and
`get_current_organization_context`.

**Rationale**:
- matches the product choice to keep watchlist behavior separate from the
  catalog API
- preserves the existing org-auth request model already used by stock APIs
- gives the frontend a narrow and explicit contract for watchlist management

**Alternatives considered:**
- **Extend `GET /stocks` with saved flags and write actions**: rejected because
  it mixes global catalog behavior with personalized watchlist behavior and
  complicates the current cache-friendly catalog design
- **Put watchlists under `/users/me`**: rejected because the feature belongs to
  the stocks domain and relies on stock-specific validation and composition

### D5: Validate symbols against the persisted stock catalog before insertion

**Decision**: Adding a watchlist item will normalize the requested symbol to
uppercase and validate it against the active persisted stock catalog before
creating the item.

Implementation support:

- extend `StockSymbolRepository` with a bulk lookup helper for watchlist read
  composition
- reuse the existing active snapshot semantics of the catalog repository for
  symbol validation and latest metadata reads

**Rationale**:
- avoids storing arbitrary symbols that the backend cannot later resolve
- keeps watchlist data aligned with the canonical stock catalog already used by
  other stock features
- prevents unnecessary future edge cases in alerts and backtests

**Alternatives considered:**
- **Allow free-form symbols and resolve later**: rejected because it weakens the
  contract and creates inconsistent downstream behavior

### D6: Use service-layer ownership checks and deterministic newest-first item ordering

**Decision**: The service layer will enforce that each watchlist belongs to the
current user within the current organization context before rename, delete,
add-item, remove-item, or list-items operations. Item reads are sorted by
`saved_at desc`.

**Rationale**:
- ownership checks belong in the business layer, not scattered through routers
- newest-first ordering matches the confirmed product requirement and keeps the
  read contract deterministic

**Alternatives considered:**
- **Sort alphabetically by symbol**: rejected because it does not match the
  confirmed UX requirement
- **Store arbitrary client-defined rank**: rejected because custom ordering is
  out of scope for v1

### D7: Keep watchlist deletes explicit and cascading at the application layer

**Decision**: Deleting a watchlist will remove the watchlist document and all
its item documents through the application service/repository layer.

**Rationale**:
- MongoDB does not provide relational cascades automatically
- explicit delete orchestration keeps behavior obvious and testable
- avoids orphaned watchlist items

**Alternatives considered:**
- **Soft-delete watchlists only**: rejected for v1 because the product has not
  asked for restore behavior and it complicates uniqueness rules
- **Leave items orphaned and clean up later**: rejected because it creates
  avoidable data integrity issues

## Risks / Trade-offs

**[Catalog refresh removes a symbol that still exists in a watchlist]** ->
Mitigation: keep watchlist item identity independent from stock metadata and
define response behavior so item records stay readable even if latest catalog
metadata is unavailable.

**[Two-collection writes create partial-failure risk on watchlist delete]** ->
Mitigation: keep delete flow narrow, remove child items before or with parent
cleanup, and cover failure paths with service tests.

**[User-owned watchlists increase per-user query volume later]** -> Mitigation:
add the recommended compound indexes from the start and keep endpoints scoped
to one watchlist or one user/org list.

**[Future requirements may want save-time stock snapshots]** -> Mitigation:
keep the response contract layered so save-time metadata can be added later
without rewriting the watchlist ownership model.

## Migration Plan

1. Add new domain models and request/response schemas for watchlists and
   watchlist items.
2. Add MongoDB repositories and indexes for `stock_watchlists` and
   `stock_watchlist_items`.
3. Extend the stock catalog repository with a bulk active-symbol lookup helper
   for watchlist response composition.
4. Add a dedicated stock watchlist service that handles ownership checks,
   uniqueness, symbol validation, create/list/rename/delete flows, and
   watchlist item composition.
5. Add an authenticated watchlist router under the stocks API namespace and
   register it in the v1 router aggregation.
6. Wire repositories and services into shared dependency factories.
7. Add unit and integration tests for auth, uniqueness, CRUD behavior, symbol
   validation, newest-first ordering, and delete cascades.

**Rollback**

- remove the watchlist router registration
- remove shared dependency wiring for watchlist services and repositories
- stop calling the new endpoints
- optionally drop the new watchlist collections if rollback needs full cleanup

## Open Questions

- When a watchlist item's symbol no longer exists in the active stock catalog,
  should the response return `stock: null`, omit the stock block entirely, or
  fail the item read?
