"""
Drawdown Kill-Switch

Hard circuit breaker that halts trading when drawdown limits are exceeded.
Protects against catastrophic losses during adverse market conditions.

Features:
- Daily loss limit
- Cumulative loss limit
- Consecutive loss counter
- Volatility spike detection
- Automatic trading halt
- Manual reset required after trigger
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class KillSwitchState(str, Enum):
    """Kill switch states."""
    ACTIVE = "active"  # Trading allowed
    WARNING = "warning"  # Approaching limits
    TRIGGERED = "triggered"  # Trading halted
    COOLDOWN = "cooldown"  # Post-trigger monitoring


class KillSwitchReason(str, Enum):
    """Reasons for kill switch trigger."""
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    CUMULATIVE_LOSS_LIMIT = "cumulative_loss_limit"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    VOLATILITY_SPIKE = "volatility_spike"
    MANUAL_HALT = "manual_halt"
    SYSTEM_ERROR = "system_error"


@dataclass
class KillSwitchConfig:
    """Kill switch configuration."""
    # Loss limits
    daily_loss_limit_pct: float = 3.0  # Max daily loss %
    cumulative_loss_limit_pct: float = 10.0  # Max total loss %

    # Consecutive losses
    max_consecutive_losses: int = 5

    # Volatility spike
    volatility_spike_multiplier: float = 3.0  # Trigger if vol > 3x normal
    volatility_window_days: int = 30  # Days for normal vol calculation

    # Cooldown
    cooldown_hours: int = 24  # Hours before can restart

    # Logging
    log_all_events: bool = True
    output_dir: str = "/Users/jim/work/curly-succotash/logs/killswitch"


@dataclass
class KillSwitchEvent:
    """Kill switch state change event."""
    timestamp: datetime
    previous_state: KillSwitchState
    new_state: KillSwitchState
    reason: Optional[KillSwitchReason]
    trigger_value: Optional[float]
    threshold_value: Optional[float]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "reason": self.reason.value if self.reason else None,
            "trigger_value": self.trigger_value,
            "threshold_value": self.threshold_value,
            "message": self.message,
        }


@dataclass
class KillSwitchMetrics:
    """Current kill switch metrics."""
    state: KillSwitchState
    daily_pnl_pct: float
    cumulative_pnl_pct: float
    consecutive_losses: int
    current_volatility: float
    normal_volatility: float
    volatility_ratio: float
    last_trigger_event: Optional[KillSwitchEvent]
    triggered_at: Optional[datetime]
    cooldown_ends_at: Optional[datetime]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "daily_pnl_pct": self.daily_pnl_pct,
            "cumulative_pnl_pct": self.cumulative_pnl_pct,
            "consecutive_losses": self.consecutive_losses,
            "current_volatility": self.current_volatility,
            "normal_volatility": self.normal_volatility,
            "volatility_ratio": self.volatility_ratio,
            "last_trigger_event": self.last_trigger_event.to_dict() if self.last_trigger_event else None,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "cooldown_ends_at": self.cooldown_ends_at.isoformat() if self.cooldown_ends_at else None,
        }


class DrawdownKillSwitch:
    """
    Hard drawdown kill-switch for trading protection.

    Monitors trading performance and automatically halts trading
    when predefined loss limits are exceeded.

    Example:
        config = KillSwitchConfig(
            daily_loss_limit_pct=3.0,
            cumulative_loss_limit_pct=10.0,
            max_consecutive_losses=5
        )
        killswitch = DrawdownKillSwitch(config, initial_capital=10000.0)

        # After each trade
        killswitch.record_trade(pnl=-50.0, pnl_pct=-0.5)

        # Check if trading is allowed
        if not killswitch.is_trading_allowed():
            logger.warning("Trading halted by kill-switch")
    """

    def __init__(self, config: KillSwitchConfig, initial_capital: float):
        self.config = config
        self.initial_capital = initial_capital

        # State
        self._state = KillSwitchState.ACTIVE
        self._daily_pnl = 0.0
        self._cumulative_pnl = 0.0
        self._consecutive_losses = 0
        self._current_volatility = 0.0
        self._normal_volatility = 0.0

        # Trigger tracking
        self._triggered_at: Optional[datetime] = None
        self._cooldown_ends_at: Optional[datetime] = None
        self._last_trigger_event: Optional[KillSwitchEvent] = None

        # History
        self._daily_pnl_history: List[float] = []
        self._event_log: List[KillSwitchEvent] = []

        # Initialize output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"[KILLSWITCH] Initialized with capital ${initial_capital:,.2f}")
        logger.info(f"[KILLSWITCH] Daily limit: {config.daily_loss_limit_pct}%")
        logger.info(f"[KILLSWITCH] Cumulative limit: {config.cumulative_loss_limit_pct}%")
        logger.info(f"[KILLSWITCH] Max consecutive losses: {config.max_consecutive_losses}")

    def record_trade(
        self,
        pnl: float,
        pnl_pct: float,
        symbol: str = "UNKNOWN",
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Record a trade and check kill-switch conditions.

        Args:
            pnl: Trade PnL in dollars
            pnl_pct: Trade PnL as percentage
            symbol: Trade symbol
            timestamp: Trade timestamp
        """
        timestamp = timestamp or datetime.now(timezone.utc)

        # Update daily and cumulative PnL before evaluating triggers.
        self._daily_pnl += pnl
        # Update cumulative PnL
        self._cumulative_pnl += pnl

        # Update consecutive losses
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        # Check all trigger conditions
        triggers = self._check_triggers(pnl_pct, timestamp)

        if triggers:
            self._trigger(triggers[0], timestamp)

        # Log trade
        if self.config.log_all_events:
            logger.debug(
                f"[KILLSWITCH] Trade recorded: {symbol} PnL=${pnl:.2f} ({pnl_pct:.2f}%) | "
                f"Daily: ${self._daily_pnl:.2f} | Cumulative: ${self._cumulative_pnl:.2f} | "
                f"Consecutive losses: {self._consecutive_losses}"
            )

    def start_new_trading_day(self, daily_pnl_pct: float = 0.0) -> None:
        """
        Start a new trading day.

        Args:
            daily_pnl_pct: Previous day's PnL percentage (for history)
        """
        # Archive previous day's PnL
        if hasattr(self, '_daily_pnl') and self._daily_pnl != 0:
            self._daily_pnl_history.append(self._daily_pnl / self.initial_capital * 100.0)

        # Reset daily PnL
        self._daily_pnl = 0.0

        # Update volatility metrics
        self._update_volatility()

        logger.info(
            f"[KILLSWITCH] New trading day started | "
            f"Previous day PnL: {daily_pnl_pct:.2f}% | "
            f"State: {self._state.value}"
        )

    def _check_triggers(
        self,
        trade_pnl_pct: float,
        timestamp: datetime
    ) -> List[KillSwitchReason]:
        """Check all trigger conditions."""
        triggers = []

        # Calculate current daily PnL percentage
        daily_pnl_pct = (self._daily_pnl / self.initial_capital) * 100.0

        # 1. Daily loss limit
        if daily_pnl_pct <= -self.config.daily_loss_limit_pct:
            triggers.append(KillSwitchReason.DAILY_LOSS_LIMIT)
            logger.warning(
                f"[KILLSWITCH] Daily loss limit reached: {daily_pnl_pct:.2f}% "
                f"(limit: -{self.config.daily_loss_limit_pct}%)"
            )

        # 2. Cumulative loss limit
        cumulative_pnl_pct = (self._cumulative_pnl / self.initial_capital) * 100.0
        if cumulative_pnl_pct <= -self.config.cumulative_loss_limit_pct:
            triggers.append(KillSwitchReason.CUMULATIVE_LOSS_LIMIT)
            logger.warning(
                f"[KILLSWITCH] Cumulative loss limit reached: {cumulative_pnl_pct:.2f}% "
                f"(limit: -{self.config.cumulative_loss_limit_pct}%)"
            )

        # 3. Consecutive losses
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            triggers.append(KillSwitchReason.CONSECUTIVE_LOSSES)
            logger.warning(
                f"[KILLSWITCH] Consecutive losses limit: {self._consecutive_losses} "
                f"(limit: {self.config.max_consecutive_losses})"
            )

        # 4. Volatility spike
        if (self._current_volatility > 0 and self._normal_volatility > 0 and
            self._current_volatility / self._normal_volatility > self.config.volatility_spike_multiplier):
            triggers.append(KillSwitchReason.VOLATILITY_SPIKE)
            logger.warning(
                f"[KILLSWITCH] Volatility spike detected: {self._current_volatility:.2f} "
                f"(normal: {self._normal_volatility:.2f}, multiplier: {self._current_volatility/self._normal_volatility:.2f}x)"
            )

        return triggers

    def _trigger(
        self,
        reason: KillSwitchReason,
        timestamp: datetime
    ) -> None:
        """Trigger the kill-switch."""
        if self._state == KillSwitchState.TRIGGERED:
            return  # Already triggered

        previous_state = self._state
        self._state = KillSwitchState.TRIGGERED
        self._triggered_at = timestamp
        self._cooldown_ends_at = timestamp + timedelta(hours=self.config.cooldown_hours)

        # Get threshold value for logging
        threshold_value = self._get_threshold_for_reason(reason)
        trigger_value = self._get_trigger_value_for_reason(reason)

        event = KillSwitchEvent(
            timestamp=timestamp,
            previous_state=previous_state,
            new_state=KillSwitchState.TRIGGERED,
            reason=reason,
            trigger_value=trigger_value,
            threshold_value=threshold_value,
            message=f"Kill-switch triggered: {reason.value}"
        )

        self._last_trigger_event = event
        self._event_log.append(event)

        logger.critical(
            f"[KILLSWITCH] ⚠️ TRIGGERED ⚠️ | Reason: {reason.value} | "
            f"Time: {timestamp.isoformat()} | "
            f"Cooldown ends: {self._cooldown_ends_at.isoformat()}"
        )

        # Save trigger event
        self._save_trigger_event(event)

    def _get_threshold_for_reason(self, reason: KillSwitchReason) -> Optional[float]:
        """Get threshold value for a trigger reason."""
        if reason == KillSwitchReason.DAILY_LOSS_LIMIT:
            return -self.config.daily_loss_limit_pct
        elif reason == KillSwitchReason.CUMULATIVE_LOSS_LIMIT:
            return -self.config.cumulative_loss_limit_pct
        elif reason == KillSwitchReason.CONSECUTIVE_LOSSES:
            return float(self.config.max_consecutive_losses)
        elif reason == KillSwitchReason.VOLATILITY_SPIKE:
            return self.config.volatility_spike_multiplier
        return None

    def _get_trigger_value_for_reason(self, reason: KillSwitchReason) -> Optional[float]:
        """Get actual trigger value for a reason."""
        if reason == KillSwitchReason.DAILY_LOSS_LIMIT:
            return (self._daily_pnl / self.initial_capital) * 100.0
        elif reason == KillSwitchReason.CUMULATIVE_LOSS_LIMIT:
            return (self._cumulative_pnl / self.initial_capital) * 100.0
        elif reason == KillSwitchReason.CONSECUTIVE_LOSSES:
            return float(self._consecutive_losses)
        elif reason == KillSwitchReason.VOLATILITY_SPIKE:
            return self._current_volatility / self._normal_volatility if self._normal_volatility > 0 else None
        return None

    def _update_volatility(self) -> None:
        """Update volatility metrics from recent PnL history."""
        if len(self._daily_pnl_history) < self.config.volatility_window_days:
            # Not enough history
            return

        # Calculate standard deviation of recent PnL
        import statistics
        recent_pnl = self._daily_pnl_history[-self.config.volatility_window_days:]

        if len(recent_pnl) > 1:
            self._normal_volatility = statistics.stdev(recent_pnl)

        # Current volatility (recent 7 days if available)
        if len(self._daily_pnl_history) >= 7:
            recent_7d = self._daily_pnl_history[-7:]
            self._current_volatility = statistics.stdev(recent_7d)
        else:
            self._current_volatility = self._normal_volatility

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        if self._state == KillSwitchState.TRIGGERED:
            # Check if cooldown has expired
            if datetime.now(timezone.utc) >= self._cooldown_ends_at:
                logger.info("[KILLSWITCH] Cooldown expired, transitioning to COOLDOWN state")
                self._state = KillSwitchState.COOLDOWN
                return True
            return False

        return self._state in [KillSwitchState.ACTIVE, KillSwitchState.COOLDOWN, KillSwitchState.WARNING]

    def manual_halt(self, reason: str = "Manual halt requested") -> None:
        """Manually halt trading."""
        timestamp = datetime.now(timezone.utc)

        event = KillSwitchEvent(
            timestamp=timestamp,
            previous_state=self._state,
            new_state=KillSwitchState.TRIGGERED,
            reason=KillSwitchReason.MANUAL_HALT,
            trigger_value=None,
            threshold_value=None,
            message=reason
        )

        self._state = KillSwitchState.TRIGGERED
        self._triggered_at = timestamp
        self._cooldown_ends_at = timestamp + timedelta(hours=self.config.cooldown_hours)
        self._last_trigger_event = event
        self._event_log.append(event)

        logger.warning(f"[KILLSWITCH] Manual halt: {reason}")
        self._save_trigger_event(event)

    def manual_reset(self) -> None:
        """Manually reset the kill-switch (after cooldown)."""
        if self._state != KillSwitchState.TRIGGERED:
            logger.warning("[KILLSWITCH] Cannot reset - not in TRIGGERED state")
            return

        if datetime.now(timezone.utc) < self._cooldown_ends_at:
            logger.warning(
                f"[KILLSWITCH] Cannot reset - cooldown still active until {self._cooldown_ends_at.isoformat()}"
            )
            return

        self._state = KillSwitchState.ACTIVE
        self._triggered_at = None
        self._cooldown_ends_at = None

        logger.info("[KILLSWITCH] Manually reset - trading resumed")

    def get_metrics(self) -> KillSwitchMetrics:
        """Get current kill-switch metrics."""
        return KillSwitchMetrics(
            state=self._state,
            daily_pnl_pct=(self._daily_pnl / self.initial_capital) * 100.0,
            cumulative_pnl_pct=(self._cumulative_pnl / self.initial_capital) * 100.0,
            consecutive_losses=self._consecutive_losses,
            current_volatility=self._current_volatility,
            normal_volatility=self._normal_volatility,
            volatility_ratio=(
                self._current_volatility / self._normal_volatility
                if self._normal_volatility > 0 else 0.0
            ),
            last_trigger_event=self._last_trigger_event,
            triggered_at=self._triggered_at,
            cooldown_ends_at=self._cooldown_ends_at,
        )

    def _save_trigger_event(self, event: KillSwitchEvent) -> None:
        """Save trigger event to file."""
        filepath = Path(self.config.output_dir) / f"trigger_{event.timestamp.strftime('%Y%m%d_%H%M%S')}.json"

        with open(filepath, 'w') as f:
            json.dump(event.to_dict(), f, indent=2)

        logger.info(f"[KILLSWITCH] Trigger event saved: {filepath}")

    def save_daily_log(self, date: datetime) -> str:
        """Save daily kill-switch log."""
        date_str = date.strftime("%Y-%m-%d")
        filepath = Path(self.config.output_dir) / f"killswitch_log_{date_str}.json"

        log_data = {
            "date": date_str,
            "state": self._state.value,
            "metrics": self.get_metrics().to_dict(),
            "events": [e.to_dict() for e in self._event_log],
            "summary": {
                "daily_pnl_pct": (self._daily_pnl / self.initial_capital) * 100.0,
                "cumulative_pnl_pct": (self._cumulative_pnl / self.initial_capital) * 100.0,
                "consecutive_losses": self._consecutive_losses,
                "total_events": len(self._event_log),
            }
        }

        with open(filepath, 'w') as f:
            json.dump(log_data, f, indent=2)

        logger.info(f"[KILLSWITCH] Daily log saved: {filepath}")
        return str(filepath)

    def clear_daily_state(self) -> None:
        """Clear state for new trading day."""
        self._daily_pnl = 0.0
        self._event_log.clear()

        if self._state == KillSwitchState.COOLDOWN:
            self._state = KillSwitchState.ACTIVE

        logger.info("[KILLSWITCH] Daily state cleared")


