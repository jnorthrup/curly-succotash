# Track: Regime-Aware Threshold & Cooldown Tuning

**Objective:**
Enhance `ThresholdScheduler` and `CooldownManager` in `backend/src/calibration_support.py` with real regime-aware logic and symbol/volatility-based tuning.

**Why this now:**
Satisfies multiple open TODOs:
- [ ] Add regime-aware threshold scheduling.
- [ ] Tune cooldown and hold policy by symbol and volatility bucket.
- [ ] Implement a cost-aware trade-head training objective (partial: by improving how we handle trade entries/exits via thresholds/cooldowns).

**Scope:**
1.  **`backend/src/calibration_support.py`**:
    *   Update `ThresholdScheduler.get_thresholds` to return different `confidence_threshold` and `move_threshold` based on the detected regime (e.g. higher confidence needed in `VOL_HIGH`).
    *   Update `CooldownManager.is_in_cooldown` to allow symbol-specific and volatility-bucket-specific cooldown periods.
    *   Implement `_get_volatility_bucket(symbol)` helper.
2.  **`backend/src/simulator.py`**:
    *   Refine `_detect_regime(candle)` to actually use volatility/indicators instead of just returning a placeholder.
    *   Ensure the simulator passes the detected regime to both `threshold_scheduler` and `cooldown_manager`.
3.  **`backend/src/tests/test_regime_cooldown.py`**:
    *   Add tests verifying that thresholds change when the regime shifts.
    *   Add tests proving that cooldowns vary by symbol or volatility.

**Stop condition:**
`pytest backend/src/tests/test_regime_cooldown.py` passes. Logs confirm "Regime shift detected: [X] -> [Y], updating thresholds" and "Symbol [S] in cooldown ([V] bucket)".
