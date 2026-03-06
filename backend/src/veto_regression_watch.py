"""
Veto Regression Watch - Automated Veto Reason Tracking

Continuously monitors veto reasons and accuracy to detect regression
in HRM model performance. Generates alerts when veto accuracy degrades
beyond acceptable thresholds.

Key Features:
- Tracks all veto reasons with timestamps
- Computes rolling veto accuracy metrics
- Detects distribution shifts in veto reasons
- Generates daily/weekly regression reports
- Alerts on accuracy degradation (>10% drop)
- Integrates with regime manifest for regime-aware analysis
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from collections import Counter, deque
from enum import Enum

logger = logging.getLogger(__name__)


class VetoReason(str, Enum):
    """Standardized veto reasons."""
    CONFIDENCE_TOO_LOW = "confidence_too_low"
    REGIME_MISMATCH = "regime_mismatch"
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"
    MODEL_UNCERTAINTY_HIGH = "model_uncertainty_high"
    BASELINE_STRONG = "baseline_strong"
    MARKET_VOLATILITY = "market_volatility"
    LIQUIDITY_CONCERN = "liquidity_concern"
    CORRELATION_RISK = "correlation_risk"
    DRAWDOWN_LIMIT = "drawdown_limit"
    POSITION_SIZE_LIMIT = "position_size_limit"
    TIMEFRAME_MISMATCH = "timeframe_mismatch"
    UNKNOWN = "unknown"


@dataclass
class VetoEvent:
    """Records a single veto event."""
    timestamp: datetime
    symbol: str
    timeframe: str
    veto_reason: VetoReason
    baseline_signal: str
    hrm_signal: str
    hrm_confidence: float
    would_have_won: Optional[bool] = None  # Determined post-trade
    would_have_pnl: Optional[float] = None
    regime_context: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "veto_reason": self.veto_reason.value,
            "baseline_signal": self.baseline_signal,
            "hrm_signal": self.hrm_signal,
            "hrm_confidence": self.hrm_confidence,
            "would_have_won": self.would_have_won,
            "would_have_pnl": self.would_have_pnl,
            "regime_context": self.regime_context,
        }


@dataclass
class VetoMetrics:
    """Aggregated veto metrics for a time window."""
    window_start: datetime
    window_end: datetime
    total_vetoes: int
    correct_vetoes: int
    incorrect_vetoes: int
    pending_vetoes: int  # Not yet resolved
    accuracy: float

    # By reason
    veto_counts_by_reason: Dict[str, int]
    accuracy_by_reason: Dict[str, float]

    # By symbol
    veto_counts_by_symbol: Dict[str, int]
    accuracy_by_symbol: Dict[str, float]

    # By regime
    veto_counts_by_regime: Dict[str, int]
    accuracy_by_regime: Dict[str, float]

    # Distribution metrics
    top_veto_reasons: List[Tuple[str, float]]  # (reason, percentage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "total_vetoes": self.total_vetoes,
            "correct_vetoes": self.correct_vetoes,
            "incorrect_vetoes": self.incorrect_vetoes,
            "pending_vetoes": self.pending_vetoes,
            "accuracy": self.accuracy,
            "veto_counts_by_reason": self.veto_counts_by_reason,
            "accuracy_by_reason": self.accuracy_by_reason,
            "veto_counts_by_symbol": self.veto_counts_by_symbol,
            "accuracy_by_symbol": self.accuracy_by_symbol,
            "veto_counts_by_regime": self.veto_counts_by_regime,
            "accuracy_by_regime": self.accuracy_by_regime,
            "top_veto_reasons": self.top_veto_reasons,
        }


@dataclass
class RegressionAlert:
    """Alert generated when regression detected."""
    timestamp: datetime
    alert_type: str  # "accuracy_drop", "distribution_shift", "reason_spike"
    severity: str  # "low", "medium", "high", "critical"
    description: str
    current_value: float
    baseline_value: float
    threshold: float
    affected_symbols: List[str]
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VetoRegressionWatch:
    """
    Monitors veto reasons and accuracy for regression detection.

    Tracks veto events, computes rolling metrics, and generates alerts
    when performance degrades beyond acceptable thresholds.

    Example:
        watch = VetoRegressionWatch(
            accuracy_threshold=0.60,
            distribution_threshold=0.10,
            window_size_days=7
        )

        # Record veto
        watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )

        # Resolve veto outcome
        watch.resolve_veto(veto_id=123, would_have_won=False, would_have_pnl=-0.02)

        # Check for regression
        alerts = watch.check_regression()
    """

    def __init__(
        self,
        accuracy_threshold: float = 0.60,
        distribution_threshold: float = 0.10,
        window_size_days: int = 7,
        alert_cooldown_hours: int = 24,
        output_dir: str = "/Users/jim/work/curly-succotash/logs/veto_watch"
    ):
        """
        Initialize veto regression watch.

        Args:
            accuracy_threshold: Minimum acceptable veto accuracy (default 60%)
            distribution_threshold: Max acceptable distribution shift (default 10%)
            window_size_days: Rolling window size for metrics
            alert_cooldown_hours: Minimum hours between same-type alerts
            output_dir: Directory for reports and alerts
        """
        self.accuracy_threshold = accuracy_threshold
        self.distribution_threshold = distribution_threshold
        self.window_size_days = window_size_days
        self.alert_cooldown_hours = alert_cooldown_hours
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Event storage
        self._vetoes: deque[VetoEvent] = deque(maxlen=10000)
        self._veto_outcomes: Dict[int, Tuple[bool, float]] = {}  # veto_id -> (won, pnl)
        self._veto_counter = 0
        self._first_veto_id = 0

        # Metrics cache
        self._current_metrics: Optional[VetoMetrics] = None
        self._baseline_metrics: Optional[VetoMetrics] = None

        # Alert tracking
        self._alerts: List[RegressionAlert] = []
        self._last_alert_time: Dict[str, datetime] = {}

        # Regime manifest (optional)
        self._regime_manifest: Dict[str, Any] = {}

        logger.info(f"[VETO_WATCH] Initialized with accuracy_threshold={accuracy_threshold}")
        logger.info(f"[VETO_WATCH] Output directory: {output_dir}")

    def load_regime_manifest(self, path: str) -> None:
        """Load regime manifest for regime-aware analysis."""
        try:
            with open(path, 'r') as f:
                self._regime_manifest = json.load(f)
            logger.info(f"[VETO_WATCH] Loaded regime manifest from {path}")
        except Exception as e:
            logger.error(f"[VETO_WATCH] Failed to load regime manifest: {e}")

    def record_veto(
        self,
        symbol: str,
        timeframe: str,
        reason: VetoReason,
        baseline_signal: str,
        hrm_signal: str,
        hrm_confidence: float,
        regime_context: Optional[List[str]] = None
    ) -> int:
        """
        Record a veto event.

        Args:
            symbol: Symbol that was vetoed
            timeframe: Timeframe
            reason: Reason for veto
            baseline_signal: What baseline wanted to do
            hrm_signal: What HRM predicted
            hrm_confidence: HRM confidence level
            regime_context: Current regime context

        Returns:
            Veto ID for later resolution
        """
        veto_id = self._veto_counter
        self._veto_counter += 1

        if self._vetoes.maxlen and len(self._vetoes) == self._vetoes.maxlen:
            self._veto_outcomes.pop(self._first_veto_id, None)
            self._first_veto_id += 1

        veto = VetoEvent(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            timeframe=timeframe,
            veto_reason=reason,
            baseline_signal=baseline_signal,
            hrm_signal=hrm_signal,
            hrm_confidence=hrm_confidence,
            regime_context=regime_context or []
        )

        self._vetoes.append(veto)
        logger.debug(f"[VETO_WATCH] Recorded veto #{veto_id}: {reason.value} on {symbol}")

        return veto_id

    def resolve_veto(
        self,
        veto_id: int,
        would_have_won: bool,
        would_have_pnl: float
    ) -> None:
        """
        Resolve a veto with actual outcome.

        Args:
            veto_id: ID from record_veto
            would_have_won: Whether the vetoed trade would have been profitable
            would_have_pnl: The PnL the vetoed trade would have generated
        """
        local_index = veto_id - self._first_veto_id
        if local_index < 0 or local_index >= len(self._vetoes):
            logger.warning(f"[VETO_WATCH] Invalid veto_id {veto_id}")
            return

        self._veto_outcomes[veto_id] = (would_have_won, would_have_pnl)

        # Update the original veto event
        veto = self._vetoes[local_index]
        veto.would_have_won = would_have_won
        veto.would_have_pnl = would_have_pnl

        logger.debug(
            f"[VETO_WATCH] Resolved veto #{veto_id}: "
            f"{'CORRECT' if not would_have_won else 'INCORRECT'} (PnL: {would_have_pnl:.2%})"
        )

    def _get_window_vetoes(
        self,
        days: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Tuple[int, VetoEvent]]:
        """Get vetoes within the specified window."""
        if start_time is None or end_time is None:
            if days is None:
                days = self.window_size_days
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

        return [
            (self._first_veto_id + i, v) for i, v in enumerate(self._vetoes)
            if start_time <= v.timestamp <= end_time
        ]

    def compute_metrics(
        self,
        window_days: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> VetoMetrics:
        """
        Compute veto metrics for the current window.

        Args:
            window_days: Override default window size

        Returns:
            VetoMetrics with aggregated statistics
        """
        if start_time is None or end_time is None:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=window_days or self.window_size_days)

        now = end_time
        window_start = start_time

        window_vetoes = self._get_window_vetoes(window_days, start_time=start_time, end_time=end_time)

        if not window_vetoes:
            return VetoMetrics(
                window_start=window_start,
                window_end=now,
                total_vetoes=0,
                correct_vetoes=0,
                incorrect_vetoes=0,
                pending_vetoes=0,
                accuracy=0.0,
                veto_counts_by_reason={},
                accuracy_by_reason={},
                veto_counts_by_symbol={},
                accuracy_by_symbol={},
                veto_counts_by_regime={},
                accuracy_by_regime={},
                top_veto_reasons=[]
            )

        # Count by outcome
        correct = 0
        incorrect = 0
        pending = 0

        for i, _ in window_vetoes:
            if i in self._veto_outcomes:
                if self._veto_outcomes[i][0]:  # would_have_won
                    incorrect += 1
                else:
                    correct += 1
            else:
                pending += 1

        total_resolved = correct + incorrect
        accuracy = (correct / total_resolved * 100) if total_resolved > 0 else 0.0

        # Count by reason
        reason_counts: Counter = Counter()
        reason_correct: Counter = Counter()
        reason_total: Counter = Counter()

        for i, veto in window_vetoes:
            reason_counts[veto.veto_reason.value] += 1
            reason_total[veto.veto_reason.value] += 1
            if i in self._veto_outcomes and not self._veto_outcomes[i][0]:
                reason_correct[veto.veto_reason.value] += 1

        accuracy_by_reason = {
            reason: (reason_correct[reason] / reason_total[reason] * 100)
            if reason_total[reason] > 0 else 0.0
            for reason in reason_counts.keys()
        }

        # Count by symbol
        symbol_counts: Counter = Counter()
        symbol_correct: Counter = Counter()
        symbol_total: Counter = Counter()

        for i, veto in window_vetoes:
            symbol_counts[veto.symbol] += 1
            symbol_total[veto.symbol] += 1
            if i in self._veto_outcomes and not self._veto_outcomes[i][0]:
                symbol_correct[veto.symbol] += 1

        accuracy_by_symbol = {
            symbol: (symbol_correct[symbol] / symbol_total[symbol] * 100)
            if symbol_total[symbol] > 0 else 0.0
            for symbol in symbol_counts.keys()
        }

        # Count by regime
        regime_counts: Counter = Counter()
        regime_correct: Counter = Counter()
        regime_total: Counter = Counter()

        for i, veto in window_vetoes:
            for regime in veto.regime_context:
                regime_counts[regime] += 1
                regime_total[regime] += 1
                if i in self._veto_outcomes and not self._veto_outcomes[i][0]:
                    regime_correct[regime] += 1

        accuracy_by_regime = {
            regime: (regime_correct[regime] / regime_total[regime] * 100)
            if regime_total[regime] > 0 else 0.0
            for regime in regime_counts.keys()
        }

        # Top veto reasons by percentage
        total_vetoes = len(window_vetoes)
        top_reasons = [
            (reason, count / total_vetoes * 100)
            for reason, count in reason_counts.most_common(5)
        ]

        metrics = VetoMetrics(
            window_start=window_start,
            window_end=now,
            total_vetoes=total_vetoes,
            correct_vetoes=correct,
            incorrect_vetoes=incorrect,
            pending_vetoes=pending,
            accuracy=accuracy,
            veto_counts_by_reason=dict(reason_counts),
            accuracy_by_reason=accuracy_by_reason,
            veto_counts_by_symbol=dict(symbol_counts),
            accuracy_by_symbol=accuracy_by_symbol,
            veto_counts_by_regime=dict(regime_counts),
            accuracy_by_regime=accuracy_by_regime,
            top_veto_reasons=top_reasons
        )

        self._current_metrics = metrics
        return metrics

    def set_baseline_metrics(self, metrics: VetoMetrics) -> None:
        """Set baseline metrics for comparison."""
        self._baseline_metrics = metrics
        logger.info(f"[VETO_WATCH] Baseline metrics set: accuracy={metrics.accuracy:.1f}%")

    def check_regression(self) -> List[RegressionAlert]:
        """
        Check for regression against baseline and thresholds.

        Returns:
            List of regression alerts
        """
        alerts = []
        current = self.compute_metrics()

        if current.total_vetoes == 0:
            return alerts

        # Check 1: Overall accuracy drop
        if self._baseline_metrics and current.accuracy < self._baseline_metrics.accuracy - 10:
            alert = RegressionAlert(
                timestamp=datetime.now(timezone.utc),
                alert_type="accuracy_drop",
                severity="high" if current.accuracy < self.accuracy_threshold else "medium",
                description=f"Veto accuracy dropped from {self._baseline_metrics.accuracy:.1f}% to {current.accuracy:.1f}%",
                current_value=current.accuracy,
                baseline_value=self._baseline_metrics.accuracy,
                threshold=10.0,
                affected_symbols=list(current.accuracy_by_symbol.keys()),
                recommended_action="Review recent vetoes and consider model retraining or threshold adjustment"
            )
            if self._should_alert(alert):
                alerts.append(alert)

        # Check 2: Below absolute threshold
        if current.accuracy < self.accuracy_threshold:
            alert = RegressionAlert(
                timestamp=datetime.now(timezone.utc),
                alert_type="below_threshold",
                severity="critical",
                description=f"Veto accuracy {current.accuracy:.1f}% below threshold {self.accuracy_threshold:.1f}%",
                current_value=current.accuracy,
                baseline_value=self.accuracy_threshold,
                threshold=self.accuracy_threshold,
                affected_symbols=list(current.accuracy_by_symbol.keys()),
                recommended_action="Immediate review required - consider demotion from veto_only stage"
            )
            if self._should_alert(alert):
                alerts.append(alert)

        # Check 3: Distribution shift
        if self._baseline_metrics:
            all_reasons = set(current.veto_counts_by_reason.keys()) | set(self._baseline_metrics.veto_counts_by_reason.keys())
            for reason in all_reasons:
                current_pct = current.veto_counts_by_reason.get(reason, 0) / max(1, current.total_vetoes) * 100
                baseline_pct = self._baseline_metrics.veto_counts_by_reason.get(reason, 0) / max(1, self._baseline_metrics.total_vetoes) * 100

                if abs(current_pct - baseline_pct) > self.distribution_threshold * 100:
                    alert = RegressionAlert(
                        timestamp=datetime.now(timezone.utc),
                        alert_type="distribution_shift",
                        severity="medium",
                        description=f"Veto reason '{reason}' shifted from {baseline_pct:.1f}% to {current_pct:.1f}%",
                        current_value=current_pct,
                        baseline_value=baseline_pct,
                        threshold=self.distribution_threshold * 100,
                        affected_symbols=[],
                        recommended_action=f"Investigate increase in {reason} vetoes"
                    )
                    if self._should_alert(alert):
                        alerts.append(alert)

        # Check 4: Symbol-specific regression
        for symbol, accuracy in current.accuracy_by_symbol.items():
            if accuracy < self.accuracy_threshold:
                alert = RegressionAlert(
                    timestamp=datetime.now(timezone.utc),
                    alert_type="symbol_regression",
                    severity="high",
                    description=f"Veto accuracy on {symbol} is {accuracy:.1f}% (below threshold)",
                    current_value=accuracy,
                    baseline_value=self.accuracy_threshold,
                    threshold=self.accuracy_threshold,
                    affected_symbols=[symbol],
                    recommended_action=f"Review {symbol} vetoes specifically - consider symbol-specific tuning"
                )
                if self._should_alert(alert):
                    alerts.append(alert)

        # Store alerts
        self._alerts.extend(alerts)
        for alert in alerts:
            self._last_alert_time[alert.alert_type] = datetime.now(timezone.utc)

        if alerts:
            logger.warning(f"[VETO_WATCH] {len(alerts)} regression alerts generated")

        return alerts

    def _should_alert(self, alert: RegressionAlert) -> bool:
        """Check if we should alert (respecting cooldown)."""
        last_alert = self._last_alert_time.get(alert.alert_type)
        if last_alert:
            cooldown = timedelta(hours=self.alert_cooldown_hours)
            if datetime.now(timezone.utc) - last_alert < cooldown:
                logger.debug(f"[VETO_WATCH] Skipping alert due to cooldown: {alert.alert_type}")
                return False
        return True

    def generate_daily_report(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate daily veto analysis report.

        Args:
            date: Date to generate report for (default: today)

        Returns:
            Report dictionary
        """
        if date is None:
            date = datetime.now(timezone.utc)

        date_str = date.strftime("%Y-%m-%d")
        day_start = date.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        metrics = self.compute_metrics(start_time=day_start, end_time=day_end)
        weekly_metrics = self.compute_metrics(window_days=7)

        report = {
            "report_type": "daily_veto_analysis",
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "daily_metrics": metrics.to_dict(),
            "weekly_metrics": weekly_metrics.to_dict(),
            "alerts_today": [
                a.to_dict() for a in self._alerts
                if a.timestamp.strftime("%Y-%m-%d") == date_str
            ],
            "top_veto_reasons": metrics.top_veto_reasons,
            "regime_analysis": {
                "regimes_detected": list(metrics.veto_counts_by_regime.keys()),
                "accuracy_by_regime": metrics.accuracy_by_regime
            },
            "symbol_breakdown": {
                "veto_counts": metrics.veto_counts_by_symbol,
                "accuracy": metrics.accuracy_by_symbol
            },
            "recommendations": self._generate_recommendations(metrics)
        }

        return report

    def generate_weekly_report(self) -> Dict[str, Any]:
        """Generate weekly veto analysis report."""
        metrics = self.compute_metrics(window_days=7)

        report = {
            "report_type": "weekly_veto_analysis",
            "week_start": metrics.window_start.isoformat(),
            "week_end": metrics.window_end.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary_metrics": metrics.to_dict(),
            "alerts_this_week": [
                a.to_dict() for a in self._alerts
                if a.timestamp >= metrics.window_start
            ],
            "trend_analysis": self._compute_trend(),
            "recommendations": self._generate_recommendations(metrics)
        }

        return report

    def _compute_trend(self) -> Dict[str, Any]:
        """Compute trend metrics."""
        if not self._current_metrics:
            return {"status": "insufficient_data"}

        # Check if we have enough data (14 days)
        window_duration = (datetime.now(timezone.utc) - self._current_metrics.window_start).days
        if window_duration < 14:
            return {"status": "insufficient_data"}

        # Compare this week vs last week
        this_week = self.compute_metrics(7)
        last_week = self.compute_metrics(14)

        return {
            "accuracy_trend": "improving" if this_week.accuracy > last_week.accuracy else "declining",
            "accuracy_change": this_week.accuracy - last_week.accuracy,
            "veto_volume_trend": "increasing" if this_week.total_vetoes > last_week.total_vetoes else "decreasing",
            "veto_volume_change": this_week.total_vetoes - last_week.total_vetoes
        }

    def _generate_recommendations(self, metrics: VetoMetrics) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if metrics.accuracy < self.accuracy_threshold:
            recommendations.append(
                f"CRITICAL: Veto accuracy ({metrics.accuracy:.1f}%) is below threshold. "
                "Consider demotion from veto_only stage."
            )

        if metrics.total_vetoes < 10:
            recommendations.append(
                "Insufficient veto sample size. Continue collecting data before making promotion decisions."
            )

        # Find worst performing symbol
        if metrics.accuracy_by_symbol:
            worst_symbol = min(metrics.accuracy_by_symbol.items(), key=lambda x: x[1])
            if worst_symbol[1] < 50:
                recommendations.append(
                    f"Review veto logic for {worst_symbol[0]} (accuracy: {worst_symbol[1]:.1f}%)"
                )

        # Find most common veto reason
        if metrics.top_veto_reasons:
            top_reason = metrics.top_veto_reasons[0]
            if top_reason[1] > 40:  # More than 40% of vetoes
                recommendations.append(
                    f"Dominant veto reason '{top_reason[0]}' ({top_reason[1]:.1f}%) - "
                    "consider tuning this specific veto condition"
                )

        if not recommendations:
            recommendations.append("No specific recommendations - continue monitoring")

        return recommendations

    def save_report(self, report: Dict[str, Any], filename: str) -> str:
        """Save report to file."""
        path = self.output_dir / filename
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"[VETO_WATCH] Report saved: {path}")
        return str(path)

    def get_alerts(self, days: int = 7) -> List[RegressionAlert]:
        """Get recent alerts."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [a for a in self._alerts if a.timestamp >= cutoff]

    def get_summary(self) -> Dict[str, Any]:
        """Get current summary status."""
        metrics = self.compute_metrics()
        recent_alerts = self.get_alerts(days=1)

        return {
            "total_vetoes_tracked": len(self._vetoes),
            "resolved_vetoes": len(self._veto_outcomes),
            "pending_vetoes": metrics.pending_vetoes,
            "current_accuracy": metrics.accuracy,
            "accuracy_threshold": self.accuracy_threshold,
            "status": "HEALTHY" if metrics.accuracy >= self.accuracy_threshold else "DEGRADED",
            "active_alerts": len(recent_alerts),
            "top_veto_reason": metrics.top_veto_reasons[0][0] if metrics.top_veto_reasons else "N/A"
        }


def create_veto_watch(
    regime_manifest_path: str = "/Users/jim/work/curly-succotash/coordination/runtime/regime_manifest.json",
    output_dir: str = "/Users/jim/work/curly-succotash/logs/veto_watch"
) -> VetoRegressionWatch:
    """
    Factory function to create veto watch with default paths.

    Returns:
        Configured VetoRegressionWatch instance
    """
    watch = VetoRegressionWatch(output_dir=output_dir)
    watch.load_regime_manifest(regime_manifest_path)
    return watch
