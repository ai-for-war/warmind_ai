## 1. Backtest schema and template contract updates

- [ ] 1.1 Extend internal backtest schema types to add `ichimoku_cloud` and its validated template parameters
- [ ] 1.2 Extend public backtest API schema validation to accept the Ichimoku template parameter contract
- [ ] 1.3 Add FE template-catalog metadata for `ichimoku_cloud`, including defaults and parameter descriptions

## 2. Warmup-aware data loading

- [ ] 2.1 Update backtest data loading to fetch pre-window warmup history by expanding the upstream start date
- [ ] 2.2 Split normalized history into warmup bars and tradable bars so only the requested backtest window can produce signals, fills, and reported outputs
- [ ] 2.3 Add deterministic validation for insufficient warmup history and insufficient tradable history

## 3. Ichimoku template implementation

- [ ] 3.1 Implement aligned Ichimoku indicator calculations for Tenkan, Kijun, Senkou A/B, and Chikou confirmation without lookahead bias
- [ ] 3.2 Implement the `ichimoku_cloud` entry and exit rules for the existing long-only next-open engine
- [ ] 3.3 Implement warning-state evaluation for weakening Ichimoku conditions without creating extra trades
- [ ] 3.4 Register the new template in the internal template registry and expose it through the public template catalog

## 4. Tests and verification

- [ ] 4.1 Add unit tests for Ichimoku parameter validation and public request validation failures
- [ ] 4.2 Add unit tests for warmup-aware data loading and for preventing warmup bars from affecting reported outputs
- [ ] 4.3 Add deterministic strategy tests for Ichimoku bullish entries, bearish exits, and warning-only bars
- [ ] 4.4 Add presenter and API tests that verify the public template catalog includes `ichimoku_cloud` with the expected parameter metadata
- [ ] 4.5 Run the relevant backtest and backtest-api test suites and resolve any failures introduced by the Ichimoku template change
