# Track: E2E Integration: Replay -> HRM -> Reconciliation

**Objective:**
Implement an end-to-end integration test that spans the entire pipeline: `ReplayEngine` -> `HRMShadowEngine` -> offload -> reconciliation (`ScoreboardGenerator` / `VetoRegressionWatch`).

**Why this now:**
Satisfies the TODO item "Add integration tests spanning replay -> features -> HRM -> offload -> reconciliation."

**Scope:**
1.  **`backend/src/tests/test_e2e_integration.py`**:
    *   Set up `ReplayEngine` to produce a deterministic sequence of candles.
    *   Set up `CoinbaseTradingSimulator` with `HRMShadowEngine` and `VetoRegressionWatch` enabled.
    *   Feed the replay candles into the simulator.
    *   Verify that `HRMShadowEngine` processes the candles and generates shadow signals.
    *   Verify that `VetoRegressionWatch` captures vetoes based on the shadow signals.
    *   Verify that `ScoreboardGenerator` correctly computes metrics from the run.

**Stop condition:**
`pytest backend/src/tests/test_e2e_integration.py` passes and logs confirm successful pipeline traversal.
