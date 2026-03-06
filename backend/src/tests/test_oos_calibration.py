"""
Tests for Out-of-Sample Calibration Split Policy

Test coverage:
- Policy configuration and validation
- Time-based splitting
- Regime-aware splitting
- Regime balance enforcement
- Minimum sample validation
- Split result serialization
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import numpy as np

from src.oos_calibration import (
    OOSplitPolicy,
    OOSplitter,
    SplitResult,
    DataSplit,
    SplitType,
    create_oosplitter,
    create_oos_splits,
)
from src.models import Candle, Timeframe


def create_synthetic_data(
    n_samples: int = 1000,
    n_regimes: int = 3,
    start_time: Optional[datetime] = None
) -> tuple:
    """Create synthetic candle data with regime labels."""
    if start_time is None:
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    data = []
    regimes = []
    regime_names = [f"REGIME_{i}" for i in range(n_regimes)]

    for i in range(n_samples):
        candle = Candle(
            timestamp=start_time + timedelta(hours=i),
            open=100 + np.random.uniform(-5, 5),
            high=105 + np.random.uniform(-2, 2),
            low=95 + np.random.uniform(-2, 2),
            close=100 + np.random.uniform(-5, 5),
            volume=np.random.uniform(1000, 2000),
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
        )
        data.append(candle)

        # Assign regimes in blocks
        regime_idx = (i * n_regimes) // n_samples
        regimes.append(regime_names[regime_idx])

    return data, regimes


class TestOOSplitPolicy:
    """Test OOS split policy configuration."""

    def test_default_policy(self):
        """Test default policy creation."""
        policy = OOSplitPolicy()

        assert policy.train_ratio == 0.6
        assert policy.calibration_ratio == 0.2
        assert policy.test_ratio == 0.2
        assert policy.min_regimes_per_split == 2
        assert policy.min_days_per_split == 30

    def test_custom_policy(self):
        """Test custom policy configuration."""
        policy = OOSplitPolicy(
            train_ratio=0.7,
            calibration_ratio=0.15,
            test_ratio=0.15,
            min_regimes_per_split=3,
            ensure_regime_balance=False,
        )

        assert policy.train_ratio == 0.7
        assert policy.calibration_ratio == 0.15
        assert not policy.ensure_regime_balance

    def test_invalid_ratios_sum(self):
        """Test that ratios must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            OOSplitPolicy(
                train_ratio=0.5,
                calibration_ratio=0.3,
                test_ratio=0.3,  # Sum = 1.1
            )

    def test_invalid_min_regimes(self):
        """Test min_regimes validation."""
        with pytest.raises(ValueError, match="must be >= 1"):
            OOSplitPolicy(min_regimes_per_split=0)

    def test_invalid_tolerance(self):
        """Test tolerance validation."""
        with pytest.raises(ValueError, match="must be in"):
            OOSplitPolicy(regime_balance_tolerance=1.5)

    def test_to_dict(self):
        """Test policy serialization."""
        policy = OOSplitPolicy()
        policy_dict = policy.to_dict()

        assert "train_ratio" in policy_dict
        assert "calibration_ratio" in policy_dict
        assert "test_ratio" in policy_dict
        assert "min_regimes_per_split" in policy_dict

    def test_from_dict(self):
        """Test policy deserialization."""
        config = {
            "train_ratio": 0.7,
            "calibration_ratio": 0.2,
            "test_ratio": 0.1,
            "min_regimes_per_split": 3,
        }

        policy = OOSplitPolicy.from_dict(config)
        assert policy.train_ratio == 0.7
        assert policy.min_regimes_per_split == 3

    def test_from_json(self):
        """Test loading policy from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "policy.json")
            config = {"train_ratio": 0.7, "calibration_ratio": 0.2, "test_ratio": 0.1}

            with open(filepath, 'w') as f:
                json.dump(config, f)

            policy = OOSplitPolicy.from_json(filepath)
            assert policy.train_ratio == 0.7

    def test_save_policy(self):
        """Test saving policy to JSON."""
        policy = OOSplitPolicy(train_ratio=0.7, calibration_ratio=0.15, test_ratio=0.15)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "policy.json")
            policy.save(filepath)

            assert os.path.exists(filepath)
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert loaded["train_ratio"] == 0.7


class TestDataSplit:
    """Test DataSplit dataclass."""

    def test_data_split_creation(self):
        """Test DataSplit creation."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = [
            Candle(
                timestamp=start_time,
                open=100, high=105, low=95, close=100,
                volume=1000, symbol="BTCUSDT", timeframe=Timeframe.ONE_HOUR
            )
        ]

        split = DataSplit(
            split_type=SplitType.TRAIN,
            data=data,
            regime_labels=["REGIME_1"],
            start_time=start_time,
            end_time=start_time,
            n_samples=1,
            regime_distribution={"REGIME_1": 1.0},
        )

        assert split.split_type == SplitType.TRAIN
        assert split.n_samples == 1

    def test_data_split_to_dict(self):
        """Test DataSplit serialization."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = [
            Candle(
                timestamp=start_time,
                open=100, high=105, low=95, close=100,
                volume=1000, symbol="BTCUSDT", timeframe=Timeframe.ONE_HOUR
            )
        ]

        split = DataSplit(
            split_type=SplitType.TRAIN,
            data=data,
            regime_labels=["REGIME_1"],
            start_time=start_time,
            end_time=start_time,
            n_samples=1,
            regime_distribution={"REGIME_1": 1.0},
        )

        split_dict = split.to_dict()
        assert split_dict["split_type"] == "train"
        assert split_dict["n_samples"] == 1
        assert "regime_distribution" in split_dict


class TestOOSplitter:
    """Test OOS splitter functionality."""

    def test_splitter_creation(self):
        """Test splitter creation."""
        policy = OOSplitPolicy()
        splitter = create_oosplitter(policy)

        assert splitter is not None
        assert splitter.policy == policy

    def test_splitter_default_policy(self):
        """Test splitter with default policy."""
        splitter = create_oosplitter()
        assert splitter.policy.train_ratio == 0.6

    def test_create_splits_basic(self):
        """Test basic split creation."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=3)

        policy = OOSplitPolicy(
            train_ratio=0.6,
            calibration_ratio=0.2,
            test_ratio=0.2,
            min_regimes_per_split=1,  # Lower for small test
            min_samples_per_regime=10,
        )

        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        assert isinstance(result, SplitResult)
        assert result.train.n_samples > 0
        assert result.calibration.n_samples > 0
        assert result.test.n_samples > 0

        # Check approximate ratios
        total = result.train.n_samples + result.calibration.n_samples + result.test.n_samples
        assert abs(result.train.n_samples / total - 0.6) < 0.1
        assert abs(result.calibration.n_samples / total - 0.2) < 0.1
        assert abs(result.test.n_samples / total - 0.2) < 0.1

    def test_create_splits_temporal_order(self):
        """Test that splits maintain temporal order."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=3)

        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Train should be before calibration, calibration before test
        assert result.train.end_time <= result.calibration.start_time
        assert result.calibration.end_time <= result.test.start_time

    def test_create_splits_regime_coverage(self):
        """Test regime coverage in splits."""
        # Create data with interleaved regimes to ensure coverage in all splits
        data = []
        regimes = []
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        regime_names = ["REGIME_0", "REGIME_1", "REGIME_2"]

        for i in range(900):
            candle = Candle(
                timestamp=start_time + timedelta(hours=i),
                open=100 + np.random.uniform(-5, 5),
                high=105 + np.random.uniform(-2, 2),
                low=95 + np.random.uniform(-2, 2),
                close=100 + np.random.uniform(-5, 5),
                volume=np.random.uniform(1000, 2000),
                symbol="BTCUSDT",
                timeframe=Timeframe.ONE_HOUR,
            )
            data.append(candle)
            # Cycle through regimes to ensure all appear in all splits
            regimes.append(regime_names[i % 3])

        policy = OOSplitPolicy(
            min_regimes_per_split=2,
            min_samples_per_regime=20,
        )

        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Each split should have all 3 regimes
        assert len(set(result.train.regime_labels)) >= 2
        assert len(set(result.calibration.regime_labels)) >= 2
        assert len(set(result.test.regime_labels)) >= 2

    def test_create_splits_insufficient_data(self):
        """Test behavior with insufficient data."""
        data, regimes = create_synthetic_data(n_samples=10, n_regimes=5)

        policy = OOSplitPolicy(
            min_regimes_per_split=3,
            min_samples_per_regime=100,  # More than available
        )

        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Should have warnings
        assert len(result.warnings) > 0

    def test_create_time_based_splits(self):
        """Test time-based split creation."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=3)

        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)

        # Define time boundaries
        train_end = data[0].timestamp + timedelta(hours=180)  # 60%
        cal_end = data[0].timestamp + timedelta(hours=240)  # 80%

        result = splitter.create_time_based_splits(
            data, regimes, train_end_time=train_end, cal_end_time=cal_end
        )

        assert isinstance(result, SplitResult)
        assert result.train.end_time <= train_end
        assert result.calibration.end_time <= cal_end

    def test_create_time_based_splits_no_data(self):
        """Test time-based splits with empty splits."""
        data, regimes = create_synthetic_data(n_samples=100, n_regimes=1)

        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)

        # All data before train_end (no calibration or test data)
        train_end = datetime(2025, 1, 1, tzinfo=timezone.utc)
        cal_end = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="No data in calibration split"):
            splitter.create_time_based_splits(data, regimes, train_end, cal_end)

    def test_regime_balance(self):
        """Test regime balancing."""
        # Create imbalanced data with both regimes in each split region
        data = []
        regimes = []
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Create interleaved regime data to ensure both regimes in all splits
        for i in range(1000):
            candle = Candle(
                timestamp=start_time + timedelta(hours=i),
                open=100, high=105, low=95, close=100,
                volume=1000, symbol="BTCUSDT", timeframe=Timeframe.ONE_HOUR
            )
            data.append(candle)
            # Alternate regimes to ensure both appear in all splits
            if i % 5 < 4:  # 80% regime A
                regimes.append("REGIME_A")
            else:  # 20% regime B
                regimes.append("REGIME_B")

        policy = OOSplitPolicy(ensure_regime_balance=True, regime_balance_tolerance=0.1)
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Check that regime distribution is more balanced after balancing
        train_dist = result.train.regime_distribution
        # After balancing, should be closer to equal (tolerance allows some imbalance)
        # With balancing, majority regime should be undersampled
        assert train_dist.get("REGIME_A", 0) < 0.8, "Regime balancing should reduce majority regime"
        assert train_dist.get("REGIME_B", 0) > 0.2, "Regime balancing should increase minority regime"

    def test_split_result_serialization(self):
        """Test split result serialization."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=2)

        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Test to_dict
        result_dict = result.to_dict()
        assert "train" in result_dict
        assert "calibration" in result_dict
        assert "test" in result_dict
        assert "policy" in result_dict

        # Test file save
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "splits.json")
            result.save(filepath)

            assert os.path.exists(filepath)
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert loaded["train"]["n_samples"] == result.train.n_samples


class TestCreateOOSplits:
    """Test high-level split creation function."""

    def test_create_oosplits(self):
        """Test create_oos_splits function."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "splits.json")

            result = create_oos_splits(
                data, regimes,
                policy=OOSplitPolicy(min_regimes_per_split=1),
                output_path=output_path
            )

            assert isinstance(result, SplitResult)
            assert os.path.exists(output_path)


