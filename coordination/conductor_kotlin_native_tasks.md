# Conductor Tasks: Curly to Kotlin-Native Placements

This file re-articulates Curly coordination tasks as Conductor-style atomic tasks,
mapped to Kotlin-native placements so runtime ownership can move into `trikeshed`.

## Task Atoms

1. `T1.data.diff_ingest`
- Goal: lazy differential archive ingest from `data.binance.vision`.
- Inputs: zipped monthly kline CSV archives.
- Output: deduped DuckDB candles + ingest registry.
- Kotlin-native placement:
  - `borg.trikeshed.duck.DiffDuckCursor`
  - `borg.trikeshed.grad.TradePairIoMux`
  - `borg.trikeshed.grad.HrmSwimlaneDsl` (manifest bridge)

1b. `T1b.acapulco.lineage`
- Goal: preserve the ta4j-excised candle ingestion lineage from:
  - `/Users/jim/work/mp-superproject/mp/acapulco.old/src/main/java/org/bereft/HistoryService.kt`
- Lineage anchors:
  - `fixOpaqueCsv(..., DataBinanceVision.klines)` candle normalization
  - `writeISAM(...)` durable cursor snapshot
  - `AssetModel.push(...)` cursor publication into the harnass event loop
- Rule: keep this path as historical contract guidance; no ta4j dependency reintroduction.

2. `T2.hrm.swimlane.materialize`
- Goal: instantiate HRM swimlanes from a concise DSEL contract.
- Inputs: `hrm_swimlanes.dsel` emitted by Curly coordination.
- Output: per-lane `CursorBridge` parameters + shared cursor surface.
- Kotlin-native placement:
  - `borg.trikeshed.grad.HrmSwimlaneDsl`
  - `borg.trikeshed.grad.TradePairIoMux.windup`

3. `T3.hrm.width.expand`
- Goal: expand effective width via repeated cube(square(2)) scaling.
- Rule: `(2^2)^3 = 64`; apply `64^k` until width >= required swimlanes.
- Output: `hrm_effective_width`, `hrm_growth_steps`.
- Kotlin-native placement:
  - `borg.trikeshed.grad.HrmSwimlaneDsl` (capacity metadata intake)
  - runtime planner in Curly coordinator (source of truth)

4. `T4.convergence.basket4`
- Goal: train convergence on a fixed 4-pair basket.
- Inputs: basket symbols, candle depth, fee/cost assumptions.
- Output: reproducible training episodes for the 24-swimlane codec.
- Kotlin-native placement:
  - upstream producer in Curly coordination
  - consumption in Moneyfan training runtime (Python today, Kotlin-ready manifest contract)

4b. `T4b.scale.stages`
- Goal: scale after convergence with explicit staged contracts.
- Stages:
  - `4x4`   (pairs/codecs convergence)
  - `24x24` (full codec panel baseline)
  - `24x64` (wider effective HRM width)
  - `24x512` (stress-scale target)
- Rule: keep BTC/ETH/SOL anchored in every stage's symbol universe.
- Output: codified stage commands in `hrm_training_harness.json` + `hrm_training_codex.md`.

5. `T5.ranker.weighted_coalesce`
- Goal: rank intents by motion + interest + holdings + trade frequency - cost.
- Inputs: weighted profile + flat fee fraction cost proxy.
- Output: stable rank score for top-k execution selection.
- Kotlin-native placement:
  - profile contract emitted by Curly coordination
  - consumer in Moneyfan runtime (Python now, portable to Kotlin ranker)

6. `T6.today.orchestrate`
- Goal: begin-today flow that syncs data, publishes manifests, runs training/services.
- Inputs: task list from `coordination/config.toml`.
- Output: deterministic launch order with PID tracking.
- Kotlin-native placement:
  - orchestration source stays in Curly coordinator
  - Kotlin runtime artifacts emitted for `trikeshed` consumption

## Placement Summary

- Curly remains orchestration source of truth (`coordination/coordinate.py`).
- Trikeshed becomes Kotlin-native execution surface for swimlane DSEL + cursor grad windup.
- Moneyfan consumes convergence/ranker contracts for training and live ranking.
