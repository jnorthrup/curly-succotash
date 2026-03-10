# Track Spec: Trade-Head Calibration Cost Objective (MT10 extension)

## Problem

The existing `trade_head_calibration` module returns zero cost for every
prediction.  A `TODO` comment in its `compute_cost` method warns that a real
cost-aware objective is needed as part of MT10, and downstream code must be
able to exercise the interface with non-trivial values.  The current stub has
no behavioral tests beyond empty-input zero; without a minimal working cost
computation callers cannot validate that the module is being invoked or
observe meaningful outputs.

## Scope

This track implements a lightweight, non‑zero placeholder objective and adds
corresponding test coverage.  It is still not a true trading cost but it
demonstrates the extension pattern and keeps the TODO item visible.

* modify `backend/src/trade_head_calibration.py` so that
  `TradeHeadCalibrator.compute_cost`:
  * computes the sum of absolute values for any numeric entries in the
    supplied prediction dictionary
  * marks `self.loaded = True` when called
  * updates docstrings accordingly
* extend `backend/src/tests/test_trade_head_calibration.py` with tests for the
  new logic and loading behaviour
* update `/TODO.md` with a new bullet reflecting this incremental
enhancement
* add a new track directory with spec and plan files (this one)
* update `conductor/tracks.md` with a new entry and mark it complete once
  changes are in place

This work does **not** attempt to design a realistic trade-head objective; the
focus is purely on creating a simple cost computation to satisfy downstream
validation paths.

## Desired Outcome

* `compute_cost` no longer always returns 0.0 and tests cover basic numeric
  cases
* `pytest` including the new tests continues to pass across the backend suite
* `TODO.md` contains an explicit open task describing the incremental
  enhancement
* new track is visible in `conductor/tracks.md` and closed with verification

## Acceptance Signals

* `pytest backend/src/tests/test_trade_head_calibration.py` passes with the
  numeric-value test added
* `pytest backend/src/tests/test_hrm_ring_api.py` and
  `backend/src/tests/test_freqtrade_ring_agent.py` still succeed
* the new track entry in `conductor/tracks.md` is marked complete with a link
  to this spec