# Convenience function for integration
def create_killswitch(
    initial_capital: float,
    daily_loss_limit_pct: float = 3.0,
    cumulative_loss_limit_pct: float = 10.0,
    max_consecutive_losses: int = 5,
    volatility_spike_multiplier: float = 3.0,
    cooldown_hours: int = 24,
    output_dir: str = "/Users/jim/work/curly-succotash/logs/killswitch"
) -> DrawdownKillSwitch:
    """
    Create a configured drawdown kill-switch.

    Args:
        initial_capital: Starting capital
        daily_loss_limit_pct: Max daily loss percentage
        cumulative_loss_limit_pct: Max cumulative loss percentage
        max_consecutive_losses: Max consecutive losses before halt
        volatility_spike_multiplier: Volatility spike trigger
        cooldown_hours: Hours before can restart after trigger
        output_dir: Log output directory

    Returns:
        Configured DrawdownKillSwitch instance
    """
    config = KillSwitchConfig(
        daily_loss_limit_pct=daily_loss_limit_pct,
        cumulative_loss_limit_pct=cumulative_loss_limit_pct,
        max_consecutive_losses=max_consecutive_losses,
        volatility_spike_multiplier=volatility_spike_multiplier,
        cooldown_hours=cooldown_hours,
        output_dir=output_dir,
    )

    return DrawdownKillSwitch(config, initial_capital)
