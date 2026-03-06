# Cross-Workspace Coordinator

This coordinator links:
- `/Users/jim/work/moneyfan`
- `/Users/jim/work/freqtrade`
- `/Users/jim/work/trikeshed`
- `/Users/jim/work/curly-succotash`
- `/Users/jim/work/ANE`

## Core Contract

The training contract is enforced in `coordination/config.toml`:
- HRM predicts **24 agent swimlanes**
- swimlane contract requires **grid + volatile_breakout** archetype representation
- world-model targets include **raw agent signals + indicator kernels**
- latent transform is **hyperbolic**
- models train with explicit **real candle depth**
- horizon uses **hyperbolic compression**
- volatility learning is **time-unit invariant**
- orchestration assumes **map-reduce grouping** and **Dykstra countercoin routing**
- executive routing objective is **slime-mold-style sparse countercoin graph flow**
- when bulls occupy countercoins, **leaf coins draw unilaterally toward energy events**
- when countercoins trail bull coins, routing learns an **emergent trade-cost discount policy**

## Why this exists

1. Keep `data.binance.vision` ingest lazy and differential.
   This is the training gate: stochastic epochs only stream from imported DuckDB candles.
   Ingest mode is explicit: `permanent` or `tmp`, and DuckDB/cache always resolve to one mode only.
2. Publish strategy-specific safety orders (not one-size-fits-all risk controls).
3. Publish swimlane archetype manifests in JSON + Kotlin DSEL.
4. Start ML/HRM + infra workflows in one command.
5. Keep the Kotlingrad + Cursor nexus explicit and verifiable.

## Commands

```bash
# Show contract + workspace + task status
python3 coordination/coordinate.py status

# Sync Binance monthly zip archives into DuckDB with differential insert
python3 coordination/coordinate.py sync-binance --max-archives 120

# Tmp-only ingest surface (cache + DuckDB under /tmp session root)
python3 coordination/coordinate.py sync-binance --storage-mode tmp --max-archives 120

# Publish strategy drawdown/safety-order profiles to all workspaces
python3 coordination/coordinate.py publish-risk

# Publish 24-lane HRM archetype manifest (JSON + DSEL)
python3 coordination/coordinate.py publish-swimlanes
python3 coordination/coordinate.py publish-swimlanes --min-effective-width 512

# Build Binance connectome universe (BTC/ETH/SOL anchors, optional script feeder)
python3 coordination/coordinate.py build-connectome

# Emit staged harness + codex (4x4 -> 24x24 -> 24x64 -> 24x512)
python3 coordination/coordinate.py emit-harness

# Validate Kotlingrad + Cursor nexus across all linked repos
python3 coordination/coordinate.py nexus-status

# Preview full "start today" run (dry-run by default)
python3 coordination/coordinate.py begin-today

# Execute full "start today" run
python3 coordination/coordinate.py begin-today --execute

# Include Python minimum adapter/services only when needed
python3 coordination/coordinate.py begin-today --include-python
python3 coordination/coordinate.py begin-today --execute --include-python

# Execute full run with tmp-only Binance storage
python3 coordination/coordinate.py begin-today --execute --storage-mode tmp

# Execute full run but skip harness generation
python3 coordination/coordinate.py begin-today --execute --skip-harness
```

## Output artifacts

- Risk profile JSONs:
  - `/Users/jim/work/moneyfan/runtime/strategy_risk_profiles.json`
  - `/Users/jim/work/freqtrade/user_data/strategy_risk_profiles.json`
  - `/Users/jim/work/curly-succotash/coordination/runtime/strategy_risk_profiles.json`
- Swimlane manifests:
  - `/Users/jim/work/curly-succotash/coordination/runtime/hrm_swimlanes.json`
  - `/Users/jim/work/curly-succotash/coordination/runtime/hrm_swimlanes.dsel`
  - `/Users/jim/work/trikeshed/runtime/hrm_swimlanes.dsel`
- Session PID/log tracking for background tasks:
  - `/Users/jim/work/curly-succotash/coordination/runtime/session-*/`
- Connectome/harness artifacts:
  - `/Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_universe.json`
  - `/Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
  - `/Users/jim/work/curly-succotash/coordination/runtime/hrm_training_harness.json`
  - `/Users/jim/work/curly-succotash/coordination/runtime/hrm_training_codex.md`
  - `/Users/jim/work/curly-succotash/coordination/runtime/run_hrm_harness.sh`

## Kotlingrad-Cursor Nexus

The concrete nexus chain is:

1. `hrm_swimlanes.json` (24 lanes) in `freqtrade/user_data`
2. `scripts/generate_kotlingrad_swimlane_expressions.py`
3. `GeneratedHrmKotlingradExpressions.kt` + `hrm_kotlingrad_expressions.json`
4. `CompositionalExpressionRegistry.resolve(...)`
5. `DuckMuxer.getAction(sym, expressionId)` cursor-expression scoring
6. Freqtrade bridge/gateway dispatch via `trikeshed_get_action_expr`
7. Trikeshed `DiffDuckCursor` + `TradePairIoMux` (`pancakeKotlingrad` symbolic pancake + cursor series folds)
8. Trikeshed `BacktradingCoroutineConductor` channelized jobs (`candleIngress -> intra/signal -> executiveEgress`)

`nexus-status` verifies all links above and fails fast if any are missing.
