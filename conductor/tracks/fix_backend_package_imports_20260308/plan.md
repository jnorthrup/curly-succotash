# Track: Fix backend package imports for tests

## Problem

Several backend unit tests import modules using
`from backend.src.xxx import ...`, but the `backend` directory
lacks an `__init__.py` package initializer. As a result pytest
fails during test collection with `ModuleNotFoundError: No module
named 'backend'` unless the workspace root is manually added to
`PYTHONPATH`.

This friction makes local development painful and hides the
intended package structure; a simple package initializer should
resolve the imports and unblock us from running the full test
suite with a normal `PYTHONPATH` configuration.

## Scope

- Add `backend/__init__.py` to turn the directory into a proper
  package.
- Ensure tests still run from the workspace root with
  `PYTHONPATH=.`, updating any documentation if necessary.
- No external dependencies or cross-repo changes.

## Acceptance

- A new `backend/__init__.py` file exists (may export helpers but
  can be empty with a docstring).
- Running `PYTHONPATH=. pytest backend/src/tests/test_daily_runbook.py -q`
  (and optionally the whole test suite) successfully imports the
  `backend` package and executes without import errors. For the
  *entire* backend suite the workspace root alone is not enough;
  include the backend directory in `PYTHONPATH` (e.g.
  `PYTHONPATH=backend:. pytest -q`) so that tests which import
  `src.*` can locate the modules in `backend/src`.
- The track plan is recorded under
  `conductor/tracks/fix_backend_package_imports_20260308/plan.md`.

## Delegation scaffold (literal) — print BEFORE launching slaves

DELEGATED WORKER LAUNCH:
  WORKER_LIMITS=2
  BOUNDED_CORPUS="backend/__init__.py backend/src/tests/"
  STOP_CONDITION="one slice or first blocker"
  RUNTIME_ROUTE="local-venv:python3 -m pytest -q"
  Worker A: "Create `backend/__init__.py` with appropriate package
  docstring or exports; stop after one slice or first blocker"
  Worker B: "Verify tests import correctly under workspace root using
  `PYTHONPATH=.`; run at least `test_daily_runbook.py`; stop after one
  slice or first blocker"

Required worker rendezvous payload (each worker must return):
- changed files (paths)
- verification command(s)
- actual result: passed | failed | blocked
- evidence/artifact paths inspected
- remaining blocker (if any)

## Owner

Conductor (master) will author the initializer and run the
verification command. Any further test-suite abnormalities will be
investigated by master or delegated as a follow-on track.
