## Context

The stock agent now has a preset specialist pattern: parent stock-agent delegation uses a typed `agent_id`, specialist runtimes have a bounded tool surface, and each specialist owns a structured output contract. `event_analyst` covers news, events, catalysts, policy, regulatory, macro, and industry evidence. `technical_analyst` covers chart state, indicators, support/resistance, trading plans, and technical backtest evidence.

Fundamental analysis is still routed through `general_worker` in stock-agent orchestration examples. That is too loose for financial-statement work because the parent can only ask for generic prose and the worker has no stable tools or output schema for business quality, growth, profitability, balance-sheet health, cash-flow quality, and reported valuation ratios.

The codebase already has validated stock data service boundaries:

- `StockCompanyService.get_overview()` uses VCI `Company.overview()` for company profile evidence.
- `StockFinancialReportService.get_report()` uses KBS `Finance` methods for income statement, balance sheet, cash flow, and ratio reports.
- The financial report service validates symbols, uses per-symbol/report/period caching, supports `quarter` and `year`, preserves provider period labels, and returns stable row items with `item`, `item_id`, and period-keyed `values`.

Phase one must avoid speculative broad field mappings. The financial statement item contract is not stable enough for deterministic metric computation, so the analyst tools should preserve the service `item`/`items` payloads and let the analyst report explicit data gaps.

## Goals / Non-Goals

**Goals:**

- Add `fundamental_analyst` as a preset stock-agent subagent.
- Create a dedicated fundamental analyst runtime with prompt, middleware, tools, and structured response validation.
- Provide exactly five phase-one tools:
  - `load_company_profile`
  - `load_income_statement`
  - `load_balance_sheet`
  - `load_cash_flow`
  - `load_financial_ratios`
- Use `StockCompanyService.get_overview()` for VCI company profile evidence.
- Use `StockFinancialReportService.get_report()` for KBS income statement, balance sheet, cash flow, and ratio evidence.
- Default financial statement tools to `period="quarter"` while allowing `period="year"`.
- Return a synthesis-ready fundamental evidence package to the parent stock agent.
- Keep parent stock agent responsible for final user-facing synthesis and recommendation labels.

**Non-Goals:**

- Do not add public REST endpoints for fundamental analysis in this change.
- Do not call `vnstock` directly from fundamental analyst tools.
- Do not use VCI `Company.ratio_summary()` for phase-one fundamental ratios.
- Do not add deterministic metric computation from raw rows in phase one.
- Do not add intrinsic valuation, target price, DCF, peer benchmarking, sector templates, or forecast assumptions.
- Do not persist fundamental-analysis reports as a new durable artifact.
- Do not let the fundamental analyst produce final buy/sell/hold/reduce/accumulate recommendations.

## Decisions

### Decision 1: Create a dedicated `fundamental_analyst` specialist runtime

The stock-agent registry will be extended with a new preset `fundamental_analyst` ID. The delegation executor will route this ID to a cached fundamental analyst runtime, mirroring the event and technical analyst pattern.

Rationale:

- Fundamental analysis has a distinct data surface and output contract.
- Reusing `general_worker` keeps financial evidence prompt-driven and harder to test.
- A specialist runtime lets the parent stock agent delegate financial-statement work while retaining final synthesis responsibility.

Alternatives considered:

- Add fundamental instructions only to the parent stock agent: rejected because it increases parent prompt/tool burden and does not provide a stable specialist output contract.
- Keep using `general_worker`: rejected because the parent still needs to parse unstructured prose and cannot rely on a fixed evidence package.

### Decision 2: Use five explicit tools instead of one aggregate tool

The runtime will expose five separate tools matching the conceptual graph:

- `load_company_profile`
- `load_income_statement`
- `load_balance_sheet`
- `load_cash_flow`
- `load_financial_ratios`

Rationale:

- Tool calls stay traceable to the analyst job being performed.
- The model can avoid unnecessary report reads when the delegated objective is narrow.
- The output can identify partial failures and data gaps per report type.

Alternatives considered:

- One aggregate `load_fundamental_evidence` tool: rejected for phase one because the requested design favors explicit graph-aligned tool routing and visible per-statement execution.

### Decision 3: Reuse internal stock services rather than direct `vnstock` calls

Fundamental analyst tools will call existing service-layer dependencies:

- `load_company_profile` calls `StockCompanyService.get_overview()`.
- Financial tools call `StockFinancialReportService.get_report()` with the matching report type.

Rationale:

- The services already centralize symbol validation, provider choice, caching, stale fallback, and response normalization.
- Direct `vnstock` calls would duplicate provider integration behavior and risk drifting from existing API contracts.
- Reusing services keeps the specialist additive and avoids new third-party integration logic.

Alternatives considered:

- Call `vnstock.Company` and `vnstock.Finance` directly from tools: rejected because the codebase already has concrete provider gateways and AGENTS guidance says not to invent broad fallback mappings for third-party payloads.

### Decision 4: Use VCI only for company profile and KBS for financial reports/ratios

`load_company_profile` will use the existing VCI overview path. `load_financial_ratios` will use KBS `Finance.ratio()` through `StockFinancialReportService`, not VCI `Company.ratio_summary()`.

Rationale:

- Company profile and financial statement evidence are already separated by the existing services.
- The user explicitly selected KBS `Finance.ratio()` for financial ratios.
- Avoiding VCI ratio summary keeps phase-one valuation and profitability evidence from mixing two different ratio scopes.

Alternatives considered:

- Include VCI `Company.ratio_summary()` as a supplement: rejected for phase one because it would introduce an additional ratio source and require a clearer reconciliation policy.

### Decision 5: Keep phase-one output evidence-only

The output contract will include:

- `symbol`
- `period`
- `summary`
- `confidence`
- `business_profile`
- `growth`
- `profitability`
- `financial_health`
- `cash_flow_quality`
- `valuation_ratios`
- `bullish_fundamental_points`
- `bearish_fundamental_risks`
- `uncertainties`
- `data_gaps`

Analysis sections should share a common shape with an assessment, raw evidence rows, interpretation, risks, and data gaps. The analyst may interpret reported rows, but it must not fabricate computed metrics or infer broad aliases when row identity is unclear.

Rationale:

- Parent stock agent needs structured, synthesis-ready evidence.
- The current item contract is stable enough to preserve row labels and values, but not stable enough for broad deterministic item mapping.
- Explicit gaps are safer than false precision.

Alternatives considered:

- Compute canonical growth, margin, leverage, cash-conversion, and valuation metrics in phase one: deferred until item IDs, sector templates, and deterministic metric logic are validated.

## Risks / Trade-offs

- **Risk: The analyst omits one required report tool for a broad fundamental task** → Mitigation: prompt routing guidance must require all relevant tools for full fundamental tasks and require data gaps when evidence is missing.
- **Risk: Five separate tools increase latency compared with one aggregate fetch** → Mitigation: each tool can be called only when relevant, and service-level caching reduces repeated provider cost.
- **Risk: Large financial report outputs bloat model context** → Mitigation: preserve the existing service payload shape first; add deterministic truncation later only if measured context usage requires it.
- **Risk: KBS row names vary across sectors or report types** → Mitigation: do not hard-code speculative broad aliases; preserve raw `item`, `periods`, and values, and report missing expected evidence explicitly.
- **Risk: Ratio evidence is interpreted as intrinsic valuation** → Mitigation: prompt and schema must state that reported valuation ratios are evidence only and do not authorize target price or DCF output.
- **Risk: Existing active stock-agent subagent changes are complete but not archived** → Mitigation: implement this change on top of the current registry pattern and archive changes in an order that preserves the complete subagent set.
