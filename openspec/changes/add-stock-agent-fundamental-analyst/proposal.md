## Why

The stock agent can already delegate event/news work and technical analysis to preset specialists, but fundamental analysis still falls back to the generic worker. That leaves financial-statement interpretation, business-quality evidence, reported ratios, and valuation context prompt-driven instead of bounded by a stable tool surface and output contract.

Adding a dedicated fundamental analyst completes the phase-one stock-agent specialist set and gives the parent stock agent a synthesis-ready financial evidence package without letting the specialist make the final all-factor recommendation.

## What Changes

- Add a preset `fundamental_analyst` subagent to the stock-agent delegation registry.
- Create a dedicated fundamental analyst runtime with its own prompt, middleware, deterministic tool surface, and structured output validation.
- Add five fundamental-analysis tools:
  - `load_company_profile`
  - `load_income_statement`
  - `load_balance_sheet`
  - `load_cash_flow`
  - `load_financial_ratios`
- Reuse the existing `StockCompanyService.get_overview()` path for company profile evidence from VCI `Company.overview()`.
- Reuse the existing `StockFinancialReportService.get_report()` path for KBS financial statement and ratio evidence from `Finance.income_statement()`, `Finance.balance_sheet()`, `Finance.cash_flow()`, and `Finance.ratio()`.
- Default financial report tools to `period="quarter"` while allowing the analyst to request `period="year"` when the user intent calls for annual evidence.
- Keep phase one focused on selected reported evidence, interpretation, risks, uncertainties, and data gaps. Do not add deterministic metric computation, intrinsic valuation, target prices, peer benchmarking, or final buy/sell/hold recommendations.
- Update stock-agent orchestration guidance so the parent routes business quality, growth, profitability, financial health, cash-flow quality, reported ratios, and valuation-ratio subtasks to `fundamental_analyst`.

## Capabilities

### New Capabilities

- `stock-fundamental-analysis`: Dedicated fundamental analyst specialist, tools, and structured financial evidence package for Vietnam-listed equities.

### Modified Capabilities

- `stock-agent-runtime`: Extend typed stock-agent delegation to support `fundamental_analyst` and route fundamental-analysis subtasks to it.

## Impact

- Affected agent runtime code:
  - `app/agents/implementations/stock_agent/delegation.py`
  - `app/agents/implementations/stock_agent/tools.py`
  - `app/agents/implementations/stock_agent/middleware/orchestration.py`
  - new `app/agents/implementations/fundamental_analyst/` module
- Affected prompt code:
  - `app/prompts/system/stock_agent.py`
  - new `app/prompts/system/fundamental_analyst.py`
- Affected stock services reused by tools:
  - `app/services/stocks/company_service.py`
  - `app/services/stocks/financial_report_service.py`
- Affected schemas/tests:
  - new fundamental analyst output validation schemas
  - stock-agent delegation and prompt tests
  - fundamental analyst tool and validation tests
- No public REST API changes are required for phase one.
- No new third-party dependency is required.
