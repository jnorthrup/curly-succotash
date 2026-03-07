# Plan

## Phase 1: Brownfield bootstrap

- [x] Create local `conductor/` truth artifacts for this repo.
- [x] Record the initial track and its bounded corpus.

## Phase 2: OOS calibration split hardening

- [x] Review `backend/src/oos_calibration.py` and `backend/src/tests/test_oos_calibration.py` against the backlog requirement for explicit regime and time windows.
- [x] Add or tighten focused tests that prove the missing behavior.
- [x] Implement the minimum code changes to make those tests pass.
- [x] Run focused verification for the OOS calibration slice.
