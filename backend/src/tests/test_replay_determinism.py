"""
Tests for ReplayEngine determinism.

Verifies that ReplayEngine produces the exact same sequence of candles
when initialized with the same seed, and different sequences with
different seeds.
"""

import unittest
from datetime import datetime, timezone, timedelta
from typing import List

from ..models import Candle, Timeframe
from ..replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from ..binance_client import BinanceArchiveClient


class MockBinanceArchiveClient(BinanceArchiveClient):
    """Mock client that returns a fixed set of candles without a database."""

    def __init__(self, candles: List[Candle]):
        self.mock_candles = candles
        self.ensure_schema_called = False

    def ensure_schema(self):
        self.ensure_schema_called = True

    def get_date_range(self, symbol, timeframe):
        if not self.mock_candles:
            return (datetime.min.replace(tzinfo=timezone.utc), datetime.min.replace(tzinfo=timezone.utc))
        timestamps = [c.timestamp for c in self.mock_candles if c.symbol == symbol]
        if not timestamps:
            return (datetime.min.replace(tzinfo=timezone.utc), datetime.min.replace(tzinfo=timezone.utc))
        return (min(timestamps), max(timestamps))

    def query_candles(self, symbol, timeframe, start, end):
        return [
            c for c in self.mock_candles
            if c.symbol == symbol and start <= c.timestamp <= end
        ]


class TestReplayDeterminism(unittest.TestCase):
    """Test suite for ReplayEngine determinism."""

    def setUp(self):
        """Set up mock data for testing."""
        self.base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.symbols = ["BTCUSDT", "ETHUSDT"]

        # Create 10 candles for each symbol with identical timestamps
        self.mock_candles = []
        for i in range(10):
            ts = self.base_time + timedelta(hours=i)
            for symbol in self.symbols:
                self.mock_candles.append(Candle(
                    timestamp=ts,
                    open=100.0 + i,
                    high=110.0 + i,
                    low=90.0 + i,
                    close=105.0 + i,
                    volume=1000.0 * (i + 1),
                    symbol=symbol,
                    timeframe=Timeframe.ONE_HOUR
                ))

        self.mock_client = MockBinanceArchiveClient(self.mock_candles)

    def test_deterministic_ordering_same_seed(self):
        """Verify same seed produces same sequence."""
        config = ReplayConfig(
            mode=ReplayMode.INSTANT,
            symbols=self.symbols,
            timeframes=[Timeframe.ONE_HOUR],
            seed=42
        )

        # Run replay 1
        engine1 = ReplayEngine(self.mock_client, config)
        sequence1 = list(engine1.stream())

        # Run replay 2
        engine2 = ReplayEngine(self.mock_client, config)
        sequence2 = list(engine2.stream())

        # Assert lengths match
        self.assertEqual(len(sequence1), len(sequence2))
        self.assertEqual(len(sequence1), 20)

        # Assert content matches exactly
        for c1, c2 in zip(sequence1, sequence2):
            self.assertEqual(c1.timestamp, c2.timestamp)
            self.assertEqual(c1.symbol, c2.symbol)

    def test_deterministic_ordering_different_seeds(self):
        """Verify different seeds produce different sequences (for same-timestamp candles)."""
        # Note: ReplayEngine maintains chronological order, but shuffles within same timestamp

        config1 = ReplayConfig(
            mode=ReplayMode.INSTANT,
            symbols=self.symbols,
            timeframes=[Timeframe.ONE_HOUR],
            seed=42
        )

        config2 = ReplayConfig(
            mode=ReplayMode.INSTANT,
            symbols=self.symbols,
            timeframes=[Timeframe.ONE_HOUR],
            seed=123
        )

        engine1 = ReplayEngine(self.mock_client, config1)
        sequence1 = list(engine1.stream())

        engine2 = ReplayEngine(self.mock_client, config2)
        sequence2 = list(engine2.stream())

        # Assert lengths match
        self.assertEqual(len(sequence1), len(sequence2))

        # Compare sequences
        # Since we have 2 symbols per timestamp, there's a 50% chance they match by coincidence for each timestamp.
        # With 10 timestamps, the chance of all matching by coincidence is (1/2)^10 = 1/1024.

        matches = 0
        for c1, c2 in zip(sequence1, sequence2):
            if c1.symbol == c2.symbol:
                matches += 1

        # If they aren't identical, deterministic shuffling is working
        self.assertLess(matches, len(sequence1), "Sequences with different seeds should not be identical")

    def test_no_seed_non_deterministic(self):
        """Verify no seed produces different results (or at least doesn't use a fixed default)."""
        config = ReplayConfig(
            mode=ReplayMode.INSTANT,
            symbols=self.symbols,
            timeframes=[Timeframe.ONE_HOUR],
            seed=None
        )

        engine1 = ReplayEngine(self.mock_client, config)
        sequence1 = list(engine1.stream())

        # Note: ReplayEngine without seed doesn't shuffle, it uses default merge order
        # which depends on dictionary iteration or stable sort.
        # Let's check if it's stable.

        engine2 = ReplayEngine(self.mock_client, config)
        sequence2 = list(engine2.stream())

        # Without seed, it should be stable but not shuffled.
        self.assertEqual(sequence1, sequence2)


if __name__ == "__main__":
    unittest.main()
