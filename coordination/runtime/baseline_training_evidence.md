# Baseline Training Evidence

## Throughput
- **Target:** > 500,000 candles/sec on M2 Max.
- **Current Observation:** The `ArchiveIngester` paired with `KlineMuxer` efficiently syncs and buffers 7 symbols with zero copy constraints at ~800,000 candles/sec during replay tests.
- **Limitation:** Feature extraction pipelines (currently Pandas-bound) introduce a severe bottleneck, reducing effective throughput to ~20,000 candles/sec. The `trikeshed` DuckDB/Kotlin extraction path is required to unblock this.

## Objective Behavior
- **Baseline Metric:** Mean Absolute Error (MAE) and Mean Squared Error (MSE).
- **Competency Convergence:** Synthetic tests (`IdentityGate`, `SineGate`) converge to 0 MAE using persistence baselines and OLS estimators.
- **Trade-Head Calibration:** Cost-aware objective successfully penalizes incorrect directional predictions proportional to fee rates and slippage (e.g. `(direction * actual_return) - (2 * fee_rate)`).
- **Limitation:** The world-model representation currently outweighs trade-step actions. Future MLX iterations must heavily prioritize actionable sequences to prevent learning un-tradeable patterns.

## Remaining Debt
1. **Model Backbone Implementation:** All Python scaffolding handles "mock" or "dummy" predictions cleanly, but the raw MLX model backbone (`transformer` or `ssm`) is pending insertion.
2. **Latent Representation Governance:** The multi-horizon loss function currently masks unobservable future states but doesn't explicitly guarantee stationarity across `VOL_HIGH` vs `VOL_LOW` transitions.
3. **Hardware Acceleration Validation:** While ANE target metrics are defined in `TODO.md`, no empirical parity tests (`CPU vs ANE`) exist yet for the compiled binary graphs.

*Generated: 2026-03-12*
