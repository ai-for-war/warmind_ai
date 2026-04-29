## 1. Schema And API Contract

- [ ] 1.1 Expand stock price source schema to allow `VCI` and `KBS`, defaulting query inputs to `VCI`.
- [ ] 1.2 Add optional `source` query support to both stock price history and intraday request schemas.
- [ ] 1.3 Update stock price response schemas so response `source` can be `VCI` or `KBS`.
- [ ] 1.4 Update intraday item schema so `id` accepts numeric VCI identifiers and string KBS identifiers.

## 2. Service And Gateway Behavior

- [ ] 2.1 Update the vnstock price gateway to build `Quote(symbol, source)` from the requested source instead of a single hard-coded source.
- [ ] 2.2 Update history reads to pass the selected source through service and gateway layers while preserving default VCI behavior.
- [ ] 2.3 Update intraday reads to pass the selected source through service and gateway layers while preserving default VCI behavior.
- [ ] 2.4 Reject `source=KBS` intraday requests that include `last_time` or `last_time_format`.
- [ ] 2.5 Preserve KBS string intraday identifiers during normalization while continuing to coerce numeric identifiers to stable integers.

## 3. Cache Isolation

- [ ] 3.1 Include `source` in history cache variants so VCI and KBS history responses cannot collide.
- [ ] 3.2 Include `source` in intraday cache variants so VCI and KBS intraday responses cannot collide.
- [ ] 3.3 Ensure stale-cache fallback uses the same selected source and query variant as the failed upstream read.

## 4. Tests

- [ ] 4.1 Add gateway tests proving `VCI` and `KBS` are passed to `vnstock.Quote` correctly.
- [ ] 4.2 Add service tests for default VCI behavior, explicit KBS behavior, cache variant isolation by source, and stale fallback by source.
- [ ] 4.3 Add validation tests rejecting KBS intraday cursor parameters.
- [ ] 4.4 Add schema/API tests for `source` query handling and KBS string intraday identifiers.
- [ ] 4.5 Run the relevant stock price unit and integration tests.
