"""
Bullpen Aggregation and Ranking System
Real-time aggregated view of all strategies with rankings and consensus signals.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import defaultdict
from enum import Enum

from .models import (
    Signal, SignalType, Timeframe, BullpenEntry, 
    ConsensusSignal, PerformanceMetrics
)
from .paper_trading import PaperTradingEngine
from .backtesting import MetricsCalculator

logger = logging.getLogger(__name__)


class RankingMetric(str, Enum):
    TOTAL_RETURN = "total_return"
    SHARPE_RATIO = "sharpe_ratio"
    WIN_RATE = "win_rate"
    CONFIDENCE = "confidence"
    RECENT_PERFORMANCE = "recent_performance"
    PROFIT_FACTOR = "profit_factor"


@dataclass
class BullpenFilter:
    symbols: Optional[List[str]] = None
    timeframes: Optional[List[Timeframe]] = None
    min_trades: int = 0
    min_confidence: float = 0.0


class BullpenAggregator:
    """
    Real-time bullpen that aggregates, compares, and ranks all strategies.
    Provides consensus signals and filtering capabilities.
    """
    
    def __init__(self, paper_engine: PaperTradingEngine):
        self.paper_engine = paper_engine
        self._cached_rankings: Dict[str, List[BullpenEntry]] = {}
        self._last_update: Optional[datetime] = None
    
    def get_bullpen_view(
        self,
        ranking_metric: RankingMetric = RankingMetric.TOTAL_RETURN,
        filter_config: Optional[BullpenFilter] = None
    ) -> Dict[str, Any]:
        """
        Get complete bullpen view with rankings, consensus, and strategy states.
        """
        entries = self._build_entries(filter_config)
        ranked_entries = self._rank_entries(entries, ranking_metric)
        consensus_signals = self._calculate_consensus(entries)
        summary = self._build_summary(entries)
        
        self._last_update = datetime.utcnow()
        
        return {
            "timestamp": self._last_update.isoformat(),
            "ranking_metric": ranking_metric.value,
            "filter": {
                "symbols": filter_config.symbols if filter_config else None,
                "timeframes": [tf.value for tf in filter_config.timeframes] if filter_config and filter_config.timeframes else None,
            },
            "summary": summary,
            "consensus_signals": [cs.to_dict() for cs in consensus_signals],
            "strategies": [e.to_dict() for e in ranked_entries],
            "total_strategies": len(ranked_entries),
        }
    
    def _build_entries(
        self, 
        filter_config: Optional[BullpenFilter] = None
    ) -> List[BullpenEntry]:
        """Build bullpen entries from all strategy states."""
        entries = []
        states = self.paper_engine.get_all_states()
        
        for state in states:
            if filter_config:
                if filter_config.symbols and state["symbol"] not in filter_config.symbols:
                    continue
                if filter_config.timeframes:
                    tf_values = [tf.value for tf in filter_config.timeframes]
                    if state["timeframe"] not in tf_values:
                        continue
                if filter_config.min_trades and state["num_trades"] < filter_config.min_trades:
                    continue
            
            recent_signals = state.get("recent_signals", [])
            latest_signal = None
            if recent_signals:
                latest_signal = Signal(
                    timestamp=datetime.fromisoformat(recent_signals[-1]["timestamp"]),
                    symbol=recent_signals[-1]["symbol"],
                    timeframe=Timeframe(recent_signals[-1]["timeframe"]),
                    strategy_name=recent_signals[-1]["strategy_name"],
                    signal_type=SignalType(recent_signals[-1]["signal_type"]),
                    entry_price=recent_signals[-1]["entry_price"],
                    stop_loss=recent_signals[-1].get("stop_loss"),
                    take_profit=recent_signals[-1].get("take_profit"),
                    confidence=recent_signals[-1]["confidence"],
                    paper_size=recent_signals[-1]["paper_size"],
                    reason=recent_signals[-1]["reason"],
                )
            
            position = state.get("current_position")
            if position:
                position_state = f"{position['side']} @ {position['entry_price']:.2f}"
            else:
                position_state = "FLAT"
            
            avg_confidence = 0.0
            if recent_signals:
                avg_confidence = sum(s["confidence"] for s in recent_signals) / len(recent_signals)
            
            entry = BullpenEntry(
                strategy_name=state["name"],
                description=state["description"],
                symbol=state["symbol"],
                timeframe=Timeframe(state["timeframe"]),
                position_state=position_state,
                latest_signal=latest_signal,
                hypothetical_pnl=state.get("total_pnl", 0),
                return_pct=state.get("return_pct", 0),
                sharpe_ratio=0.0,
                win_rate=0.0,
                num_trades=state.get("num_trades", 0),
                confidence=avg_confidence,
            )
            
            entries.append(entry)
        
        return entries
    
    def _rank_entries(
        self,
        entries: List[BullpenEntry],
        metric: RankingMetric
    ) -> List[BullpenEntry]:
        """Rank entries by specified metric."""
        
        def get_sort_key(entry: BullpenEntry) -> float:
            if metric == RankingMetric.TOTAL_RETURN:
                return entry.return_pct
            elif metric == RankingMetric.SHARPE_RATIO:
                return entry.sharpe_ratio
            elif metric == RankingMetric.WIN_RATE:
                return entry.win_rate
            elif metric == RankingMetric.CONFIDENCE:
                return entry.confidence
            elif metric == RankingMetric.RECENT_PERFORMANCE:
                return entry.hypothetical_pnl
            elif metric == RankingMetric.PROFIT_FACTOR:
                return entry.return_pct
            return 0.0
        
        sorted_entries = sorted(entries, key=get_sort_key, reverse=True)
        
        for i, entry in enumerate(sorted_entries, 1):
            entry.rank = i
        
        return sorted_entries
    
    def _calculate_consensus(
        self,
        entries: List[BullpenEntry]
    ) -> List[ConsensusSignal]:
        """Calculate consensus signals per symbol/timeframe."""
        
        groups: Dict[str, List[BullpenEntry]] = defaultdict(list)
        
        for entry in entries:
            key = f"{entry.symbol}|{entry.timeframe.value}"
            groups[key].append(entry)
        
        consensus_signals = []
        
        for key, group_entries in groups.items():
            symbol, timeframe_str = key.split("|", 1)
            timeframe = Timeframe(timeframe_str)
            
            long_count = 0
            short_count = 0
            flat_count = 0
            
            for entry in group_entries:
                if "LONG" in entry.position_state:
                    long_count += 1
                elif "SHORT" in entry.position_state:
                    short_count += 1
                else:
                    flat_count += 1
            
            total = len(group_entries)
            
            if long_count > short_count and long_count > flat_count:
                consensus = SignalType.LONG
                strength = long_count / total
            elif short_count > long_count and short_count > flat_count:
                consensus = SignalType.SHORT
                strength = short_count / total
            else:
                consensus = SignalType.FLAT
                strength = flat_count / total
            
            consensus_signal = ConsensusSignal(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.utcnow(),
                long_count=long_count,
                short_count=short_count,
                flat_count=flat_count,
                consensus=consensus,
                consensus_strength=strength,
            )
            
            consensus_signals.append(consensus_signal)
        
        return consensus_signals
    
    def _build_summary(self, entries: List[BullpenEntry]) -> Dict[str, Any]:
        """Build summary statistics."""
        if not entries:
            return {
                "total_strategies": 0,
                "active_positions": 0,
                "avg_return_pct": 0,
                "best_performer": None,
                "worst_performer": None,
            }
        
        active_positions = sum(1 for e in entries if e.position_state != "FLAT")
        avg_return = sum(e.return_pct for e in entries) / len(entries)
        
        sorted_by_return = sorted(entries, key=lambda e: e.return_pct, reverse=True)
        best = sorted_by_return[0]
        worst = sorted_by_return[-1]
        
        return {
            "total_strategies": len(entries),
            "active_positions": active_positions,
            "avg_return_pct": avg_return,
            "total_long": sum(1 for e in entries if "LONG" in e.position_state),
            "total_short": sum(1 for e in entries if "SHORT" in e.position_state),
            "total_flat": sum(1 for e in entries if e.position_state == "FLAT"),
            "best_performer": {
                "name": best.strategy_name,
                "symbol": best.symbol,
                "return_pct": best.return_pct,
            },
            "worst_performer": {
                "name": worst.strategy_name,
                "symbol": worst.symbol,
                "return_pct": worst.return_pct,
            },
        }
    
    def get_strategy_detail(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: Timeframe
    ) -> Optional[Dict[str, Any]]:
        """Get detailed view for a specific strategy."""
        state = self.paper_engine.get_strategy_state(symbol, timeframe, strategy_name)
        
        if not state:
            return None
        
        return {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe.value,
            "state": state,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_consensus_for_symbol(
        self,
        symbol: str,
        timeframe: Optional[Timeframe] = None
    ) -> List[ConsensusSignal]:
        """Get consensus signals for a specific symbol."""
        filter_config = BullpenFilter(
            symbols=[symbol],
            timeframes=[timeframe] if timeframe else None,
        )
        entries = self._build_entries(filter_config)
        return self._calculate_consensus(entries)
    
    def get_top_strategies(
        self,
        n: int = 5,
        metric: RankingMetric = RankingMetric.TOTAL_RETURN
    ) -> List[Dict[str, Any]]:
        """Get top N strategies by metric."""
        entries = self._build_entries()
        ranked = self._rank_entries(entries, metric)
        
        return [e.to_dict() for e in ranked[:n]]
    
    def export_bullpen_snapshot(self) -> Dict[str, Any]:
        """Export full bullpen snapshot for persistence or API."""
        view = self.get_bullpen_view()
        
        return {
            "snapshot_timestamp": datetime.utcnow().isoformat(),
            "bullpen": view,
            "all_positions": self.paper_engine.get_positions(),
            "recent_signals": self.paper_engine.get_recent_signals(100),
        }