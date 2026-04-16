## 1. Public backtest API contracts

- [x] 1.1 Add FE-facing request and response schemas for the dedicated backtest API domain
- [x] 1.2 Add public template-catalog response schemas that describe supported templates and parameter metadata for FE form rendering
- [x] 1.3 Add a public run-response contract that includes the structured backtest result plus the backend-applied execution assumptions

## 2. Router and dependency wiring

- [ ] 2.1 Add a dedicated router under `app/api/v1/backtests/` with prefix `/backtests` and tag `backtests`
- [ ] 2.2 Register the new backtest router in the aggregate v1 router without attaching public backtest endpoints to the `stocks` router
- [ ] 2.3 Wire the public handlers to the existing org-auth dependencies and to the internal `BacktestService`

## 3. Endpoint implementation

- [ ] 3.1 Implement `GET /api/v1/backtests/templates` to return the current v1 template catalog with FE-oriented metadata
- [ ] 3.2 Implement `POST /api/v1/backtests/run` to validate FE input, map it into the internal backtest request, and return the completed synchronous run result
- [ ] 3.3 Ensure the public run request accepts the stock symbol in the request body and does not expose fixed engine assumptions as FE-configurable inputs

## 4. Tests and verification

- [ ] 4.1 Add integration tests for template discovery and synchronous backtest execution through the new `/api/v1/backtests/*` surface
- [ ] 4.2 Add integration tests for organization-scoped access and request-validation failures on the new backtest endpoints
- [ ] 4.3 Add regression coverage showing the new public backtest API remains separate from the `stocks` router surface
- [ ] 4.4 Run the relevant backtest, router, and integration test suites and resolve any failures introduced by the new API domain
