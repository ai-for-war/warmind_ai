## Context

The backend now has an internal backtest service under `app/services/backtest`,
but FE still has no public contract for discovering supported strategies or
submitting a run. Backtest execution is conceptually broader than the stock
catalog or quote-read surface, so the user explicitly wants a standalone
backtest domain instead of placing FE-facing execution under `/stocks/*`.

This change is cross-cutting because it introduces:

- a new API router and schema set for FE-facing backtest requests
- dependency wiring from public API handlers into the internal backtest service
- template-discovery responses owned by the backend rather than hardcoded in FE
- public request/response contracts that must stay narrower than the internal
  service implementation details

The agreed v1 assumptions inherited from the current internal backtest
capability are:

- exactly one stock symbol per run
- daily timeframe only
- long-only execution
- `all_in` sizing
- `next_open` execution model
- fixed templates only: `buy_and_hold`, `sma_crossover`
- default `initial_capital = 100_000_000`
- structured outputs: `summary_metrics`, `performance_metrics`, `trade_log`,
  `equity_curve`

The FE-specific decisions already agreed for this change are:

- the API domain is standalone under `/api/v1/backtests/*`
- the stock symbol is provided in the request body rather than as a stock-route
  path parameter
- v1 should support template discovery plus synchronous execution
- the change should not add run persistence, run history, async jobs, or
  compare endpoints

## Goals / Non-Goals

**Goals:**
- Add a dedicated FE-facing backtest API domain separate from the `stocks`
  router
- Provide one discovery endpoint for supported templates and FE form metadata
- Provide one synchronous run endpoint that executes a backtest through the
  existing internal backtest service
- Keep public request input limited to the fields FE should control in v1
- Reuse the existing org-auth access model already used by stock endpoints

**Non-Goals:**
- Add backtest endpoints under `/api/v1/stocks/*`
- Expose every internal engine assumption as user-configurable FE input
- Persist backtest runs, add run IDs, or provide run-history endpoints
- Add batch execution, optimization, comparison, or portfolio backtests
- Add async job orchestration, polling, or websocket progress updates

## Decisions

### D1: Introduce a standalone `/api/v1/backtests/*` router instead of extending the stock router

**Decision**: Add a dedicated backtest router under `app/api/v1/backtests/`
with prefix `/backtests` and tag `backtests`. FE-facing execution will not be
nested under `/stocks/{symbol}`.

Recommended routes:

- `GET /api/v1/backtests/templates`
- `POST /api/v1/backtests/run`

**Rationale**:
- backtest execution is a separate product capability, not just another stock
  quote read
- the user explicitly wants a standalone backtest domain
- keeping the API separate avoids overloading the stock router with simulation
  semantics

**Alternatives considered:**
- **`/api/v1/stocks/{symbol}/backtests/*`**: rejected because the user wants a
  separate domain and because execution is broader than stock quote transport
- **Expose backtest only through internal services and no FE API**: rejected
  because FE needs a stable contract now

### D2: Keep v1 execution synchronous with a command-style run endpoint

**Decision**: Use a synchronous execution endpoint:

- `POST /api/v1/backtests/run`

The endpoint accepts one run request and returns the completed backtest result
in the same response.

**Rationale**:
- the current internal service already executes one deterministic run in
  process
- synchronous execution keeps FE integration simple for the first release
- there is no agreed persistence or background-job model yet

**Alternatives considered:**
- **`POST /api/v1/backtests/runs` with persisted run resources**: rejected for
  v1 because it implies run storage, run IDs, and history retrieval
- **Async jobs plus polling**: rejected because it adds infrastructure and UI
  complexity before there is evidence the runtime needs it

### D3: Expose only FE-controlled request fields and return engine assumptions explicitly

**Decision**: The public run request includes only:

- `symbol`
- `date_from`
- `date_to`
- `template_id`
- `template_params`
- optional `initial_capital`

The public request does not expose `timeframe`, `direction`,
`position_sizing`, or `execution_model` as FE-controlled inputs in v1 because
those are already fixed by the internal capability.

The run response should include an explicit `assumptions` block so FE can show
the backend-owned execution assumptions alongside the result.

