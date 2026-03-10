# Track: Calibration Governor Integration & Cadence

**Objective:**
Integrate `CalibrationGovernor` with real inputs from `DriftMonitor` and performance metrics in `CoinbaseTradingSimulator`. Implement a cadence-based check instead of running the logic every cycle (candle). Add drift monitoring and artifact expiration logic.

**Why this now:**
Satisfies multiple open TODOs:
- [ ] Add calibration governor cadence and trigger policy instead of running every cycle.
- [ ] Add calibration drift monitoring and auto-expire stale artifacts.

**Scope:**
1.  **`backend/src/calibration_governor.py`**:
    *   Add `check_cadence_cycles` to `GovernorConfig` (default e.g. 100).
    *   Add `_cycles_since_last_check` counter to `CalibrationGovernor`.
    *   Update `should_calibrate` to only evaluate full logic if cycle cadence is met (or if `force` is True).
2.  **`backend/src/simulator.py`**:
    *   Implement `_monitor_drift` using `self.drift_monitor.detect_drift`.
    *   Collect recent performance in `_on_new_candle` to pass to `_check_recalibration`.
    *   Update `_check_recalibration` to pass real `performance_drop` and `drift_detected` flags to the governor.
    *   Incorporate `self.calibration_governor.is_artifact_fresh` and `self.drift_monitor.should_expire_artifacts`.
3.  **`backend/src/tests/test_calibration_integration.py`**:
    *   Add integration tests proving that calibration is skipped when cadence is not met, and triggered when drift/performance thresholds are hit.

**Stop condition:**
`pytest backend/src/tests/test_calibration_integration.py` passes. Logs confirm "Skipping calibration check (cadence not met)" and "Recalibration triggered" when appropriate.
