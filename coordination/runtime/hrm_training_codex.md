# HRM Training Codex

- generated_at: 2026-03-06T03:34:58
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

## Stages

### convergence_4x4 (4 pairs, effective width 4)
- stage_name: convergence_4x4
- pair_width_target: 4
- pair_width_resolved: 4
- codec_outputs: 4
- effective_width_target: 4
- max_training_seconds: 1800
- bar_sequences_per_episode: 64
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 4`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 1800 --episodes 100000 --pair-width 4 --min-pair-width 4 --max-pair-width 4 --codec-outputs 4 --bar-sequences-per-episode 64 --min-bar-window 64 --max-bar-window 192 --candles-per-extent 1000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`

### hrm_24x24 (capped at 7/24 pairs, effective width 24)
- stage_name: hrm_24x24
- pair_width_target: 24
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 24
- max_training_seconds: 3600
- bar_sequences_per_episode: 100
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 24`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 3600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 100 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 1500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage

### hrm_24x64 (capped at 7/64 pairs, effective width 64)
- stage_name: hrm_24x64
- pair_width_target: 64
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 64
- max_training_seconds: 7200
- bar_sequences_per_episode: 120
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 64`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 7200 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 120 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage

### hrm_24x512 (capped at 7/512 pairs, effective width 512)
- stage_name: hrm_24x512
- pair_width_target: 512
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 512
- max_training_seconds: 21600
- bar_sequences_per_episode: 160
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 512`
- train_command: `python3 museum/train.py --pretrain-only --timer-based --max-training-seconds 21600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 160 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
- note: pair width capped by current pair universe size; do not interpret this as a full-width stage
