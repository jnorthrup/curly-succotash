"""
Calibration Support Modules

Combined module for:
- Regime-aware threshold scheduling
- Cooldown and hold policy  
- Calibration drift monitoring

These modules support the calibration infrastructure with regime-aware
decision making, trade cooldowns, and drift detection.
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

from .models import Timeframe, Candle

logger = logging.getLogger(__name__)


# ============================================================================
# Regime-Aware Threshold Scheduling
# ============================================================================

@dataclass
class RegimeThresholdConfig:
    """Threshold configuration for a specific regime."""
    regime: str
    confidence_threshold: float = 0.6
    position_size_modifier: float = 1.0
    stop_loss_multiplier: float = 1.0
    take_profit_multiplier: float = 1.0
    min_confidence: float = 0.3
    max_confidence: float = 0.9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime,
            "confidence_threshold": self.confidence_threshold,
            "position_size_modifier": self.position_size_modifier,
            "stop_loss_multiplier": self.stop_loss_multiplier,
            "take_profit_multiplier": self.take_profit_multiplier,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
        }


class ThresholdScheduler:
    """Select and adjust thresholds based on regime."""

    def __init__(self, threshold_configs: List[RegimeThresholdConfig]):
        """Initialize scheduler.

        Args:
            threshold_configs: List of regime-specific threshold configs
        """
        self.thresholds_by_regime = {t.regime: t for t in threshold_configs}
        self.default_threshold = RegimeThresholdConfig(regime="DEFAULT")

    def get_thresholds(self, detected_regimes: List[str]) -> RegimeThresholdConfig:
        """Get thresholds for current regime mix.

        Args:
            detected_regimes: List of currently detected regime names

        Returns:
            Combined threshold config for regime mix
        """
        if not detected_regimes:
            return self.default_threshold

        # Get thresholds for each detected regime
        regime_thresholds = []
        for regime in detected_regimes:
            if regime in self.thresholds_by_regime:
                regime_thresholds.append(self.thresholds_by_regime[regime])
            else:
                regime_thresholds.append(self.default_threshold)

        # If multiple regimes, average the thresholds
        if len(regime_thresholds) == 1:
            return regime_thresholds[0]

        # Average thresholds across regimes
        avg_config = RegimeThresholdConfig(
            regime="_".join(detected_regimes),
            confidence_threshold=np.mean([t.confidence_threshold for t in regime_thresholds]),
            position_size_modifier=np.mean([t.position_size_modifier for t in regime_thresholds]),
            stop_loss_multiplier=np.mean([t.stop_loss_multiplier for t in regime_thresholds]),
            take_profit_multiplier=np.mean([t.take_profit_multiplier for t in regime_thresholds]),
            min_confidence=np.mean([t.min_confidence for t in regime_thresholds]),
            max_confidence=np.mean([t.max_confidence for t in regime_thresholds]),
        )
        return avg_config

    def adjust_for_uncertainty(
        self,
        base_thresholds: RegimeThresholdConfig,
        uncertainty: float
    ) -> RegimeThresholdConfig:
        """Widen thresholds under high uncertainty.

        Args:
            base_thresholds: Base threshold config
            uncertainty: Uncertainty level (0.0-1.0)

        Returns:
            Adjusted threshold config
        """
        # Increase confidence threshold under uncertainty
        confidence_adjustment = uncertainty * 0.2  # Up to +0.2
        new_threshold = min(0.95, base_thresholds.confidence_threshold + confidence_adjustment)

        # Reduce position size under uncertainty
        size_modifier = base_thresholds.position_size_modifier * (1.0 - uncertainty * 0.5)

        # Widen stop loss under uncertainty
        stop_loss_mult = base_thresholds.stop_loss_multiplier * (1.0 + uncertainty * 0.3)

        return RegimeThresholdConfig(
            regime=base_thresholds.regime,
            confidence_threshold=new_threshold,
            position_size_modifier=size_modifier,
            stop_loss_multiplier=stop_loss_mult,
            take_profit_multiplier=base_thresholds.take_profit_multiplier,
            min_confidence=base_thresholds.min_confidence,
            max_confidence=base_thresholds.max_confidence,
        )


# ============================================================================
# Cooldown and Hold Policy
# ============================================================================

@dataclass
class CooldownConfig:
    """Configuration for cooldown policy."""
    symbol: str
    volatility_bucket: str = "NORMAL"  # LOW, NORMAL, HIGH
    min_cooldown_minutes: int = 30
    max_cooldown_minutes: int = 240
    hold_period_minutes: int = 60
    max_consecutive_losses: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "volatility_bucket": self.volatility_bucket,
            "min_cooldown_minutes": self.min_cooldown_minutes,
            "max_cooldown_minutes": self.max_cooldown_minutes,
            "hold_period_minutes": self.hold_period_minutes,
            "max_consecutive_losses": self.max_consecutive_losses,
        }


@dataclass
class TradeRecord:
    """Record of a completed trade for cooldown tracking."""
    symbol: str
    exit_time: datetime
    pnl: float
    pnl_percent: float
    entry_time: datetime
    holding_period_minutes: int


class CooldownManager:
    """Track and enforce trading cooldowns."""

    def __init__(self, cooldown_configs: List[CooldownConfig]):
        """Initialize manager.

        Args:
            cooldown_configs: List of cooldown configs per symbol/volatility
        """
        self.configs_by_symbol = {c.symbol: c for c in cooldown_configs}
        self.default_config = CooldownConfig(symbol="DEFAULT")

        # Trade history for cooldown tracking
        self._trade_history: Dict[str, List[TradeRecord]] = {}
        self._last_exit_times: Dict[str, datetime] = {}
        self._consecutive_losses: Dict[str, int] = {}

    def record_trade(
        self,
        symbol: str,
        entry_time: datetime,
        exit_time: datetime,
        pnl: float,
        pnl_percent: float
    ) -> None:
        """Record a completed trade.

        Args:
            symbol: Trading pair symbol
            entry_time: Trade entry time
            exit_time: Trade exit time
            pnl: Trade PnL
            pnl_percent: Trade PnL percentage
        """
        holding_period = int((exit_time - entry_time).total_seconds() / 60)

        trade = TradeRecord(
            symbol=symbol,
            exit_time=exit_time,
            pnl=pnl,
            pnl_percent=pnl_percent,
            entry_time=entry_time,
            holding_period_minutes=holding_period,
        )

        # Add to history
        if symbol not in self._trade_history:
            self._trade_history[symbol] = []
        self._trade_history[symbol].append(trade)

        # Update last exit time
        self._last_exit_times[symbol] = exit_time

        # Update consecutive losses
        if pnl < 0:
            self._consecutive_losses[symbol] = self._consecutive_losses.get(symbol, 0) + 1
        else:
            self._consecutive_losses[symbol] = 0

        logger.info(f"[COOLDOWN] Recorded trade for {symbol}: PnL={pnl:.2f}, consecutive_losses={self._consecutive_losses.get(symbol, 0)}")

    def is_in_cooldown(self, symbol: str, current_time: datetime) -> bool:
        """Check if symbol is in cooldown period.

        Args:
            symbol: Trading pair symbol
            current_time: Current timestamp

        Returns:
            True if in cooldown
        """
        config = self.configs_by_symbol.get(symbol, self.default_config)

        if symbol not in self._last_exit_times:
            return False

        last_exit = self._last_exit_times[symbol]
        minutes_since_exit = (current_time - last_exit).total_seconds() / 60

        # Check consecutive losses
        consecutive_losses = self._consecutive_losses.get(symbol, 0)
        if consecutive_losses >= config.max_consecutive_losses:
            # Extended cooldown after consecutive losses
            extended_cooldown = config.max_cooldown_minutes * 1.5
            return minutes_since_exit < extended_cooldown

        # Normal cooldown
        return minutes_since_exit < config.min_cooldown_minutes

    def get_remaining_cooldown(self, symbol: str, current_time: datetime) -> int:
        """Get remaining cooldown time in seconds.

        Args:
            symbol: Trading pair symbol
            current_time: Current timestamp

        Returns:
            Remaining cooldown seconds (0 if not in cooldown)
        """
        if not self.is_in_cooldown(symbol, current_time):
            return 0

        config = self.configs_by_symbol.get(symbol, self.default_config)
        last_exit = self._last_exit_times.get(symbol)

        if last_exit is None:
            return 0

        minutes_since_exit = (current_time - last_exit).total_seconds() / 60

        # Check consecutive losses
        consecutive_losses = self._consecutive_losses.get(symbol, 0)
        cooldown_minutes = config.max_cooldown_minutes * 1.5 if consecutive_losses >= config.max_consecutive_losses else config.min_cooldown_minutes

        remaining_minutes = max(0, cooldown_minutes - minutes_since_exit)
        return int(remaining_minutes * 60)

    def get_hold_policy(self, symbol: str, volatility: str) -> CooldownConfig:
        """Get hold policy for symbol and volatility.

        Args:
            symbol: Trading pair symbol
            volatility: Volatility bucket (LOW, NORMAL, HIGH)

        Returns:
            CooldownConfig for symbol/volatility
        """
        config = self.configs_by_symbol.get(symbol)
        if config and config.volatility_bucket == volatility:
            return config

        # Return volatility-based default
        if volatility == "HIGH":
            return CooldownConfig(
                symbol=symbol,
                volatility_bucket="HIGH",
                min_cooldown_minutes=60,
                max_cooldown_minutes=360,
                hold_period_minutes=120,
            )
        elif volatility == "LOW":
            return CooldownConfig(
                symbol=symbol,
                volatility_bucket="LOW",
                min_cooldown_minutes=15,
                max_cooldown_minutes=120,
                hold_period_minutes=30,
            )
        else:
            return CooldownConfig(symbol=symbol, volatility_bucket="NORMAL")


# ============================================================================
# Calibration Drift Monitoring
# ============================================================================

class DriftLevel(str, Enum):
    """Drift alert levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DriftMetrics:
    """Drift measurement metrics."""
    timestamp: datetime
    population_stability_index: float  # PSI
    kl_divergence: float
    calibration_error_change: float
    days_since_calibration: int
    samples_analyzed: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "psi": self.population_stability_index,
            "kl_divergence": self.kl_divergence,
            "calibration_error_change": self.calibration_error_change,
            "days_since_calibration": self.days_since_calibration,
            "samples_analyzed": self.samples_analyzed,
        }


