# stock-financial-reports Specification

## Purpose
TBD - created by archiving change add-kbs-financial-report-endpoints. Update Purpose after archive.
## Requirements
### Requirement: Stock financial report APIs follow the existing authenticated organization request model
The system SHALL provide authenticated stock financial report APIs that require
an active user and a valid `X-Organization-ID` request context, consistent with
the existing organization-scoped stock API contract. Financial report reads
MUST remain scoped by API access control only and MUST NOT create
per-organization copies of upstream market data.

#### Scenario: Read financial report with valid organization context
- **WHEN** an authenticated active user calls a stock financial report API with a valid `X-Organization-ID`
- **THEN** the system returns financial report data for the requested stock symbol, report type, and period when data exists

#### Scenario: Reject financial report reads without valid organization context
- **WHEN** a request to a stock financial report API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: The backend exposes per-report financial report reads for one stock symbol
The system SHALL expose a dedicated stock financial report read API under the
stock API surface for one stock symbol, one report type, and one period per
request. The API MUST support income statement, balance sheet, cash flow, and
financial ratio reports. The API MUST NOT require or perform an aggregate read
of all financial report types in one request.

#### Scenario: Read income statement report
- **WHEN** the caller requests the financial report endpoint for a valid stock symbol with report type `income-statement`
- **THEN** the system returns only the income statement payload for that stock symbol and requested period

#### Scenario: Read balance sheet report
- **WHEN** the caller requests the financial report endpoint for a valid stock symbol with report type `balance-sheet`
- **THEN** the system returns only the balance sheet payload for that stock symbol and requested period

#### Scenario: Read cash flow report
- **WHEN** the caller requests the financial report endpoint for a valid stock symbol with report type `cash-flow`
- **THEN** the system returns only the cash flow payload for that stock symbol and requested period

#### Scenario: Read financial ratio report
- **WHEN** the caller requests the financial report endpoint for a valid stock symbol with report type `ratio`
- **THEN** the system returns only the financial ratio payload for that stock symbol and requested period

#### Scenario: Reject unsupported report type
- **WHEN** the caller requests the financial report endpoint with an unsupported report type
- **THEN** the system MUST reject the request as invalid or not found before making an upstream financial report read

#### Scenario: Do not aggregate all report types
- **WHEN** the caller requests one supported financial report type
- **THEN** the system MUST fetch and return only that requested report type
- **AND** the system MUST NOT fetch income statement, balance sheet, cash flow, and ratio data together for that request

### Requirement: Financial report reads support annual and quarterly periods
The system SHALL support financial report reads for `quarter` and `year`
periods. When the caller does not provide a period, the system MUST use
`quarter`.

#### Scenario: Read quarterly financial report by default
- **WHEN** the caller requests a supported financial report without a period query parameter
- **THEN** the system fetches and returns the requested report using period `quarter`

#### Scenario: Read explicit quarterly financial report
- **WHEN** the caller requests a supported financial report with period `quarter`
- **THEN** the system fetches and returns quarterly financial report data

#### Scenario: Read explicit annual financial report
- **WHEN** the caller requests a supported financial report with period `year`
- **THEN** the system fetches and returns annual financial report data

#### Scenario: Reject unsupported financial report period
- **WHEN** the caller requests a supported financial report with a period other than `quarter` or `year`
- **THEN** the system MUST reject the request as invalid before making an upstream financial report read

### Requirement: Financial report reads use vnstock Finance with source KBS only
The system SHALL fetch financial report data using the `vnstock` finance
integration configured with source `KBS` only. The backend MUST NOT expose a
source selector for this capability and MUST NOT rotate to or fallback to
another source provider automatically.

#### Scenario: Fetch financial report data from KBS
- **WHEN** the backend serves any supported stock financial report request
- **THEN** the system fetches upstream data using the `vnstock` finance integration configured with source `KBS`

#### Scenario: Do not automatically substitute financial report providers
- **WHEN** the backend serves any supported stock financial report request
- **THEN** the system MUST use source `KBS`
- **AND** the system MUST NOT substitute `VCI` or another provider automatically

### Requirement: Financial report responses preserve stable row and period-value structure
The system SHALL normalize KBS financial report payloads into a stable response
contract that includes response metadata, the ordered period labels, and row
items. Each row item MUST include `item`, `item_id`, and `values`, where
`values` maps each returned period label to that row's value for the period.
The backend MUST preserve KBS period labels as returned by the runtime and MUST
NOT collapse or rename duplicate or suffixed period labels.

