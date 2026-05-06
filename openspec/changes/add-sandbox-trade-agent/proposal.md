## Why

Users need a safe way to experiment with automated stock trading behavior without connecting to a real broker or placing real orders. A sandbox trade agent lets a user start an autonomous paper-trading session for one Vietnam-listed symbol, observe the agent's decisions every 3 minutes during market hours, and inspect simulated orders, positions, T+2 settlement, and portfolio state.

## What Changes

- Add a standalone sandbox trade-agent capability that is independent of stock research scheduling.
- Let an authenticated user create, list, read, pause, resume, stop, and delete paper-trading sessions scoped to their organization.
- Run one session for one stock symbol with default virtual capital of `100,000,000 VND`, while allowing the user to provide initial capital.
- Wake active sessions every 3 minutes only on Monday through Friday and only inside configured Vietnam continuous trading windows.
- Exclude holiday-calendar support from this phase.
- Let the agent make autonomous structured decisions to `BUY`, `SELL`, or `HOLD` from market data and current sandbox portfolio state.
- Execute accepted decisions only in the sandbox, with no broker integration and no real order placement.
- Enforce mechanical execution constraints: available cash for buys, sellable quantity for sells, long-only positions, and T+2 settlement for cash and securities.
- Persist session ticks, agent decisions, sandbox orders, positions, settlements, and portfolio snapshots.
- Skip ticks when fresh market data is unavailable instead of calling the agent.
- Provide backend APIs and worker processing first; UI/socket delivery is not part of the initial requirement unless a simple existing event path can be reused without changing the scope.

## Capabilities

### New Capabilities

- `sandbox-trade-agent`: Organization-scoped autonomous paper-trading sessions, market-hour ticking, structured agent decisions, sandbox execution, T+2 settlement, and portfolio history.

### Modified Capabilities

- None.

## Impact

- New API routes for sandbox trade-agent session management, session status/history, order/tick/portfolio reads, and internal worker dispatch.
- New domain models, schemas, repositories, services, and MongoDB indexes for sessions, ticks, orders, positions, settlements, and portfolio snapshots.
- New Redis queue and worker path for due trade-agent ticks.
- Reuse existing stock symbol validation and stock price market-data reads where appropriate.
- Add prompt and runtime support for a trade agent that returns validated structured decisions.
- Add settings for the trade-agent queue name, cadence, Vietnam trading windows, and optional worker polling interval.
- Add tests for session CRUD, trading-window checks, T+2 settlement, execution constraints, idempotent tick dispatch, skipped ticks, and worker processing.
