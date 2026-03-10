# Track Spec: HRM Ring-Agent API Integration

## Problem

The repo contains `backend/src/freqtrade_ring_agent.py` and unit tests for its internal behavior, but no backend route currently serves that path. The backlog still has open integration debt around HRM serving through the ring agent.

## Scope

This track covers:

- adding a minimal backend API surface for ring-agent request processing and artifact evaluation
- focused integration tests that exercise the API with realistic handoff and artifact payloads
- repo-local Conductor truth for this brownfield slice

This track does not cover:

- production traffic/load testing
- deployment rollback fault injection
- broader simulator or frontend changes

## Desired Outcome

- an operator can submit a ring-agent handoff payload through the backend API
- an operator can submit an artifact path for promotion evaluation through the same API surface
- focused tests prove that promotion state changes are visible to subsequent requests

## Cross-Repo Context

- `moneyfan/museum` remains the upstream source for handoff and fidelity artifact schemas.
- `freqtrade` already marks ring-agent integration complete on its side, so this repo's role is local serving-path validation rather than ownership transfer.
- `literbike` and `trikeshed` still have active transport/DSEL tracks; they inform boundaries but are not blockers for this API slice.

## Acceptance Signals

- focused backend tests pass for the new API path
- the active model version changes after a promotable artifact evaluation
- local `conductor/` truth exists for the active slice
