## ADDED Requirements

### Requirement: Dedicated fundamental analyst subagent
The system SHALL provide a dedicated `fundamental_analyst` subagent for Vietnam-listed equity fundamental analysis. The fundamental analyst MUST return a structured synthesis-ready fundamental evidence package and MUST NOT produce the parent stock agent's final all-factor investment recommendation.

#### Scenario: Fundamental analyst returns evidence package
- **WHEN** the stock agent delegates a fundamental-analysis task for one Vietnam-listed stock
- **THEN** the task executes through the dedicated fundamental analyst runtime
- **AND** the result contains a structured fundamental evidence package
- **AND** the result keeps final all-factor recommendation responsibility with the parent stock agent

#### Scenario: Fundamental analyst does not produce final recommendation
- **WHEN** the fundamental analyst analyzes financial statements, ratios, or business quality
- **THEN** it MUST NOT return a final buy, sell, hold, reduce, accumulate, or all-factor recommendation label
- **AND** it MUST frame its result as evidence for parent synthesis

### Requirement: Fundamental analyst exposes five phase-one tools
The fundamental analyst runtime SHALL expose exactly five phase-one tools for company profile and financial evidence loading: `load_company_profile`, `load_income_statement`, `load_balance_sheet`, `load_cash_flow`, and `load_financial_ratios`.

#### Scenario: Fundamental tool surface is bounded
- **WHEN** the fundamental analyst runtime is created
- **THEN** the tool surface includes `load_company_profile`
- **AND** the tool surface includes `load_income_statement`
- **AND** the tool surface includes `load_balance_sheet`
- **AND** the tool surface includes `load_cash_flow`
- **AND** the tool surface includes `load_financial_ratios`

#### Scenario: Fundamental analyst cannot use unrelated specialist tools
- **WHEN** the fundamental analyst runtime is created
- **THEN** it MUST NOT expose stock-agent coordination tools such as `delegate_tasks` or `load_skill`
- **AND** it MUST NOT expose technical analyst tools such as `compute_technical_indicators`, `load_price_history`, or `run_backtest`
- **AND** it MUST NOT expose event analyst web research tools for phase-one fundamental analysis

### Requirement: Company profile tool uses existing VCI overview service path
The `load_company_profile` tool SHALL load company profile evidence through the existing `StockCompanyService.get_overview()` path, backed by VCI `Company.overview()`. The tool MUST NOT implement a direct `vnstock` company integration path of its own.

#### Scenario: Load company profile evidence
- **WHEN** the fundamental analyst calls `load_company_profile` with a valid stock symbol
- **THEN** the system loads profile evidence through `StockCompanyService.get_overview()`
- **AND** the returned evidence identifies source `VCI`
- **AND** the returned evidence includes available overview fields such as company profile, industry names, charter capital, issue shares, and source metadata

#### Scenario: Company profile rejects invalid symbol through service validation
- **WHEN** the fundamental analyst calls `load_company_profile` with an unknown or unsupported stock symbol
- **THEN** the tool returns a bounded failure or data gap derived from the existing service validation result
- **AND** the analyst can continue with available evidence without fabricating company profile details

### Requirement: Financial statement tools use existing KBS financial report service path
The financial statement tools SHALL load reported financial evidence through the existing `StockFinancialReportService.get_report()` path, backed by KBS `Finance` methods. `load_income_statement` MUST use report type `income-statement`, `load_balance_sheet` MUST use report type `balance-sheet`, `load_cash_flow` MUST use report type `cash-flow`, and `load_financial_ratios` MUST use report type `ratio`.

#### Scenario: Load income statement evidence from KBS
- **WHEN** the fundamental analyst calls `load_income_statement` with a valid stock symbol
- **THEN** the system loads evidence through `StockFinancialReportService.get_report()` using report type `income-statement`
- **AND** the returned evidence identifies source `KBS`

#### Scenario: Load balance sheet evidence from KBS
- **WHEN** the fundamental analyst calls `load_balance_sheet` with a valid stock symbol
- **THEN** the system loads evidence through `StockFinancialReportService.get_report()` using report type `balance-sheet`
- **AND** the returned evidence identifies source `KBS`

#### Scenario: Load cash flow evidence from KBS
- **WHEN** the fundamental analyst calls `load_cash_flow` with a valid stock symbol
- **THEN** the system loads evidence through `StockFinancialReportService.get_report()` using report type `cash-flow`
- **AND** the returned evidence identifies source `KBS`

