# Plan for Cost Objective Enhancement

## Phase 1: Update local truth

* Add new bullet to `conductor/tracks.md` describing the enhancement and
  pointing to this directory; leave it unchecked until after verification.
* Ensure `/TODO.md` has the extra open task (already added above).

## Phase 2: Modify module and tests

* Edit `backend/src/trade_head_calibration.py`:
  * change `compute_cost` as described in the spec
  * update docstring comments
* Add two new assertions in `backend/src/tests/test_trade_head_calibration.py`:
  * numeric input cost calculation
  * calling `compute_cost` sets `loaded` flag

## Phase 3: Verification

* Run `pytest backend/src/tests/test_trade_head_calibration.py` (plus the two
  ring-agent tests) to confirm no regressions.
* Observe that the new numeric test passes and cost is non-zero.

## Phase 4: Close track

* Update `conductor/tracks.md` entry to checked with command output and date.
* The backlog bullet in `/TODO.md` remains open until a realistic objective is
  built.
