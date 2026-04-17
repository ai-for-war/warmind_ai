## 1. Domain and schema foundations

- [x] 1.1 Add stock watchlist and stock watchlist item domain models under `app/domain/models/`
- [x] 1.2 Add request and response schemas for watchlist create, list, rename, delete, list items, add item, and remove item flows under `app/domain/schemas/`
- [x] 1.3 Define schema fields for watchlist ownership, watchlist identity, item identity, saved timestamps, and merged stock metadata response blocks

## 2. Persistence and catalog integration

- [x] 2.1 Add a `stock_watchlists` repository with create, list-by-user-and-organization, find-owned-watchlist, rename, delete, and duplicate-name checks
- [x] 2.2 Add a `stock_watchlist_items` repository with add, list-by-watchlist newest-first, remove-by-symbol, duplicate-symbol checks, and delete-by-watchlist behavior
- [x] 2.3 Create MongoDB indexes for unique watchlist names per `user + organization` and unique symbols per watchlist
- [x] 2.4 Extend the stock catalog repository with bulk active-symbol lookup support for watchlist item response composition
- [x] 2.5 Wire the new repositories into `app/common/repo.py`

## 3. Watchlist service behavior

- [x] 3.1 Add a dedicated stock watchlist service under `app/services/stocks/` for watchlist CRUD and item operations
- [x] 3.2 Implement ownership enforcement for all watchlist reads and writes using `current_user + organization` scope
- [x] 3.3 Implement watchlist-name normalization and uniqueness handling for create and rename flows
- [x] 3.4 Implement symbol normalization, stock-catalog validation, and per-watchlist duplicate rejection for add-item flows
- [x] 3.5 Implement watchlist item reads that merge saved items with the latest persisted stock catalog data without save-time stock snapshots
- [x] 3.6 Implement cascading delete behavior so removing a watchlist also removes its watchlist items
- [x] 3.7 Wire the watchlist service into `app/common/service.py`

## 4. API wiring

- [ ] 4.1 Add authenticated watchlist endpoints under `app/api/v1/stocks/` for create, list, rename, delete, list items, add item, and remove item operations
- [ ] 4.2 Apply `get_current_active_user` and `get_current_organization_context` to all watchlist endpoints
- [ ] 4.3 Register the watchlist router in the v1 router aggregation
- [ ] 4.4 Ensure API responses expose newest-first watchlist items with merged latest stock catalog metadata

## 5. Tests and verification

- [ ] 5.1 Add repository tests for watchlist-name uniqueness, per-watchlist symbol uniqueness, newest-first item listing, and delete cascades
- [ ] 5.2 Add service tests for ownership enforcement, stock-catalog validation, rename behavior, add/remove item behavior, and latest-catalog merge behavior
- [ ] 5.3 Add API tests for organization-auth access control and full watchlist CRUD plus item add/remove flows
- [ ] 5.4 Add API or service tests that verify the same symbol can exist in different watchlists for the same user and organization
