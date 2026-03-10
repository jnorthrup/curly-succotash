# Plan

## Phase 1: Restore repo-local truth

- [x] Recreate the minimal local `conductor/` workflow, product, and track files.
- [x] Record the bounded corpus and acceptance signals for the ring-agent API slice.
- [x] Coalesce sibling-repo conductor tracks into a local-only context snapshot.

## Phase 2: Serve the ring-agent path

- [x] Add a backend route for processing HRM ring-agent payloads.
- [x] Add a backend route for evaluating HRM artifacts and updating active version state.
- [x] Add a backend route for reading current ring-agent status.

## Phase 3: Focused verification

- [x] Add integration tests that drive the new API surface end-to-end.
- [x] Run focused backend verification for the changed route and test corpus.
- [x] Reconcile local track truth with the verified result.


**Verification:** On 2026‑03‑07 the local venv ran `pytest backend/src/tests/test_hrm_ring_api.py` and all tests passed. API routes `/api/hrm/ring/status`, `/process`, and `/evaluate` were exercised, confirming promotion and version reuse. Track truth has been updated accordingly.
