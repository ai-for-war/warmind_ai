## MODIFIED Requirements

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
- **THEN** the response includes `buy_and_hold`, `sma_crossover`, and
  `ichimoku_cloud`
- **AND** the `ichimoku_cloud` entry includes parameter metadata for
  `tenkan_window`, `kijun_window`, `senkou_b_window`, `displacement`, and
  `warmup_bars`
- **AND** the response does not advertise unsupported templates outside the
  current v1 capability

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

#### Scenario: Public run request accepts valid Ichimoku parameters
- **WHEN** an authenticated caller submits a public backtest run request with
  template `ichimoku_cloud` and valid Ichimoku template parameters
- **THEN** the public request validates successfully
- **AND** the request maps those parameters to the internal backtest contract

#### Scenario: Response exposes the applied assumptions
- **WHEN** the system returns a successful public backtest response
- **THEN** the response includes the structured backtest result
- **AND** the response includes the backend-applied execution assumptions so FE
  can present them alongside the result
