"""
Daily Operator Runbook Generator

Generates comprehensive daily reports for trading operators showing:
- What traded (baseline decisions)
- What HRM wanted (shadow signals)
- Why HRM was blocked (veto reasons)
- PnL comparison (baseline vs HRM shadow)
- Promotion readiness status
- Kill-switch status
- Regime coverage for the day

Output formats:
- Markdown (human-readable)
- JSON (automation/consumption)
"""

import json
import logging
import math
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class ReportFormat(str, Enum):
    """Output format for runbook reports."""
    MARKDOWN = "markdown"
    JSON = "json"
    CSV = "csv"


@dataclass
class DailySnapshot:
    """Snapshot of trading day metrics."""
    date: str
    total_trading_hours: float
    symbols_tracked: List[str]
    timeframes_tracked: List[str]

    # Baseline performance
    baseline_trades: int
    baseline_net_pnl: float
    baseline_win_rate: float
    baseline_sharpe: float
    baseline_max_drawdown: float

    # HRM shadow performance
    hrm_shadow_trades: int
    hrm_shadow_net_pnl: float
    hrm_shadow_win_rate: float
    hrm_shadow_sharpe: float
    hrm_shadow_max_drawdown: float

    # Comparison
    pnl_difference: float
    hrm_outperformance: bool
    outperformance_rate: float

    # Veto metrics
    total_vetoes: int
    veto_accuracy: float
    top_veto_reasons: List[Any]

    # Regime coverage
    regimes_detected: List[str]
    regime_coverage_pct: float

    # Kill-switch status
    killswitch_active: bool
    killswitch_triggers: List[str]

    # Promotion status
    symbols_ready_promotion: List[str]
    symbols_require_demotion: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradeSummary:
    """Summary of trades for the day."""
    symbol: str
    timeframe: str
    baseline_trades: int
    baseline_pnl: float
    hrm_shadow_trades: int
    hrm_shadow_pnl: float
    vetoes_issued: int
    veto_accuracy: float
    winner: str  # "baseline", "hrm", "tie"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DailyRunbookGenerator:
    """
    Generates daily operator runbooks with comprehensive trading analysis.

    Example:
        generator = DailyRunbookGenerator(
            output_dir="/Users/jim/work/curly-succotash/logs/runbooks"
        )

        # Generate from simulator data
        runbook = generator.generate_from_simulator(
            simulator=simulator,
            shadow_engine=shadow_engine,
            promotion_ladder=promotion_ladder,
            veto_watch=veto_watch,
            killswitch=killswitch
        )

        # Save reports
        generator.save_markdown(runbook, "daily_runbook_2026-03-06.md")
        generator.save_json(runbook, "daily_runbook_2026-03-06.json")
    """

    def __init__(
        self,
        output_dir: str = "/Users/jim/work/curly-succotash/logs/runbooks",
        timezone_str: str = "UTC"
    ):
        """
        Initialize runbook generator.

        Args:
            output_dir: Directory for saving reports
            timezone_str: Timezone for report timestamps
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timezone_str = timezone_str

        logger.info(f"[RUNBOOK] Generator initialized, output: {output_dir}")

    def generate_from_simulator(
        self,
        simulator: Any,
        shadow_engine: Any,
        promotion_ladder: Any,
        veto_watch: Any,
        killswitch: Any,
        date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate daily runbook from simulator components.

        Args:
            simulator: Trading simulator instance
            shadow_engine: HRM shadow engine instance
            promotion_ladder: HRM promotion ladder instance
            veto_watch: Veto regression watch instance
            killswitch: Kill-switch instance
            date: Date to generate report for (default: today)

        Returns:
            Complete runbook dictionary
        """
        if date is None:
            date = self._infer_report_date(simulator, shadow_engine)

        date_str = date.strftime("%Y-%m-%d")

        # Collect snapshot data
        snapshot = self._collect_snapshot(
            simulator=simulator,
            shadow_engine=shadow_engine,
            veto_watch=veto_watch,
            killswitch=killswitch,
            date=date
        )

        # Collect promotion status
        promotion_status = self._collect_promotion_status(promotion_ladder)

        # Collect veto analysis
        veto_analysis = self._collect_veto_analysis(veto_watch, date)

        # Collect trade summaries
        trade_summaries = self._collect_trade_summaries(simulator, shadow_engine, veto_analysis, date)

        snapshot.symbols_ready_promotion = [
            f"{item['symbol']}/{item['timeframe']}"
            for item in promotion_status.get("ready_for_promotion", [])
        ]
        snapshot.symbols_require_demotion = [
            f"{item['symbol']}/{item['timeframe']}"
            for item in promotion_status.get("require_demotion", [])
        ]

        # Generate narrative
        narrative = self._generate_narrative(snapshot, promotion_status, veto_analysis)

        runbook = {
            "report_type": "daily_operator_runbook",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_date": date_str,
            "timezone": self.timezone_str,
            "executive_summary": self._generate_executive_summary(snapshot, narrative),
            "daily_snapshot": snapshot.to_dict(),
            "trade_summaries": [t.to_dict() for t in trade_summaries],
            "promotion_status": promotion_status,
            "veto_analysis": veto_analysis,
            "killswitch_status": self._collect_killswitch_status(killswitch),
            "regime_analysis": self._collect_regime_analysis(snapshot),
            "narrative": narrative,
            "action_items": self._generate_action_items(snapshot, promotion_status, veto_analysis),
            "appendix": {
                "data_sources": self._collect_data_sources(simulator),
                "methodology": self._get_methodology_notes()
            }
        }

        return runbook

    def _infer_report_date(
        self,
        simulator: Any,
        shadow_engine: Any,
    ) -> datetime:
        """Use the latest observed trade activity as the default report date."""
        candidate_timestamps: List[datetime] = []

        paper_engine = getattr(simulator, "paper_engine", None)
        if paper_engine:
            for trade in paper_engine.get_completed_trades():
                timestamp = self._trade_timestamp(trade)
                if timestamp is not None:
                    candidate_timestamps.append(timestamp)

        for trade in list(getattr(shadow_engine, "shadow_trades", []) or []):
            timestamp = getattr(trade, "timestamp", None)
            if timestamp is not None:
                candidate_timestamps.append(timestamp)

        if not candidate_timestamps:
            return datetime.now(timezone.utc)

        latest_timestamp = max(
            ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            for ts in candidate_timestamps
        )
        return latest_timestamp.astimezone(timezone.utc)

    def _collect_snapshot(
        self,
        simulator: Any,
        shadow_engine: Any,
        veto_watch: Any,
        killswitch: Any,
        date: datetime
    ) -> DailySnapshot:
        """Collect daily snapshot metrics."""
        start_time, end_time = self._report_window(date)
        baseline_trades = self._filter_baseline_trades(simulator, start_time, end_time)
        shadow_trades = self._filter_shadow_trades(shadow_engine, start_time, end_time)
        veto_report = veto_watch.generate_daily_report(date) if veto_watch else {}
        veto_metrics = veto_report.get("daily_metrics", {})
        ks_status = self._collect_killswitch_status(killswitch)

        baseline_stats = self._compute_trade_metrics(baseline_trades, dict_mode=True)
        shadow_stats = self._compute_trade_metrics(shadow_trades, dict_mode=False)
        outperformance_rate = self._compute_outperformance_rate(baseline_trades, shadow_trades)
        pnl_diff = shadow_stats["net_pnl"] - baseline_stats["net_pnl"]
        hrm_outperforms = pnl_diff > 0
        symbols_tracked = sorted(set(self._configured_symbols(simulator)) | {trade["symbol"] for trade in baseline_trades} | {trade.symbol for trade in shadow_trades})
        timeframes_tracked = sorted(set(self._configured_timeframes(simulator)) | {trade.get("timeframe", "unknown") for trade in baseline_trades} | {trade.timeframe.value for trade in shadow_trades})
        regimes_detected = veto_report.get("regime_analysis", {}).get("regimes_detected", [])

        return DailySnapshot(
            date=date.strftime("%Y-%m-%d"),
            total_trading_hours=(end_time - start_time).total_seconds() / 3600.0,
            symbols_tracked=symbols_tracked,
            timeframes_tracked=timeframes_tracked,
            baseline_trades=baseline_stats["trades"],
            baseline_net_pnl=baseline_stats["net_pnl"],
            baseline_win_rate=baseline_stats["win_rate"],
            baseline_sharpe=baseline_stats["sharpe"],
            baseline_max_drawdown=baseline_stats["max_drawdown"],
            hrm_shadow_trades=shadow_stats["trades"],
            hrm_shadow_net_pnl=shadow_stats["net_pnl"],
            hrm_shadow_win_rate=shadow_stats["win_rate"],
            hrm_shadow_sharpe=shadow_stats["sharpe"],
            hrm_shadow_max_drawdown=shadow_stats["max_drawdown"],
            pnl_difference=pnl_diff,
            hrm_outperformance=hrm_outperforms,
            outperformance_rate=outperformance_rate,
            total_vetoes=veto_metrics.get("total_vetoes", 0),
            veto_accuracy=veto_metrics.get("accuracy", 0.0),
            top_veto_reasons=veto_report.get("top_veto_reasons", []),
            regimes_detected=regimes_detected,
            regime_coverage_pct=self._compute_regime_coverage_pct(veto_watch, regimes_detected),
            killswitch_active=ks_status["is_active"],
            killswitch_triggers=ks_status["active_triggers"],
            symbols_ready_promotion=[],  # Filled in by promotion status
            symbols_require_demotion=[]  # Filled in by promotion status
        )

    def _report_window(self, date: datetime) -> tuple[datetime, datetime]:
        report_time = date if date.tzinfo else date.replace(tzinfo=timezone.utc)
        start_time = report_time.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return start_time, start_time + timedelta(days=1)

    def _configured_symbols(self, simulator: Any) -> List[str]:
        return list(getattr(getattr(simulator, "config", None), "symbols", []) or [])

    def _configured_timeframes(self, simulator: Any) -> List[str]:
        return [
            timeframe.value if hasattr(timeframe, "value") else str(timeframe)
            for timeframe in (getattr(getattr(simulator, "config", None), "timeframes", []) or [])
        ]

    def _filter_baseline_trades(
        self,
        simulator: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        paper_engine = getattr(simulator, "paper_engine", None)
        if not paper_engine:
            return []
        trades = paper_engine.get_completed_trades()
        return [
            trade for trade in trades
            if self._trade_in_window(self._trade_timestamp(trade), start_time, end_time)
        ]

    def _filter_shadow_trades(
        self,
        shadow_engine: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Any]:
        trades = list(getattr(shadow_engine, "shadow_trades", []) or [])
        return [
            trade for trade in trades
            if self._trade_in_window(getattr(trade, "timestamp", None), start_time, end_time)
        ]

    def _trade_timestamp(self, trade: Dict[str, Any]) -> Optional[datetime]:
        timestamp = trade.get("exit_time") or trade.get("timestamp") or trade.get("entry_time")
        if timestamp is None:
            return None
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp)
        return timestamp

    def _trade_in_window(
        self,
        timestamp: Optional[datetime],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        if timestamp is None:
            return False
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return start_time <= timestamp.astimezone(timezone.utc) < end_time

    def _compute_trade_metrics(
        self,
        trades: List[Any],
        *,
        dict_mode: bool,
    ) -> Dict[str, float]:
        pnl_values = [
            float(trade.get("pnl", 0.0)) if dict_mode else float(getattr(trade, "net_pnl", 0.0))
            for trade in trades
        ]
        trade_count = len(pnl_values)
        net_pnl = sum(pnl_values)
        win_rate = (sum(1 for pnl in pnl_values if pnl > 0) / trade_count * 100.0) if trade_count else 0.0
        sharpe = 0.0
        if trade_count > 1:
            stddev = statistics.stdev(pnl_values)
            if stddev > 0:
                sharpe = statistics.mean(pnl_values) / stddev * math.sqrt(trade_count)

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in pnl_values:
            cumulative += pnl
            peak = max(peak, cumulative)
            base = peak if peak > 0 else 1.0
            max_drawdown = max(max_drawdown, (peak - cumulative) / base * 100.0)

        return {
            "trades": trade_count,
            "net_pnl": net_pnl,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
        }

    def _compute_outperformance_rate(
        self,
        baseline_trades: List[Dict[str, Any]],
        shadow_trades: List[Any],
    ) -> float:
        baseline_by_key: Dict[tuple[str, str], float] = {}
        for trade in baseline_trades:
            key = (trade.get("symbol", "UNKNOWN"), str(trade.get("timeframe", "unknown")))
            baseline_by_key[key] = baseline_by_key.get(key, 0.0) + float(trade.get("pnl", 0.0))

        shadow_by_key: Dict[tuple[str, str], float] = {}
        for trade in shadow_trades:
            key = (trade.symbol, trade.timeframe.value)
            shadow_by_key[key] = shadow_by_key.get(key, 0.0) + float(trade.net_pnl)

        keys = set(baseline_by_key) | set(shadow_by_key)
        if not keys:
            return 0.0

        wins = sum(1 for key in keys if shadow_by_key.get(key, 0.0) > baseline_by_key.get(key, 0.0))
        return wins / len(keys) * 100.0

    def _compute_regime_coverage_pct(
        self,
        veto_watch: Any,
        regimes_detected: List[str],
    ) -> float:
        manifest = getattr(veto_watch, "_regime_manifest", {}) if veto_watch else {}
        total_regimes = 0
        if isinstance(manifest, dict):
            regimes = manifest.get("regimes", {})
            for values in regimes.values():
                if isinstance(values, list):
                    total_regimes += len(values)
        if total_regimes <= 0:
            return 0.0
        return len(set(regimes_detected)) / total_regimes * 100.0

    def _collect_promotion_status(self, promotion_ladder: Any) -> Dict[str, Any]:
        """Collect promotion ladder status."""
        if not promotion_ladder:
            return {
                "total_symbols_tracked": 0,
                "by_stage": {"shadow": 0, "veto_only": 0, "size_capped": 0, "primary": 0},
                "symbols": [],
                "ready_for_promotion": [],
                "require_demotion": [],
            }
        states = promotion_ladder.get_all_states()

        status = {
            "total_symbols_tracked": len(states),
            "by_stage": {
                "shadow": 0,
                "veto_only": 0,
                "size_capped": 0,
                "primary": 0
            },
            "symbols": []
        }

        for key, state in states.items():
            stage = state.current_stage.value
            status["by_stage"][stage] = status["by_stage"].get(stage, 0) + 1

            status["symbols"].append({
                "symbol": state.symbol,
                "timeframe": state.timeframe.value,
                "current_stage": stage,
                "days_in_stage": (datetime.now(timezone.utc) - state.stage_entered_at).days,
                "total_trades": state.total_trades,
                "cumulative_pnl": state.cumulative_pnl,
                "ready_for_promotion": False  # Would be set by evaluation
            })

        # Get promotion-ready symbols
        ready = promotion_ladder.get_promotion_ready_symbols()
        status["ready_for_promotion"] = [
            {"symbol": e.symbol, "timeframe": e.timeframe, "target_stage": e.target_stage.value}
            for e in ready
        ]

        # Get demotion-required symbols
        demotion = promotion_ladder.get_demotion_required_symbols()
        status["require_demotion"] = [
            {"symbol": e.symbol, "timeframe": e.timeframe, "reason": e.blocked_reasons}
            for e in demotion
        ]

        return status

    def _collect_veto_analysis(self, veto_watch: Any, date: datetime) -> Dict[str, Any]:
        """Collect veto analysis from veto watch."""
        if not veto_watch:
            return {
                "summary": {"total_vetoes_tracked": 0, "accuracy": 0.0, "status": "UNAVAILABLE"},
                "daily_metrics": {},
                "top_veto_reasons": [],
                "regime_analysis": {},
                "symbol_breakdown": {},
                "recommendations": [],
                "total_vetoes": 0,
            }
        summary = veto_watch.get_summary()
        daily_report = veto_watch.generate_daily_report(date)
        summary["accuracy"] = daily_report.get("daily_metrics", {}).get("accuracy", summary.get("current_accuracy", 0.0))
        summary["total_vetoes"] = daily_report.get("daily_metrics", {}).get("total_vetoes", 0)

        return {
            "summary": summary,
            "daily_metrics": daily_report.get("daily_metrics", {}),
            "top_veto_reasons": daily_report.get("top_veto_reasons", []),
            "regime_analysis": daily_report.get("regime_analysis", {}),
            "symbol_breakdown": daily_report.get("symbol_breakdown", {}),
            "recommendations": daily_report.get("recommendations", []),
            # Ensure total_vetoes is in summary for markdown conversion
            "total_vetoes": summary.get("total_vetoes_tracked", 0)
        }

    def _collect_trade_summaries(
        self,
        simulator: Any,
        shadow_engine: Any,
        veto_analysis: Dict[str, Any],
        date: datetime,
    ) -> List[TradeSummary]:
        """Collect per-symbol trade summaries."""
        start_time, end_time = self._report_window(date)
        baseline_trades = self._filter_baseline_trades(simulator, start_time, end_time)
        shadow_trades = self._filter_shadow_trades(shadow_engine, start_time, end_time)
        symbol_breakdown = veto_analysis.get("symbol_breakdown", {})
        veto_counts = symbol_breakdown.get("veto_counts", {})
        veto_accuracy = symbol_breakdown.get("accuracy", {})
        summaries: List[TradeSummary] = []

        grouped_baseline: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for trade in baseline_trades:
            key = (trade.get("symbol", "UNKNOWN"), str(trade.get("timeframe", "unknown")))
            grouped_baseline.setdefault(key, []).append(trade)

        grouped_shadow: Dict[tuple[str, str], List[Any]] = {}
        for trade in shadow_trades:
            key = (trade.symbol, trade.timeframe.value)
            grouped_shadow.setdefault(key, []).append(trade)

        for symbol, timeframe in sorted(set(grouped_baseline) | set(grouped_shadow)):
            baseline_group = grouped_baseline.get((symbol, timeframe), [])
            shadow_group = grouped_shadow.get((symbol, timeframe), [])
            baseline_pnl = sum(float(trade.get("pnl", 0.0)) for trade in baseline_group)
            shadow_pnl = sum(float(trade.net_pnl) for trade in shadow_group)

            summaries.append(
                TradeSummary(
                    symbol=symbol,
                    timeframe=timeframe,
                    baseline_trades=len(baseline_group),
                    baseline_pnl=baseline_pnl,
                    hrm_shadow_trades=len(shadow_group),
                    hrm_shadow_pnl=shadow_pnl,
                    vetoes_issued=int(veto_counts.get(symbol, 0)),
                    veto_accuracy=float(veto_accuracy.get(symbol, 0.0)),
                    winner=self._determine_winner(baseline_pnl, shadow_pnl),
                )
            )

        return summaries

    def _determine_winner(self, baseline_pnl: float, hrm_pnl: float) -> str:
        """Determine which approach won."""
        if abs(baseline_pnl - hrm_pnl) < 0.001:  # Within 0.1%
            return "tie"
        return "hrm" if hrm_pnl > baseline_pnl else "baseline"

    def _generate_narrative(
        self,
        snapshot: DailySnapshot,
        promotion_status: Dict[str, Any],
        veto_analysis: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generate human-readable narrative sections."""
        narrative = {}

        # Overall performance narrative
        if snapshot.hrm_outperformance:
            narrative["performance"] = (
                f"HRM shadow mode outperformed baseline trading today, "
                f"generating ${snapshot.pnl_difference:.2f} more in PnL "
                f"({snapshot.outperformance_rate:.1f}% outperformance rate). "
                f"HRM would have executed {snapshot.hrm_shadow_trades} trades "
                f"compared to baseline's {snapshot.baseline_trades} trades."
            )
        else:
            narrative["performance"] = (
                f"Baseline trading outperformed HRM shadow mode today by "
                f"${abs(snapshot.pnl_difference):.2f}. "
                f"Baseline executed {snapshot.baseline_trades} trades with "
                f"{snapshot.baseline_win_rate:.1f}% win rate."
            )

        # Veto narrative
        if snapshot.total_vetoes > 0:
            narrative["vetoes"] = (
                f"HRM issued {snapshot.total_vetoes} vetoes today with "
                f"{snapshot.veto_accuracy:.1f}% accuracy. "
                f"Top veto reason: {snapshot.top_veto_reasons[0][0] if snapshot.top_veto_reasons else 'N/A'}."
            )
        else:
            narrative["vetoes"] = "No vetoes were issued today."

        # Promotion narrative
        if promotion_status.get("ready_for_promotion"):
            ready_symbols = ", ".join(
                f"{s['symbol']}/{s['timeframe']}"
                for s in promotion_status["ready_for_promotion"]
            )
            narrative["promotion"] = (
                f"The following symbols are ready for promotion: {ready_symbols}. "
                f"Review promotion criteria and consider advancing to next stage."
            )
        else:
            narrative["promotion"] = "No symbols are currently ready for promotion."

        # Kill-switch narrative
        if snapshot.killswitch_active:
            narrative["killswitch"] = (
                f"⚠️ KILL-SWITCH IS ACTIVE. Trading has been halted due to: "
                f"{', '.join(snapshot.killswitch_triggers)}. "
                f"Manual intervention required before resuming."
            )
        else:
            narrative["killswitch"] = "Kill-switch is inactive - trading operations normal."

        return narrative

    def _generate_executive_summary(
        self,
        snapshot: DailySnapshot,
        narrative: Dict[str, str]
    ) -> str:
        """Generate executive summary paragraph."""
        status_emoji = "✅" if snapshot.hrm_outperformance else "⚠️"
        ks_emoji = "🔴" if snapshot.killswitch_active else "🟢"

        return (
            f"{status_emoji} **HRM Performance**: {'Outperforming' if snapshot.hrm_outperformance else 'Underperforming'} "
            f"(PnL diff: ${snapshot.pnl_difference:.2f})\n\n"
            f"{ks_emoji} **Kill-Switch**: {'ACTIVE - Trading Halted' if snapshot.killswitch_active else 'Inactive - Normal Operations'}\n\n"
            f"📊 **Trading Summary**: {snapshot.baseline_trades} baseline trades, "
            f"{snapshot.hrm_shadow_trades} HRM shadow trades, "
            f"{snapshot.total_vetoes} vetoes issued\n\n"
            f"🎯 **Veto Accuracy**: {snapshot.veto_accuracy:.1f}%\n\n"
            f"🌍 **Regime Coverage**: {snapshot.regime_coverage_pct:.1f}% of target regimes detected"
        )

    def _generate_action_items(
        self,
        snapshot: DailySnapshot,
        promotion_status: Dict[str, Any],
        veto_analysis: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Generate actionable items for operators."""
        actions = []

        # Kill-switch actions
        if snapshot.killswitch_active:
            actions.append({
                "priority": "CRITICAL",
                "action": "Review and resolve kill-switch triggers",
                "details": f"Triggers: {', '.join(snapshot.killswitch_triggers)}",
                "owner": "Trading Operator"
            })

        # Promotion actions
        for symbol in promotion_status.get("ready_for_promotion", []):
            actions.append({
                "priority": "HIGH",
                "action": f"Review promotion for {symbol['symbol']}/{symbol['timeframe']}",
                "details": f"Target stage: {symbol['target_stage']}",
                "owner": "ML Team"
            })

        # Demotion actions
        for symbol in promotion_status.get("require_demotion", []):
            actions.append({
                "priority": "HIGH",
                "action": f"Review demotion for {symbol['symbol']}/{symbol['timeframe']}",
                "details": f"Reasons: {', '.join(symbol['reason'])}",
                "owner": "ML Team"
            })

        # Veto accuracy actions
        if snapshot.veto_accuracy < 60:
            actions.append({
                "priority": "MEDIUM",
                "action": "Investigate low veto accuracy",
                "details": f"Current accuracy: {snapshot.veto_accuracy:.1f}%",
                "owner": "ML Team"
            })

        # Regime coverage actions
        if snapshot.regime_coverage_pct < 80:
            actions.append({
                "priority": "LOW",
                "action": "Improve regime coverage",
                "details": f"Current coverage: {snapshot.regime_coverage_pct:.1f}%",
                "owner": "Data Team"
            })

        if not actions:
            actions.append({
                "priority": "INFO",
                "action": "Continue monitoring - no immediate actions required",
                "details": "All systems operating within normal parameters",
                "owner": "Trading Operator"
            })

        return actions

    def _collect_killswitch_status(self, killswitch: Any) -> Dict[str, Any]:
        """Collect kill-switch status."""
        if not killswitch:
            return {
                "is_active": False,
                "triggered_at": None,
                "trigger_reason": None,
                "active_triggers": [],
                "cooldown_remaining_hours": 0,
                "can_reset": False,
                "recent_triggers": [],
            }

        metrics = killswitch.get_metrics()
        now = datetime.now(timezone.utc)
        last_trigger = metrics.last_trigger_event
        cooldown_remaining = 0
        if metrics.cooldown_ends_at and metrics.cooldown_ends_at > now:
            cooldown_remaining = int((metrics.cooldown_ends_at - now).total_seconds() // 3600)

        trigger_reason = last_trigger.reason.value if last_trigger and last_trigger.reason else None

        return {
            "is_active": metrics.state.value == "triggered",
            "triggered_at": metrics.triggered_at.isoformat() if metrics.triggered_at else None,
            "trigger_reason": trigger_reason,
            "active_triggers": [trigger_reason] if trigger_reason else [],
            "cooldown_remaining_hours": cooldown_remaining,
            "can_reset": bool(metrics.cooldown_ends_at and now >= metrics.cooldown_ends_at),
            "recent_triggers": [
                {
                    "timestamp": last_trigger.timestamp.isoformat(),
                    "reason": trigger_reason,
                    "symbol": "SYSTEM"
                }
            ] if last_trigger else []
        }

    def _collect_regime_analysis(self, snapshot: DailySnapshot) -> Dict[str, Any]:
        """Collect regime analysis."""
        return {
            "regimes_detected": snapshot.regimes_detected,
            "coverage_percentage": snapshot.regime_coverage_pct,
            "missing_regimes": self._identify_missing_regimes(snapshot.regimes_detected),
            "time_in_regime": {
                regime: "TBD"  # Would be computed from regime duration tracking
                for regime in snapshot.regimes_detected
            }
        }

    def _identify_missing_regimes(self, detected: List[str]) -> List[str]:
        """Identify missing regimes from target list."""
        target_regimes = [
            "VOL_NORMAL", "VOL_HIGH", "VOL_LOW",
            "TREND_BULL_STRONG", "TREND_BULL_WEAK",
            "TREND_BEAR_STRONG", "TREND_BEAR_WEAK",
            "TREND_RANGE", "LIQUIDITY_HIGH", "LIQUIDITY_LOW"
        ]
        return [r for r in target_regimes if r not in detected]

    def _collect_data_sources(self, simulator: Any) -> List[Dict[str, str]]:
        """Collect data source information."""
        return [
            {
                "name": "Trading Simulator",
                "type": "baseline_trading",
                "description": "Primary trading engine with 12 strategies"
            },
            {
                "name": "HRM Shadow Engine",
                "type": "shadow_mode",
                "description": "HRM predictions in shadow mode"
            },
            {
                "name": "Promotion Ladder",
                "type": "promotion_tracking",
                "description": "HRM promotion stage tracking"
            },
            {
                "name": "Veto Watch",
                "type": "regression_monitoring",
                "description": "Veto reason tracking and regression detection"
            }
        ]

    def _get_methodology_notes(self) -> str:
        """Return methodology notes for the report."""
        return """
This daily runbook compares baseline trading performance against HRM shadow mode predictions.

**Key Metrics:**
- PnL Difference: HRM shadow PnL minus baseline PnL (after fees/slippage)
- Outperformance Rate: Percentage of symbols where HRM outperformed baseline
- Veto Accuracy: Percentage of vetoes that correctly avoided losing trades
- Regime Coverage: Percentage of target market regimes detected during the day

**Promotion Criteria:**
- Shadow → Veto Only: 7 days, 100 trades, beat baseline
- Veto Only → Size Capped: 14 days, 200 trades, >60% veto accuracy
- Size Capped → Primary: 30 days, 500 trades, Sharpe > 1.5

**Data Quality:**
- All PnL figures include fees (0.1%) and slippage (5 bps)
- Veto accuracy computed only on resolved trades (exited positions)
- Regime detection uses volatility, trend, and liquidity indicators
"""

    def save_markdown(self, runbook: Dict[str, Any], filename: str) -> str:
        """Save runbook as Markdown."""
        path = self.output_dir / filename

        md = self._convert_to_markdown(runbook)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(md)

        logger.info(f"[RUNBOOK] Markdown report saved: {path}")
        return str(path)

    def _convert_to_markdown(self, runbook: Dict[str, Any]) -> str:
        """Convert runbook dictionary to Markdown format."""
        md = []

        # Header
        md.append(f"# Daily Operator Runbook")
        md.append(f"**Date**: {runbook['report_date']}")
        md.append(f"**Generated**: {runbook['generated_at']}")
        md.append("")

        # Executive Summary
        md.append("## Executive Summary")
        md.append(runbook['executive_summary'])
        md.append("")

        # Daily Snapshot
        snapshot = runbook['daily_snapshot']
        md.append("## Daily Snapshot")
        md.append("")
        md.append("### Baseline Performance")
        md.append(f"- **Trades**: {snapshot['baseline_trades']}")
        md.append(f"- **Net PnL**: ${snapshot['baseline_net_pnl']:.2f}")
        md.append(f"- **Win Rate**: {snapshot['baseline_win_rate']:.1f}%")
        md.append(f"- **Sharpe Ratio**: {snapshot['baseline_sharpe']:.2f}")
        md.append(f"- **Max Drawdown**: {snapshot['baseline_max_drawdown']:.2f}%")
        md.append("")
        md.append("### HRM Shadow Performance")
        md.append(f"- **Trades**: {snapshot['hrm_shadow_trades']}")
        md.append(f"- **Net PnL**: ${snapshot['hrm_shadow_net_pnl']:.2f}")
        md.append(f"- **Win Rate**: {snapshot['hrm_shadow_win_rate']:.1f}%")
        md.append(f"- **Sharpe Ratio**: {snapshot['hrm_shadow_sharpe']:.2f}")
        md.append(f"- **Max Drawdown**: {snapshot['hrm_shadow_max_drawdown']:.2f}%")
        md.append("")
        md.append("### Comparison")
        md.append(f"- **PnL Difference**: ${snapshot['pnl_difference']:.2f}")
        md.append(f"- **HRM Outperformance**: {'✅ Yes' if snapshot['hrm_outperformance'] else '❌ No'}")
        md.append(f"- **Outperformance Rate**: {snapshot['outperformance_rate']:.1f}%")
        md.append("")

        # Narrative
        md.append("## Analysis")
        for section, text in runbook['narrative'].items():
            md.append(f"### {section.replace('_', ' ').title()}")
            md.append(text)
            md.append("")

        # Promotion Status
        md.append("## Promotion Status")
        promo = runbook['promotion_status']
        md.append(f"- **Total Symbols Tracked**: {promo['total_symbols_tracked']}")
        md.append(f"- **By Stage**: {', '.join(f'{k}={v}' for k, v in promo['by_stage'].items())}")
        md.append("")
        if promo.get('ready_for_promotion'):
            md.append("### Ready for Promotion")
            for sym in promo['ready_for_promotion']:
                md.append(f"- {sym['symbol']}/{sym['timeframe']} → {sym['target_stage']}")
            md.append("")
        if promo.get('require_demotion'):
            md.append("### Require Demotion")
            for sym in promo['require_demotion']:
                md.append(f"- {sym['symbol']}/{sym['timeframe']}: {', '.join(sym['reason'])}")
            md.append("")

        # Action Items
        md.append("## Action Items")
        for action in runbook['action_items']:
            md.append(f"### {action['priority']}: {action['action']}")
            md.append(f"**Details**: {action['details']}")
            md.append(f"**Owner**: {action['owner']}")
            md.append("")

        # Veto Analysis
        md.append("## Veto Analysis")
        veto = runbook['veto_analysis']
        md.append(f"- **Total Vetoes**: {veto.get('total_vetoes', veto['summary'].get('total_vetoes_tracked', 0))}")
        md.append(f"- **Accuracy**: {veto['summary'].get('accuracy', 0.0):.1f}%")
        md.append(f"- **Status**: {veto['summary'].get('status', 'UNKNOWN')}")
        md.append("")
        if veto.get('top_veto_reasons'):
            md.append("### Top Veto Reasons")
            for reason, pct in veto['top_veto_reasons']:
                md.append(f"- {reason.replace('_', ' ').title()}: {pct:.1f}%")
            md.append("")

        # Recommendations
        if veto.get('recommendations'):
            md.append("## Recommendations")
            for rec in veto['recommendations']:
                md.append(f"- {rec}")
            md.append("")

        return "\n".join(md)

    def save_json(self, runbook: Dict[str, Any], filename: str) -> str:
        """Save runbook as JSON."""
        path = self.output_dir / filename

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(runbook, f, indent=2)

        logger.info(f"[RUNBOOK] JSON report saved: {path}")
        return str(path)

    def save_csv(self, runbook: Dict[str, Any], filename: str) -> str:
        """Save trade summaries as CSV."""
        path = self.output_dir / filename

        import csv

        summaries = runbook.get('trade_summaries', [])
        if not summaries:
            logger.warning("[RUNBOOK] No trade summaries to save")
            return ""

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=summaries[0].keys())
            writer.writeheader()
            writer.writerows(summaries)

        logger.info(f"[RUNBOOK] CSV report saved: {path}")
        return str(path)


def create_runbook_generator(
    output_dir: str = "/Users/jim/work/curly-succotash/logs/runbooks"
) -> DailyRunbookGenerator:
    """
    Factory function to create runbook generator.

    Returns:
        Configured DailyRunbookGenerator instance
    """
    return DailyRunbookGenerator(output_dir=output_dir)
