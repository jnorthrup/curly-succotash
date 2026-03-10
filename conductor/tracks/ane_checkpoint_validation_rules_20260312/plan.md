# Track: ANE Checkpoint Validation Rules

## Objective
Satisfy the TODO item "Validate checkpoint save, resume, and restart behavior against the ANE compile budget."

## Scope
- `coordination/runtime/ane_checkpointing_rules.md`: Create documentation that asserts the rules for taking intermediate state out of MLX, serializing it, and restarting an ANE compile task without losing momentum or blowing the graph compilation memory limit. This is purely procedural doctrine since the actual hardware compiler (CoreML tools) lives out of tree.

## Stop Condition
The rule definition exists and is explicitly tied to the failure recovery metrics defined in `ane_artifact_formats.json`.
