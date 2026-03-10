# Cross-Repo Track Context

This file is a local context snapshot for `curly-succotash`.
It is not the source of truth for sibling repos; each sibling repo keeps its own `conductor/` truth.

Snapshot date: 2026-03-08

## Repo Snapshot

### `../autoresearch`

- Cloned locally at `/Users/jim/work/autoresearch`.
- Product surface is intentionally small: `program.md` supplies the autonomous-research instructions, `train.py` is the mutable training loop, and `prepare.py` stays fixed.
- The repo expects bounded experiment iteration against a fixed training metric rather than broad multi-file refactors.

Local implication for `curly-succotash`:

- the generated HRM harness should export a concrete handoff contract for `autoresearch`, not just assume an operator will infer it
- local coordination owns the bridge artifact; `autoresearch` owns the actual experiment loop once activated

### `../ANE`

- No `conductor/tracks.md` or `conductor/tracks/` found.
- Treat ANE work as missing repo-local track truth from the perspective of this repo.

### `../literbike` (`lite*bike`)

Open or in-progress tracks:

- `CAS Lazy N-Way Gateway Projections`
- `QUIC Proto RFC Comment-Docs Discipline`
- `Port Kotlin QUIC (Full Packet Processing from Trikeshed)`:
  - marked as the agent-harness critical path
  - still blocking on connection lifecycle management and stream multiplexing
- `Port Kotlin IPFS (Complete DHT Client from Trikeshed)`
- `Integration Tests (End-to-End QUIC + DHT + DuckDB)`

Local implication for `curly-succotash`:

- transport/runtime integration below the HRM serving layer is still moving in `literbike`
- local simulator/ring-agent API work should not claim transport completeness

### `../freqtrade`

Most listed tracks are closed.
Relevant active track:

- `Pretesting + Paper Testing Drawdown Guardrails with Unified Kotlingrad DSEL`

Relevant closed tracks:

- `HRM Model Integration for Ring Agent (ALPHA CRITICAL PATH)`
- `HRM Stochastic Paper Trading Integration`

Local implication for `curly-succotash`:

- `freqtrade` already considers the ring-agent integration track complete on its side
- remaining local work here is validation and serving-path proof, not re-owning `freqtrade` product truth

### `../moneyfan`

Top-level `conductor/` truth is absent, but legacy truth exists under `../moneyfan/museum/conductor/`.

Open or in-progress legacy tracks:

- `Implement a profit-driven MLX HRM training loop`
- `Freqtrade offload + HRM fidelity audit loop`
- `Pretesting + Paper Testing Drawdown Source Artifacts`
- `Runtime Drawdown Guardrails and Rollback-Safe Execution`

Local implication for `curly-succotash`:

- handoff payloads and fidelity artifacts consumed by the local ring-agent path originate from `moneyfan`
- local API tests should preserve those schemas rather than invent new ones

### `../trikeshed`

Closed track:

- `Freqtrade Retirement and Feature Extraction`

In-progress track:

- `Unified Kotlingrad DSEL for Pretesting + Paper Testing Drawdown`

Local implication for `curly-succotash`:

- DSEL and drawdown contract work is still stabilizing upstream
- current local slice should avoid binding new backend routes to unfinished Kotlin-side DSEL semantics

## Current Slice Guidance

- Keep the active `curly-succotash` slice centered on ring-agent API serving and verification.
- Reuse `moneyfan` handoff and fidelity artifact schemas as the compatibility anchor.
- Treat `literbike` transport and `trikeshed` DSEL work as adjacent dependencies, not blockers for the current backend API slice.
- Do not edit sibling repos as part of this context coalescing pass.
