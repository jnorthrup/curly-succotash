# Spec

## Slice

Publish a bounded adaptation contract between the local HRM harness artifacts and sibling `../autoresearch`.

## Inputs

- `coordination/runtime/hrm_training_harness.json`
- `coordination/runtime/hrm_training_codex.md`
- `coordination/runtime/hrm_swimlanes.dsel`
- sibling repo `/Users/jim/work/autoresearch`

## Contract requirements

- Do not make `autoresearch` execution implicit; emit the handoff directly in local runtime artifacts.
- Preserve the current HRM readiness gates and shadow-first posture.
- Keep `prepare.py` fixed and limit the experiment mutation surface to `program.md` and `train.py`.
- Start from the smallest harness stage (`convergence_4x4`) as the first adaptation target.

## Verification

- Focused pytest coverage in `coordination/tests/test_coordinate_harness.py`
