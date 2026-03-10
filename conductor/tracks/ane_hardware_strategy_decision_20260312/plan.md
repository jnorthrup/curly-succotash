# Track: ANE Hardware Strategy Decision

## Objective
Satisfy the TODO item "Decide whether ANE is a research sidecar, a training accelerator, or a dead end for the current trading milestones."

## Scope
- `coordination/runtime/ane_strategy_decision.md`: Create an architectural decision record (ADR) that formally classifies the Apple Neural Engine (ANE) as a "Research Sidecar" rather than the primary training accelerator. The reasoning is based on the extreme rigidities of Ahead-of-Time (AOT) compilation, static shape requirements, and lack of mature support for the dynamic computational graphs needed in the immediate HRM RL/trading milestones. MLX (via GPU) is nominated as the primary training accelerator.

## Stop Condition
The ADR is committed locally and the track is marked complete in `TODO.md` and `conductor/tracks.md`.
