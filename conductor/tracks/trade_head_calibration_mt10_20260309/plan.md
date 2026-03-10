# Plan

## Phase 1: Local truth

- Add a new track entry to `conductor/tracks.md` describing this slice and link
  to the new spec directory.
- Ensure `TODO.md` reflects the placeholder state (maybe tag as partial or leave
  open with comment pointing to this track).

## Phase 2: Module and tests

- Create `backend/src/trade_head_calibration.py` with a `TradeHeadCalibrator`
  class.  Implement a method `compute_cost` or similar that accepts a
  prediction and returns 0.0 by default, with a docstring explaining this is a
  stub for cost-aware objective logic.
- Add `backend/src/tests/test_trade_head_calibration.py` verifying the
  class instantiates and `compute_cost` returns 0.0 for empty input.
- Modify existing tests (`test_hrm_ring_api.py` and `test_freqtrade_ring_agent.py`)
  to import the new module so that import time errors would be caught early.

## Phase 3: Verification

- Run `pytest` against the new test file and the existing hrm/ring tests.
- Ensure all tests pass with the current venv.
- Update track state in `tracks.md` to mark as completed and record verification
  command and results.

## Phase 4: Clean up

- Optionally note in `TODO.md` that MT10 now has a placeholder interface and
  should be revisited for real implementation.
