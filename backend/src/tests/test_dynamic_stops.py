import pytest
from datetime import datetime, timezone, timedelta
from backend.src.models import Candle, Timeframe, SignalType, Position, Signal
from backend.src.strategies import BaseStrategy, StrategyConfig


class MockStrategy(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config)
        self._min_candles = 0
    @property
    def name(self): return "Mock"
    @property
    def description(self): return "Mock"
    def generate_signal(self, candles): return None


def create_candle(price: float, timestamp: datetime, high: float = None, low: float = None):
    return Candle(
        timestamp=timestamp,
        open=price,
        high=high or price,
        low=low or price,
        close=price,
        volume=1000.0,
        symbol="BTCUSDT",
        timeframe=Timeframe.ONE_HOUR
    )


def test_dynamic_roi():
    config = StrategyConfig(
        minimal_roi={0: 0.05, 60: 0.02} # 5% immediate, 2% after 1 hour
    )
    strat = MockStrategy(config)
    
    start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    entry_price = 100.0
    
    # Enter position
    strat.position = Position(
        symbol="BTCUSDT",
        strategy_name="Mock",
        side=SignalType.LONG,
        entry_price=entry_price,
        entry_time=start_time,
        size=1.0,
        stop_loss=90.0,
        take_profit=110.0
    )
    
    # 1. Price is 103 (3% ROI) at minute 0. Should NOT hit ROI (needs 5%).
    c1 = create_candle(103.0, start_time)
    strat.process_candle(c1)
    assert strat.position is not None
    
    # 2. Price is 103 (3% ROI) at minute 61. Should hit ROI (needs 2%).
    c2 = create_candle(103.0, start_time + timedelta(minutes=61))
    strat.process_candle(c2)
    assert strat.position is None
    assert strat.trades[-1]["reason"] == "ROI hit (2.0%)"


def test_trailing_stop():
    config = StrategyConfig(
        trailing_stop=True,
        trailing_stop_positive_offset=0.01, # 1% trail
        minimal_roi={0: 1.0} # 100% ROI, won't trigger
    )
    strat = MockStrategy(config)
    
    start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    entry_price = 100.0
    
    # Enter position with initial SL at 95
    strat.position = Position(
        symbol="BTCUSDT",
        strategy_name="Mock",
        side=SignalType.LONG,
        entry_price=entry_price,
        entry_time=start_time,
        size=1.0,
        stop_loss=95.0,
        take_profit=120.0
    )
    
    # 1. Price moves to 110. SL should trail to 110 * 0.99 = 108.9
    c1 = create_candle(110.0, start_time + timedelta(minutes=10))
    strat.process_candle(c1)
    assert strat.position.stop_loss == pytest.approx(108.9)
    
    # 2. Price drops to 108. SL should be hit.
    c2 = create_candle(108.0, start_time + timedelta(minutes=20), low=108.0)
    strat.process_candle(c2)
    assert strat.position is None
    assert strat.trades[-1]["reason"] == "Stop-loss hit"
