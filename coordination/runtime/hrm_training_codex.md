# HRM Training Codex

- generated_at: 2026-03-02T12:57:33
- duckdb_path: /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb
- pair_universe_path: /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt
- pair_universe_count: 7

## Stages

### convergence_4x4
- pair_width_target: 4
- pair_width_resolved: 4
- codec_outputs: 4
- effective_width_target: 4
- max_training_seconds: 1800
- bar_sequences_per_episode: 64
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 4`
- train_command: `python3 train.py --pretrain-only --timer-based --max-training-seconds 1800 --episodes 100000 --pair-width 4 --min-pair-width 4 --max-pair-width 4 --codec-outputs 4 --bar-sequences-per-episode 64 --min-bar-window 64 --max-bar-window 192 --candles-per-extent 1000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`

### hrm_24x24
- pair_width_target: 24
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 24
- max_training_seconds: 3600
- bar_sequences_per_episode: 100
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 24`
- train_command: `python3 train.py --pretrain-only --timer-based --max-training-seconds 3600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 100 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 1500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`

### hrm_24x64
- pair_width_target: 64
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 64
- max_training_seconds: 7200
- bar_sequences_per_episode: 120
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 64`
- train_command: `python3 train.py --pretrain-only --timer-based --max-training-seconds 7200 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 120 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`

### hrm_24x512
- pair_width_target: 512
- pair_width_resolved: 7
- codec_outputs: 24
- effective_width_target: 512
- max_training_seconds: 21600
- bar_sequences_per_episode: 160
- publish_swimlane_width_command: `python3 coordination/coordinate.py publish-swimlanes --min-effective-width 512`
- train_command: `python3 train.py --pretrain-only --timer-based --max-training-seconds 21600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 160 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt`
