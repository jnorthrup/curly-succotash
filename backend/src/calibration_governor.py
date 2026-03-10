"""
Calibration Governor

Decides when calibration should run based on multiple triggers:
- Scheduled cadence (min/max time between calibrations)
- Drift detection (calibration drift exceeds threshold)
- Performance drop (recent performance degradation)
- Regime change (market regime shifted)

Prevents excessive calibration while ensuring timely updates when needed.

Key Features:
- Multi-trigger decision system
- Configurable thresholds and cadences
- Decision logging with reasons
- Cooldown mechanism to prevent thrashing

Example:
    config = GovernorConfig(
        min_hours_between_calibration=24,
        max_hours_between_calibration=168,
        drift_threshold=0.15
    )
    governor = CalibrationGovernor(config)
    should_calibrate, trigger = governor.should_calibrate(
        last_calibration_time=last_cal,
        current_drift=0.18,
        recent_performance=0.85,
        regime_changed=False
    )
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class CalibrationTrigger(Enum):
    """Reasons for triggering calibration."""
    SCHEDULED = "scheduled"
    DRIFT_DETECTED = "drift_detected"
    PERFORMANCE_DROP = "performance_drop"
    REGIME_CHANGE = "regime_change"
    MANUAL = "manual"
    INITIAL = "initial"  # First-time calibration


class CalibrationOutcome(Enum):
    """Calibration decision outcomes."""
    CALIBRATE = "calibrate"
    SKIP = "skip"
    DEFER = "defer"  # Defer to next check


@dataclass
class GovernorConfig:
    """Configuration for calibration governor.

    Attributes:
        min_hours_between_calibration: Minimum hours between calibration runs
        max_hours_between_calibration: Maximum hours before forced calibration
        drift_threshold: Drift level that triggers calibration (0.0-1.0)
        drift_window_hours: Window for drift calculation
        performance_drop_threshold: Performance drop that triggers calibration
        performance_window_hours: Window for performance calculation
        trigger_on_regime_change: Whether regime changes trigger calibration
        min_samples_in_regime: Minimum samples before calibrating in new regime
        cooldown_after_calibration_hours: Cooldown period after calibration
        enable_drift_detection: Enable drift-based triggers
        enable_performance_triggers: Enable performance-based triggers
    """
    min_hours_between_calibration: int = 24
    max_hours_between_calibration: int = 168  # 1 week
    drift_threshold: float = 0.15
    drift_window_hours: int = 6
    performance_drop_threshold: float = 0.20
    performance_window_hours: int = 12
    trigger_on_regime_change: bool = True
    min_samples_in_regime: int = 100
    cooldown_after_calibration_hours: int = 2
    enable_drift_detection: bool = True
    enable_performance_triggers: bool = True
    check_cadence_cycles: int = 100

    def __post_init__(self):
        """Validate configuration."""
        if self.min_hours_between_calibration < 1:
            raise ValueError("min_hours_between_calibration must be >= 1")
        if self.max_hours_between_calibration < self.min_hours_between_calibration:
            raise ValueError("max_hours must be >= min_hours")
        if not 0.0 <= self.drift_threshold <= 1.0:
            raise ValueError("drift_threshold must be in [0.0, 1.0]")
        if not 0.0 <= self.performance_drop_threshold <= 1.0:
            raise ValueError("performance_drop_threshold must be in [0.0, 1.0]")
        if self.check_cadence_cycles < 1:
            raise ValueError("check_cadence_cycles must be >= 1")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "min_hours_between_calibration": self.min_hours_between_calibration,
            "max_hours_between_calibration": self.max_hours_between_calibration,
            "drift_threshold": self.drift_threshold,
            "drift_window_hours": self.drift_window_hours,
            "performance_drop_threshold": self.performance_drop_threshold,
            "performance_window_hours": self.performance_window_hours,
            "trigger_on_regime_change": self.trigger_on_regime_change,
            "min_samples_in_regime": self.min_samples_in_regime,
            "cooldown_after_calibration_hours": self.cooldown_after_calibration_hours,
            "enable_drift_detection": self.enable_drift_detection,
            "enable_performance_triggers": self.enable_performance_triggers,
            "check_cadence_cycles": self.check_cadence_cycles,
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "GovernorConfig":
        """Create config from dictionary."""
        return cls(
            min_hours_between_calibration=config.get("min_hours_between_calibration", 24),
            max_hours_between_calibration=config.get("max_hours_between_calibration", 168),
            drift_threshold=config.get("drift_threshold", 0.15),
            drift_window_hours=config.get("drift_window_hours", 6),
            performance_drop_threshold=config.get("performance_drop_threshold", 0.20),
            performance_window_hours=config.get("performance_window_hours", 12),
            trigger_on_regime_change=config.get("trigger_on_regime_change", True),
            min_samples_in_regime=config.get("min_samples_in_regime", 100),
            cooldown_after_calibration_hours=config.get("cooldown_after_calibration_hours", 2),
            enable_drift_detection=config.get("enable_drift_detection", True),
            enable_performance_triggers=config.get("enable_performance_triggers", True),
            check_cadence_cycles=config.get("check_cadence_cycles", 100),
        )


@dataclass
class CalibrationDecision:
    """Result of governor decision."""
    decision: CalibrationOutcome
    trigger: Optional[CalibrationTrigger]
    reason: str
    confidence: float  # 0.0-1.0 confidence in decision
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "decision": self.decision.value,
            "trigger": self.trigger.value if self.trigger else None,
            "reason": self.reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class CalibrationGovernor:
    """Decides when calibration should run.

    Evaluates multiple triggers:
    1. Scheduled cadence (min/max time)
    2. Drift detection
    3. Performance drop
    4. Regime change

    Example:
        config = GovernorConfig()
        governor = CalibrationGovernor(config)
        decision = governor.should_calibrate(
            last_calibration_time=last_cal,
            current_drift=0.18,
            recent_performance=0.85,
            regime_changed=False
        )
    """

    def __init__(self, config: Optional[GovernorConfig] = None):
        """Initialize governor.

        Args:
            config: Governor configuration (uses defaults if None)
        """
        self.config = config or GovernorConfig()
        self._decision_history: List[CalibrationDecision] = []
        self._last_calibration_time: Optional[datetime] = None
        self._regime_sample_counts: Dict[str, int] = {}
        self._initial_calibration_triggered: bool = False  # Track if initial calibration has been triggered
        self._cycles_since_last_check: int = 0

    def should_recalibrate(
        self,
        current_time: datetime,
        performance_drop: bool = False,
        drift_detected: bool = False,
        force_recalibrate: bool = False
    ) -> CalibrationDecision:
        """Alias for should_calibrate with simplified boolean triggers.
        
        Matches the signature expected by CoinbaseTradingSimulator.
        """
        if force_recalibrate:
            return self._create_decision(
                CalibrationOutcome.CALIBRATE,
                CalibrationTrigger.MANUAL,
                "Manual forced recalibration",
                confidence=1.0
            )
            
        return self.should_calibrate(
            last_calibration_time=self._last_calibration_time,
            current_drift=self.config.drift_threshold if drift_detected else 0.0,
            recent_performance=1.0 - self.config.performance_drop_threshold if performance_drop else 1.0,
            regime_changed=False,
            current_time=current_time
        )

    def should_calibrate(
        self,
        last_calibration_time: Optional[datetime],
        current_drift: float,
        recent_performance: float,
        regime_changed: bool,
        current_regime: Optional[str] = None,
        samples_in_regime: int = 0,
        current_time: Optional[datetime] = None
    ) -> CalibrationDecision:
        """Evaluate triggers and decide if calibration is needed.

        Args:
            last_calibration_time: Time of last calibration (None if never)
            current_drift: Current calibration drift (0.0-1.0)
            recent_performance: Recent performance metric (0.0-1.0)
            regime_changed: Whether regime changed since last calibration
            current_regime: Current regime name
            samples_in_regime: Number of samples in current regime
            current_time: Current simulation time (defaults to now)

        Returns:
            CalibrationDecision with decision and reason
        """
        now = current_time or datetime.now(timezone.utc)
        
        # Only update _last_calibration_time if a valid time is passed.
        # This prevents recalibration from being treated as perpetual initial calibration
        # when last_calibration_time=None is passed but we already have a recorded time.
        if last_calibration_time is not None:
            self._last_calibration_time = last_calibration_time

        # Check if this is initial calibration
        if last_calibration_time is None:
            # If we've already triggered initial calibration but haven't recorded it,
            # return SKIP to avoid repeated CALIBRATE responses (bounded runtime behavior)
            if self._initial_calibration_triggered:
                return self._create_decision(
                    CalibrationOutcome.SKIP,
                    CalibrationTrigger.INITIAL,
                    "Initial calibration already triggered, waiting for record_calibration",
                    confidence=1.0
                )
            # First time seeing None - trigger initial calibration
            self._initial_calibration_triggered = True
            return self._create_decision(
                CalibrationOutcome.CALIBRATE,
                CalibrationTrigger.INITIAL,
                "Initial calibration required",
                confidence=1.0
            )

        # Increment cycles
        self._cycles_since_last_check += 1

        # Check cadence
        if self._cycles_since_last_check < self.config.check_cadence_cycles:
            return self._create_decision(
                CalibrationOutcome.SKIP,
                None,
                f"Cadence not met ({self._cycles_since_last_check} < {self.config.check_cadence_cycles})",
                confidence=1.0
            )

        # If we reached here, it's a "full evaluation"
        self._cycles_since_last_check = 0

        # Check cooldown period
        hours_since_cal = (now - last_calibration_time).total_seconds() / 3600
        if hours_since_cal < self.config.cooldown_after_calibration_hours:
            return self._create_decision(
                CalibrationOutcome.SKIP,
                None,
                f"In cooldown period ({hours_since_cal:.1f}h < {self.config.cooldown_after_calibration_hours}h)",
                confidence=1.0
            )

        # Check minimum time between calibration
        if hours_since_cal < self.config.min_hours_between_calibration:
            return self._create_decision(
                CalibrationOutcome.SKIP,
                None,
                f"Minimum interval not reached ({hours_since_cal:.1f}h < {self.config.min_hours_between_calibration}h)",
                confidence=0.9
            )

        # Check maximum time (forced calibration)
        if hours_since_cal >= self.config.max_hours_between_calibration:
            return self._create_decision(
                CalibrationOutcome.CALIBRATE,
                CalibrationTrigger.SCHEDULED,
                f"Maximum interval exceeded ({hours_since_cal:.1f}h >= {self.config.max_hours_between_calibration}h)",
                confidence=1.0,
                metadata={"hours_since_calibration": hours_since_cal}
            )

        # Check drift trigger
        if self.config.enable_drift_detection and current_drift >= self.config.drift_threshold:
            return self._create_decision(
                CalibrationOutcome.CALIBRATE,
                CalibrationTrigger.DRIFT_DETECTED,
                f"Drift threshold exceeded ({current_drift:.3f} >= {self.config.drift_threshold})",
                confidence=min(1.0, current_drift / self.config.drift_threshold),
                metadata={"drift": current_drift}
            )

        # Check performance trigger
        if self.config.enable_performance_triggers and recent_performance <= (1.0 - self.config.performance_drop_threshold):
            return self._create_decision(
                CalibrationOutcome.CALIBRATE,
                CalibrationTrigger.PERFORMANCE_DROP,
                f"Performance drop detected ({recent_performance:.3f} <= {1.0 - self.config.performance_drop_threshold:.3f})",
                confidence=min(1.0, (1.0 - recent_performance) / self.config.performance_drop_threshold),
                metadata={"performance": recent_performance}
            )

        # Check regime change trigger
        if self.config.trigger_on_regime_change and regime_changed:
            if current_regime:
                # Track samples in new regime
                self._regime_sample_counts[current_regime] = \
                    self._regime_sample_counts.get(current_regime, 0) + 1

                samples = self._regime_sample_counts[current_regime]
                if samples >= self.config.min_samples_in_regime:
                    return self._create_decision(
                        CalibrationOutcome.CALIBRATE,
                        CalibrationTrigger.REGIME_CHANGE,
                        f"Regime change with sufficient samples ({samples} >= {self.config.min_samples_in_regime})",
                        confidence=min(1.0, samples / self.config.min_samples_in_regime),
                        metadata={"regime": current_regime, "samples": samples}
                    )
                else:
                    return self._create_decision(
                        CalibrationOutcome.DEFER,
                        CalibrationTrigger.REGIME_CHANGE,
                        f"Regime change but insufficient samples ({samples} < {self.config.min_samples_in_regime})",
                        confidence=0.5,
                        metadata={"regime": current_regime, "samples": samples}
                    )
            else:
                return self._create_decision(
                    CalibrationOutcome.CALIBRATE,
                    CalibrationTrigger.REGIME_CHANGE,
                    "Regime change detected",
                    confidence=0.8
                )

        # No triggers met - skip
        return self._create_decision(
            CalibrationOutcome.SKIP,
            None,
            f"No triggers met (drift={current_drift:.3f}, perf={recent_performance:.3f}, regime_changed={regime_changed})",
            confidence=0.7,
            metadata={
                "drift": current_drift,
                "performance": recent_performance,
                "regime_changed": regime_changed,
                "hours_since_calibration": hours_since_cal,
            }
        )

    def _create_decision(
        self,
        decision: CalibrationOutcome,
        trigger: Optional[CalibrationTrigger],
        reason: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CalibrationDecision:
        """Create and record a calibration decision."""
        cal_decision = CalibrationDecision(
            decision=decision,
            trigger=trigger,
            reason=reason,
            confidence=confidence,
            metadata=metadata or {}
        )

        self._decision_history.append(cal_decision)

        # Log decision
        log_level = logging.INFO if decision == CalibrationOutcome.SKIP else logging.WARNING
        logger.log(log_level, f"[GOVERNOR] {decision.value}: {reason}")

        return cal_decision

    def record_calibration(self, calibration_time: Optional[datetime] = None) -> None:
        """Record that calibration was performed.

        Args:
            calibration_time: Time of calibration (defaults to now)
        """
        if calibration_time is None:
            calibration_time = datetime.now(timezone.utc)
        self._last_calibration_time = calibration_time
        
        # Reset the initial calibration triggered flag since calibration is now recorded
        self._initial_calibration_triggered = False

        # Reset cycle counter
        self._cycles_since_last_check = 0

        # Reset regime sample counts
        self._regime_sample_counts.clear()

        logger.info(f"[GOVERNOR] Calibration recorded at {calibration_time}")

    def get_decision_history(self) -> List[CalibrationDecision]:
        """Get history of calibration decisions."""
        return self._decision_history.copy()

    def get_last_calibration(self) -> Optional[datetime]:
        """Get time of last calibration."""
        return self._last_calibration_time

    def get_hours_until_next_allowed(self) -> float:
        """Get hours until next calibration is allowed."""
        if self._last_calibration_time is None:
            return 0.0

        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_calibration_time).total_seconds() / 3600
        remaining = self.config.min_hours_between_calibration - elapsed
        return max(0.0, remaining)

    def get_hours_until_forced(self) -> float:
        """Get hours until calibration is forced (max interval)."""
        if self._last_calibration_time is None:
            return 0.0

        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_calibration_time).total_seconds() / 3600
        remaining = self.config.max_hours_between_calibration - elapsed
        return max(0.0, remaining)

    def is_artifact_fresh(self, artifact_path: str, max_age_hours: float = 168.0) -> bool:
        """Check if artifact file exists and is fresh based on modification time.
        
        Args:
            artifact_path: Path to artifact file
            max_age_hours: Maximum age in hours (default 7 days = 168 hours)
            
        Returns:
            True if file exists and was modified within max_age_hours, False otherwise
        """
        try:
            if not os.path.exists(artifact_path):
                return False
                
            mtime = os.path.getmtime(artifact_path)
            mod_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - mod_time).total_seconds() / 3600
            
            return age_hours <= max_age_hours
            
        except (OSError, ValueError):
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get governor status summary."""
        hours_since = 0.0
        if self._last_calibration_time:
            hours_since = (datetime.now(timezone.utc) - self._last_calibration_time).total_seconds() / 3600

        return {
            "last_calibration": self._last_calibration_time.isoformat() if self._last_calibration_time else None,
            "hours_since_calibration": hours_since,
            "hours_until_next_allowed": self.get_hours_until_next_allowed(),
            "hours_until_forced": self.get_hours_until_forced(),
            "config": self.config.to_dict(),
            "decisions_made": len(self._decision_history),
        }

    def save_status(self, filepath: str) -> None:
        """Save governor status to JSON file."""
        status = self.get_status()
        with open(filepath, 'w') as f:
            json.dump(status, f, indent=2)
        logger.info(f"[GOVERNOR] Status saved to {filepath}")


def create_calibration_governor(
    config: Optional[GovernorConfig] = None,
    config_path: Optional[str] = None
) -> CalibrationGovernor:
    """Factory function to create calibration governor.

    Args:
        config: Optional config object
        config_path: Optional path to config JSON

    Returns:
        CalibrationGovernor instance
    """
    if config is None:
        if config_path:
            config = GovernorConfig.from_dict(json.load(open(config_path)))
        else:
            config = GovernorConfig()

    return CalibrationGovernor(config)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    config = GovernorConfig(
        min_hours_between_calibration=24,
        max_hours_between_calibration=168,
        drift_threshold=0.15,
    )

    governor = CalibrationGovernor(config)

    # Simulate decision making
    last_cal = datetime.now(timezone.utc) - timedelta(hours=48)

    decision = governor.should_calibrate(
        last_calibration_time=last_cal,
        current_drift=0.18,
        recent_performance=0.85,
        regime_changed=False
    )

    print(f"Decision: {decision.decision.value}")
    print(f"Trigger: {decision.trigger.value if decision.trigger else 'None'}")
    print(f"Reason: {decision.reason}")
    print(f"Confidence: {decision.confidence:.2f}")