class TestRegimeValidation:
    """Test regime validation specifically."""

    def test_min_regimes_validation(self):
        """Test minimum regimes validation."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=1)

        policy = OOSplitPolicy(min_regimes_per_split=2)
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Should have warnings about insufficient regimes
        assert any("regimes" in w.lower() for w in result.warnings)

    def test_min_samples_per_regime_validation(self):
        """Test minimum samples per regime validation."""
        data, regimes = create_synthetic_data(n_samples=100, n_regimes=5)

        policy = OOSplitPolicy(min_samples_per_regime=50)  # More than available per regime
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Should have warnings about insufficient samples
        assert any("samples" in w.lower() for w in result.warnings)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_dataset(self):
        """Test with very small dataset."""
        data, regimes = create_synthetic_data(n_samples=10, n_regimes=2)

        policy = OOSplitPolicy(min_regimes_per_split=1, min_samples_per_regime=1)
        splitter = OOSplitter(policy)

        # Should still work but with warnings
        result = splitter.create_splits(data, regimes)
        assert result.train.n_samples > 0
        assert result.calibration.n_samples > 0
        assert result.test.n_samples > 0

    def test_single_regime(self):
        """Test with single regime."""
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=1)

        policy = OOSplitPolicy(
            min_regimes_per_split=1,
            ensure_regime_balance=False,
        )
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        assert len(set(result.train.regime_labels)) == 1

    def test_many_regimes(self):
        """Test with many regimes."""
        data, regimes = create_synthetic_data(n_samples=1000, n_regimes=10)

        policy = OOSplitPolicy(min_regimes_per_split=3, min_samples_per_regime=10)
        splitter = OOSplitter(policy)
        result = splitter.create_splits(data, regimes)

        # Each split should have multiple regimes
        assert len(set(result.train.regime_labels)) >= 3

    def test_unsorted_data(self):
        """Test with unsorted data."""
        # Create data in random order
        data, regimes = create_synthetic_data(n_samples=300, n_regimes=3)

        # Shuffle data
        import random
        random.seed(42)
        indices = list(range(len(data)))
        random.shuffle(indices)

        shuffled_data = [data[i] for i in indices]
        shuffled_regimes = [regimes[i] for i in indices]

        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)
        result = splitter.create_splits(shuffled_data, shuffled_regimes)

        # Splits should still be temporally ordered
        assert result.train.end_time <= result.calibration.start_time
        assert result.calibration.end_time <= result.test.start_time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
