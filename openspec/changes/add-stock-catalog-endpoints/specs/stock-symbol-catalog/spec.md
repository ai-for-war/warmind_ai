## ADDED Requirements

### Requirement: Stock catalog read access follows the existing authenticated organization request model
The system SHALL provide an authenticated stock catalog read API that requires
an active user and a valid `X-Organization-ID` request context, consistent with
the existing organization-scoped API contract. The stock catalog itself MUST be
stored as a global shared dataset and MUST NOT be partitioned per organization.

#### Scenario: Read stock catalog with valid organization context
- **WHEN** an authenticated active user calls the stock catalog read API with a valid `X-Organization-ID`
- **THEN** the system returns stock catalog data from the shared catalog dataset

#### Scenario: Reject stock catalog reads without valid organization context
- **WHEN** a request to the stock catalog read API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: Manual stock catalog refresh is restricted to Super Admins
The system SHALL provide a manual stock catalog refresh API that is restricted
to authenticated Super Admin users. The refresh API MUST fetch listing data
from `vnstock` using the `VCI` source only.

#### Scenario: Super Admin manually refreshes the stock catalog
- **WHEN** an authenticated Super Admin calls the stock catalog refresh API
- **THEN** the system fetches the latest stock listing snapshot from `vnstock` using `Listing(source='VCI')`
- **AND** the system updates the persisted stock catalog snapshot

#### Scenario: Non-Super Admin cannot manually refresh the stock catalog
- **WHEN** an authenticated user without Super Admin privileges calls the stock catalog refresh API
- **THEN** the system MUST reject the request

### Requirement: Manual refresh persists a normalized stock symbol catalog in MongoDB
The system SHALL normalize and persist stock symbol data in MongoDB during
manual refresh. Each persisted stock symbol document MUST be uniquely
identified by `symbol` and MUST store the metadata required for list, search,
exchange filtering, and group filtering. The system MUST preserve the last
successful snapshot if a later refresh attempt fails.

#### Scenario: Upsert stock symbol documents by symbol
- **WHEN** a manual refresh succeeds
- **THEN** the system upserts stock symbol documents keyed by `symbol`
- **AND** each persisted document includes symbol identity and the normalized metadata needed by the stock catalog API

#### Scenario: Preserve the previous snapshot when refresh fails
- **WHEN** a manual refresh attempt fails before a new snapshot is fully persisted
- **THEN** the system MUST keep the previous successful stock catalog snapshot available for reads

### Requirement: Users can list and filter stock symbols from the persisted catalog
The system SHALL provide one stock catalog read endpoint that returns paginated
results from the persisted MongoDB catalog. The endpoint MUST support an
unfiltered list mode and MUST support filtering by stock symbol or company-name
query, exchange, and stock group.

#### Scenario: Return an unfiltered paginated stock symbol list
- **WHEN** the caller requests the stock catalog without supplying any filter parameters
- **THEN** the system returns a paginated list of persisted stock symbols

#### Scenario: Filter stock symbols by exchange
- **WHEN** the caller supplies an `exchange` filter
- **THEN** the system returns only stock symbols whose persisted exchange matches that value

#### Scenario: Filter stock symbols by group
- **WHEN** the caller supplies a `group` filter
- **THEN** the system returns only stock symbols whose persisted group membership includes that value

#### Scenario: Search stock symbols by query text
- **WHEN** the caller supplies a `q` search query
- **THEN** the system returns only stock symbols whose persisted symbol or company-name data matches that query

### Requirement: Unfiltered stock list responses use cache while filtered queries read MongoDB directly
The system SHALL allow Redis caching for unfiltered stock list responses only.
Requests that include any filtering or search parameter MUST query MongoDB
directly instead of serving filtered results from Redis cache. A successful
manual refresh MUST invalidate cached unfiltered stock list responses.

#### Scenario: Serve the default stock list from cache
- **WHEN** the caller requests the stock catalog without filters and a valid cached response exists
- **THEN** the system returns the cached unfiltered stock list response

#### Scenario: Bypass cache for filtered stock queries
- **WHEN** the caller requests the stock catalog with `q`, `exchange`, or `group`
- **THEN** the system queries MongoDB directly for that request

#### Scenario: Invalidate cached unfiltered lists after refresh
- **WHEN** a manual refresh successfully persists a new stock catalog snapshot
- **THEN** the system invalidates cached unfiltered stock list responses before subsequent default-list reads are served
