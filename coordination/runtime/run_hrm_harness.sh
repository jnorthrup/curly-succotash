#!/usr/bin/env bash
set -euo pipefail

cd /Users/jim/work/moneyfan

echo "[HARNESS] Stage convergence_4x4"
cd /Users/jim/work/curly-succotash
python3 coordination/coordinate.py publish-swimlanes --min-effective-width 4
cd /Users/jim/work/moneyfan
python3 train.py --pretrain-only --timer-based --max-training-seconds 1800 --episodes 100000 --pair-width 4 --min-pair-width 4 --max-pair-width 4 --codec-outputs 4 --bar-sequences-per-episode 64 --min-bar-window 64 --max-bar-window 192 --candles-per-extent 1000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt

echo "[HARNESS] Stage hrm_24x24"
cd /Users/jim/work/curly-succotash
python3 coordination/coordinate.py publish-swimlanes --min-effective-width 24
cd /Users/jim/work/moneyfan
python3 train.py --pretrain-only --timer-based --max-training-seconds 3600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 100 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 1500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt

echo "[HARNESS] Stage hrm_24x64"
cd /Users/jim/work/curly-succotash
python3 coordination/coordinate.py publish-swimlanes --min-effective-width 64
cd /Users/jim/work/moneyfan
python3 train.py --pretrain-only --timer-based --max-training-seconds 7200 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 120 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2000 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt

echo "[HARNESS] Stage hrm_24x512"
cd /Users/jim/work/curly-succotash
python3 coordination/coordinate.py publish-swimlanes --min-effective-width 512
cd /Users/jim/work/moneyfan
python3 train.py --pretrain-only --timer-based --max-training-seconds 21600 --episodes 100000 --pair-width 7 --min-pair-width 7 --max-pair-width 7 --codec-outputs 24 --bar-sequences-per-episode 160 --min-bar-window 64 --max-bar-window 256 --candles-per-extent 2500 --ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 --learning-rate 1e-4 --candle-source duckdb_sequences_import --duckdb-corpus-path /Users/jim/work/moneyfan/data/binance/hrm_data.duckdb --pair-universe-file /Users/jim/work/curly-succotash/coordination/runtime/binance_connectome_symbols.txt
