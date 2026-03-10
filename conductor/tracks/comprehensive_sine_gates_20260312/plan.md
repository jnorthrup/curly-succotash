# Track: Comprehensive Sine Synthetic Gates

## Objective
Satisfy the TODO item "Add `sine` synthetic gates covering amplitude, phase, frequency, and noisy sine."
This involves expanding the `SyntheticGate` suite to include specialized sine variations and improving the naive baselines (`EMA`, `Linear`) used for competency comparison.

## Scope
- `backend/src/baselines.py`:
  - Implement a real `ema_baseline` with a configurable alpha.
  - Implement a real `linear_baseline` using a sliding window for simple linear regression.
- `backend/src/synthetic_gates.py`:
  - Add `AmplitudeSineGate`, `FrequencySineGate`, `PhaseSineGate`, and `NoisySineGate`.
  - Update `CompetencyEvaluator` to include these new gates.
- `backend/src/tests/test_synthetic_gates.py`:
  - Add tests for new sine gates and improved baselines.

## Stop Condition
`pytest backend/src/tests/test_synthetic_gates.py` passes with all 10+ tests.
Check off the corresponding items in `TODO.md`.
