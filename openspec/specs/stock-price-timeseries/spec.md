# stock-price-timeseries Specification

## Purpose
TBD - created by archiving change add-stock-price-timeseries-endpoints. Update Purpose after archive.
## Requirements
### Requirement: Stock price timeseries APIs follow the existing authenticated organization request model
The system SHALL provide authenticated stock price timeseries APIs that require
an active user and a valid `X-Organization-ID` request context, consistent with
the existing organization-scoped API contract. Price timeseries reads MUST
remain scoped by API access control only and MUST NOT create per-organization
copies of the upstream market data.

#### Scenario: Read stock price timeseries with valid organization context
- **WHEN** an authenticated active user calls a stock price timeseries API with a valid `X-Organization-ID`
- **THEN** the system returns price timeseries data for the requested stock symbol

#### Scenario: Reject stock price timeseries reads without valid organization context
- **WHEN** a request to a stock price timeseries API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: The backend exposes dedicated stock price history and intraday endpoints for one stock symbol
The system SHALL expose dedicated read endpoints under the stock API surface
for stock price timeseries by stock symbol. The API surface MUST include a
historical OHLCV endpoint and an intraday trade-timeseries endpoint.

#### Scenario: Read historical OHLCV data for one stock symbol
- **WHEN** the caller requests the stock price history endpoint for one valid stock symbol
- **THEN** the system returns only the historical OHLCV payload for that request

#### Scenario: Read intraday trade timeseries for one stock symbol
- **WHEN** the caller requests the stock intraday endpoint for one valid stock symbol
- **THEN** the system returns only the intraday trade-timeseries payload for that request

### Requirement: Stock price timeseries reads use vnstock Quote with source VCI only
The system SHALL fetch stock price timeseries using `vnstock` quote methods
with source `VCI` only. The backend MUST NOT rotate to another source provider
for this capability in v1.

#### Scenario: Fetch historical price data from VCI
- **WHEN** the backend serves a stock price history request
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `VCI`

#### Scenario: Fetch intraday data from VCI
- **WHEN** the backend serves a stock intraday request
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `VCI`

#### Scenario: Keep stock price source fixed to VCI
- **WHEN** the backend serves any stock price timeseries endpoint in v1
- **THEN** the system MUST use source `VCI`
- **AND** the system MUST NOT substitute `KBS` or another provider automatically

### Requirement: Stock price timeseries responses preserve canonical VCI raw fields
The system SHALL normalize each stock price timeseries endpoint to a stable
backend contract derived from the exact VCI method scope in use. Historical
price responses MUST preserve raw OHLCV timeseries fields, and intraday
responses MUST preserve raw trade-timeseries fields. The backend MUST NOT add
speculative cross-provider alias mappings or backend-derived analytics in v1.

#### Scenario: Return canonical historical OHLCV fields
- **WHEN** the backend returns a stock price history response
- **THEN** each returned item includes the canonical VCI historical fields needed by the product for that endpoint

#### Scenario: Return canonical intraday trade fields
- **WHEN** the backend returns a stock intraday response
- **THEN** each returned item includes the canonical VCI intraday trade fields needed by the product for that endpoint

#### Scenario: Exclude derived summary metrics from v1 responses
- **WHEN** the backend returns a stock price timeseries response in v1
- **THEN** the response contains raw normalized timeseries data only
- **AND** the system MUST NOT append backend-derived analytics or summary-statistics fields

### Requirement: Requested stock symbols must be validated against the shared stock catalog before upstream quote reads
The system SHALL validate the requested stock symbol before fetching upstream
price data. The backend MUST normalize the symbol into canonical uppercase form
and MUST reject symbols that are not present in the backend stock catalog
instead of sending unnecessary upstream quote requests.

#### Scenario: Normalize a valid symbol before fetching price timeseries
- **WHEN** the caller requests stock price timeseries for a valid stock symbol using mixed-case input
- **THEN** the system normalizes that symbol into canonical uppercase form before the upstream read

#### Scenario: Reject an unknown stock symbol for price timeseries
- **WHEN** the caller requests stock price timeseries for a symbol that is not present in the backend stock catalog
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT send an upstream quote request for that symbol

### Requirement: Stock price history and intraday endpoints support endpoint-specific query contracts
The system SHALL support query parameters that match the confirmed v1 product
scope for each endpoint. The historical endpoint MUST support explicit time
range and lookback-style reads, and the intraday endpoint MUST support bounded
reads with an optional time cursor.

#### Scenario: Read historical data with explicit time range
- **WHEN** the caller requests the stock price history endpoint with a valid `start` value and an optional `end` value
- **THEN** the system returns historical price data for that symbol constrained by the supplied time window and interval

#### Scenario: Read historical data with lookback length
- **WHEN** the caller requests the stock price history endpoint with a valid `length` value
- **THEN** the system returns historical price data for that symbol using that lookback length and the requested interval

#### Scenario: Read intraday data with page size only
- **WHEN** the caller requests the stock intraday endpoint with a valid `page_size` value and no time cursor
- **THEN** the system returns an intraday trade-timeseries slice limited by that page size

#### Scenario: Read intraday data with a time cursor
- **WHEN** the caller requests the stock intraday endpoint with a valid `last_time` value
- **THEN** the system returns intraday trade-timeseries data using that time cursor in the upstream read

### Requirement: Stock price timeseries reads use per-symbol and per-query caching with stale fallback
The system SHALL allow live upstream reads for stock price timeseries in the
request path, backed by Redis caching per stock symbol, endpoint section, and
normalized query variant. If an upstream request fails, the system MUST serve
the latest cached response for that same symbol, endpoint section, and query
variant when a valid cached response exists.

#### Scenario: Serve stock price timeseries from cache when available
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol and query variant and a valid cached response already exists for that same symbol, endpoint section, and query variant
- **THEN** the system returns the cached response

#### Scenario: Cache a successful upstream price timeseries response
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol and query variant and no valid cached response exists
- **THEN** the system fetches the requested timeseries payload from upstream
- **AND** the system stores the successful normalized response in cache for that same symbol, endpoint section, and query variant

#### Scenario: Serve stale cache when upstream quote read fails
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol and query variant, the upstream quote read fails, and a previous cached response exists for that same symbol, endpoint section, and query variant
- **THEN** the system returns the cached response instead of failing the request

### Requirement: Endpoint-level failures are isolated to the requested stock price section and query variant
The system SHALL isolate stock price timeseries failures at the endpoint and
query-variant level. An upstream or normalization failure for one endpoint or
query variant MUST NOT block later requests for other stock price endpoints or
other query variants of the same stock symbol.

#### Scenario: One failing endpoint does not block another endpoint
- **WHEN** an upstream failure occurs while serving one requested stock price timeseries endpoint for a stock symbol
- **THEN** the failure applies only to that requested endpoint
- **AND** the system continues to allow later requests for other stock price timeseries endpoints of the same stock symbol

#### Scenario: One failing query variant does not block another query variant
- **WHEN** an upstream failure occurs while serving one query variant of a stock price timeseries endpoint for a stock symbol
- **THEN** the failure applies only to that requested query variant
- **AND** the system continues to allow later requests for other query variants of that same endpoint and stock symbol

