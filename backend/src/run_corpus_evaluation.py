"""
Run Corpus Evaluation - Evaluate strategies against a defined data corpus.

Uses the ReplayEngine, AdversarialOrchestrator, and EvaluationHarness to
systematically test strategies against a target data corpus.
"""

import os
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from .models import Timeframe, TimeframeUtils
from .binance_client import BinanceArchiveClient, BinanceArchiveConfig
from .data_corpus import get_corpus_config, CorpusTarget
from .evaluation import EvaluationHarness
from .strategies import create_all_strategies, StrategyConfig
from .adversarial_agents import create_random_orchestrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("corpus_evaluation")


def parse_args():
    parser = argparse.ArgumentParser(description="Run evaluation against a data corpus")
    parser.add_argument("--corpus", type=str, default="v1_minimal", help="Name of the corpus target")
    parser.add_argument("--intensity", type=float, default=0.3, help="Adversarial intensity (0.0-1.0)")
    parser.add_argument("--output-dir", type=str, default="evaluation_results", help="Directory to save results")
    parser.add_argument("--duckdb-path", type=str, help="Override DuckDB path")
    parser.add_argument("--no-adversarial", action="store_true", help="Disable adversarial perturbations")
    return parser.parse_args()


def run_evaluation():
    args = parse_args()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Load corpus configuration
    corpus = get_corpus_config(args.corpus)
    logger.info(f"[EVAL] Target Corpus: {corpus.name} ({corpus.description})")
    logger.info(f"[EVAL] Symbols: {corpus.symbols}")
    logger.info(f"[EVAL] Timeframes: {corpus.timeframes}")

    # Initialize client
    client_config = BinanceArchiveConfig()
    if args.duckdb_path:
        client_config.duckdb_path = args.duckdb_path
    client = BinanceArchiveClient(client_config)

    # Create strategies
    strat_config = StrategyConfig(initial_capital=10000.0)
    strategies = create_all_strategies(strat_config)

    # Create orchestrator if enabled
    orchestrator = None
    if not args.no_adversarial:
        orchestrator = create_random_orchestrator(seed=42, intensity=args.intensity)
        logger.info(f"[EVAL] Adversarial enabled (intensity={args.intensity})")
    else:
        logger.info("[EVAL] Adversarial disabled")

    # Initialize harness
    harness = EvaluationHarness(client, strategies, orchestrator)

    # Run evaluations
    all_results = {
        "corpus_name": corpus.name,
        "evaluation_time": datetime.now(timezone.utc).isoformat(),
        "intensity": args.intensity if orchestrator else 0.0,
        "results": []
    }

    for symbol in corpus.symbols:
        for tf_str in corpus.timeframes:
            try:
                tf = TimeframeUtils.from_string(tf_str)

                # Get available date range
                db_start, db_end = client.get_date_range(symbol, tf)

                if db_start == db_end:
                    logger.warning(f"[EVAL] No data for {symbol} {tf_str}, skipping")
                    continue

                # Filter by corpus start_month
                corpus_start = datetime.strptime(corpus.start_month, "%Y-%m").replace(tzinfo=timezone.utc)
                start_time = max(db_start, corpus_start)
                end_time = db_end

                if start_time >= end_time:
                    logger.warning(f"[EVAL] Invalid date range for {symbol} {tf_str}, skipping")
                    continue

                logger.info(f"[EVAL] Evaluating {symbol} {tf_str} | Range: {start_time} to {end_time}")

                # Export perturbed candles for HRM if enabled
                export_path = os.path.join(args.output_dir, f"candles_{symbol}_{tf_str}.json")

                result = harness.run_eval_period(
                    symbol=symbol,
                    timeframe=tf,
                    start_time=start_time,
                    end_time=end_time,
                    export_path=export_path
                )

                all_results["results"].append(result)

            except Exception as e:
                logger.error(f"[ERROR] Failed to evaluate {symbol} {tf_str}: {e}")

    # Save aggregate results
    summary_path = os.path.join(args.output_dir, f"evaluation_summary_{corpus.name}.json")
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    logger.info(f"[EVAL] Evaluation complete. Summary saved to {summary_path}")


if __name__ == "__main__":
    run_evaluation()