**Rationale**:
- FE should only send fields the product currently allows users to change
- locking fixed engine assumptions at the API boundary reduces validation
  ambiguity
- returning assumptions makes results easier to interpret and debug

**Alternatives considered:**
- **Expose every internal request field directly**: rejected because it leaks
  implementation detail and expands the public contract too early
- **Hide engine assumptions from the response**: rejected because FE needs a
  stable explanation of how the run was executed

### D4: Add a template-discovery endpoint so FE does not hardcode strategy forms

**Decision**: `GET /api/v1/backtests/templates` returns a list of supported
templates and backend-owned parameter metadata for each one.

Recommended response structure per template:

- `template_id`
- `display_name`
- `description`
- `parameters`

Recommended parameter metadata:

- `name`
- `type`
- `required`
- `default`
- `min`
- optional `description`

**Rationale**:
- FE should not duplicate backend template definitions
- discovery reduces drift when templates or defaults change
- the current v1 fixed-template approach maps naturally to backend-owned
  metadata

**Alternatives considered:**
- **Hardcode template forms in FE**: rejected because it creates avoidable drift
- **Return raw internal schema classes or Pydantic metadata**: rejected because
  FE needs a stable transport contract, not Python-specific implementation data

### D5: Reuse the internal backtest service rather than branching execution logic in the API layer

**Decision**: The public API handler converts the FE request into the existing
internal `BacktestService` request shape and delegates execution to that
service. Router code remains thin. Public API schemas may differ from internal
schemas, but business logic stays inside `app/services/backtest`.

**Rationale**:
- preserves one source of truth for backtest execution
- reduces risk of FE and agent backtests diverging
- matches the router-service separation already used elsewhere in the repo

**Alternatives considered:**
- **Implement separate FE-only backtest orchestration**: rejected because it
  duplicates business logic
- **Expose the internal service schemas directly as public contract**: rejected
  because the FE API should remain narrower and more intentional

### D6: Reuse the existing organization-auth access pattern from stock endpoints

**Decision**: Both public backtest endpoints require the same auth and
organization-context dependencies already used by stock endpoints:

- active user
- organization context

**Rationale**:
- keeps access control consistent across financial-data capabilities
- avoids inventing a separate auth pattern for backtest APIs
- existing tests and FE behavior already understand this org-scoped access model

**Alternatives considered:**
- **Public unauthenticated template listing**: rejected because template
  discovery remains part of the authenticated product surface
- **Different auth rules for templates vs execution**: rejected because the
  extra complexity does not buy much in v1

## Risks / Trade-offs

**[A synchronous run endpoint can become slow as backtests grow more complex]** -> Mitigation:
start with synchronous execution for v1 simplicity and add async job
orchestration only if real request latency demands it.

**[A separate backtest domain duplicates some stock-related concepts such as symbols and date ranges]** -> Mitigation:
accept the duplication at the API boundary while keeping execution logic shared
through the internal backtest service.

**[Template metadata can drift if FE and backend each own part of the form contract]** -> Mitigation:
make the backend the source of truth via `GET /backtests/templates`.

**[Future persistence may force route expansion beyond `POST /backtests/run`]** -> Mitigation:
keep the current command-style endpoint narrow and evolve to `/runs` resources
later if product requirements justify it.

## Migration Plan

1. Add FE-facing backtest request/response schemas under the public API schema
   layer.
2. Add a dedicated router under `app/api/v1/backtests/` and register it in the
   aggregate v1 router.
3. Add a template-discovery response builder backed by the current supported
   fixed templates.
4. Add a run handler that:
   - validates FE input
   - maps the public request to the internal backtest request
   - calls `BacktestService`
   - maps the result to the public FE response contract
5. Wire the public router to the existing auth and organization-context
   dependencies.
6. Add integration tests for:
   - org-scoped access
   - template discovery
   - run request validation
   - successful synchronous execution
   - failure isolation between endpoints

**Rollback**

- remove the new backtest router from the v1 aggregate router
- remove public backtest schemas and dependency wiring added for FE
- keep the internal backtest service untouched because it remains useful for AI
  and future integrations

## Open Questions

- None for the currently agreed v1 scope.
