"""
Out-of-Sample Calibration Split Policy

Implements regime-aware data splitting for calibration with explicit time windows
and non-overlapping OOS governance. Ensures each split has proper regime coverage
and temporal ordering to prevent data leakage.

Key Features:
- Time-based splits (train/calibration/test)
- Regime-aware stratification
- Minimum regime coverage per split
- Temporal ordering enforcement
- Configuration-driven policy

Example:
    policy = OOSplitPolicy(
        train_ratio=0.6,
        calibration_ratio=0.2,
        test_ratio=0.2,
        min_regimes_per_split=2
    )
    splits = policy.create_splits(data, regime_labels)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

import numpy as np

from .models import Candle, Timeframe

logger = logging.getLogger(__name__)


class SplitType(str, Enum):
    """Types of data splits."""
    TRAIN = "train"
    CALIBRATION = "calibration"
    TEST = "test"
    OOS = "out_of_sample"


@dataclass
class DataSplit:
    """A single data split with metadata."""
    split_type: SplitType
    data: List[Candle]
    regime_labels: List[str]
    start_time: datetime
    end_time: datetime
    n_samples: int
    regime_distribution: Dict[str, float]  # regime -> percentage

    def to_dict(self) -> Dict[str, Any]:
        """Convert split to dictionary."""
        return {
            "split_type": self.split_type.value,
            "n_samples": self.n_samples,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "regime_distribution": self.regime_distribution,
            "unique_regimes": list(set(self.regime_labels)),
        }


@dataclass
class SplitResult:
    """Result of data splitting operation."""
    train: DataSplit
    calibration: DataSplit
    test: DataSplit
    policy: "OOSplitPolicy"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "policy": self.policy.to_dict(),
            "train": self.train.to_dict(),
            "calibration": self.calibration.to_dict(),
            "test": self.test.to_dict(),
            "warnings": self.warnings,
        }

    def save(self, filepath: str) -> None:
        """Save split result to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[OOSPLIT] Split result saved to {filepath}")


@dataclass
class OOSplitPolicy:
    """Out-of-sample split policy with regime awareness.

    Attributes:
        train_ratio: Fraction of data for training (0.0-1.0)
        calibration_ratio: Fraction of data for calibration (0.0-1.0)
        test_ratio: Fraction of data for testing (0.0-1.0)
        min_regimes_per_split: Minimum number of unique regimes required per split
        ensure_regime_balance: Whether to stratify by regime distribution
        min_days_per_split: Minimum number of days per split
        no_future_leakage: Enforce strict temporal ordering
        min_samples_per_regime: Minimum samples required in each regime
        regime_balance_tolerance: Tolerance for regime distribution mismatch (0.0-1.0)
    """
    train_ratio: float = 0.6
    calibration_ratio: float = 0.2
    test_ratio: float = 0.2
    min_regimes_per_split: int = 2
    ensure_regime_balance: bool = True
    min_days_per_split: int = 30
    no_future_leakage: bool = True
    min_samples_per_regime: int = 100
    regime_balance_tolerance: float = 0.2  # 20% tolerance

    def __post_init__(self):
        """Validate policy configuration."""
        total = self.train_ratio + self.calibration_ratio + self.test_ratio
        if not np.isclose(total, 1.0):
            raise ValueError(f"Ratios must sum to 1.0, got {total}")

        if self.min_regimes_per_split < 1:
            raise ValueError("min_regimes_per_split must be >= 1")

        if not 0.0 <= self.regime_balance_tolerance <= 1.0:
            raise ValueError("regime_balance_tolerance must be in [0.0, 1.0]")

    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary."""
        return {
            "train_ratio": self.train_ratio,
            "calibration_ratio": self.calibration_ratio,
            "test_ratio": self.test_ratio,
            "min_regimes_per_split": self.min_regimes_per_split,
            "ensure_regime_balance": self.ensure_regime_balance,
            "min_days_per_split": self.min_days_per_split,
            "no_future_leakage": self.no_future_leakage,
            "min_samples_per_regime": self.min_samples_per_regime,
            "regime_balance_tolerance": self.regime_balance_tolerance,
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "OOSplitPolicy":
        """Create policy from dictionary."""
        return cls(
            train_ratio=config.get("train_ratio", 0.6),
            calibration_ratio=config.get("calibration_ratio", 0.2),
            test_ratio=config.get("test_ratio", 0.2),
            min_regimes_per_split=config.get("min_regimes_per_split", 2),
            ensure_regime_balance=config.get("ensure_regime_balance", True),
            min_days_per_split=config.get("min_days_per_split", 30),
            no_future_leakage=config.get("no_future_leakage", True),
            min_samples_per_regime=config.get("min_samples_per_regime", 100),
            regime_balance_tolerance=config.get("regime_balance_tolerance", 0.2),
        )

    @classmethod
    def from_json(cls, filepath: str) -> "OOSplitPolicy":
        """Load policy from JSON file."""
        with open(filepath, 'r') as f:
            config = json.load(f)
        return cls.from_dict(config)

    def save(self, filepath: str) -> None:
        """Save policy to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[OOSPLIT] Policy saved to {filepath}")


