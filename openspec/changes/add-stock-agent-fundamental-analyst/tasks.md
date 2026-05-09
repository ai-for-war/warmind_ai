## 1. Fundamental Analyst Contracts

- [x] 1.1 Create `app/agents/implementations/fundamental_analyst/` module structure with agent, runtime, middleware, validation, and tools packages.
- [x] 1.2 Define fundamental analyst output schemas covering `symbol`, `period`, `summary`, `confidence`, evidence sections, bullish points, bearish risks, uncertainties, and data gaps.
- [x] 1.3 Define shared evidence-section schemas with assessment, evidence rows, interpretation, risks, and section-level data gaps.
- [x] 1.4 Add parser/validation helpers for fundamental analyst structured responses, including fenced JSON handling consistent with existing specialist validation helpers.

## 2. Fundamental Tool Surface

- [x] 2.1 Add lazy tool dependency helpers for `StockCompanyService` and `StockFinancialReportService`.
- [x] 2.2 Implement `load_company_profile` using `StockCompanyService.get_overview()` and returning the VCI overview `item` plus metadata and gaps.
- [x] 2.3 Implement `load_income_statement` using `StockFinancialReportService.get_report()` with report type `income-statement`.
- [x] 2.4 Implement `load_balance_sheet` using `StockFinancialReportService.get_report()` with report type `balance-sheet`.
- [x] 2.5 Implement `load_cash_flow` using `StockFinancialReportService.get_report()` with report type `cash-flow`.
- [x] 2.6 Implement `load_financial_ratios` using `StockFinancialReportService.get_report()` with report type `ratio` and no VCI ratio-summary fallback.
- [x] 2.7 Ensure all financial report tools default to `period="quarter"` and accept `period="year"` while preserving service validation for unsupported periods.
- [x] 2.8 Add shared validation and data-gap helpers while preserving service `item`/`items` payloads without broad speculative item aliases.
- [x] 2.9 Add a fundamental analyst tool surface builder exposing exactly the five phase-one tools.

## 3. Fundamental Runtime And Prompt

- [x] 3.1 Add `app/prompts/system/fundamental_analyst.py` with role, scope, tool routing guidance, evidence-only boundaries, output requirements, and summarization prompt.
- [x] 3.2 Add fundamental analyst runtime config/model builder aligned with stock-agent runtime config patterns.
- [x] 3.3 Add middleware for summarization, bounded tool output, and tool error conversion that instructs the analyst to report gaps instead of fabricating values.
- [x] 3.4 Implement `create_fundamental_analyst_agent` with the dedicated model, five-tool surface, middleware, system prompt, and structured response format.

## 4. Stock-Agent Delegation Integration

- [x] 4.1 Extend stock-agent subagent constants, registry, and `StockSubagentId` literal to include `fundamental_analyst`.
- [x] 4.2 Add cached fundamental analyst runtime construction to the stock-agent delegation executor.
- [x] 4.3 Route delegated `fundamental_analyst` tasks through the specialist payload path.
- [x] 4.4 Update `delegate_tasks` tool documentation to include `fundamental_analyst` and its intended scope.
- [x] 4.5 Update stock-agent orchestration prompt to list `fundamental_analyst`, define routing rules, and replace generic-worker financial examples with the specialist.
- [x] 4.6 Ensure recursive delegation remains unavailable to the fundamental analyst runtime.

## 5. Unit Tests

- [ ] 5.1 Add validation tests for successful and invalid `FundamentalAnalystOutput` payloads.
- [ ] 5.2 Add tests proving `technical_read`-style final recommendations, target prices, or unsupported final recommendation labels are rejected or prevented by schema/prompt contract where enforceable.
- [ ] 5.3 Add tool tests for `load_company_profile` verifying it calls the company service path and reports VCI metadata.
- [ ] 5.4 Add tool tests for each KBS financial report tool verifying the correct report type, default quarterly period, annual override, raw `items`, and data gaps.
- [ ] 5.5 Add a test proving `load_financial_ratios` does not call VCI ratio-summary dependencies.
- [ ] 5.6 Add runtime creation tests verifying the fundamental analyst exposes exactly the five phase-one tools and structured response format.
- [ ] 5.7 Add delegation tests proving `fundamental_analyst` routes to the specialist runtime and unknown IDs remain rejected.
- [ ] 5.8 Add stock-agent prompt/orchestration tests proving fundamental routing rules are present and generic-worker financial examples are removed or replaced.

## 6. Verification

- [ ] 6.1 Run targeted fundamental analyst validation and tool tests.
- [ ] 6.2 Run targeted stock-agent delegation and prompt tests.
- [ ] 6.3 Run existing stock company and financial report service tests to confirm no regression in reused service paths.
- [ ] 6.4 Run `openspec validate add-stock-agent-fundamental-analyst --strict` and fix any proposal/spec/task validation issues.
