# HRM Training Codex

- generated_at: 2026-03-10T15:40:30
- duckdb_path: /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb
- pair_universe_path: /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt
- pair_universe_count: 7

## Operating Posture

- baseline_trading_status: active_now
- baseline_trading_mode: deterministic_paper
- baseline_rule: Do not wait on HRM milestones to start capturing paper-trading opportunities.
- hrm_current_role: shadow
- hrm_role_rule: HRM gathers evidence in shadow mode until it earns authority.

### HRM Promotion Ramp
- shadow
- veto_only
- size_capped
- primary

### HRM Promotion Requirements
- synthetic convergence on cheap tasks such as sine and feature+1
- market forecasting beats naive baselines on walk-forward data
- cost-aware paper validation remains positive through the promotion gate

## Autoresearch Adaptation

- status: ready_when_harness_exists
- objective: adapt HRM training evidence into bounded autoresearch experiments
- activation_gate: only begin once the staged HRM harness, codex, and swimlane artifacts exist
- repo_path: /Users/jim/work/autoresearch
- program_path: /Users/jim/work/autoresearch/program.md
- train_entrypoint: /Users/jim/work/autoresearch/train.py

### Autoresearch Harness Inputs
- hrm_training_harness_json: /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_harness.json
- hrm_training_codex_md: /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_codex.md
- hrm_swimlane_dsel: /Users/jim/work/curly-succotash/coordination/runtime/hrm_swimlanes.dsel

### Autoresearch Experiment Focus
- cheap synthetic convergence before market-facing claims
- readiness failures map to explicit experiment themes
- preserve HRM promotion gates and shadow-first posture

### Autoresearch Run Setup

#### Branch Naming Policy
- pattern: `exp/{stage}/{theme}/{YYYYMMDD}`
- example: `exp/convergence_4x4/sine_wider/20260308`
- rule: branch name encodes source stage, mutation theme, and creation date

#### Results Log
- path: `/Users/jim/work/curly-succotash/coordination/runtime/autoresearch_results.jsonl`
- format: jsonl

##### Results Log Schema
- experiment_id: string: unique identifier for the experiment run
- branch: string: git branch name
- stage: string: HRM stage being adapted (e.g., convergence_4x4)
- theme: string: mutation theme or readiness gap addressed
- timestamp: string: ISO8601 completion time
- metrics: {'validation_loss': 'float: final validation loss', 'synthetic_milestone_results': 'object: per-task outcomes'}
- verdict: string: promote|rollback|inconclusive
- evidence_path: string: path to detailed metrics artifact

#### Baseline Recording Policy
- record_baseline_on: each successful stage completion in HRM harness

##### Baseline Artifacts
- `validation_loss_curve.json`
- `synthetic_milestone_evidence.json`
- `stage_completion_certificate.json`

- comparison_rule: autoresearch experiments must beat or match baseline validation loss without violating readiness gates

#### Loop Commit/Rollback Policy

##### Commit Condition
- experiment verdict is 'promote' AND baseline comparison passes AND readiness gates remain satisfied

##### Rollback Condition
- experiment verdict is 'rollback' OR validation loss degrades OR readiness gate violation detected

##### Actions
- commit: merge branch to main, update harness baseline reference
- rollback: abandon branch, log failure evidence, preserve for postmortem
- inconclusive: preserve branch for manual review, extend experiment budget if theme is high-priority

#### First Handoff
- source_stage: convergence_4x4
- goal: use the smallest harness stage as the baseline adaptation target
- success_signal: candidate experiments reduce validation loss without violating readiness gates
##### First Gate Set
- M0_identity
- M1_sine

## Kotlin Autoresearch Adaptation

- status: ready_when_harness_exists
- objective: adapt HRM training evidence into a native-first Kotlin autoresearch harness
- activation_gate: only begin once the staged HRM harness, codex, and swimlane artifacts exist
- runtime_route: kilo
- repo_path: /Users/jim/work/TrikeShed
- mutable_training_surface: /Users/jim/work/TrikeShed/src/posixMain/kotlin/borg/trikeshed/autoresearch/MutableAutoresearchExperiment.kt
- native_entrypoint: borg.trikeshed.autoresearch.autoresearchNativeMain
- jvm_scaffold_surface: src/jvmTest/kotlin/borg/trikeshed/autoresearch

### Kotlin Harness Inputs
- hrm_training_harness_json: /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_harness.json
- hrm_training_codex_md: /Users/jim/work/curly-succotash/coordination/runtime/hrm_training_codex.md
- hrm_swimlane_dsel: /Users/jim/work/curly-succotash/coordination/runtime/hrm_swimlanes.dsel

