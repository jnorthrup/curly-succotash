import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from ..replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from ..models import Candle, Timeframe

@pytest.fixture
def mock_client():
    client = MagicMock()
    return client

def create_candle(symbol, timestamp, close=100.0, timeframe=Timeframe.ONE_HOUR):
    return Candle(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10.0,
        symbol=symbol,
        timeframe=timeframe
    )

def test_staggered_symbol_alignment(mock_client):
    """Verify that staggered symbol data is correctly aligned to a common start."""
    # Symbol A starts at T
    # Symbol B starts at T + 1h
    T = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    candles_a = [create_candle("A", T), create_candle("A", T + timedelta(hours=1))]
    candles_b = [create_candle("B", T + timedelta(hours=1))]
    
    # Mock client behavior
    mock_client.get_date_range.side_effect = lambda s, tf: (T, T + timedelta(hours=1)) if s == "A" else (T + timedelta(hours=1), T + timedelta(hours=1))
    
    def query_side_effect(s, tf, start, end):
        if s == "A": return candles_a
        if s == "B": return candles_b
        return []
    mock_client.query_candles.side_effect = query_side_effect
    
    # Case 1: align_symbols=True, infinite_cursor=True
    config = ReplayConfig(
        symbols=["A", "B"],
        timeframes=[Timeframe.ONE_HOUR],
        align_symbols=True,
        infinite_cursor=True
    )
    
    engine = ReplayEngine(mock_client, config)
    engine._load_candles()
    
    # Expected candles:
    # T: A (real), B (padded - 0.0)
    # T+1h: A (real), B (real)
    
    assert len(engine._candles) == 4
    
    # Check T
    t_candles = [c for c in engine._candles if c.timestamp == T]
    assert len(t_candles) == 2
    a_t = next(c for c in t_candles if c.symbol == "A")
    b_t = next(c for c in t_candles if c.symbol == "B")
    assert a_t.open == 100.0
    assert b_t.open == 0.0 # Padded with 0s at start
    
    # Check T+1h
    t1_candles = [c for c in engine._candles if c.timestamp == T + timedelta(hours=1)]
    assert len(t1_candles) == 2
    a_t1 = next(c for c in t1_candles if c.symbol == "A")
    b_t1 = next(c for c in t1_candles if c.symbol == "B")
    assert a_t1.open == 100.0
    assert b_t1.open == 100.0

def test_gap_filling(mock_client):
    """Verify that gaps in a single symbol are filled with carried-forward values when infinite mode is on."""
    # Symbol A has a gap
    T = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    # Gap at T+1h
    candles_a = [create_candle("A", T, close=100.0), create_candle("A", T + timedelta(hours=2), close=110.0)]
    
    mock_client.get_date_range.return_value = (T, T + timedelta(hours=2))
    mock_client.query_candles.return_value = candles_a
    
    config = ReplayConfig(
        symbols=["A"],
        timeframes=[Timeframe.ONE_HOUR],
        infinite_cursor=True
    )
    
    engine = ReplayEngine(mock_client, config)
    engine._load_candles()
    
    # Expected candles:
    # T: A (real)
    # T+1h: A (padded - carry forward 100.0)
    # T+2h: A (real)
    
    assert len(engine._candles) == 3
    assert engine._candles[0].timestamp == T
    assert engine._candles[0].close == 100.0
    
    assert engine._candles[1].timestamp == T + timedelta(hours=1)
    assert engine._candles[1].close == 100.0 # Carried forward
    assert engine._candles[1].volume == 0.0
    
    assert engine._candles[2].timestamp == T + timedelta(hours=2)
    assert engine._candles[2].close == 110.0

def test_infinite_end_padding(mock_client):
    """Verify that all symbols are padded until the latest global end time in infinite mode."""
    # Symbol A ends at T, Symbol B ends at T + 1h
    T = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    candles_a = [create_candle("A", T, close=100.0)]
    candles_b = [create_candle("B", T, close=200.0), create_candle("B", T + timedelta(hours=1), close=210.0)]
    
    mock_client.get_date_range.side_effect = lambda s, tf: (T, T + timedelta(hours=1))
    
    def query_side_effect(s, tf, start, end):
        if s == "A": return candles_a
        if s == "B": return candles_b
        return []
    mock_client.query_candles.side_effect = query_side_effect
    
    config = ReplayConfig(
        symbols=["A", "B"],
        timeframes=[Timeframe.ONE_HOUR],
        infinite_cursor=True
    )
    
    engine = ReplayEngine(mock_client, config)
    engine._load_candles()
    
    # Expected:
    # T: A (real 100), B (real 200)
    # T+1h: A (padded 100), B (real 210)
    
    assert len(engine._candles) == 4
    t1_candles = [c for c in engine._candles if c.timestamp == T + timedelta(hours=1)]
    assert len(t1_candles) == 2
    a_t1 = next(c for c in t1_candles if c.symbol == "A")
    assert a_t1.close == 100.0
    assert a_t1.volume == 0.0
    assert a_t1.symbol == "A"
    
    b_t1 = next(c for c in t1_candles if c.symbol == "B")
    assert b_t1.close == 210.0
    assert b_t1.symbol == "B"

def test_deterministic_ordering_with_padding(mock_client):
    """Verify that padding doesn't break deterministic ordering when seed is used."""
    T = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    # Two symbols with same timestamps
    candles_a = [create_candle("A", T), create_candle("A", T + timedelta(hours=1))]
    candles_b = [create_candle("B", T), create_candle("B", T + timedelta(hours=1))]
    
    mock_client.get_date_range.return_value = (T, T + timedelta(hours=1))
    
    def query_side_effect(s, tf, start, end):
        if s == "A": return candles_a
        if s == "B": return candles_b
        return []
    mock_client.query_candles.side_effect = query_side_effect
    
    # Run twice with same seed
    config1 = ReplayConfig(
        symbols=["A", "B"],
        timeframes=[Timeframe.ONE_HOUR],
        seed=42,
        infinite_cursor=True
    )
    engine1 = ReplayEngine(mock_client, config1)
    engine1._load_candles()
    
    config2 = ReplayConfig(
        symbols=["A", "B"],
        timeframes=[Timeframe.ONE_HOUR],
        seed=42,
        infinite_cursor=True
    )
    engine2 = ReplayEngine(mock_client, config2)
    engine2._load_candles()
    
    assert len(engine1._candles) == len(engine2._candles)
    for c1, c2 in zip(engine1._candles, engine2._candles):
        assert c1.symbol == c2.symbol
        assert c1.timestamp == c2.timestamp

def test_no_padding_when_disabled(mock_client):
    """Verify that no padding occurs when infinite_cursor and align_symbols are disabled."""
    T = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    candles_a = [create_candle("A", T), create_candle("A", T + timedelta(hours=2))]
    
    mock_client.get_date_range.return_value = (T, T + timedelta(hours=2))
    mock_client.query_candles.return_value = candles_a
    
    config = ReplayConfig(
        symbols=["A"],
        timeframes=[Timeframe.ONE_HOUR],
        infinite_cursor=False,
        align_symbols=False
    )
    
    engine = ReplayEngine(mock_client, config)
    engine._load_candles()
    
    # Should only have 2 candles (T and T+2h), no gap filling
    assert len(engine._candles) == 2
    assert engine._candles[0].timestamp == T
    assert engine._candles[1].timestamp == T + timedelta(hours=2)
