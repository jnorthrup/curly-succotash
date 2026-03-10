# Track: Curate OOS Validation Dataset

## Objective
Satisfy the TODO item "Curate a multi-regime validation dataset with non-overlapping OOS governance."
Provide a JSON-driven split policy to rigorously divide historical ingestion data into disjoint train, calibration, and hold-out test periods that all individually hit regime coverage requirements. Also provide an operator script to run the curation.

## Scope
- `coordination/runtime/oos_governance_policy.json`: Create an explicit policy with hard date bounds separating Q1-Q3 2023 for training, Q3-Q4 2023 for calibration, and Q4 2023 - Q1 2024 for testing. 
- `backend/scripts/curate_oos_dataset.py`: Create script that uses `OOSplitter` to apply the policy over sample data and generate a JSON dataset manifest (`logs/oos_validation/curated_dataset_manifest.json`).

## Stop Condition
`python3 backend/scripts/curate_oos_dataset.py` passes without `ValueError` regarding overlapping bounds and correctly produces the manifest. Update `TODO.md` and `conductor/tracks.md`.
