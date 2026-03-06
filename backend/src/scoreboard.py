"""
Daily Scoreboard Generator

Generates daily comparison reports of baseline PnL vs HRM shadow PnL
after fees and slippage.

Output Formats:
- JSON: Machine-readable for dashboards
- Markdown: Human-readable for operators
- CSV: Spreadsheet-compatible for analysis
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum

from .models import Trade, Timeframe
from .hrm_shadow import ShadowMetrics, ShadowTrade

logger = logging.getLogger(__name__)


class ScoreboardFormat(str, Enum):
    """Output format for scoreboard."""
    JSON = "json"
    MARKDOWN = "markdown"
    CSV = "csv"


@dataclass
class DailyScoreboardEntry:
    """Single entry in daily scoreboard."""
    symbol: str
    timeframe: str
    baseline_strategy: str
    baseline_trades: int
    baseline_net_pnl: float
    baseline_sharpe: float
    baseline_max_drawdown: float
    baseline_win_rate: float

    hrm_shadow_trades: int
    hrm_shadow_net_pnl: float
    hrm_shadow_sharpe: float
    hrm_shadow_max_drawdown: float
    hrm_shadow_win_rate: float

    pnl_difference: float  # HRM - Baseline
    sharpe_difference: float
    hrm_outperformance: bool
    outperformance_pct: float  # (HRM - Baseline) / Baseline * 100

    vetoes_issued: int
    veto_accuracy: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyScoreboard:
    """Complete daily scoreboard."""
    date: str
    generated_at: str
    trading_day: str
    mode: str  # shadow, veto_only, size_capped, primary

    # Summary statistics
    total_symbols: int
    total_baseline_trades: int
    total_hrm_trades: int
    total_baseline_pnl: float
    total_hrm_pnl: float
    total_pnl_difference: float

    # Aggregate metrics
    avg_baseline_sharpe: float
    avg_hrm_sharpe: float
    symbols_hrm_outperformed: int
    outperformance_rate: float  # % of symbols where HRM won

    # Entries by symbol/timeframe
    entries: List[DailyScoreboardEntry]

    # Veto summary
    total_vetoes: int
    avg_veto_accuracy: float

    # Notes
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "generated_at": self.generated_at,
            "trading_day": self.trading_day,
            "mode": self.mode,
            "summary": {
                "total_symbols": self.total_symbols,
                "total_baseline_trades": self.total_baseline_trades,
                "total_hrm_trades": self.total_hrm_trades,
                "total_baseline_pnl": self.total_baseline_pnl,
                "total_hrm_pnl": self.total_hrm_pnl,
                "total_pnl_difference": self.total_pnl_difference,
                "avg_baseline_sharpe": self.avg_baseline_sharpe,
                "avg_hrm_sharpe": self.avg_hrm_sharpe,
                "symbols_hrm_outperformed": self.symbols_hrm_outperformed,
                "outperformance_rate": self.outperformance_rate,
                "total_vetoes": self.total_vetoes,
                "avg_veto_accuracy": self.avg_veto_accuracy,
            },
            "entries": [e.to_dict() for e in self.entries],
            "notes": self.notes,
        }


class ScoreboardGenerator:
    """
    Generates daily scoreboard comparing baseline vs HRM shadow.

    Example:
        generator = ScoreboardGenerator(output_dir="/path/to/scoreboards")

        scoreboard = generator.generate(
            date=datetime.now(timezone.utc),
            metrics=[shadow_metrics1, shadow_metrics2, ...],
            mode="shadow"
        )

        # Save in multiple formats
        generator.save_json(scoreboard)
        generator.save_markdown(scoreboard)
        generator.save_csv(scoreboard)
    """

    def __init__(
        self,
        output_dir: str = "/Users/jim/work/curly-succotash/logs/scoreboards"
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[SCOREBOARD] Generator initialized: {output_dir}")

    def generate(
        self,
        date: datetime,
        metrics: List[ShadowMetrics],
        mode: str,
        baseline_strategies: Optional[Dict[str, str]] = None
    ) -> DailyScoreboard:
        """
        Generate daily scoreboard from shadow metrics.

        Args:
            date: Date to generate scoreboard for
            metrics: List of ShadowMetrics from shadow engine
            mode: Shadow mode (shadow, veto_only, size_capped, primary)
            baseline_strategies: Map of symbol/timeframe to strategy name

        Returns:
            DailyScoreboard with aggregated results
        """
        date_str = date.strftime("%Y-%m-%d")
        generated_at = datetime.now(timezone.utc).isoformat()
        trading_day = (date - timedelta(days=1)).strftime("%Y-%m-%d")  # Previous day

        # Convert metrics to entries
        entries = []
        total_baseline_pnl = 0.0
        total_hrm_pnl = 0.0
        total_baseline_trades = 0
        total_hrm_trades = 0
        symbols_hrm_outperformed = 0
        total_vetoes = 0
        veto_accuracies = []

        for m in metrics:
            baseline_strategy = (
                baseline_strategies.get(f"{m.symbol}_{m.timeframe.value}", "UNKNOWN")
                if baseline_strategies else "Baseline"
            )

            outperformance_pct = (
                (m.pnl_difference / m.baseline_net_pnl * 100.0)
                if m.baseline_net_pnl != 0 else 0.0
            )

            entry = DailyScoreboardEntry(
                symbol=m.symbol,
                timeframe=m.timeframe.value,
                baseline_strategy=baseline_strategy,
                baseline_trades=m.baseline_trades,
                baseline_net_pnl=m.baseline_net_pnl,
                baseline_sharpe=m.baseline_sharpe,
                baseline_max_drawdown=m.baseline_max_drawdown,
                baseline_win_rate=m.baseline_win_rate,
                hrm_shadow_trades=m.hrm_shadow_trades,
                hrm_shadow_net_pnl=m.hrm_shadow_net_pnl,
                hrm_shadow_sharpe=m.hrm_shadow_sharpe,
                hrm_shadow_max_drawdown=m.hrm_shadow_max_drawdown,
                hrm_shadow_win_rate=m.hrm_shadow_win_rate,
                pnl_difference=m.pnl_difference,
                sharpe_difference=m.sharpe_difference,
                hrm_outperformance=m.hrm_outperformance,
                outperformance_pct=outperformance_pct,
                vetoes_issued=m.vetoes_issued,
                veto_accuracy=m.veto_accuracy,
            )

            entries.append(entry)

            # Aggregate totals
            total_baseline_pnl += m.baseline_net_pnl
            total_hrm_pnl += m.hrm_shadow_net_pnl
            total_baseline_trades += m.baseline_trades
            total_hrm_trades += m.hrm_shadow_trades

            if m.hrm_outperformance:
                symbols_hrm_outperformed += 1

            total_vetoes += m.vetoes_issued
            if m.veto_accuracy > 0:
                veto_accuracies.append(m.veto_accuracy)

        # Compute aggregate metrics
        total_symbols = len(entries)
        total_pnl_difference = total_hrm_pnl - total_baseline_pnl
        outperformance_rate = (
            symbols_hrm_outperformed / total_symbols * 100.0
            if total_symbols > 0 else 0.0
        )

        avg_baseline_sharpe = (
            sum(m.baseline_sharpe for m in metrics) / len(metrics)
            if metrics else 0.0
        )
        avg_hrm_sharpe = (
            sum(m.hrm_shadow_sharpe for m in metrics) / len(metrics)
            if metrics else 0.0
        )
        avg_veto_accuracy = (
            sum(veto_accuracies) / len(veto_accuracies)
            if veto_accuracies else 0.0
        )

        # Generate notes
        notes = self._generate_notes(
            total_pnl_difference=total_pnl_difference,
            outperformance_rate=outperformance_rate,
            total_vetoes=total_vetoes,
            mode=mode
        )

        scoreboard = DailyScoreboard(
            date=date_str,
            generated_at=generated_at,
            trading_day=trading_day,
            mode=mode,
            total_symbols=total_symbols,
            total_baseline_trades=total_baseline_trades,
            total_hrm_trades=total_hrm_trades,
            total_baseline_pnl=total_baseline_pnl,
            total_hrm_pnl=total_hrm_pnl,
            total_pnl_difference=total_pnl_difference,
            avg_baseline_sharpe=avg_baseline_sharpe,
            avg_hrm_sharpe=avg_hrm_sharpe,
            symbols_hrm_outperformed=symbols_hrm_outperformed,
            outperformance_rate=outperformance_rate,
            entries=entries,
            total_vetoes=total_vetoes,
            avg_veto_accuracy=avg_veto_accuracy,
            notes=notes,
        )

        logger.info(
            f"[SCOREBOARD] Generated for {date_str}: "
            f"{total_symbols} symbols, HRM outperformed in {symbols_hrm_outperformed} ({outperformance_rate:.1f}%)"
        )

        return scoreboard

    def _generate_notes(
        self,
        total_pnl_difference: float,
        outperformance_rate: float,
        total_vetoes: int,
        mode: str
    ) -> List[str]:
        """Generate human-readable notes for scoreboard."""
        notes = []

        # Overall performance note
        if total_pnl_difference > 0:
            notes.append(
                f"✓ HRM shadow outperformed baseline by ${total_pnl_difference:.2f} total"
            )
        else:
            notes.append(
                f"✗ HRM shadow underperformed baseline by ${abs(total_pnl_difference):.2f}"
            )

        # Outperformance rate note
        if outperformance_rate >= 70:
            notes.append(
                f"✓ HRM outperformed on {outperformance_rate:.1f}% of symbols (STRONG)"
            )
        elif outperformance_rate >= 50:
            notes.append(
                f"~ HRM outperformed on {outperformance_rate:.1f}% of symbols (MODERATE)"
            )
        else:
            notes.append(
                f"✗ HRM outperformed on only {outperformance_rate:.1f}% of symbols (WEAK)"
            )

        # Veto note
        if total_vetoes > 0:
            notes.append(f"⚠ {total_vetoes} vetoes issued by HRM")

        # Mode-specific note
        if mode == "shadow":
            notes.append("ℹ Mode: SHADOW - HRM has no trading authority")
        elif mode == "veto_only":
            notes.append("⚠ Mode: VETO_ONLY - HRM can block baseline trades")
        elif mode == "size_capped":
            notes.append("⚠ Mode: SIZE_CAPPED - HRM trading with size limits")
        elif mode == "primary":
            notes.append("✓ Mode: PRIMARY - HRM has full trading authority")

        return notes

    def save_json(
        self,
        scoreboard: DailyScoreboard,
        filename: Optional[str] = None
    ) -> str:
        """Save scoreboard as JSON."""
        if filename is None:
            filename = f"scoreboard_{scoreboard.date}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            json.dump(scoreboard.to_dict(), f, indent=2)

        logger.info(f"[SCOREBOARD] JSON saved: {filepath}")
        return str(filepath)

    def save_markdown(
        self,
        scoreboard: DailyScoreboard,
        filename: Optional[str] = None
    ) -> str:
        """Save scoreboard as Markdown report."""
        if filename is None:
            filename = f"scoreboard_{scoreboard.date}.md"

        filepath = self.output_dir / filename

        md_lines = [
            f"# Daily Trading Scoreboard",
            f"",
            f"**Date:** {scoreboard.trading_day}",
            f"**Generated:** {scoreboard.generated_at}",
            f"**Mode:** {scoreboard.mode.upper()}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Baseline | HRM Shadow | Difference |",
            f"|--------|----------|------------|------------|",
            f"| Total PnL | ${scoreboard.total_baseline_pnl:.2f} | ${scoreboard.total_hrm_pnl:.2f} | ${scoreboard.total_pnl_difference:.2f} |",
            f"| Trades | {scoreboard.total_baseline_trades} | {scoreboard.total_hrm_trades} | - |",
            f"| Avg Sharpe | {scoreboard.avg_baseline_sharpe:.2f} | {scoreboard.avg_hrm_sharpe:.2f} | {scoreboard.avg_hrm_sharpe - scoreboard.avg_baseline_sharpe:.2f} |",
            f"| Symbols | {scoreboard.total_symbols} | - | - |",
            f"",
            f"**HRM Outperformance Rate:** {scoreboard.outperformance_rate:.1f}% ({scoreboard.symbols_hrm_outperformed}/{scoreboard.total_symbols} symbols)",
            f"",
            f"**Total Vetoes Issued:** {scoreboard.total_vetoes}",
            f"",
            f"## Notes",
            f"",
        ]

        for note in scoreboard.notes:
            md_lines.append(f"- {note}")

        md_lines.extend([
            f"",
            f"## Detailed Results",
            f"",
            f"| Symbol | Timeframe | Baseline PnL | HRM PnL | Difference | HRM Win? |",
            f"|--------|-----------|--------------|---------|------------|----------|",
        ])

        for entry in scoreboard.entries:
            win_marker = "✓" if entry.hrm_outperformance else "✗"
            md_lines.append(
                f"| {entry.symbol} | {entry.timeframe} | "
                f"${entry.baseline_net_pnl:.2f} | ${entry.hrm_shadow_net_pnl:.2f} | "
                f"${entry.pnl_difference:.2f} | {win_marker} |"
            )

        md_lines.extend([
            f"",
            f"---",
            f"",
            f"*This is an automated report generated by the HRM shadow mode system.*",
        ])

        with open(filepath, 'w') as f:
            f.write('\n'.join(md_lines))

        logger.info(f"[SCOREBOARD] Markdown saved: {filepath}")
        return str(filepath)

    def save_csv(
        self,
        scoreboard: DailyScoreboard,
        filename: Optional[str] = None
    ) -> str:
        """Save scoreboard as CSV."""
        if filename is None:
            filename = f"scoreboard_{scoreboard.date}.csv"

        filepath = self.output_dir / filename

        import csv

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Date', 'Symbol', 'Timeframe', 'Baseline Strategy',
                'Baseline Trades', 'Baseline Net PnL', 'Baseline Sharpe',
                'HRM Shadow Trades', 'HRM Shadow Net PnL', 'HRM Shadow Sharpe',
                'PnL Difference', 'HRM Outperformance', 'Vetoes Issued'
            ])

            # Data rows
            for entry in scoreboard.entries:
                writer.writerow([
                    scoreboard.date,
                    entry.symbol,
                    entry.timeframe,
                    entry.baseline_strategy,
                    entry.baseline_trades,
                    f"{entry.baseline_net_pnl:.2f}",
                    f"{entry.baseline_sharpe:.2f}",
                    entry.hrm_shadow_trades,
                    f"{entry.hrm_shadow_net_pnl:.2f}",
                    f"{entry.hrm_shadow_sharpe:.2f}",
                    f"{entry.pnl_difference:.2f}",
                    entry.hrm_outperformance,
                    entry.vetoes_issued,
                ])

        logger.info(f"[SCOREBOARD] CSV saved: {filepath}")
        return str(filepath)

    def save_all_formats(
        self,
        scoreboard: DailyScoreboard,
        base_filename: Optional[str] = None
    ) -> Dict[str, str]:
        """Save scoreboard in all formats."""
        if base_filename is None:
            base_filename = f"scoreboard_{scoreboard.date}"

        return {
            "json": self.save_json(scoreboard, f"{base_filename}.json"),
            "markdown": self.save_markdown(scoreboard, f"{base_filename}.md"),
            "csv": self.save_csv(scoreboard, f"{base_filename}.csv"),
        }


def generate_daily_scoreboard(
    date: datetime,
    metrics: List[ShadowMetrics],
    mode: str,
    output_dir: str = "/Users/jim/work/curly-succotash/logs/scoreboards",
    baseline_strategies: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Convenience function to generate and save daily scoreboard.

    Args:
        date: Date to generate scoreboard for
        metrics: List of ShadowMetrics
        mode: Shadow mode
        output_dir: Output directory
        baseline_strategies: Map of symbol/timeframe to strategy name

    Returns:
        Dictionary of saved file paths by format
    """
    generator = ScoreboardGenerator(output_dir=output_dir)
    scoreboard = generator.generate(date, metrics, mode, baseline_strategies)
    return generator.save_all_formats(scoreboard)