class OOSplitter:
    """Out-of-sample data splitter with regime awareness.

    Creates train/calibration/test splits that:
    1. Respect temporal ordering (no future leakage)
    2. Have minimum regime coverage per split
    3. Maintain regime distribution balance (optional)
    4. Meet minimum sample requirements

    Example:
        policy = OOSplitPolicy()
        splitter = OOSplitter(policy)
        splits = splitter.create_splits(data, regime_labels)
    """

    def __init__(self, policy: OOSplitPolicy):
        """Initialize splitter.

        Args:
            policy: Split policy configuration
        """
        self.policy = policy
        self._warnings: List[str] = []

    def create_splits(
        self,
        data: List[Candle],
        regime_labels: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> SplitResult:
        """Create train/calibration/test splits.

        Args:
            data: List of candles to split
            regime_labels: Regime label for each candle
            start_time: Optional start time override
            end_time: Optional end time override

        Returns:
            SplitResult with all three splits

        Raises:
            ValueError: If data insufficient for policy requirements
        """
        self._warnings = []

        if len(data) != len(regime_labels):
            raise ValueError("data and regime_labels must have same length")

        if len(data) < 3:
            raise ValueError("Need at least 3 samples for splitting")

        # Sort by timestamp if not already sorted
        sorted_indices = np.argsort([c.timestamp for c in data])
        sorted_data = [data[i] for i in sorted_indices]
        sorted_regimes = [regime_labels[i] for i in sorted_indices]

        # Determine time bounds
        if start_time is None:
            start_time = sorted_data[0].timestamp
        if end_time is None:
            end_time = sorted_data[-1].timestamp

        # Calculate split indices
        n = len(sorted_data)
        train_end_idx = int(n * self.policy.train_ratio)
        cal_end_idx = int(n * (self.policy.train_ratio + self.policy.calibration_ratio))

        # Ensure minimum samples per split
        min_samples = self.policy.min_samples_per_regime * self.policy.min_regimes_per_split
        if train_end_idx < min_samples:
            self._warnings.append(f"Train split has fewer than {min_samples} samples")
        if cal_end_idx - train_end_idx < min_samples:
            self._warnings.append(f"Calibration split has fewer than {min_samples} samples")
        if n - cal_end_idx < min_samples:
            self._warnings.append(f"Test split has fewer than {min_samples} samples")

        # Create splits
        train_data = sorted_data[:train_end_idx]
        train_regimes = sorted_regimes[:train_end_idx]

        cal_data = sorted_data[train_end_idx:cal_end_idx]
        cal_regimes = sorted_regimes[train_end_idx:cal_end_idx]

        test_data = sorted_data[cal_end_idx:]
        test_regimes = sorted_regimes[cal_end_idx:]

        # Validate regime coverage
        self._validate_regime_coverage(train_data, train_regimes, SplitType.TRAIN)
        self._validate_regime_coverage(cal_data, cal_regimes, SplitType.CALIBRATION)
        self._validate_regime_coverage(test_data, test_regimes, SplitType.TEST)

        # Optionally balance regime distribution
        if self.policy.ensure_regime_balance:
            train_data, train_regimes = self._balance_regimes(train_data, train_regimes)
            cal_data, cal_regimes = self._balance_regimes(cal_data, cal_regimes)
            test_data, test_regimes = self._balance_regimes(test_data, test_regimes)

        # Create DataSplit objects
        train_split = self._create_data_split(
            SplitType.TRAIN, train_data, train_regimes
        )
        cal_split = self._create_data_split(
            SplitType.CALIBRATION, cal_data, cal_regimes
        )
        test_split = self._create_data_split(
            SplitType.TEST, test_data, test_regimes
        )

        result = SplitResult(
            train=train_split,
            calibration=cal_split,
            test=test_split,
            policy=self.policy,
            warnings=self._warnings,
        )

        logger.info(f"[OOSPLIT] Created splits: train={len(train_data)}, "
                   f"cal={len(cal_data)}, test={len(test_data)}")

        if self._warnings:
            for warning in self._warnings:
                logger.warning(f"[OOSPLIT] {warning}")

        return result

    def create_time_based_splits(
        self,
        data: List[Candle],
        regime_labels: List[str],
        train_end_time: datetime,
        cal_end_time: datetime
    ) -> SplitResult:
        """Create splits based on explicit time boundaries.

        Args:
            data: List of candles
            regime_labels: Regime labels
            train_end_time: End time for training split
            cal_end_time: End time for calibration split

        Returns:
            SplitResult with time-based splits
        """
        self._warnings = []

        if len(data) != len(regime_labels):
            raise ValueError("data and regime_labels must have same length")

        # Sort by timestamp
        sorted_indices = np.argsort([c.timestamp for c in data])
        sorted_data = [data[i] for i in sorted_indices]
        sorted_regimes = [regime_labels[i] for i in sorted_indices]

        # Split by time
        train_data, train_regimes = [], []
        cal_data, cal_regimes = [], []
        test_data, test_regimes = [], []

        for candle, regime in zip(sorted_data, sorted_regimes):
            if candle.timestamp <= train_end_time:
                train_data.append(candle)
                train_regimes.append(regime)
            elif candle.timestamp <= cal_end_time:
                cal_data.append(candle)
                cal_regimes.append(regime)
            else:
                test_data.append(candle)
                test_regimes.append(regime)

        # Validate
        if not train_data:
            raise ValueError("No data in training split")
        if not cal_data:
            raise ValueError("No data in calibration split")
        if not test_data:
            raise ValueError("No data in test split")

        self._validate_regime_coverage(train_data, train_regimes, SplitType.TRAIN)
        self._validate_regime_coverage(cal_data, cal_regimes, SplitType.CALIBRATION)
        self._validate_regime_coverage(test_data, test_regimes, SplitType.TEST)

        # Create splits
        train_split = self._create_data_split(SplitType.TRAIN, train_data, train_regimes)
        cal_split = self._create_data_split(SplitType.CALIBRATION, cal_data, cal_regimes)
        test_split = self._create_data_split(SplitType.TEST, test_data, test_regimes)

        return SplitResult(
            train=train_split,
            calibration=cal_split,
            test=test_split,
            policy=self.policy,
            warnings=self._warnings,
        )

    def _create_data_split(
        self,
        split_type: SplitType,
        data: List[Candle],
        regime_labels: List[str]
    ) -> DataSplit:
        """Create a DataSplit object."""
        if not data:
            raise ValueError(f"Cannot create empty {split_type.value} split")

        # Calculate regime distribution
        regime_counts = {}
        for regime in regime_labels:
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        regime_distribution = {
            regime: count / len(regime_labels)
            for regime, count in regime_counts.items()
        }

        return DataSplit(
            split_type=split_type,
            data=data,
            regime_labels=regime_labels,
            start_time=data[0].timestamp,
            end_time=data[-1].timestamp,
            n_samples=len(data),
            regime_distribution=regime_distribution,
        )

    def _validate_regime_coverage(
        self,
        data: List[Candle],
        regimes: List[str],
        split_type: SplitType
    ) -> None:
        """Validate that split has sufficient regime coverage."""
        unique_regimes = set(regimes)

        if len(unique_regimes) < self.policy.min_regimes_per_split:
            self._warnings.append(
                f"{split_type.value} split has {len(unique_regimes)} regimes, "
                f"minimum is {self.policy.min_regimes_per_split}"
            )

        # Check minimum samples per regime
        regime_counts = {}
        for regime in regimes:
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        for regime, count in regime_counts.items():
            if count < self.policy.min_samples_per_regime:
                self._warnings.append(
                    f"{split_type.value} split has regime '{regime}' with only "
                    f"{count} samples (minimum: {self.policy.min_samples_per_regime})"
                )

    def _balance_regimes(
        self,
        data: List[Candle],
        regimes: List[str]
    ) -> Tuple[List[Candle], List[str]]:
        """Balance regime distribution in split.

        Undersamples majority regimes to match minority regime within tolerance.
        """
        if not self.policy.ensure_regime_balance:
            return data, regimes

        # Count regimes
        regime_indices = {}
        for i, regime in enumerate(regimes):
            if regime not in regime_indices:
                regime_indices[regime] = []
            regime_indices[regime].append(i)

        # Find minority regime count
        min_count = min(len(indices) for indices in regime_indices.values())
        target_count = max(min_count, self.policy.min_samples_per_regime)

        # Undersample majority regimes
        selected_indices = []
        for regime, indices in regime_indices.items():
            if len(indices) > target_count * (1 + self.policy.regime_balance_tolerance):
                # Undersample this regime
                rng = np.random.RandomState(42)
                selected = rng.choice(indices, size=target_count, replace=False)
                selected_indices.extend(selected)
            else:
                selected_indices.extend(indices)

        # Sort indices to maintain temporal order
        selected_indices = sorted(selected_indices)

        balanced_data = [data[i] for i in selected_indices]
        balanced_regimes = [regimes[i] for i in selected_indices]

        return balanced_data, balanced_regimes


def create_oosplitter(
    policy: Optional[OOSplitPolicy] = None,
    config_path: Optional[str] = None
) -> OOSplitter:
    """Factory function to create OOSplitter.

    Args:
        policy: Optional policy object
        config_path: Optional path to policy JSON config

    Returns:
        OOSplitter instance
    """
    if policy is None:
        if config_path:
            policy = OOSplitPolicy.from_json(config_path)
        else:
            policy = OOSplitPolicy()

    return OOSplitter(policy)


def create_oos_splits(
    data: List[Candle],
    regime_labels: List[str],
    policy: Optional[OOSplitPolicy] = None,
    output_path: Optional[str] = None
) -> SplitResult:
    """Create OOS splits with default or custom policy.

    Args:
        data: List of candles
        regime_labels: Regime labels per candle
        policy: Optional custom policy
        output_path: Optional path to save results

    Returns:
        SplitResult
    """
    splitter = create_oosplitter(policy)
    result = splitter.create_splits(data, regime_labels)

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result.save(output_path)

    return result


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create synthetic data for demonstration
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    data = []
    regimes = []

    for i in range(1000):
        candle = Candle(
            timestamp=base_time + timedelta(hours=i),
            open=100 + np.random.uniform(-5, 5),
            high=105 + np.random.uniform(-2, 2),
            low=95 + np.random.uniform(-2, 2),
            close=100 + np.random.uniform(-5, 5),
            volume=np.random.uniform(1000, 2000),
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
        )
        data.append(candle)

        # Assign regimes based on volatility
        if i < 300:
            regimes.append("VOL_LOW")
        elif i < 600:
            regimes.append("VOL_NORMAL")
        else:
            regimes.append("VOL_HIGH")

    # Create splits
    policy = OOSplitPolicy(
        train_ratio=0.6,
        calibration_ratio=0.2,
        test_ratio=0.2,
        min_regimes_per_split=2,
    )

    splitter = OOSplitter(policy)
    result = splitter.create_splits(data, regimes)

    print(f"Train: {result.train.n_samples} samples, "
          f"regimes: {list(result.train.regime_distribution.keys())}")
    print(f"Calibration: {result.calibration.n_samples} samples, "
          f"regimes: {list(result.calibration.regime_distribution.keys())}")
    print(f"Test: {result.test.n_samples} samples, "
          f"regimes: {list(result.test.regime_distribution.keys())}")

    if result.warnings:
        print(f"Warnings: {result.warnings}")
