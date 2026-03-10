# Track: Synthetic Gates Report & Test Coverage

## Problem

The `synthetic_gates` module powers HRM competency validation and includes
serialization and reporting logic. Current unit tests exercise basic
shape generation and identity gate only. Several code paths remain untested
including correlation handling, failure outcome classification, `GateResult`
serialization, and report file writing. Reliable JSON artifacts are required
by downstream tooling and are mentioned in the project backlog under
"Capture synthetic gate artifacts as machine-readable JSON for every run."

## Scope

- add new unit tests covering:
  * `GateResult.to_dict()`
  * correlation calculation when predictions are constant or inputs constant
  * report generation populated failure outcomes (ARCH/SCALE/TRANSFER)
  * `save_report` writes a file with expected structure
  * `run_competency_check` return value and optional report output
- no changes to product code unless tests expose a bug (none expected)

## Acceptance

- new tests under `backend/src/tests/test_synthetic_gates_report.py`
- `pytest` runs with the new tests passing
- track file exists and is linked from `conductor/tracks.md`

## Phase 1: Add tests

- [x] create test file with the cases above
- [x] run `pytest` locally to confirm success
- [x] update track notes accordingly

## Phase 2: Verify

- [x] ensure full synthetic gate suite still passes
- [x] mark plan checkboxes and record verification result

**Verification:** On 2026‑03‑07 the new test module executed 4 additional assertions and all 10 total synthetic gate tests passed. `run_competency_check` produced a JSON file and returned a bool as expected.  


**Owner:** Conductor (master)
