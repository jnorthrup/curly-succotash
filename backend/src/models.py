"""
Coinbase Trading Simulator - Core Data Models
All data structures for candles, signals, positions, and metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import json


class SignalType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


class Timeframe(str, Enum):
    ONE_MINUTE = "ONE_MINUTE"
    FIVE_MINUTE = "FIVE_MINUTE"
    FIFTEEN_MINUTE = "FIFTEEN_MINUTE"
    THIRTY_MINUTE = "THIRTY_MINUTE"
    ONE_HOUR = "ONE_HOUR"
    TWO_HOUR = "TWO_HOUR"
    SIX_HOUR = "SIX_HOUR"
    ONE_DAY = "ONE_DAY"

    @classmethod
    def to_seconds(cls, tf: "Timeframe") -> int:
        mapping = {
            cls.ONE_MINUTE: 60,
            cls.FIVE_MINUTE: 300,
            cls.FIFTEEN_MINUTE: 900,
            cls.THIRTY_MINUTE: 1800,
            cls.ONE_HOUR: 3600,
            cls.TWO_HOUR: 7200,
            cls.SIX_HOUR: 21600,
            cls.ONE_DAY: 86400,
        }
        return mapping[tf]


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: Timeframe

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
        }

    @classmethod
    def from_coinbase(cls, data: Dict, symbol: str, timeframe: Timeframe) -> "Candle":
        return cls(
            timestamp=datetime.utcfromtimestamp(int(data["start"])),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
            symbol=symbol,
            timeframe=timeframe,
        )


@dataclass
class Signal:
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    strategy_name: str
    signal_type: SignalType
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    confidence: float
    paper_size: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
            "paper_size": self.paper_size,
            "reason": self.reason,
        }


@dataclass
class Position:
    symbol: str
    strategy_name: str
    side: SignalType
    entry_price: float
    entry_time: datetime
    size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    def update_pnl(self, current_price: float):
        self.current_price = current_price
        if self.side == SignalType.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        elif self.side == SignalType.SHORT:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "size": self.size,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
        }


@dataclass
class Trade:
    timestamp: datetime
    symbol: str
    strategy_name: str
    side: SignalType
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_percent: float
    holding_period_seconds: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "holding_period_seconds": self.holding_period_seconds,
            "reason": self.reason,
        }


@dataclass
class PerformanceMetrics:
    strategy_name: str
    symbol: str
    timeframe: Timeframe
    net_pnl: float
    total_return_pct: float
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    avg_trade_pnl: float
    num_trades: int
    profit_factor: float
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "net_pnl": self.net_pnl,
            "total_return_pct": self.total_return_pct,
            "cagr": self.cagr,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "avg_trade_pnl": self.avg_trade_pnl,
            "num_trades": self.num_trades,
            "profit_factor": self.profit_factor,
            "equity_curve": self.equity_curve,
        }


@dataclass
class StrategyState:
    name: str
    description: str
    current_position: Optional[Position]
    signals: List[Signal] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    equity: float = 10000.0
    initial_capital: float = 10000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "current_position": self.current_position.to_dict() if self.current_position else None,
            "recent_signals": [s.to_dict() for s in self.signals[-10:]],
            "num_trades": len(self.trades),
            "equity": self.equity,
            "total_pnl": self.equity - self.initial_capital,
            "return_pct": ((self.equity - self.initial_capital) / self.initial_capital) * 100,
        }


@dataclass
class BullpenEntry:
    strategy_name: str
    description: str
    symbol: str
    timeframe: Timeframe
    position_state: str
    latest_signal: Optional[Signal]
    hypothetical_pnl: float
    return_pct: float
    sharpe_ratio: float
    win_rate: float
    num_trades: int
    confidence: float
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "description": self.description,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "position_state": self.position_state,
            "latest_signal": self.latest_signal.to_dict() if self.latest_signal else None,
            "hypothetical_pnl": self.hypothetical_pnl,
            "return_pct": self.return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "num_trades": self.num_trades,
            "confidence": self.confidence,
            "rank": self.rank,
        }


@dataclass
class ConsensusSignal:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    long_count: int
    short_count: int
    flat_count: int
    consensus: SignalType
    consensus_strength: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "long_count": self.long_count,
            "short_count": self.short_count,
            "flat_count": self.flat_count,
            "consensus": self.consensus.value,
            "consensus_strength": self.consensus_strength,
        }


@dataclass
class SimulatorConfig:
    symbols: List[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD", "SOL-USD"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    commission_pct: float = 0.1
    poll_interval_seconds: int = 60
    backtest_start_days_ago: int = 90

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "timeframes": [tf.value for tf in self.timeframes],
            "initial_capital": self.initial_capital,
            "position_size_pct": self.position_size_pct,
            "commission_pct": self.commission_pct,
            "poll_interval_seconds": self.poll_interval_seconds,
            "backtest_start_days_ago": self.backtest_start_days_ago,
        }