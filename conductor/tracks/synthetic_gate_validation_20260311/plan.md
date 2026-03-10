# Track: Synthetic Gate Validation & Identity Benchmarking

**Objective:**
Enhance the synthetic gate suite in `backend/src/synthetic_gates.py` and `backend/src/simulator.py` to include strict cross-regime validation and benchmark the `identity` gate against persistence baselines.

**Why this now:**
Satisfies multiple open TODOs:
- [ ] Add `identity` synthetic gates that must converge near-zero.
- [ ] Compare HRM against persistence baselines on every synthetic gate.
- [ ] Add cross-regime validation requirements before any increase in authority.

**Scope:**
1.  **`backend/src/synthetic_gates.py`**:
    *   Implement `PersistenceBaseline` agent that simply returns the last input value.
    *   Implement `IdentityGate` that verifies if the model can reproduce the input exactly (should converge to zero error).
2.  **`backend/src/simulator.py`**:
    *   Add a `_run_synthetic_validation` method that specifically tests "Shock" and "Regime-Shift" scenarios.
    *   Implement logic to "Refuse any milestone pass" (e.g. log a CRITICAL error or set a flag) if HRM fails to beat the `PersistenceBaseline` on the `IdentityGate`.
3.  **`backend/src/tests/test_synthetic_validation.py`**:
    *   Add tests proving that `IdentityGate` error is near-zero for a perfect model.
    *   Add tests verifying that HRM performance is compared against the `PersistenceBaseline`.

**Stop condition:**
`pytest backend/src/tests/test_synthetic_validation.py` passes. Logs confirm "HRM vs Persistence Baseline: [X] vs [Y]" and "Identity Gate convergence: [Z]".
