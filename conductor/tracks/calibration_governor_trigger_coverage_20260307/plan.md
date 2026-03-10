# Track: Calibration Governor Trigger Coverage

## Problem

The `CalibrationGovernor` class supports multiple triggers (scheduled, drift, performance, regime change), but existing
unit tests only cover initial and cooldown/interval logic. Missing coverage leaves risk that drift/performance/regime
logic regresses unnoticed.

## Scope

- add focused unit tests verifying each trigger type fires appropriately
- ensure `should_calibrate` respects configuration flags and thresholds
- no product code changes beyond tests

## Acceptance

- new tests are added under `backend/src/tests/test_calibration_governor.py`
- `pytest` runs without failures (full suite not required but helpful)
- a local track file with plan exists and is linked from `conductor/tracks.md`

## Phase 1: Add tests

- [x] Drift threshold triggers calibration when exceeded
- [x] Performance drop triggers calibration when below threshold
- [x] Scheduled max interval triggers calibration
- [x] Regime change with sufficient samples triggers calibration
- [x] Regime change with insufficient samples returns DEFER

## Phase 2: Verify

- [x] Run `pytest backend/src/tests/test_calibration_governor.py` and confirm new tests pass
- [x] Mark plan checkboxes

**Verification:** 7 tests executed locally; all passed 2026‑03‑07. Added four new assertions covering drift, performance, schedule, and regime-change logic.  

