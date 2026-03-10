# Product Surface

- `backend/` owns the simulator API, replay, HRM shadow/promotion, and Freqtrade-facing adapters.
- `coordination/` owns runtime manifests, operator codex output, and orchestration helpers.
- `frontend/` owns the paper-trading dashboard.

Current brownfield priority is validating the HRM-to-Freqtrade serving path with repo-local tests and operator-visible surfaces.
