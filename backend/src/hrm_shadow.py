"""
HRM Shadow Mode Infrastructure

Shadow mode runs HRM predictions in parallel with baseline trading,
recording counterfactual outcomes without affecting actual trades.

Key Features:
- Runs HRM on same symbols/timestamps as baseline
- Records what HRM would have traded (counterfactual)
- Computes shadow PnL excluding fees/slippage initially
- Applies fee/slippage model for realistic comparison
- Never blocks baseline trading decisions
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

from .models import Candle, Signal, Timeframe, Trade, Position
from .strategies import BaseStrategy

logger = logging.getLogger(__name__)


class ShadowMode(str, Enum):
    """HRM shadow mode stages."""
    SHADOW = "shadow"  # Pure observation, no impact
    VETO_ONLY = "veto_only"  # Can block baseline trades
    SIZE_CAPPED = "size_capped"  # Can trade with size limits
    PRIMARY = "primary"  # Full authority


@dataclass
class ShadowSignal:
    """HRM shadow trading signal."""
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    hrm_signal: str  # LONG, SHORT, FLAT
    hrm_confidence: float
    baseline_signal: str  # What baseline strategy signaled
    baseline_strategy: str
    action_taken: str  # "baseline_followed", "hrm_veto", "hrm_override"
    veto_reason: Optional[str] = None
    counterfactual_entry: Optional[float] = None
    counterfactual_size: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "hrm_signal": self.hrm_signal,
            "hrm_confidence": self.hrm_confidence,
            "baseline_signal": self.baseline_signal,
            "baseline_strategy": self.baseline_strategy,
            "action_taken": self.action_taken,
            "veto_reason": self.veto_reason,
            "counterfactual_entry": self.counterfactual_entry,
            "counterfactual_size": self.counterfactual_size,
        }


@dataclass
class ShadowTrade:
    """Counterfactual HRM trade."""
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    side: str
    entry_price: float
    exit_price: Optional[float]
    size: float
    pnl: float
    pnl_percent: float
    fees: float
    slippage: float
    net_pnl: float
    holding_period_seconds: int
    is_counterfactual: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "fees": self.fees,
            "slippage": self.slippage,
            "net_pnl": self.net_pnl,
            "holding_period_seconds": self.holding_period_seconds,
            "is_counterfactual": self.is_counterfactual,
        }


@dataclass
class ShadowMetrics:
    """Shadow mode performance metrics."""
    symbol: str
    timeframe: Timeframe
    start_time: datetime
    end_time: datetime

    # Baseline metrics
    baseline_trades: int = 0
    baseline_net_pnl: float = 0.0
    baseline_sharpe: float = 0.0
    baseline_max_drawdown: float = 0.0
    baseline_win_rate: float = 0.0

    # HRM shadow metrics
    hrm_shadow_trades: int = 0
    hrm_shadow_net_pnl: float = 0.0
    hrm_shadow_sharpe: float = 0.0
    hrm_shadow_max_drawdown: float = 0.0
    hrm_shadow_win_rate: float = 0.0

    # Comparison metrics
    pnl_difference: float = 0.0  # HRM - Baseline
    sharpe_difference: float = 0.0
    hrm_outperformance: bool = False

    # Veto metrics
    vetoes_issued: int = 0
    vetoed_trades_would_have_won: int = 0
    vetoed_trades_would_have_lost: int = 0
    veto_accuracy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timeframe"] = self.timeframe.value
        payload["start_time"] = self.start_time.isoformat()
        payload["end_time"] = self.end_time.isoformat()
        return payload


@dataclass
class ShadowConfig:
    """Shadow mode configuration."""
    mode: ShadowMode = ShadowMode.SHADOW
    symbols: List[str] = field(default_factory=list)
    timeframes: List[Timeframe] = field(default_factory=list)

    # HRM model configuration
    hrm_model_path: Optional[str] = None
    hrm_confidence_threshold: float = 0.6

    # Trading constraints
    max_position_size_pct: float = 5.0
    commission_pct: float = 0.1
    slippage_bps: float = 5.0

    # Veto configuration (for veto_only mode)
    veto_on_confidence_below: float = 0.5
    veto_on_opposite_signal: bool = True

    # Logging
    log_all_signals: bool = True
    log_counterfactual_trades: bool = True

    # Storage
    output_dir: str = "/Users/jim/work/curly-succotash/logs/shadow_mode"

    # Optional injected predictor for tests or external model wrappers
    predictor: Optional[Callable[[Candle, List[Candle]], Tuple[str, float]]] = None


class HRMShadowEngine:
    """
    HRM shadow mode trading engine.

    Runs HRM predictions in parallel with baseline strategies,
    tracking counterfactual performance for comparison.

    Example:
        config = ShadowConfig(
            mode=ShadowMode.SHADOW,
            symbols=["BTCUSDT", "ETHUSDT"],
            hrm_model_path="/path/to/hrm/model.safetensors"
        )
        shadow_engine = HRMShadowEngine(config)

        # For each candle
        shadow_signal = shadow_engine.process_candle(
            candle=candle,
            baseline_signal=baseline_signal
        )
    """

    def __init__(self, config: ShadowConfig):
        self.config = config
        self.mode = config.mode

        # State tracking
        self._shadow_positions: Dict[str, Position] = {}
        self._shadow_trades: List[ShadowTrade] = []
        self._shadow_signals: List[ShadowSignal] = []
        self._metrics: Dict[str, ShadowMetrics] = {}

        # HRM model (loaded on demand)
        self._hrm_model: Optional[Any] = None

        # Initialize output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"[SHADOW] HRM Shadow Engine initialized")
        logger.info(f"[SHADOW] Mode: {self.mode.value}")
        logger.info(f"[SHADOW] Symbols: {config.symbols}")
        logger.info(f"[SHADOW] Confidence threshold: {config.hrm_confidence_threshold}")

    def load_hrm_model(self, model_path: str) -> None:
        """Load HRM model for inference."""
        logger.info(f"[SHADOW] HRM model would be loaded from: {model_path}")
        self.config.hrm_model_path = model_path

    def predict_hrm_signal(
        self,
        candle: Candle,
        context: List[Candle]
    ) -> Tuple[str, float]:
        """
        Get HRM prediction for current candle.

        Returns:
            Tuple of (signal, confidence) where signal is LONG/SHORT/FLAT
        """
        if self.config.predictor:
            signal, confidence = self.config.predictor(candle, context)
            return signal, max(0.0, min(1.0, confidence))

        return "FLAT", 0.0

    def process_candle(
        self,
        candle: Candle,
        baseline_signal: Signal,
        context: Optional[List[Candle]] = None
    ) -> ShadowSignal:
        """
        Process candle through HRM shadow mode.

        Args:
            candle: Current candle
            baseline_signal: Signal from baseline strategy
            context: Optional historical context

        Returns:
            ShadowSignal with HRM prediction and comparison
        """
        # Get HRM prediction
        hrm_signal, hrm_confidence = self.predict_hrm_signal(candle, context or [])

        # Determine action based on shadow mode
        if self.mode == ShadowMode.SHADOW:
            # Pure observation - never interfere
            action_taken = "baseline_followed"
            veto_reason = None
        elif self.mode == ShadowMode.VETO_ONLY:
            # Can block baseline trades
            baseline_actionable = baseline_signal.signal_type.value in {"LONG", "SHORT"}
            if (self.config.veto_on_opposite_signal and
                baseline_actionable and
                hrm_signal != baseline_signal.signal_type.value and
                hrm_confidence > self.config.veto_on_confidence_below):
                action_taken = "hrm_veto"
                veto_reason = f"HRM opposes with {hrm_confidence:.2f} confidence"
            else:
                action_taken = "baseline_followed"
                veto_reason = None
        elif self.mode == ShadowMode.SIZE_CAPPED:
            # Can trade with size limits
            if hrm_confidence > self.config.hrm_confidence_threshold:
                action_taken = "hrm_override"
                veto_reason = None
            else:
                action_taken = "baseline_followed"
                veto_reason = None
        else:  # PRIMARY
            # HRM has full authority
            if hrm_confidence > self.config.hrm_confidence_threshold:
                action_taken = "hrm_override"
                veto_reason = None
            else:
                action_taken = "baseline_followed"
                veto_reason = "HRM confidence below threshold"

        # Maintain a counterfactual book regardless of whether baseline was overridden.
        counterfactual_entry, counterfactual_size = self._apply_counterfactual_signal(
            candle=candle,
            baseline_signal=baseline_signal,
            hrm_signal=hrm_signal,
            hrm_confidence=hrm_confidence,
        )

        shadow_signal = ShadowSignal(
            timestamp=candle.timestamp,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            hrm_signal=hrm_signal,
            hrm_confidence=hrm_confidence,
            baseline_signal=baseline_signal.signal_type.value,
            baseline_strategy=baseline_signal.strategy_name,
            action_taken=action_taken,
            veto_reason=veto_reason,
            counterfactual_entry=counterfactual_entry,
            counterfactual_size=counterfactual_size,
        )

        # Log signal if configured
        if self.config.log_all_signals:
            self._shadow_signals.append(shadow_signal)

        return shadow_signal

    def _position_key(self, symbol: str, timeframe: Timeframe) -> str:
        return f"{symbol}_{timeframe.value}"

    def _apply_counterfactual_signal(
        self,
        candle: Candle,
        baseline_signal: Signal,
        hrm_signal: str,
        hrm_confidence: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Open or close counterfactual HRM positions off the current candle."""
        key = self._position_key(candle.symbol, candle.timeframe)
        current_position = self._shadow_positions.get(key)
        should_open = (
            hrm_signal in {"LONG", "SHORT"} and
            hrm_confidence >= self.config.hrm_confidence_threshold
        )

        if current_position and (not should_open or current_position["side"] != hrm_signal):
            self._close_counterfactual_position(candle, current_position)
            self._shadow_positions.pop(key, None)
            current_position = None

        if current_position or not should_open:
            return None, None

        size = baseline_signal.paper_size if baseline_signal.paper_size > 0 else 0.0
        if size <= 0:
            return None, None

        self._shadow_positions[key] = {
            "side": hrm_signal,
            "entry_price": candle.close,
            "entry_time": candle.timestamp,
            "size": size,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
        }
        return candle.close, size

    def _close_counterfactual_position(
        self,
        candle: Candle,
        position: Dict[str, Any],
    ) -> ShadowTrade:
        """Close an open counterfactual position at the current candle close."""
        entry_price = float(position["entry_price"])
        exit_price = candle.close
        size = float(position["size"])
        round_trip_notional = (entry_price + exit_price) * size

        if position["side"] == "LONG":
            gross_pnl = (exit_price - entry_price) * size
        else:
            gross_pnl = (entry_price - exit_price) * size

        fees = round_trip_notional * self.config.commission_pct / 100.0
        slippage = round_trip_notional * self.config.slippage_bps / 10000.0
        net_pnl = gross_pnl - fees - slippage
        pnl_percent = (net_pnl / (entry_price * size)) * 100.0 if entry_price > 0 and size > 0 else 0.0
        holding_period_seconds = max(
            0,
            int((candle.timestamp - position["entry_time"]).total_seconds()),
        )

        trade = ShadowTrade(
            timestamp=candle.timestamp,
            symbol=position["symbol"],
            timeframe=position["timeframe"],
            side=position["side"],
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=gross_pnl,
            pnl_percent=pnl_percent,
            fees=fees,
            slippage=slippage,
            net_pnl=net_pnl,
            holding_period_seconds=holding_period_seconds,
        )
        self._shadow_trades.append(trade)
        return trade

    def execute_shadow_trade(
        self,
        shadow_signal: ShadowSignal,
        exit_price: Optional[float] = None
    ) -> Optional[ShadowTrade]:
        """
        Execute counterfactual trade based on shadow signal.

        Args:
            shadow_signal: Shadow signal to execute
            exit_price: Optional exit price (for immediate close)

        Returns:
            ShadowTrade if trade was executed, None otherwise
        """
        if shadow_signal.action_taken != "hrm_override":
            return None

        if shadow_signal.counterfactual_entry is None:
            return None

        # Calculate fees and slippage
        entry = shadow_signal.counterfactual_entry
        size = shadow_signal.counterfactual_size or 0.0
        notional = entry * size

        fees = notional * self.config.commission_pct / 100.0
        slippage = notional * self.config.slippage_bps / 10000.0

        # Calculate PnL (placeholder - would use actual exit)
        exit_px = exit_price or entry  # Placeholder
        gross_pnl = (exit_px - entry) * size
        net_pnl = gross_pnl - fees - slippage
        pnl_percent = (net_pnl / notional) * 100.0 if notional > 0 else 0.0

        trade = ShadowTrade(
            timestamp=shadow_signal.timestamp,
            symbol=shadow_signal.symbol,
            timeframe=shadow_signal.timeframe,
            side=shadow_signal.hrm_signal,
            entry_price=entry,
            exit_price=exit_px,
            size=size,
            pnl=gross_pnl,
            pnl_percent=pnl_percent,
            fees=fees,
            slippage=slippage,
            net_pnl=net_pnl,
            holding_period_seconds=0,  # Would track actual holding period
        )

        self._shadow_trades.append(trade)

        if self.config.log_counterfactual_trades:
            logger.debug(
                f"[SHADOW] Trade: {shadow_signal.symbol} {shadow_signal.hrm_signal} | "
                f"Entry: {entry:.2f} | Net PnL: {net_pnl:.2f} ({pnl_percent:.2f}%)"
            )

        return trade

    def compute_metrics(
        self,
        symbol: str,
        timeframe: Timeframe,
        baseline_trades: List[Any],
        start_time: datetime,
        end_time: datetime
    ) -> ShadowMetrics:
        """
        Compute shadow mode metrics for comparison.

        Args:
            symbol: Symbol to compute metrics for
            timeframe: Timeframe
            baseline_trades: Actual baseline trades
            start_time: Period start
            end_time: Period end

        Returns:
            ShadowMetrics with comparison statistics
        """
        # Filter shadow trades for this symbol/timeframe
        shadow_trades = [
            t for t in self._shadow_trades
            if (
                t.symbol == symbol and
                t.timeframe == timeframe and
                start_time <= t.timestamp <= end_time
            )
        ]

        filtered_baseline_trades = [
            trade for trade in baseline_trades
            if self._trade_timestamp(trade) is None or start_time <= self._trade_timestamp(trade) <= end_time
        ]

        # Compute baseline metrics
        baseline_net_pnl = sum(self._trade_pnl(trade) for trade in filtered_baseline_trades)
        baseline_win_rate = (
            sum(1 for trade in filtered_baseline_trades if self._trade_pnl(trade) > 0) / len(filtered_baseline_trades)
            if filtered_baseline_trades else 0.0
        )

        # Compute HRM shadow metrics
        hrm_net_pnl = sum(t.net_pnl for t in shadow_trades)
        hrm_win_rate = (
            sum(1 for t in shadow_trades if t.net_pnl > 0) / len(shadow_trades)
            if shadow_trades else 0.0
        )

        # Placeholder Sharpe and drawdown (would compute properly)
        baseline_sharpe = 0.0
        hrm_sharpe = 0.0
        baseline_drawdown = 0.0
        hrm_drawdown = 0.0

        # Compute veto metrics
        vetoes = [
            s for s in self._shadow_signals
            if (
                s.action_taken == "hrm_veto" and
                s.symbol == symbol and
                s.timeframe == timeframe and
                start_time <= s.timestamp <= end_time
            )
        ]
        veto_wins = 0  # Would track actual outcomes
        veto_losses = 0

        metrics = ShadowMetrics(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            baseline_trades=len(filtered_baseline_trades),
            baseline_net_pnl=baseline_net_pnl,
            baseline_sharpe=baseline_sharpe,
            baseline_max_drawdown=baseline_drawdown,
            baseline_win_rate=baseline_win_rate,
            hrm_shadow_trades=len(shadow_trades),
            hrm_shadow_net_pnl=hrm_net_pnl,
            hrm_shadow_sharpe=hrm_sharpe,
            hrm_shadow_max_drawdown=hrm_drawdown,
            hrm_shadow_win_rate=hrm_win_rate,
            pnl_difference=hrm_net_pnl - baseline_net_pnl,
            sharpe_difference=hrm_sharpe - baseline_sharpe,
            hrm_outperformance=hrm_net_pnl > baseline_net_pnl,
            vetoes_issued=len(vetoes),
            vetoed_trades_would_have_won=veto_wins,
            vetoed_trades_would_have_lost=veto_losses,
            veto_accuracy=veto_wins / len(vetoes) if vetoes else 0.0,
        )

        self._metrics[f"{symbol}_{timeframe.value}"] = metrics

        return metrics

    def _trade_pnl(self, trade: Any) -> float:
        if isinstance(trade, dict):
            return float(trade.get("pnl", 0.0))
        return float(trade.pnl)

    def _trade_timestamp(self, trade: Any) -> Optional[datetime]:
        timestamp: Optional[Any]
        if isinstance(trade, dict):
            timestamp = trade.get("exit_time") or trade.get("timestamp") or trade.get("entry_time")
        else:
            timestamp = getattr(trade, "timestamp", None)

        if timestamp is None:
            return None
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp)
        return timestamp

    def save_daily_log(self, date: datetime) -> str:
        """
        Save daily shadow mode log.

        Args:
            date: Date to save log for

        Returns:
            Path to saved log file
        """
        date_str = date.strftime("%Y-%m-%d")
        log_file = Path(self.config.output_dir) / f"shadow_log_{date_str}.json"

        log_data = {
            "date": date_str,
            "mode": self.mode.value,
            "signals": [s.to_dict() for s in self._shadow_signals],
            "trades": [t.to_dict() for t in self._shadow_trades],
            "metrics": {k: v.to_dict() for k, v in self._metrics.items()},
            "summary": {
                "total_signals": len(self._shadow_signals),
                "total_trades": len(self._shadow_trades),
                "vetoes_issued": sum(1 for s in self._shadow_signals if s.action_taken == "hrm_veto"),
            }
        }

        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)

        logger.info(f"[SHADOW] Daily log saved to {log_file}")

        return str(log_file)

    def clear_daily_state(self) -> None:
        """Clear state for new trading day."""
        self._shadow_signals.clear()
        self._shadow_trades.clear()
        # Keep metrics for historical tracking

    @property
    def shadow_trades(self) -> List[ShadowTrade]:
        """Get all shadow trades."""
        return self._shadow_trades.copy()

    @property
    def shadow_signals(self) -> List[ShadowSignal]:
        """Get all shadow signals."""
        return self._shadow_signals.copy()

    @property
    def metrics(self) -> Dict[str, ShadowMetrics]:
        """Get all computed metrics."""
        return self._metrics.copy()
