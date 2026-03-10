import pytest
import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from backend.src.evaluation import EvaluationHarness, export_for_hrm
from backend.src.models import Timeframe, Candle


def test_export_fidelity_artifact(tmp_path):
    # Mock eval results
    eval_results = {
        "symbol": "BTCUSDT",
        "timeframe": "ONE_HOUR",
        "period_start": "2023-01-01T00:00:00Z",
        "period_end": "2023-01-02T00:00:00Z",
        "strategies": {
            "test_strat": {
                "num_trades": 5,
                "total_pnl": 100.0
            }
        }
    }
    
    harness = EvaluationHarness(None, []) # client and strats not needed for export only
    output_path = str(tmp_path / "fidelity_artifact.json")
    
    harness.export_fidelity_artifact(eval_results, "v2.0.0", output_path)
    
    assert os.path.exists(output_path)
    with open(output_path, 'r') as f:
        data = json.load(f)
        
    assert data["schema"] == "moneyfan.freqtrade.fidelity_pipeline_run.v1"
    assert data["model_version"] == "v2.0.0"
    assert data["reconcile_summary"]["dispatch_total"] == 5
    assert data["reconcile_summary"]["fidelity_metrics"]["total_pnl"] == 100.0


def test_export_for_hrm_with_candles(tmp_path):
    """Test export_for_hrm returns correct count and writes JSON with proper keys."""
    # Create a mock client
    mock_client = MagicMock()
    
    # Create 3 Candle objects with valid fields
    base_time = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = [
        Candle(
            timestamp=base_time + timedelta(hours=i),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=10.0 + i,
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR
        )
        for i in range(3)
    ]
    
    # Configure mock to return the candles
    mock_client.query_candles.return_value = candles
    
    # Set up parameters
    symbol = "BTCUSDT"
    timeframe = Timeframe.ONE_HOUR
    start_time = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2023, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    output_path = str(tmp_path / "export_for_hrm.json")
    
    # Call export_for_hrm
    result = export_for_hrm(mock_client, symbol, timeframe, start_time, end_time, output_path)
    
    # Assert return value is 3
    assert result == 3
    
    # Assert output file contains 3 JSON entries with correct keys
    assert os.path.exists(output_path)
    with open(output_path, 'r') as f:
        data = json.load(f)
    
    assert len(data) == 3
    
    # Check that each entry has the required keys
    for entry in data:
        assert 't' in entry
        assert 'o' in entry
        assert 'h' in entry
        assert 'l' in entry
        assert 'c' in entry
        assert 'v' in entry


def test_export_for_hrm_empty_returns_zero(tmp_path):
    """Test export_for_hrm returns 0 when candles are empty and doesn't write file."""
    # Create a mock client
    mock_client = MagicMock()
    
    # Configure mock to return empty list
    mock_client.query_candles.return_value = []
    
    # Set up parameters
    symbol = "BTCUSDT"
    timeframe = Timeframe.ONE_HOUR
    start_time = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2023, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    output_path = str(tmp_path / "export_for_hrm_empty.json")
    
    # Call export_for_hrm
    result = export_for_hrm(mock_client, symbol, timeframe, start_time, end_time, output_path)
    
    # Assert return value is 0
    assert result == 0
    
    # Assert output file does not exist
    assert not os.path.exists(output_path)
