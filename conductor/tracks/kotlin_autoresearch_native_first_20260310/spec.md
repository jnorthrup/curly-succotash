# Spec

## Slice

Publish a native-first Kotlin autoresearch harness contract in Curly and land the first synthetic-only TrikeShed runtime that consumes it.

## Inputs

- `coordination/runtime/hrm_training_harness.json`
- `coordination/runtime/hrm_training_codex.md`
- `coordination/runtime/hrm_swimlanes.dsel`
- sibling repo `/Users/jim/work/TrikeShed`
- reference repo `/Users/jim/work/autoresearch`

## Contract requirements

- Add a `kotlin_autoresearch_adaptation` block beside `autoresearch_adaptation`.
- Record `runtime_route: kilo` and point the Kotlin contract at `/Users/jim/work/TrikeShed`.
- Keep the first handoff on `convergence_4x4` with first gate set `M0_identity` + `M1_sine`.
- Preserve the single mutable-surface doctrine for routine experiments.
- Keep this slice synthetic-only; no DuckDB market loop, ANE path, or freqtrade runtime ownership.

## Verification

- Focused pytest coverage in `coordination/tests/test_coordinate_harness.py`
- Regenerated harness artifacts show both adaptation blocks
- TrikeShed JVM tests and native smoke validate the Kotlin harness surface
