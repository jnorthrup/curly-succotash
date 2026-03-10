# Plan

## Phase 1: Correct local truth

- [x] Record sibling `../autoresearch` as an adjacent repo with a concrete ownership surface.
- [x] Open a local track for adapting HRM harness output into an `autoresearch` handoff.

## Phase 2: Publish the handoff contract

- [x] Extend `coordination/coordinate.py emit-harness` so the generated harness JSON and codex include an explicit `autoresearch` adaptation contract.
- [x] Add focused unit coverage for the new adaptation contract helper.
- [x] Run focused verification for the generated harness and codex artifacts.
- [x] Restore `pytest` in the active Python environment, then rerun `coordination/tests/test_coordinate_harness.py`.

## Phase 3: Convert autoresearch instructions

- [x] Rewrite sibling `../autoresearch/program.md` so the autonomous loop consumes the HRM harness contract instead of generic LLM-pretraining-only guidance.
- [x] Verify the rewritten `program.md` preserves immutable surfaces (`prepare.py`) and bounded mutation rules.

## Phase 4: Publish concrete autoresearch setup fields

- [x] Extend the emitted `autoresearch_adaptation` contract with concrete run-setup fields for branch naming, results logging, baseline policy, and loop commit policy.
- [x] Cover the new setup fields in focused harness tests and regenerate the emitted harness artifact.

## Phase 5: Reconcile autoresearch instructions with emitted run setup

- [x] Update sibling `../autoresearch/program.md` so branch naming, results logging, baseline policy, and commit/rollback behavior match the emitted `autoresearch_adaptation.run_setup` contract.
- [x] Verify the rewritten instructions still preserve `prepare.py` immutability and keep routine experiment edits constrained to `train.py`.

## Acceptance

- `coordination/runtime/hrm_training_harness.json` gains a machine-readable `autoresearch_adaptation` block.
- `coordination/runtime/hrm_training_codex.md` mirrors the same handoff in operator-readable form.
- The contract names the sibling repo path, required harness inputs, mutation boundaries, and activation gate.

## Verification

- `python3 coordination/coordinate.py emit-harness`
- `python3` JSON inspection of `coordination/runtime/hrm_training_harness.json`
- `rg -n "Autoresearch Adaptation|repo_path: /Users/jim/work/autoresearch|hrm_training_harness_json" coordination/runtime/hrm_training_codex.md`
- `test -f /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_harness.json && test -f /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_codex.md && test -f /Users/jim/work/curly-succotash/coordination/runtime/hrm_swimlanes.dsel`
- `test -f /Users/jim/work/autoresearch/train.py && test -f /Users/jim/work/autoresearch/prepare.py`
- `git diff --name-only` in `/Users/jim/work/autoresearch` shows only `program.md`
- `./.venv/bin/python -m pytest coordination/tests/test_coordinate_harness.py`
- `./.venv/bin/python -m py_compile coordination/coordinate.py`
- `./.venv/bin/python coordination/coordinate.py emit-harness`
- JSON inspection confirms `coordination/runtime/hrm_training_harness.json` now includes `autoresearch_adaptation.run_setup`

## Blocker

- None. Root `.venv` now points at `backend/.venv`, and focused harness verification passes there.
