## Why

The product already exposes stock catalog and stock detail endpoints, but users
still lack a first-class way to save symbols they care about for fast access.
This now blocks the next planned stock features because watchlists are the
natural user-owned anchor for follow-on capabilities such as alerts, backtests,
and portfolio-adjacent workflows.

## What Changes

- Add a new authenticated stock watchlist capability scoped by
  `user + organization`
- Allow one user to create multiple named watchlists inside the current
  organization context
- Allow users to add and remove stock symbols from one watchlist, with item
  ordering based on most-recent save time
- Add dedicated read endpoints for listing watchlists and listing watchlist
  items instead of overloading the existing stock catalog APIs
- Return watchlist items merged with the latest persisted stock catalog data at
  read time, rather than storing per-item stock snapshots
- Enforce unique watchlist names per `user + organization` and unique symbols
  per watchlist

## Capabilities

### New Capabilities
- `stock-watchlists`: manage user-owned stock watchlists within an authenticated
  organization context, including watchlist CRUD, add/remove symbol behavior,
  and read responses enriched from the latest persisted stock catalog

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds authenticated watchlist endpoints under
  `/api/v1/stocks/watchlists` for create, list, rename, delete, add item,
  remove item, and list items
- **Affected code**: new stock watchlist models, schemas, repositories,
  services, and router wiring under `app/domain/`, `app/repo/`, `app/services/`,
  `app/common/`, and `app/api/v1/`
- **Data layer**: introduces dedicated MongoDB collections for watchlists and
  watchlist items, with unique indexes for watchlist names and per-watchlist
  symbols
- **Read behavior**: reuses the persisted global stock catalog as the source of
  truth for stock metadata when returning watchlist items
- **Future features**: establishes a durable watchlist data model that can be
  reused later by alerts, backtests, and other personalized stock workflows
