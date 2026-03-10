# Track: ANE Artifact Formats Definition

## Objective
Satisfy the TODO item "Define artifact formats that can move between ANE experiments and the main training pipeline."

## Scope
- `coordination/runtime/ane_artifact_formats.json`: Create a schema definition dictating how model weights and training state are exported from MLX to CoreML/ANE, and how evaluation metrics flow back into the moneyfan pipeline. This provides the contract for `../autoresearch` or other sibling repos to serialize their models without breaking `curly-succotash` evaluation loops.

## Stop Condition
The JSON schema definition is present in the coordination directory and tracked in `TODO.md` and `conductor/tracks.md`.