### Kotlin Experiment Focus
- native-first synthetic convergence before market-facing claims
- M0_identity and M1_sine are the first gate set for the convergence_4x4 handoff
- preserve JVM parity scaffolding until native compilation and smoke are routine

### Kotlin Run Setup

#### Branch Naming Policy
- pattern: `exp/{stage}/{theme}/{YYYYMMDD}`
- example: `exp/convergence_4x4/native_identity/20260310`
- rule: branch name encodes source stage, mutation theme, and creation date

#### Results Log
- path: `/Users/jim/work/curly-succotash/coordination/runtime/kotlin_autoresearch_results.jsonl`
- format: jsonl

##### Results Log Schema
- experiment_id: string: unique identifier for the experiment run
- branch: string: git branch name
- stage: string: HRM stage being adapted (e.g., convergence_4x4)
- theme: string: mutation theme or readiness gap addressed
- timestamp: string: ISO8601 completion time
- metrics: {'validation_loss': 'float: final validation loss', 'synthetic_milestone_results': 'object: per-task outcomes'}
- verdict: string: promote|rollback|inconclusive
- evidence_path: string: path to detailed metrics artifact

#### Baseline Recording Policy
- record_baseline_on: each successful stage completion in HRM harness

##### Baseline Artifacts
- `validation_loss_curve.json`
- `synthetic_milestone_evidence.json`
- `stage_completion_certificate.json`

- comparison_rule: autoresearch experiments must beat or match baseline validation loss without violating readiness gates

#### Loop Commit/Rollback Policy

##### Commit Condition
- experiment verdict is 'promote' AND baseline comparison passes AND readiness gates remain satisfied

##### Rollback Condition
- experiment verdict is 'rollback' OR validation loss degrades OR readiness gate violation detected

##### Actions
- commit: merge branch to main, update harness baseline reference
- rollback: abandon branch, log failure evidence, preserve for postmortem
- inconclusive: preserve branch for manual review, extend experiment budget if theme is high-priority

#### First Handoff
- source_stage: convergence_4x4
- goal: use the smallest harness stage as the native-first Kotlin baseline adaptation target
- success_signal: native synthetic experiments clear identity and sine gates while preserving the shared JSONL artifact contract
##### First Gate Set
- M0_identity
- M1_sine

## Readiness Contract

### Failure States
- FAIL_ARCH: cheap synthetic competence does not converge; architecture or implementation is suspect
- FAIL_SCALE: task is learnable but current width, depth, or optimizer budget is mis-scaled
- FAIL_TRANSFER: synthetic competence does not beat naive baselines on market forecasting tasks
- FAIL_TRADING: forecasting competence does not survive cost-aware paper trading

### Synthetic Milestones
- M0_identity: tasks=x_to_x,scalar_1x1_to_16x16,ane_scalar_parity | expected=near_zero
- M1_sine: tasks=single_sine,mixed_sine,noisy_sine,piecewise_sine | expected=near_zero_or_better_than_baseline
- M2_feature_plus_1: tasks=feature_plus_1 | expected=beats_persistence_and_ema
- M3_feature_plus_n: tasks=feature_plus_1_2_4_8 | expected=graceful_multi_horizon_degradation

### Market Gates
- M4_walk_forward: expected=beats_naive_forecasting_baselines
- M5_paper_promotion: expected=positive_cost_aware_shadow_edge

## Stages

### convergence_4x4_w4 (4 pairs, effective width 4)
- stage_name: convergence_4x4_w4
- pair_width_target: 4
- pair_width_resolved: 4
- codec_outputs: 4
- effective_width_target: 4
- max_training_seconds: 1800
- bar_sequences_per_episode: 64
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 4`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 1800 --episodes 100000 --pair-width 4 --min-pair-width 4 --max-pair-width 4 --codec-outputs 4 --bar-sequences-per-episode 64 --min-bar-window 64 --max-bar-window 192 --candles-per-extent 1000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`

### hrm_24x24_w24 (capped at 7/24 pairs, effective width 24)
- stage_name: hrm_24x24_w24
- pair_width_target: 24
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 24
- max_training_seconds: 3600
- bar_sequences_per_episode: 100
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 24`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 3600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 100 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 1500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage

### hrm_24x64_w64 (capped at 7/64 pairs, effective width 64)
- stage_name: hrm_24x64_w64
- pair_width_target: 64
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 64
- max_training_seconds: 7200
- bar_sequences_per_episode: 120
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 64`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 7200 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 120 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage

### hrm_24x512_w512 (capped at 7/512 pairs, effective width 512)
- stage_name: hrm_24x512_w512
- pair_width_target: 512
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 512
- max_training_seconds: 21600
- bar_sequences_per_episode: 160
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 512`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 21600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 160 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage
