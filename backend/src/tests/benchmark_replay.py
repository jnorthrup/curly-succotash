"""
Benchmark for ReplayEngine and ArchiveIngester.

Measures:
1. Replay throughput (candles per second) in INSTANT mode.
2. Replay timing accuracy in COMPRESSED mode.
3. Memory usage during large replay (qualitative).
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from src.models import Candle, Timeframe
from src.replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from src.binance_client import BinanceArchiveClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockBenchClient(BinanceArchiveClient):
    """Mock client for benchmarking."""
    def __init__(self, count: int):
        self.count = count
        self.base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.candles = [
            Candle(
                timestamp=self.base_time + timedelta(minutes=i),
                open=100.0, high=101.0, low=99.0, close=100.5, volume=100.0,
                symbol="BTCUSDT", timeframe=Timeframe.ONE_MINUTE
            ) for i in range(count)
        ]

    def get_date_range(self, symbol, timeframe):
        return (self.base_time, self.base_time + timedelta(minutes=self.count))

    def query_candles(self, symbol, timeframe, start, end):
        return self.candles


def benchmark_instant_throughput(candle_count: int = 100000):
    """Benchmark max throughput in INSTANT mode."""
    client = MockBenchClient(candle_count)
    config = ReplayConfig(
        mode=ReplayMode.INSTANT,
        symbols=["BTCUSDT"],
        timeframes=[Timeframe.ONE_MINUTE]
    )
    engine = ReplayEngine(client, config)

    logger.info(f"Starting INSTANT throughput benchmark with {candle_count} candles...")

    start_time = time.perf_counter()
    processed = 0

    for _ in engine.stream():
        processed += 1

    end_time = time.perf_counter()
    duration = end_time - start_time
    rate = processed / duration if duration > 0 else 0

    logger.info(f"INSTANT Mode: Processed {processed} candles in {duration:.4f}s ({rate:.2f} candles/sec)")
    return rate


def benchmark_compressed_accuracy(factor: float = 1000.0, candle_count: int = 100):
    """Benchmark timing accuracy in COMPRESSED mode."""
    client = MockBenchClient(candle_count)
    config = ReplayConfig(
        mode=ReplayMode.COMPRESSED,
        compression_factor=factor,
        symbols=["BTCUSDT"],
        timeframes=[Timeframe.ONE_MINUTE]
    )
    engine = ReplayEngine(client, config)

    # Each candle is 1 min (60s) apart.
    # With factor 1000, delay should be 60 / 1000 = 0.06s per candle.
    expected_duration = (candle_count - 1) * (60.0 / factor)

    logger.info(f"Starting COMPRESSED accuracy benchmark (Factor={factor}) with {candle_count} candles...")
    logger.info(f"Expected duration: {expected_duration:.4f}s")

    start_time = time.perf_counter()
    processed = 0

    for _ in engine.stream():
        processed += 1

    end_time = time.perf_counter()
    actual_duration = end_time - start_time

    error = abs(actual_duration - expected_duration)
    error_pct = (error / expected_duration * 100) if expected_duration > 0 else 0

    logger.info(f"COMPRESSED Mode: Actual duration {actual_duration:.4f}s, Error: {error:.4f}s ({error_pct:.2f}%)")
    return error_pct


if __name__ == "__main__":
    benchmark_instant_throughput(200000)
    benchmark_compressed_accuracy(1000.0, 50)
    benchmark_compressed_accuracy(10000.0, 50)
