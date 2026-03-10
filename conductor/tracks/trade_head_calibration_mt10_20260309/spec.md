# Track Spec: Trade-Head Calibration Module (MT10)

## Problem

The `TODO.md` backlog lists a cost-aware trade-head training objective as an
open task.  End-to-end training code refers to a `trade_head_calibration`
module which does not yet exist.  Without a placeholder or basic interface the
codebase cannot evolve toward a real objective, and the HRM promotion path
cannot reliably surface whether trade-head calibration was ever loaded.

## Scope

This track covers the following brownfield slice:

* create a new Python module `backend/src/trade_head_calibration.py` containing
  a `TradeHeadCalibrator` class with a minimal, cost-aware objective stub
  method.
* add focused unit tests verifying the class exists, can be instantiated, and
  that the placeholder objective returns zero cost when given empty inputs.
* update `backend/src/tests` imports and the ring-agent and HRM API tests to
  reference the new module where appropriate.
* record repo-local Conductor truth for the slice and mark the track
  completed once tests pass.

This does **not** implement a real cost-aware objective; that will be handled by
subsequent tracks when more training logic is added.

## Desired Outcome

* `trade_head_calibration.py` and its tests exist and are imported by the
  ring-agent code without errors.
* pytest runs include the new test file and pass.
* backlog item "Implement a cost-aware trade-head training objective" is
  marked or noted as having a placeholder interface now available.

## Acceptance Signals

* `pytest backend/src/tests/test_trade_head_calibration.py` passes.
* `backend/src/tests/test_hrm_ring_api.py` and
  `backend/src/tests/test_freqtrade_ring_agent.py` continue to pass after
  importing the new module.
* `conductor/tracks.md` is updated with this track and closed after
  verification.
