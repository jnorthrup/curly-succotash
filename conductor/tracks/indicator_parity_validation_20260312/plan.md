# Track: Indicator Parity Validation

## Objective
Satisfy the TODO item "Validate Kotlin indicator outputs against the Python reference implementation."

## Scope
- Create a Python script `backend/scripts/generate_indicator_ground_truth.py` that generates a sample dataset of OHLCV candles, computes standard indicators (SMA, EMA, RSI, BB, ATR) using `pandas`, and exports both the inputs and the computed indicator outputs as a JSON file.
- This JSON file serves as the ground truth required for the Kotlin/trikeshed tests.

## Stop Condition
The python script successfully writes `tmp/indicator_parity_ground_truth.json` with the required columns.
