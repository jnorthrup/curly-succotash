import pytest
from datetime import datetime, timezone
from backend.src.models import Candle, Timeframe
from backend.src.trade_head_labeler import TradeHeadLabeler


def create_candle(price: float, high: float = None, low: float = None):
    return Candle(
        timestamp=datetime.now(timezone.utc),
        open=price,
        high=high or price,
        low=low or price,
        close=price,
        volume=1000.0,
        symbol="BTCUSDT",
        timeframe=Timeframe.ONE_HOUR
    )


def test_labeler_long_win():
    labeler = TradeHeadLabeler()
    current = create_candle(100.0)
    # Long TP at 102, SL at 99
    future = [
        create_candle(101.0, high=101.5),
        create_candle(102.5, high=103.0) # Hits TP
    ]
    
    label = labeler.generate_label(current, future, tp_pct=0.02, sl_pct=0.01)
    assert label == 1


def test_labeler_long_loss():
    labeler = TradeHeadLabeler()
    current = create_candle(100.0)
    # Long TP at 102, SL at 99
    future = [
        create_candle(99.5, low=98.5), # Hits SL
        create_candle(103.0) # TP would have been hit later
    ]
    
    label = labeler.generate_label(current, future, tp_pct=0.02, sl_pct=0.01)
    assert label == 0


def test_labeler_short_win():
    labeler = TradeHeadLabeler()
    current = create_candle(100.0)
    # Short TP at 98, SL at 101
    future = [
        create_candle(99.0, low=98.5),
        create_candle(97.5, low=97.0) # Hits TP
    ]
    
    label = labeler.generate_label(current, future, tp_pct=0.02, sl_pct=0.01)
    assert label == -1


def test_labeler_volatile_neutral():
    labeler = TradeHeadLabeler()
    current = create_candle(100.0)
    # Both hit same candle (or sequence)
    future = [
        create_candle(100.0, high=105.0, low=95.0) # Hits everything
    ]
    
    label = labeler.generate_label(current, future, tp_pct=0.02, sl_pct=0.01)
    assert label == 0


def test_batch_labels():
    labeler = TradeHeadLabeler()
    candles = [create_candle(100 + i) for i in range(10)]
    # Trending up: should mostly be long
    labels = labeler.generate_batch_labels(candles, lookahead_window=2, tp_pct=0.01, sl_pct=0.05)
    
    assert len(labels) == 10
    assert labels[0] == 1
    assert labels[-1] == 0 # End of sequence
