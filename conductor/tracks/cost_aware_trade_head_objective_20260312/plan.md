# Track: Cost-Aware Trade-Head Objective

## Objective
Satisfy the TODO item "Implement a cost-aware trade-head training objective that actually reflects trading."
The current `TradeHeadCalibrator` in `backend/src/trade_head_calibration.py` uses a naive "sum of absolute values" placeholder. This track will implement a real objective function that penalizes predictions based on trading realism (e.g., predicted direction vs actual direction, and incorporating slippage/fee assumptions).

## Scope
- `backend/src/trade_head_calibration.py`: Implement a real `compute_cost` logic using predicted versus actual market outcomes, accounting for basic trading costs (fees/slippage). Update the signature to accept ground truth `actual` values.
- `backend/src/tests/test_trade_head_calibration.py`: Update existing tests to pass actual values and add new tests verifying the cost logic correctly penalizes wrong directions and accounts for fees.

## Stop Condition
`pytest backend/src/tests/test_trade_head_calibration.py` passes with tests confirming correct cost behavior for winning, losing, and neutral trades with fees. Update `TODO.md`.
