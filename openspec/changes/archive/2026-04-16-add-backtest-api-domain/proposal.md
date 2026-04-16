## Why

The backend now has an internal backtest capability, but the frontend still has
no stable API contract for discovering supported strategies and executing one
backtest run. The product needs a dedicated backtest API domain so FE can call
backtesting directly without depending on stock-domain routes or on internal
agent-only service contracts.

## What Changes

- Add a dedicated backtest API domain under `/api/v1/backtests/*` instead of
  nesting FE-facing backtest endpoints under `/api/v1/stocks/*`
- Add a template-discovery endpoint so FE can render backtest forms from
  backend-owned template metadata
- Add a synchronous backtest execution endpoint that accepts a stock symbol in
  the request body and returns structured run results
- Reuse the existing internal backtest service for execution rather than
  re-implementing strategy or engine logic in the API layer
- Keep v1 FE scope aligned with the current internal backtest capability:
  single symbol, daily timeframe, long-only, fixed templates, and no persisted
  run history

## Capabilities

### New Capabilities
- `backtest-api`: provide a frontend-facing API domain for listing supported
  backtest templates and executing one synchronous stock backtest run through a
  dedicated `/api/v1/backtests/*` surface

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds a dedicated backtest API surface under
  `/api/v1/backtests/*` for template discovery and run execution
- **Affected code**: new router and request/response schemas for FE-facing
  backtest endpoints, plus dependency wiring to reuse the internal backtest
  service
- **Domain boundaries**: introduces a standalone backtest API domain rather than
  attaching FE-facing backtest execution to the existing `stocks` router
- **Execution model**: preserves the current internal backtest assumptions in
  v1 instead of exposing configurable engine behaviors to FE
- **Testing**: requires API and service-integration tests for organization
  access, request validation, template discovery, execution responses, and
  endpoint isolation
