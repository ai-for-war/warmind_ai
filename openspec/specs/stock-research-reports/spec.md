# stock-research-reports Specification

## Purpose
TBD - created by archiving change add-stock-research-reports. Update Purpose after archive.
## Requirements
### Requirement: Stock research report APIs follow the existing authenticated organization request model
The system SHALL provide stock research report APIs that require an active user
and a valid `X-Organization-ID` request context, consistent with the existing
organization-scoped API contract. Stock research reports MUST remain scoped by
the combination of `user + organization`.

#### Scenario: Access stock research reports within a valid organization context
- **WHEN** an authenticated active user calls a stock research report API with a valid `X-Organization-ID`
- **THEN** the system processes the request within that user's scope for the specified organization

#### Scenario: Reject stock research report requests without valid organization access
- **WHEN** a request to a stock research report API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: Users can create asynchronous stock research reports for one catalog-validated symbol
The system SHALL provide a dedicated create endpoint for stock research reports.
Creating a report MUST accept one Vietnam stock symbol, MUST validate that
symbol against the persisted stock catalog, MUST create a persisted report job,
and MUST return `202 Accepted` without waiting for report completion.

#### Scenario: Create a stock research report for a valid symbol
- **WHEN** a user requests a stock research report for one symbol that exists in the persisted stock catalog
- **THEN** the system creates a persisted report record for that symbol
- **AND** the system returns `202 Accepted`

#### Scenario: Reject a stock research report for an unknown symbol
- **WHEN** a user requests a stock research report for a symbol that does not exist in the persisted stock catalog
- **THEN** the system MUST reject the request
- **AND** the system MUST NOT create a report record for that symbol

### Requirement: Stock research reports run asynchronously with persisted lifecycle state
The system SHALL process stock research reports asynchronously after accepting
the create request. Each report MUST persist lifecycle state so callers can
observe whether the report is queued, running, completed, partial, or failed.

#### Scenario: Accepted report enters background processing
- **WHEN** the system accepts a valid stock research report request
- **THEN** the report is persisted with an initial queued state
- **AND** the system starts background processing after the HTTP response returns

#### Scenario: Completed report persists terminal success state
- **WHEN** background processing finishes successfully for a stock research report
- **THEN** the system persists a terminal success state for that report

#### Scenario: Failed report persists terminal failure state
- **WHEN** background processing cannot produce a final stock research report
- **THEN** the system persists a terminal failure state for that report

### Requirement: The system stores stock research output as markdown content plus web sources
The system SHALL persist the final stock research artifact as markdown report
content plus a `sources[]` collection of web-source metadata. Each source item
MUST include `source_id`, `url`, and `title`. The markdown content MUST be
allowed to cite those sources using `[Sx]` reference tokens.

#### Scenario: Persist a completed report artifact
- **WHEN** background processing completes a stock research report
- **THEN** the system stores markdown report content for that report
- **AND** the system stores the associated `sources[]` entries for that report

#### Scenario: Source references map to stored source entries
- **WHEN** the stored markdown content cites one or more source reference tokens such as `[S1]`
- **THEN** each cited source reference token MUST map to one stored source entry in that report's `sources[]`

### Requirement: Stock research citations are web-only and do not require current-price citations
The system SHALL treat stored report citations as web-only sources in v1.
Internal stock-service data MUST NOT be stored as citation sources in a stock
research report. The system MAY allow current-price statements to appear in the
markdown report without citations.

#### Scenario: Store only web sources in report metadata
- **WHEN** the system persists a stock research report's `sources[]`
- **THEN** each stored source entry represents one web source with a real URL

#### Scenario: Current-price text may appear without a citation token
- **WHEN** the generated stock research report includes a current-price statement
- **THEN** the system allows that statement to be stored even when it does not include a source reference token

### Requirement: Users can read and list their persisted stock research reports
The system SHALL provide dedicated read endpoints for one report and for report
history within the current user and organization scope. Read responses MUST
return the persisted report status and, when available, the stored markdown
content and `sources[]`.

#### Scenario: Read one persisted stock research report
- **WHEN** a user requests one stock research report they own in the current organization
- **THEN** the system returns that report's persisted lifecycle state
- **AND** the response includes stored markdown content and `sources[]` when available

#### Scenario: List stock research report history
- **WHEN** a user requests the stock research report list endpoint in one valid organization context
- **THEN** the system returns that user's persisted stock research reports for that organization

#### Scenario: Reject access to another user's stock research report
- **WHEN** a user requests a stock research report owned by another user in the same organization
- **THEN** the system MUST reject the request

