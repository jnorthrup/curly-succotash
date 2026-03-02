"""
Paper Trading Engine
Processes strategy signals without placing real orders.
Tracks hypothetical positions and P&L for each strategy.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Callable
from collections import defaultdict
import asyncio

from .models import (
    Candle, Signal, SignalType, Position, Trade, 
    PerformanceMetrics, Timeframe, StrategyState
)
from .strategies import BaseStrategy, create_all_strategies, StrategyConfig

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingConfig:
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    commission_pct: float = 0.1
    max_positions_per_strategy: int = 1


@dataclass
class StrategyTracker:
    """Tracks state for a single strategy instance."""
    strategy: BaseStrategy
    symbol: str
    timeframe: Timeframe
    equity_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def record_equity(self, timestamp: datetime):
        self.equity_history.append({
            "timestamp": timestamp.isoformat(),
            "equity": self.strategy.equity,
        })


class PaperTradingEngine:
    """
    Paper trading engine that runs all strategies against incoming candles.
    
    SAFETY: This engine ONLY tracks hypothetical positions.
            No real orders are ever placed.
    """
    
    def __init__(self, config: PaperTradingConfig = None):
        self.config = config or PaperTradingConfig()
        self.trackers: Dict[str, Dict[str, Dict[str, StrategyTracker]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self.all_signals: List[Signal] = []
        self.signal_callbacks: List[Callable[[Signal], None]] = []
        self._lock = asyncio.Lock()
        
        logger.info("[PAPER] Paper Trading Engine initialized - NO REAL TRADES")
    
    def initialize_strategies(
        self, 
        symbols: List[str], 
        timeframes: List[Timeframe]
    ) -> int:
        """Initialize strategy instances for each symbol/timeframe combination."""
        count = 0
        
        strategy_config = StrategyConfig(
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
        )
        
        for symbol in symbols:
            for timeframe in timeframes:
                strategies = create_all_strategies(strategy_config)
                
                for strategy in strategies:
                    tracker = StrategyTracker(
                        strategy=strategy,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    self.trackers[symbol][timeframe.value][strategy.name] = tracker
                    count += 1
        
        logger.info(f"[PAPER] Initialized {count} strategy instances across {len(symbols)} symbols")
        return count
    
    async def process_candle(self, candle: Candle) -> List[Signal]:
        """
        Process incoming candle through all relevant strategies.
        Returns list of generated signals.
        """
        async with self._lock:
            signals = []
            
            timeframe_trackers = self.trackers.get(candle.symbol, {}).get(candle.timeframe.value, {})
            
            for strategy_name, tracker in timeframe_trackers.items():
                try:
                    signal = tracker.strategy.process_candle(candle)
                    
                    if signal:
                        signals.append(signal)
                        self.all_signals.append(signal)
                        
                        for callback in self.signal_callbacks:
                            try:
                                callback(signal)
                            except Exception as e:
                                logger.error(f"[PAPER] Signal callback error: {e}")
                    
                    tracker.record_equity(candle.timestamp)
                    
                except Exception as e:
                    logger.error(f"[PAPER] Strategy {strategy_name} error: {e}")
            
            return signals
    
    def process_candle_sync(self, candle: Candle) -> List[Signal]:
        """Synchronous version of process_candle for backtesting."""
        signals = []
        
        timeframe_trackers = self.trackers.get(candle.symbol, {}).get(candle.timeframe.value, {})
        
        for strategy_name, tracker in timeframe_trackers.items():
            try:
                signal = tracker.strategy.process_candle(candle)
                
                if signal:
                    signals.append(signal)
                    self.all_signals.append(signal)
                
                tracker.record_equity(candle.timestamp)
                
            except Exception as e:
                logger.error(f"[PAPER] Strategy {strategy_name} error: {e}")
        
        return signals
    
    def register_signal_callback(self, callback: Callable[[Signal], None]):
        """Register callback to be called on each new signal."""
        self.signal_callbacks.append(callback)
    
    def get_strategy_state(
        self, 
        symbol: str, 
        timeframe: Timeframe, 
        strategy_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get current state for a specific strategy."""
        tracker = self.trackers.get(symbol, {}).get(timeframe.value, {}).get(strategy_name)
        
        if not tracker:
            return None
        
        return {
            **tracker.strategy.get_state(),
            "symbol": symbol,
            "timeframe": timeframe.value,
            "equity_history": tracker.equity_history[-100:],
        }
    
    def get_all_states(self) -> List[Dict[str, Any]]:
        """Get states for all strategy instances."""
        states = []
        
        for symbol, timeframe_dict in self.trackers.items():
            for timeframe, strategy_dict in timeframe_dict.items():
                for strategy_name, tracker in strategy_dict.items():
                    states.append({
                        **tracker.strategy.get_state(),
                        "symbol": symbol,
                        "timeframe": timeframe,
                    })
        
        return states
    
    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get most recent signals across all strategies."""
        return [s.to_dict() for s in self.all_signals[-limit:]]
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions across strategies."""
        positions = []
        
        for symbol, timeframe_dict in self.trackers.items():
            for timeframe, strategy_dict in timeframe_dict.items():
                for strategy_name, tracker in strategy_dict.items():
                    if tracker.strategy.position:
                        positions.append({
                            **tracker.strategy.position.to_dict(),
                            "timeframe": timeframe,
                        })
        
        return positions
    
    def reset_all(self):
        """Reset all strategies for new backtest/session."""
        for symbol, timeframe_dict in self.trackers.items():
            for timeframe, strategy_dict in timeframe_dict.items():
                for strategy_name, tracker in strategy_dict.items():
                    tracker.strategy.reset()
                    tracker.equity_history = []
        
        self.all_signals = []
        logger.info("[PAPER] All strategies reset")


class SignalEmitter:
    """
    Emits signals in real-time as they are generated.
    Supports multiple output formats and destinations.
    """
    
    def __init__(self):
        self.subscribers: List[Callable[[Dict], None]] = []
        self.signal_buffer: List[Signal] = []
        self.max_buffer_size = 1000
    
    def emit(self, signal: Signal):
        """Emit a signal to all subscribers."""
        signal_dict = signal.to_dict()
        
        self.signal_buffer.append(signal)
        if len(self.signal_buffer) > self.max_buffer_size:
            self.signal_buffer = self.signal_buffer[-500:]
        
        for subscriber in self.subscribers:
            try:
                subscriber(signal_dict)
            except Exception as e:
                logger.error(f"[EMITTER] Subscriber error: {e}")
        
        logger.info(
            f"[SIGNAL] {signal.strategy_name} | {signal.symbol} | "
            f"{signal.signal_type.value} @ {signal.entry_price:.2f} | "
            f"Confidence: {signal.confidence:.2%}"
        )
    
    def subscribe(self, callback: Callable[[Dict], None]):
        """Subscribe to signal emissions."""
        self.subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[Dict], None]):
        """Unsubscribe from signal emissions."""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
    
    def get_buffered_signals(self, limit: int = 100) -> List[Dict]:
        """Get buffered signals."""
        return [s.to_dict() for s in self.signal_buffer[-limit:]]