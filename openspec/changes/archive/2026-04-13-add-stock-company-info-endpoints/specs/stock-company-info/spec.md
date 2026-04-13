## ADDED Requirements

### Requirement: Stock company information APIs follow the existing authenticated organization request model
The system SHALL provide authenticated stock company information APIs that
require an active user and a valid `X-Organization-ID` request context,
consistent with the existing organization-scoped API contract. Company
information reads MUST remain scoped by API access control only and MUST NOT
create per-organization copies of the upstream market data.

#### Scenario: Read company information with valid organization context
- **WHEN** an authenticated active user calls a stock company information API with a valid `X-Organization-ID`
- **THEN** the system returns company information for the requested stock symbol

#### Scenario: Reject company information reads without valid organization context
- **WHEN** a request to a stock company information API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: The backend exposes tab-wise company information endpoints for one stock symbol
The system SHALL expose dedicated read endpoints under the stock API surface
for tab-wise company information by stock symbol. The API surface MUST include
separate endpoints for overview, shareholders, officers, subsidiaries,
affiliates, events, news, reports, ratio summary, and trading stats.

#### Scenario: Read overview tab data
- **WHEN** the caller requests the company overview endpoint for one valid stock symbol
- **THEN** the system returns only the overview payload for that tab

#### Scenario: Read list-based company tabs independently
- **WHEN** the caller requests any of the shareholders, officers, subsidiaries, affiliates, events, news, or reports endpoints for one valid stock symbol
- **THEN** the system returns only the payload for that requested tab
- **AND** the system MUST NOT require the client to fetch unrelated company tabs in the same response

#### Scenario: Read snapshot-based company tabs independently
- **WHEN** the caller requests either the ratio summary endpoint or the trading stats endpoint for one valid stock symbol
- **THEN** the system returns only the payload for that requested tab

### Requirement: Company information reads use vnstock Company with source VCI only
The system SHALL fetch company information using `vnstock` company-information
methods with source `VCI` only. The backend MUST NOT rotate to another source
provider for this capability in v1.

#### Scenario: Fetch company overview from VCI
- **WHEN** the backend serves a company overview request
- **THEN** the system fetches upstream data using the `vnstock` company-information integration configured with source `VCI`

#### Scenario: Keep company information source fixed to VCI
- **WHEN** the backend serves any stock company information endpoint in v1
- **THEN** the system MUST use source `VCI`
- **AND** the system MUST NOT substitute `KBS` or another provider automatically

### Requirement: Company information responses preserve canonical VCI section fields
The system SHALL normalize each company-information endpoint to a stable
backend contract derived from the exact VCI method scope in use. The backend
MUST preserve the documented VCI section fields for each endpoint and MUST NOT
introduce speculative cross-provider alias mappings.

#### Scenario: Return canonical overview fields
- **WHEN** the backend returns the company overview response
- **THEN** the response includes the canonical VCI overview fields needed by the product for that tab

#### Scenario: Return canonical shareholders fields
- **WHEN** the backend returns the shareholders response
- **THEN** each returned item includes the canonical VCI shareholder fields for that section

#### Scenario: Avoid speculative field aliases
- **WHEN** the backend maps upstream VCI company-information payloads into API responses
- **THEN** the system MUST use canonical field names derived from the exact VCI method scope
- **AND** the system MUST NOT add broad fallback aliases that are not required by the current runtime path

### Requirement: Requested stock symbols must be validated before upstream company reads
The system SHALL validate the requested stock symbol before fetching upstream
company information. The backend MUST normalize the symbol into canonical
uppercase form and MUST reject unknown or unsupported symbols instead of
sending unnecessary upstream requests.

#### Scenario: Normalize a valid symbol before fetching company information
- **WHEN** the caller requests company information for a valid stock symbol using mixed-case input
- **THEN** the system normalizes that symbol into canonical uppercase form before the upstream read

#### Scenario: Reject an unknown stock symbol
- **WHEN** the caller requests company information for a symbol that is not present in the backend stock catalog
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT send an upstream company-information request for that symbol

### Requirement: Company information reads use per-symbol caching with stale fallback
The system SHALL allow live upstream reads for company information in the
request path, backed by Redis caching per stock symbol and endpoint section. If
an upstream request fails, the system MUST serve the latest cached response for
that same symbol and section when a valid cached response exists.

#### Scenario: Serve company information from cache when available
- **WHEN** the caller requests one company-information endpoint for a symbol and a valid cached response already exists for that symbol and section
- **THEN** the system returns the cached response

#### Scenario: Cache a successful upstream company response
- **WHEN** the caller requests one company-information endpoint for a symbol and no valid cached response exists
- **THEN** the system fetches the requested section from upstream
- **AND** the system stores the successful normalized response in cache for that symbol and section

#### Scenario: Serve stale cache when upstream fails
- **WHEN** the caller requests one company-information endpoint for a symbol, the upstream read fails, and a previous cached response exists for that symbol and section
- **THEN** the system returns the cached response instead of failing the request

### Requirement: Endpoint-level failures are isolated to the requested company tab
The system SHALL isolate company-information failures at the endpoint level.
An upstream or normalization failure for one company-information section MUST
NOT block unrelated company-information sections from being served on later
requests for the same stock symbol.

#### Scenario: One failing tab does not block another tab
- **WHEN** an upstream failure occurs while serving one requested company-information endpoint for a stock symbol
- **THEN** the failure applies only to that requested endpoint
- **AND** the system continues to allow later requests for other company-information endpoints of the same stock symbol