@dataclass
class DriftAlert:
    """Alert generated from drift detection."""
    level: DriftLevel
    drift_type: str
    description: str
    recommended_action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "drift_type": self.drift_type,
            "description": self.description,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp.isoformat(),
        }


class DriftMonitor:
    """Monitor calibration drift over time."""

    def __init__(
        self,
        psi_threshold: float = 0.2,
        kl_threshold: float = 0.3,
        ece_change_threshold: float = 0.1
    ):
        """Initialize monitor.

        Args:
            psi_threshold: PSI threshold for drift alert
            kl_threshold: KL divergence threshold
            ece_change_threshold: ECE change threshold
        """
        self.psi_threshold = psi_threshold
        self.kl_threshold = kl_threshold
        self.ece_change_threshold = ece_change_threshold

        self._baseline_distribution: Optional[np.ndarray] = None
        self._last_calibration_ece: Optional[float] = None
        self._calibration_time: Optional[datetime] = None
        self._alert_history: List[DriftAlert] = []

    def set_baseline(
        self,
        baseline_distribution: np.ndarray,
        calibration_ece: float,
        calibration_time: datetime
    ) -> None:
        """Set baseline distribution for drift comparison.

        Args:
            baseline_distribution: Baseline confidence/probability distribution
            calibration_ece: ECE at calibration time
            calibration_time: Time of last calibration
        """
        self._baseline_distribution = baseline_distribution
        self._last_calibration_ece = calibration_ece
        self._calibration_time = calibration_time

        logger.info(f"[DRIFT] Baseline set with {len(baseline_distribution)} samples, ECE={calibration_ece:.4f}")

    def compute_psi(
        self,
        expected_dist: np.ndarray,
        actual_dist: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """Compute Population Stability Index.

        PSI < 0.1: No significant change
        0.1 <= PSI < 0.2: Moderate change
        PSI >= 0.2: Significant change

        Args:
            expected_dist: Expected (baseline) distribution
            actual_dist: Actual (current) distribution
            n_bins: Number of bins for histogram

        Returns:
            PSI value
        """
        # Create histograms
        hist_expected, bin_edges = np.histogram(expected_dist, bins=n_bins, range=(0, 1), density=True)
        hist_actual, _ = np.histogram(actual_dist, bins=bin_edges, density=True)

        # Add small epsilon to avoid division by zero
        eps = 1e-10
        hist_expected = hist_expected + eps
        hist_actual = hist_actual + eps

        # Normalize
        hist_expected = hist_expected / np.sum(hist_expected)
        hist_actual = hist_actual / np.sum(hist_actual)

        # Compute PSI
        psi = np.sum((hist_actual - hist_expected) * np.log(hist_actual / hist_expected))
        return float(psi)

    def compute_kl_divergence(
        self,
        p_dist: np.ndarray,
        q_dist: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """Compute KL divergence between two distributions.

        Args:
            p_dist: First distribution (actual)
            q_dist: Second distribution (baseline)
            n_bins: Number of bins

        Returns:
            KL divergence value
        """
        # Create histograms
        hist_p, bin_edges = np.histogram(p_dist, bins=n_bins, range=(0, 1), density=True)
        hist_q, _ = np.histogram(q_dist, bins=bin_edges, density=True)

        # Add epsilon
        eps = 1e-10
        hist_p = hist_p + eps
        hist_q = hist_q + eps

        # Normalize
        hist_p = hist_p / np.sum(hist_p)
        hist_q = hist_q / np.sum(hist_q)

        # Compute KL divergence
        kl = np.sum(hist_p * np.log(hist_p / hist_q))
        return float(kl)

    def detect_drift(
        self,
        current_distribution: np.ndarray,
        current_ece: float
    ) -> Optional[DriftAlert]:
        """Detect drift and generate alert if needed.

        Args:
            current_distribution: Current confidence distribution
            current_ece: Current calibration error

        Returns:
            DriftAlert if drift detected, None otherwise
        """
        if self._baseline_distribution is None:
            logger.warning("[DRIFT] No baseline set, cannot detect drift")
            return None

        # Compute metrics
        psi = self.compute_psi(self._baseline_distribution, current_distribution)
        kl = self.compute_kl_divergence(current_distribution, self._baseline_distribution)

        ece_change = 0.0
        if self._last_calibration_ece is not None:
            ece_change = abs(current_ece - self._last_calibration_ece)

        # Determine drift level
        drift_score = 0.0
        drift_types = []

        if psi >= self.psi_threshold:
            drift_score += 1.0
            drift_types.append(f"PSI={psi:.3f}")
            logger.warning(f"[DRIFT] PSI drift detected: {psi:.3f}")

        if kl >= self.kl_threshold:
            drift_score += 1.0
            drift_types.append(f"KL={kl:.3f}")
            logger.warning(f"[DRIFT] KL drift detected: {kl:.3f}")

        if ece_change >= self.ece_change_threshold:
            drift_score += 1.0
            drift_types.append(f"ECE_change={ece_change:.3f}")
            logger.warning(f"[DRIFT] ECE drift detected: {ece_change:.3f}")

        if drift_score == 0:
            return None

        # Determine alert level
        if drift_score >= 3:
            level = DriftLevel.CRITICAL
        elif drift_score >= 2:
            level = DriftLevel.HIGH
        elif drift_score >= 1:
            level = DriftLevel.MEDIUM
        else:
            level = DriftLevel.LOW

        # Generate alert
        alert = DriftAlert(
            level=level,
            drift_type=", ".join(drift_types),
            description=f"Drift detected: {', '.join(drift_types)}",
            recommended_action=self._get_recommendation(level, drift_types),
        )

        self._alert_history.append(alert)
        logger.warning(f"[DRIFT] Alert generated: {alert.level.value} - {alert.description}")

        return alert

    def _get_recommendation(
        self,
        level: DriftLevel,
        drift_types: List[str]
    ) -> str:
        """Get recommended action for drift level."""
        if level == DriftLevel.CRITICAL:
            return "Immediate recalibration required. Consider pausing trading."
        elif level == DriftLevel.HIGH:
            return "Schedule recalibration within 24 hours. Monitor closely."
        elif level == DriftLevel.MEDIUM:
            return "Consider recalibration. Review recent performance."
        else:
            return "Continue monitoring. No immediate action required."

    def should_expire_artifacts(
        self,
        artifact_age_days: int,
        drift_level: float
    ) -> bool:
        """Decide if calibration artifacts should be expired.

        Args:
            artifact_age_days: Age of artifacts in days
            drift_level: Current drift level (0.0-1.0)

        Returns:
            True if artifacts should be expired
        """
        # Expire if old or high drift
        max_age_days = 30  # Maximum artifact age
        drift_expire_threshold = 0.5  # Drift level that triggers expiry

        if artifact_age_days >= max_age_days:
            logger.info(f"[DRIFT] Artifacts expired due to age ({artifact_age_days} days)")
            return True

        if drift_level >= drift_expire_threshold:
            logger.info(f"[DRIFT] Artifacts expired due to drift ({drift_level:.3f})")
            return True

        return False

    def get_metrics(
        self,
        current_distribution: np.ndarray,
        current_ece: float
    ) -> DriftMetrics:
        """Get current drift metrics."""
        psi = 0.0
        kl = 0.0
        ece_change = 0.0

        if self._baseline_distribution is not None:
            psi = self.compute_psi(self._baseline_distribution, current_distribution)
            kl = self.compute_kl_divergence(current_distribution, self._baseline_distribution)

        if self._last_calibration_ece is not None:
            ece_change = abs(current_ece - self._last_calibration_ece)

        days_since_cal = 0
        if self._calibration_time:
            days_since_cal = (datetime.now(timezone.utc) - self._calibration_time).days

        return DriftMetrics(
            timestamp=datetime.now(timezone.utc),
            population_stability_index=psi,
            kl_divergence=kl,
            calibration_error_change=ece_change,
            days_since_calibration=days_since_cal,
            samples_analyzed=len(current_distribution),
        )

    def get_alert_history(self) -> List[DriftAlert]:
        """Get history of drift alerts."""
        return self._alert_history.copy()


# ============================================================================
# Factory Functions
# ============================================================================

def create_threshold_scheduler(
    threshold_configs: Optional[List[RegimeThresholdConfig]] = None
) -> ThresholdScheduler:
    """Create threshold scheduler."""
    if threshold_configs is None:
        threshold_configs = [
            RegimeThresholdConfig(regime="VOL_LOW", confidence_threshold=0.5),
            RegimeThresholdConfig(regime="VOL_NORMAL", confidence_threshold=0.6),
            RegimeThresholdConfig(regime="VOL_HIGH", confidence_threshold=0.7),
        ]
    return ThresholdScheduler(threshold_configs)


def create_cooldown_manager(
    cooldown_configs: Optional[List[CooldownConfig]] = None
) -> CooldownManager:
    """Create cooldown manager."""
    if cooldown_configs is None:
        cooldown_configs = [
            CooldownConfig(symbol="BTCUSDT", volatility_bucket="NORMAL"),
            CooldownConfig(symbol="ETHUSDT", volatility_bucket="NORMAL"),
        ]
    return CooldownManager(cooldown_configs)


def create_drift_monitor(
    psi_threshold: float = 0.2,
    kl_threshold: float = 0.3,
    ece_change_threshold: float = 0.1
) -> DriftMonitor:
    """Create drift monitor."""
    return DriftMonitor(
        psi_threshold=psi_threshold,
        kl_threshold=kl_threshold,
        ece_change_threshold=ece_change_threshold,
    )


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Test threshold scheduler
    scheduler = create_threshold_scheduler()
    thresholds = scheduler.get_thresholds(["VOL_NORMAL"])
    print(f"Thresholds for VOL_NORMAL: confidence={thresholds.confidence_threshold}")

    # Test cooldown manager
    cooldown_mgr = create_cooldown_manager()
    cooldown_mgr.record_trade(
        symbol="BTCUSDT",
        entry_time=datetime.now(timezone.utc) - timedelta(hours=2),
        exit_time=datetime.now(timezone.utc),
        pnl=-100.0,
        pnl_percent=-0.01,
    )
    in_cooldown = cooldown_mgr.is_in_cooldown("BTCUSDT", datetime.now(timezone.utc))
    print(f"BTCUSDT in cooldown: {in_cooldown}")

    # Test drift monitor
    drift_monitor = create_drift_monitor()
    baseline = np.random.beta(2, 2, 1000)
    drift_monitor.set_baseline(baseline, calibration_ece=0.05, calibration_time=datetime.now(timezone.utc))

    current = np.random.beta(2.5, 2, 1000)  # Slightly shifted
    alert = drift_monitor.detect_drift(current, current_ece=0.08)
    if alert:
        print(f"Drift alert: {alert.level.value} - {alert.description}")
