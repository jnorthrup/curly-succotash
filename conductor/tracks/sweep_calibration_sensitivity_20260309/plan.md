# Track: Calibration Sensitivity Sweep Script

## Objective
Satisfy the TODO item "Sweep calibration sensitivity for `--min-scale`, confidence bins, and sample windows." The core python sweep logic (`backend/src/calibration_sweep.py`) was implemented previously but lacked an operator-facing script and wasn't officially closed out in the backlog. Also fix a minor JSON serialization bug involving numpy bools in the sweep result export.

## Scope
- Fix JSON serialization of boolean `robust` flag in `CalibrationSweeper`.
- Create `backend/scripts/run_calibration_sweep.sh` to run the sweep.
- Update `TODO.md` to check off the item.
- Update `conductor/tracks.md` to reflect the completion.

## Stop Condition
Script runs and produces a JSON/CSV sweep result artifact.
