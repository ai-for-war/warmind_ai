## ADDED Requirements

### Requirement: The system exposes a dedicated frontend-facing backtest API domain
The system SHALL expose FE-facing backtest endpoints under a dedicated
`/api/v1/backtests/*` API surface. The system MUST NOT require FE to call
stock-domain routes such as `/api/v1/stocks/*` to discover backtest templates
or execute a backtest run.

#### Scenario: Backtest API uses a standalone domain
- **WHEN** FE needs to interact with backtest capabilities
- **THEN** the backend exposes those capabilities through `/api/v1/backtests/*`
- **AND** FE does not need to call stock-domain routes to execute one backtest

### Requirement: The system lists supported backtest templates for FE form discovery
The system SHALL provide an authenticated endpoint that returns the currently
supported backtest templates and their backend-owned parameter metadata. The
response MUST allow FE to render v1 forms without hardcoding the template
contract.

#### Scenario: FE requests supported templates
- **WHEN** an authenticated caller requests the backtest template catalog
- **THEN** the system returns the supported template IDs for v1
- **AND** each template entry includes human-readable metadata and parameter
  definitions needed for FE input rendering

#### Scenario: Template catalog reflects the current v1 template scope
- **WHEN** the backend responds to the template catalog request
- **THEN** the response includes `buy_and_hold` and `sma_crossover`
- **AND** the response does not advertise unsupported templates outside the
  current v1 capability

### Requirement: The system executes one synchronous backtest run through the public API
The system SHALL provide an authenticated synchronous run endpoint under the
backtest API domain. The request MUST include the stock symbol in the request
body together with the selected template, date range, template parameters, and
optional initial capital. A successful response MUST return the completed
backtest result in the same response.

#### Scenario: FE runs one valid backtest
- **WHEN** an authenticated caller submits a valid backtest run request through
  the public backtest API
- **THEN** the system executes one backtest run through the internal backtest
  service
- **AND** the response includes the completed structured result for that run

#### Scenario: Symbol is supplied in the request body
- **WHEN** an authenticated caller submits a backtest run request
- **THEN** the system reads the stock symbol from the request body
- **AND** the public route does not require the symbol as a stock-domain path
  parameter

### Requirement: The public run request stays narrower than the internal engine contract
The system SHALL limit FE-controlled run input in v1 to the fields the product
explicitly allows users to change: `symbol`, `date_from`, `date_to`,
`template_id`, `template_params`, and optional `initial_capital`. The public
API MUST NOT expose additional engine controls such as timeframe, execution
model, exposure direction, or position sizing as FE-configurable request
fields in v1.

#### Scenario: Fixed execution assumptions are not FE-configurable
- **WHEN** an authenticated caller submits a public backtest run request
- **THEN** the request contract accepts the allowed v1 fields only
- **AND** the caller cannot override fixed engine assumptions such as daily
  timeframe, long-only execution, all-in sizing, or next-open fills

#### Scenario: Response exposes the applied assumptions
- **WHEN** the system returns a successful public backtest response
- **THEN** the response includes the structured backtest result
- **AND** the response includes the backend-applied execution assumptions so FE
  can present them alongside the result

### Requirement: Public backtest endpoints reuse the existing organization-scoped access model
The system SHALL require the existing active-user and organization-context
dependencies for FE-facing backtest endpoints, matching the current stock API
access model.

#### Scenario: Backtest endpoints reject missing organization context
- **WHEN** a caller requests one public backtest endpoint without the required
  organization context
- **THEN** the system rejects the request according to the existing
  organization-auth behavior

#### Scenario: Authorized caller can access both template discovery and run execution
- **WHEN** a caller is authenticated and has access to the active organization
- **THEN** the caller can request the template catalog
- **AND** the caller can submit one backtest run request through the public
  backtest API

### Requirement: Endpoint failures remain isolated within the backtest API domain
The system SHALL isolate failures at the requested backtest endpoint. A failure
in template discovery MUST NOT block run execution later, and a failure during
one run request MUST NOT prevent later requests to the template catalog or to
other backtest runs.

#### Scenario: One failing endpoint does not block another
- **WHEN** one public backtest endpoint returns an error for a given request
- **THEN** later requests to another backtest endpoint remain executable
- **AND** the failure does not corrupt the overall backtest API domain state
