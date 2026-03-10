import pytest
import pandas as pd
from backend.src.kotlin_bridge import KotlinBridgeAdapter, wire_strategy
from backend.src import quality_gates


# Disable STRICT_QA for tests
quality_gates.STRICT_QA = False


def test_kotlin_bridge_adapter_instantiates():
    """Test that KotlinBridgeAdapter can be instantiated with a dummy path."""
    # This should not raise even with a non-existent library
    adapter = KotlinBridgeAdapter('dummy.so')
    assert adapter is not None


def test_wire_strategy_returns_dataframe_with_kotlin_columns():
    """Test that wire_strategy wraps a class and populate_indicators adds Kotlin columns."""
    # Create a stub strategy class with populate_indicators that returns empty df
    class StubStrategy:
        def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
            return dataframe
    
    # Apply the wire_strategy decorator
    WrappedStrategy = wire_strategy(StubStrategy)
    
    # Instantiate the wrapped strategy
    instance = WrappedStrategy()
    
    # Create empty dataframe and metadata
    empty_df = pd.DataFrame()
    metadata = {'pair': 'BTC', 'timeframe': '1h'}
    
    # Call populate_indicators
    result = instance.populate_indicators(empty_df, metadata)
    
    # Assert that 'sma' and 'ema' columns are in the result
    assert 'sma' in result.columns
    assert 'ema' in result.columns


def test_wire_strategy_wrapped_class_has_bridge():
    """Test that after wrapping, the instance has a .bridge attribute that is a KotlinBridgeAdapter."""
    class StubStrategy:
        pass
    
    # Apply the wire_strategy decorator
    WrappedStrategy = wire_strategy(StubStrategy)
    
    # Instantiate the wrapped strategy
    instance = WrappedStrategy()
    
    # Assert that the instance has a bridge attribute
    assert hasattr(instance, 'bridge')
    
    # Assert that the bridge is a KotlinBridgeAdapter
    assert isinstance(instance.bridge, KotlinBridgeAdapter)