#### Scenario: Load financial ratio evidence from KBS Finance ratio
- **WHEN** the fundamental analyst calls `load_financial_ratios` with a valid stock symbol
- **THEN** the system loads evidence through `StockFinancialReportService.get_report()` using report type `ratio`
- **AND** the returned evidence identifies source `KBS`
- **AND** the tool MUST NOT substitute VCI `Company.ratio_summary()` for KBS `Finance.ratio()`

### Requirement: Financial tools support quarterly default and annual override
Each financial report tool SHALL default to `period="quarter"` when the analyst does not specify a period and SHALL allow `period="year"` when annual evidence is requested. Unsupported periods MUST be rejected before upstream financial report reads.

#### Scenario: Default to quarterly financial evidence
- **WHEN** the fundamental analyst calls a financial report tool without a period argument
- **THEN** the tool loads the requested report using `period="quarter"`

#### Scenario: Load annual financial evidence
- **WHEN** the fundamental analyst calls a financial report tool with `period="year"`
- **THEN** the tool loads the requested report using `period="year"`

#### Scenario: Reject unsupported financial period
- **WHEN** the fundamental analyst calls a financial report tool with a period other than `quarter` or `year`
- **THEN** the tool returns a bounded validation failure
- **AND** the system MUST NOT make an upstream financial report read for that unsupported period

### Requirement: Fundamental tools return compact selected evidence and data gaps
Fundamental analyst tools SHALL return compact selected evidence rows, period labels, raw item names, raw item IDs, values by period, source metadata, and data gaps. The tools MUST NOT require or return full unbounded financial report tables for phase-one analysis.

#### Scenario: Return compact row evidence
- **WHEN** a financial report tool successfully loads report data
- **THEN** the tool returns selected evidence rows with raw `item`, `item_id`, and `values`
- **AND** the tool preserves provider period labels in `periods`
- **AND** the tool includes source metadata including symbol, source, report type, period, and cache state when available

#### Scenario: Report missing expected evidence
- **WHEN** a financial report tool cannot find rows relevant to a requested fundamental job
- **THEN** the tool returns missing expected items or data gaps instead of fabricating row values
- **AND** the analyst includes those gaps in its structured output

#### Scenario: Preserve partial failures
- **WHEN** one fundamental tool fails but other tools succeed
- **THEN** the failed tool result is represented as a bounded partial failure or data gap
- **AND** the fundamental analyst can still return an evidence package based on available evidence

### Requirement: Fundamental analyst output uses stable evidence sections
The fundamental analyst structured output SHALL include `symbol`, `period`, `summary`, `confidence`, `business_profile`, `growth`, `profitability`, `financial_health`, `cash_flow_quality`, `valuation_ratios`, `bullish_fundamental_points`, `bearish_fundamental_risks`, `uncertainties`, `data_gaps`, and `source_metadata`.

#### Scenario: Return complete structured output envelope
- **WHEN** the fundamental analyst completes a delegated task
- **THEN** the structured response includes a normalized stock `symbol`
- **AND** it includes the financial evidence `period`
- **AND** it includes a non-empty `summary`
- **AND** it includes `confidence`
- **AND** it includes the required evidence sections and gap fields

#### Scenario: Evidence sections carry analysis and raw support
- **WHEN** the fundamental analyst populates `growth`, `profitability`, `financial_health`, `cash_flow_quality`, or `valuation_ratios`
- **THEN** each section includes an assessment
- **AND** each section includes evidence rows or an explicit explanation that relevant evidence is unavailable
- **AND** each section includes interpretation, risks, and section-level data gaps

### Requirement: Fundamental analyst avoids unsupported metric computation and valuation claims
The fundamental analyst SHALL interpret reported evidence but MUST NOT claim deterministic metric precision, intrinsic value, target price, peer-relative valuation, or forecast-based conclusions unless a future tool provides explicit deterministic support.

#### Scenario: Avoid computed metric fabrication
- **WHEN** raw financial report rows do not provide a requested metric directly
- **THEN** the fundamental analyst MUST NOT invent the metric from speculative item mappings
- **AND** it MUST report the missing evidence as a data gap or uncertainty

#### Scenario: Avoid intrinsic valuation output
- **WHEN** the fundamental analyst reviews reported P/E, P/B, EPS, or related ratio rows
- **THEN** it may describe reported valuation-ratio evidence
- **AND** it MUST NOT produce an intrinsic value, target price, DCF valuation, or final valuation-based recommendation