#### Scenario: Return stable financial report envelope
- **WHEN** the backend returns a supported financial report response
- **THEN** the response includes `symbol`, `source`, `report_type`, `period`, `periods`, `cache_hit`, and `items`

#### Scenario: Return row values keyed by provider period labels
- **WHEN** the backend returns financial report rows with one or more period labels
- **THEN** each returned item includes a `values` object keyed by the returned period labels
- **AND** the response `periods` list preserves the period labels used in the row `values`

#### Scenario: Preserve null financial cells
- **WHEN** KBS returns missing or NaN values for financial report cells
- **THEN** the system returns those missing cells as null values in the row `values`

#### Scenario: Preserve upstream row ordering
- **WHEN** KBS returns financial report rows in an ordered DataFrame-like payload
- **THEN** the system preserves that row order in the response `items`

### Requirement: Financial report v1 excludes hierarchy metadata
The system SHALL keep the v1 financial report response focused on financial
line items and period values. The response items MUST NOT include hierarchy
metadata fields such as `item_en`, `unit`, `levels`, or `row_number` in v1.

#### Scenario: Return v1 rows without hierarchy metadata
- **WHEN** the backend returns a supported financial report response
- **THEN** each response item includes `item`, `item_id`, and `values`
- **AND** each response item MUST NOT include `item_en`, `unit`, `levels`, or `row_number`

### Requirement: Requested stock symbols must be validated before upstream financial report reads
The system SHALL validate the requested stock symbol before fetching upstream
financial report data. The backend MUST normalize the symbol into canonical
uppercase form and MUST reject unknown or unsupported symbols instead of
sending unnecessary upstream KBS requests.

#### Scenario: Normalize a valid symbol before fetching financial report data
- **WHEN** the caller requests a financial report for a valid stock symbol using mixed-case input
- **THEN** the system normalizes that symbol into canonical uppercase form before the upstream read

#### Scenario: Reject an unknown stock symbol
- **WHEN** the caller requests a financial report for a symbol that is not present in the backend stock catalog
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT send an upstream financial report request for that symbol

### Requirement: Financial report reads return not found when KBS has no report data
The system SHALL return not found when the requested stock symbol is valid but
KBS returns no financial report rows for the requested report type and period.

#### Scenario: Valid symbol has no requested KBS report data
- **WHEN** the caller requests a supported financial report for a stock symbol that exists in the backend stock catalog
- **AND** KBS returns no rows for the requested report type and period
- **THEN** the system MUST return `404`

### Requirement: Financial report reads use per-symbol, per-report, per-period caching with stale fallback
The system SHALL allow live upstream reads for financial report data in the
request path, backed by Redis caching per stock symbol, report type, and
period. If an upstream request fails, the system MUST serve the latest cached
response for that same symbol, report type, and period when a valid cached
response exists.

#### Scenario: Serve financial report from cache when available
- **WHEN** the caller requests one financial report for a symbol, report type, and period, and a valid cached response already exists for that same request variant
- **THEN** the system returns the cached response

#### Scenario: Cache a successful upstream financial report response
- **WHEN** the caller requests one financial report for a symbol, report type, and period, and no valid cached response exists
- **THEN** the system fetches the requested financial report payload from upstream
- **AND** the system stores the successful normalized response in cache for that same symbol, report type, and period

#### Scenario: Serve stale cache when upstream financial report read fails
- **WHEN** the caller requests one financial report for a symbol, report type, and period, the upstream financial report read fails, and a previous cached response exists for that same request variant
- **THEN** the system returns the cached response instead of failing the request

#### Scenario: Cache variants are isolated by report type and period
- **WHEN** the caller requests financial reports for the same symbol with different report types or periods
- **THEN** the system MUST cache and retrieve those responses independently

### Requirement: Financial report endpoint failures are isolated to the requested report variant
The system SHALL isolate stock financial report failures at the requested
symbol, report type, and period level. An upstream or normalization failure for
one financial report variant MUST NOT block unrelated financial report variants
from being served on later requests.

#### Scenario: One failing report variant does not block another variant
- **WHEN** an upstream failure occurs while serving one requested financial report variant for a stock symbol
- **THEN** the failure applies only to that requested symbol, report type, and period
- **AND** the system continues to allow later requests for other financial report types or periods of the same stock symbol

