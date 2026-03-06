"""
Data Corpus Definition - Coverage targets for historical data ingestion.

Defines the symbols, timeframes, and date ranges that constitute the
'canonical' data corpus for training and evaluation.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict

logger = logging.getLogger(__name__)


@dataclass
class CorpusTarget:
    """Target coverage for a specific data corpus."""
    name: str
    symbols: List[str]
    timeframes: List[str]
    start_month: str
    end_month: str = ""  # Empty means current
    description: str = ""


# Standard symbol buckets
STABLECOIN_PAIRS = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT"]
TOP_7_L1 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]
TOP_30_VOLUME = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "AVAXUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT", "SHIBUSDT", "TRXUSDT", "LTCUSDT",
    "BCHUSDT", "UNIUSDT", "NEARUSDT", "ATOMUSDT", "APTUSDT", "FILUSDT", "OPUSDT",
    "LDOUSDT", "ARBUSDT", "TIAUSDT", "INJUSDT", "SEIUSDT", "SUIUSDT", "RNDRUSDT",
    "STXUSDT", "FETUSDT"
]

# Corpus definitions
CORPUS_V1_MINIMAL = CorpusTarget(
    name="v1_minimal",
    symbols=TOP_7_L1,
    timeframes=["1h", "1d"],
    start_month="2024-01",
    description="Minimal training set for convergence testing"
)

CORPUS_V1_FULL = CorpusTarget(
    name="v1_full",
    symbols=TOP_30_VOLUME,
    timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
    start_month="2023-01",
    description="Full baseline data corpus for HRM pretraining"
)

# Registry for easy lookup
CORPUS_REGISTRY = {
    "v1_minimal": CORPUS_V1_MINIMAL,
    "v1_full": CORPUS_V1_FULL,
}


def get_corpus_config(name: str = "v1_minimal") -> CorpusTarget:
    """Get a corpus target definition by name."""
    if name not in CORPUS_REGISTRY:
        logger.warning(f"Corpus '{name}' not found, defaulting to v1_minimal")
        return CORPUS_V1_MINIMAL
    return CORPUS_REGISTRY[name]


def get_all_symbols() -> List[str]:
    """Get deduplicated list of all symbols across all corpus definitions."""
    all_symbols = set()
    for corpus in CORPUS_REGISTRY.values():
        all_symbols.update(corpus.symbols)
    return sorted(list(all_symbols))
