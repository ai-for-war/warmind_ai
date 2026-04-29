## MODIFIED Requirements

### Requirement: Stock price timeseries reads use vnstock Quote with source VCI only
The system SHALL fetch stock price timeseries using `vnstock` quote methods with an explicit supported source. The supported sources MUST be `VCI` and `KBS`. When the caller does not provide a source, the system MUST use `VCI` to preserve existing behavior. The backend MUST NOT rotate to or fallback to another source provider automatically for this capability.

#### Scenario: Fetch historical price data from the default source
- **WHEN** the backend serves a stock price history request without an explicit source
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `VCI`

#### Scenario: Fetch intraday data from the default source
- **WHEN** the backend serves a stock intraday request without an explicit source
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `VCI`

#### Scenario: Fetch historical price data from KBS
- **WHEN** the backend serves a stock price history request with source `KBS`
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `KBS`

#### Scenario: Fetch intraday data from KBS
- **WHEN** the backend serves a stock intraday request with source `KBS`
- **THEN** the system fetches upstream data using the `vnstock` quote integration configured with source `KBS`

#### Scenario: Do not automatically substitute providers
- **WHEN** the backend serves any stock price timeseries endpoint
- **THEN** the system MUST use the requested source or the default `VCI` source
- **AND** the system MUST NOT automatically substitute `KBS`, `VCI`, or another provider on behalf of the caller

### Requirement: Stock price timeseries responses preserve canonical VCI raw fields
The system SHALL normalize each stock price timeseries endpoint to a stable backend contract derived from the documented shared fields for the selected `vnstock` source and method scope in use. Historical price responses MUST preserve raw OHLCV timeseries fields, and intraday responses MUST preserve raw trade-timeseries fields. The backend MUST NOT add speculative cross-provider alias mappings or backend-derived analytics.

#### Scenario: Return canonical historical OHLCV fields
- **WHEN** the backend returns a stock price history response
- **THEN** each returned item includes `time`, `open`, `high`, `low`, `close`, and `volume`

#### Scenario: Return canonical intraday trade fields
- **WHEN** the backend returns a stock intraday response
- **THEN** each returned item includes `time`, `price`, `volume`, `match_type`, and `id`

#### Scenario: Return selected source metadata
- **WHEN** the backend returns a stock price timeseries response
- **THEN** the response source identifies the upstream source used to fetch the response

#### Scenario: Preserve provider-compatible intraday identifiers
- **WHEN** the backend returns a stock intraday response from a provider whose trade identifiers are numeric or string values
- **THEN** each returned item preserves the identifier as a stable integer or non-empty string value

#### Scenario: Exclude derived summary metrics from responses
- **WHEN** the backend returns a stock price timeseries response
- **THEN** the response contains raw normalized timeseries data only
- **AND** the system MUST NOT append backend-derived analytics or summary-statistics fields

### Requirement: Stock price history and intraday endpoints support endpoint-specific query contracts
The system SHALL support query parameters that match the confirmed product scope for each endpoint and selected source. The historical endpoint MUST support explicit time range and lookback-style reads for supported sources. The intraday endpoint MUST support bounded reads for supported sources, and MUST support time cursors only for sources that document cursor parameters.

#### Scenario: Read historical data with explicit time range
- **WHEN** the caller requests the stock price history endpoint with a valid `start` value and an optional `end` value
- **THEN** the system returns historical price data for that symbol constrained by the supplied time window and interval

#### Scenario: Read historical data with lookback length
- **WHEN** the caller requests the stock price history endpoint with a valid `length` value
- **THEN** the system returns historical price data for that symbol using that lookback length and the requested interval

#### Scenario: Read intraday data with page size only
- **WHEN** the caller requests the stock intraday endpoint with a valid `page_size` value and no time cursor
- **THEN** the system returns an intraday trade-timeseries slice limited by that page size

#### Scenario: Read VCI intraday data with a time cursor
- **WHEN** the caller requests the stock intraday endpoint with source `VCI` and a valid `last_time` value
- **THEN** the system returns intraday trade-timeseries data using that time cursor in the upstream read

#### Scenario: Reject KBS intraday cursor parameters
- **WHEN** the caller requests the stock intraday endpoint with source `KBS` and supplies `last_time` or `last_time_format`
- **THEN** the system MUST reject the request as invalid
- **AND** the system MUST NOT silently omit the unsupported cursor parameters from the upstream read

### Requirement: Stock price timeseries reads use per-symbol and per-query caching with stale fallback
The system SHALL allow live upstream reads for stock price timeseries in the request path, backed by Redis caching per stock symbol, endpoint section, selected source, and normalized query variant. If an upstream request fails, the system MUST serve the latest cached response for that same symbol, endpoint section, selected source, and query variant when a valid cached response exists.

#### Scenario: Serve stock price timeseries from cache when available
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol, source, and query variant and a valid cached response already exists for that same symbol, endpoint section, source, and query variant
- **THEN** the system returns the cached response

#### Scenario: Cache a successful upstream price timeseries response
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol, source, and query variant and no valid cached response exists
- **THEN** the system fetches the requested timeseries payload from upstream
- **AND** the system stores the successful normalized response in cache for that same symbol, endpoint section, source, and query variant

#### Scenario: Serve stale cache when upstream quote read fails
- **WHEN** the caller requests one stock price timeseries endpoint for a symbol, source, and query variant, the upstream quote read fails, and a previous cached response exists for that same symbol, endpoint section, source, and query variant
- **THEN** the system returns the cached response instead of failing the request
