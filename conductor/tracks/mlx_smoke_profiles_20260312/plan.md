# Track: MLX Smoke Profiles

## Objective
Satisfy the TODO item "Produce bounded MLX smoke profiles that are fast enough for frequent iteration."
Local model training on macOS leveraging the MLX framework requires predefined hyperparameter groupings that limit compute time for development iteration (e.g., pipeline smoke tests, synthetic competency convergence, and bounded market ingestion).

## Scope
- `coordination/runtime/mlx_smoke_profiles.json`: Create a definition containing `mlx_micro_smoke`, `mlx_fast_convergence`, and `mlx_bounded_market` profiles. Each defines maximum iteration counts, small network widths, and bounded datasets to constrain execution times from 5 to 300 seconds.

## Stop Condition
The JSON artifact is available in the runtime coordination directory and accurately reflects the bounds needed for rapid MLX training checks. Update `TODO.md` and `conductor/tracks.md`.
