# Track: ANE Model Candidate Definition

## Objective
Satisfy the TODO item "Define which HRM or proxy models are viable ANE candidates instead of guessing."

## Scope
- `coordination/runtime/ane_model_candidates.md`: Define the architectural constraints imposed by the Apple Neural Engine (ANE) compile budget and specifically nominate viable network architectures (e.g., standard MLPs, certain Transformer blocks without complex dynamic masking, specific convolution types).
- Document why highly dynamic architectures or those with unsupported ops (like exotic activation functions not native to CoreML) are non-viable.

## Stop Condition
The documentation artifact is committed locally and the track is marked complete in `TODO.md` and `conductor/tracks.md`.
