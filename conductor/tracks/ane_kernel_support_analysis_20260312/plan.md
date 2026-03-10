# Track: ANE Kernel Support Analysis

## Objective
Satisfy the TODO item "Identify which kernels are missing for HRM-like workloads versus transformer Stories110M."

## Scope
- `coordination/runtime/ane_kernel_analysis.md`: Create an analysis document comparing the standard `Stories110M` transformer blocks (which compile cleanly to ANE) against the specialized requirements of a trading Hierarchical Risk Model (HRM). Explicitly document the missing or fallback-prone kernels required for HRM workloads (e.g., dynamic masking, causal attention with dynamic KV caching, specialized loss objectives, and non-standard activations).

## Stop Condition
The analysis document is committed locally and the track is marked complete in `TODO.md` and `conductor/tracks.md`.
