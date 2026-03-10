# Track: Exchange Integrations — Binance + Coinbase

## Problem

*Status: ✅ completed 2026‑03‑07*

The repo contains exchange client stubs (`binance_client.py`, `coinbase_client.py`) and trading logic, but there is no
complete backend integration wiring and focused integration tests. This prevents end-to-end operator workflows for
promoting/trading artifacts.

## Scope

- Implement `Binance` and `Coinbase` client wiring in `backend/src/` (clients + minimal route registration in `main.py`).
- Add focused integration tests that exercise the new routes and basic handshake with the clients.
- No cross-repo changes; keep work limited to the bounded corpus below.

## Acceptance

- New or updated files under `backend/src/` implement clients and register routes.
- Focused integration tests live in `backend/src/tests/test_exchanges.py` and pass locally.
- Master verifies changed files and runs verification commands.

## Delegation scaffold (literal) — print BEFORE launching slaves

DELEGATED WORKER LAUNCH:
  WORKER_LIMITS=2
  BOUNDED_CORPUS="backend/src/binance_client.py backend/src/coinbase_client.py backend/src/main.py backend/src/tests/test_exchanges.py"
  STOP_CONDITION="one slice or first blocker"
  RUNTIME_ROUTE="local-venv:python3 -m pytest backend/src/tests/test_exchanges.py -q"
  Worker A: "Implement Binance client + register route `/api/exchanges/binance`; update `backend/src/main.py` wiring; stop after one slice or first blocker"
  Worker B: "Implement Coinbase client + register route `/api/exchanges/coinbase`; add integration tests in `backend/src/tests/test_exchanges.py`; stop after one slice or first blocker"

Required worker rendezvous payload (each worker must return):
- changed files (paths)
- verification command(s)
- actual result: passed | failed | blocked
- evidence/artifact paths inspected
- remaining blocker (if any)

## Owner

Conductor (master) — assigns workers and verifies authenticity of returned artifacts.

## Notes

This track intentionally keeps the scope narrow: clients implement minimal functionality to satisfy the tests (connectivity
stubs, config read, and response shaping). Production hardening and performance are out of scope for this slice.
