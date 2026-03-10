import pytest
import os
from backend.src.kotlin_bridge import KotlinBridgeAdapter
from backend.src.quality_gates import forbid_mock_fallbacks


def test_quality_gate_blocks_mock_in_strict_mode(monkeypatch):
    # Set strict mode
    monkeypatch.setenv("STRICT_QA", "true")
    # We need to reload the module or just re-import to pick up env change if it was at module level
    # But my implementation checks it inside the wrapper
    
    from backend.src import quality_gates
    monkeypatch.setattr(quality_gates, "STRICT_QA", True)
    
    adapter = KotlinBridgeAdapter("lib")
    
    with pytest.raises(RuntimeError, match="Quality Gate Violation"):
        adapter.get_indicators("BTC", "1h")


def test_quality_gate_allows_mock_in_normal_mode(monkeypatch):
    # Set normal mode
    monkeypatch.setenv("STRICT_QA", "false")
    from backend.src import quality_gates
    monkeypatch.setattr(quality_gates, "STRICT_QA", False)
    
    adapter = KotlinBridgeAdapter("lib")
    df = adapter.get_indicators("BTC", "1h")
    assert df is not None
    assert "sma" in df.columns
