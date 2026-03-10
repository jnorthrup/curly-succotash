# Track: Upgrade Execution Realism

## Objective
Satisfy the TODO item "Upgrade execution realism for latency and market impact assumptions."
The base paper trading strategy implementation (`BaseStrategy` in `backend/src/strategies.py`) previously executed trades using raw candle close prices without applying latency offsets, slippage, or market impact based on position sizing.

## Scope
- `backend/src/strategies.py`: Update `StrategyConfig` to include parameters for `commission_pct`, `slippage_bps`, `market_impact_factor`, and `latency_ms`. Update `BaseStrategy._execute_paper_signal` and `BaseStrategy._close_position` to incorporate these execution costs, modifying actual entry/exit prices to reflect slippage, and calculating net PnL by factoring in commissions.

## Stop Condition
`pytest backend/src/tests/test_simulator.py` continues to pass, validating that the execution strategy changes do not break system tests or rank tracking. Update `TODO.md` and `conductor/tracks.md`.
