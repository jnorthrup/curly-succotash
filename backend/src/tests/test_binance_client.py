"""
Unit tests for backend/src/binance_client.py
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from backend.src.binance_client import BinanceArchiveClient, BinanceArchiveConfig, CandleSchema
from backend.src.models import Candle, Timeframe


class TestBinanceArchiveConfig:
    """Tests for BinanceArchiveConfig."""

    def test_config_defaults(self):
        """Test that BinanceArchiveConfig() has symbols list with 'BTCUSDT', timeframes list with '1h'."""
        config = BinanceArchiveConfig()
        assert 'BTCUSDT' in config.symbols
        assert '1h' in config.timeframes


class TestCandleSchema:
    """Tests for CandleSchema."""

    def test_candle_schema_create_table_sql(self):
        """Test CandleSchema.get_create_table_sql() contains 'candles' and 'symbol' and 'timestamp'."""
        sql = CandleSchema.get_create_table_sql()
        assert 'candles' in sql
        assert 'symbol' in sql
        assert 'timestamp' in sql

    def test_candle_schema_create_index_sql(self):
        """Test CandleSchema.get_create_index_sql() contains 'idx_symbol_timeframe'."""
        sql = CandleSchema.get_create_index_sql()
        assert 'idx_symbol_timeframe' in sql


class TestBinanceArchiveClient:
    """Tests for BinanceArchiveClient."""

    def test_client_init_with_memory_db(self, tmp_path):
        """Test that BinanceArchiveClient initializes without raising when using in-memory DuckDB."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        client = BinanceArchiveClient(config)
        assert client._conn is not None
        client.close()

    def test_ensure_schema_creates_table(self, tmp_path):
        """Test that after ensure_schema(), querying 'SELECT count(*) FROM candles' returns 0."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        client = BinanceArchiveClient(config)
        client.ensure_schema()
        
        result = client._conn.execute('SELECT count(*) FROM candles').fetchone()
        assert result[0] == 0
        client.close()

    def test_query_candles_empty_db(self, tmp_path):
        """Test that query_candles returns empty list when DB has no data."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        client = BinanceArchiveClient(config)
        client.ensure_schema()
        
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        candles = client.query_candles('BTCUSDT', Timeframe.ONE_HOUR, start, end)
        
        assert candles == []
        client.close()

    def test_query_candles_returns_data(self, tmp_path):
        """Test inserting a row and then querying returns a Candle with matching fields."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        client = BinanceArchiveClient(config)
        client.ensure_schema()
        
        # Insert test data directly
        conn = client._ensure_connection()
        conn.execute(
            'INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            ['BTCUSDT', '1h', datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, 102.0, 98.0, 101.0, 1000.0]
        )
        
        # Query back
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        candles = client.query_candles('BTCUSDT', Timeframe.ONE_HOUR, start, end)
        
        assert len(candles) == 1
        assert candles[0].symbol == 'BTCUSDT'
        assert candles[0].close == 101.0
        client.close()

    def test_map_timeframe_one_hour(self, tmp_path):
        """Test that _map_timeframe(Timeframe.ONE_HOUR) == '1h'."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        client = BinanceArchiveClient(config)
        
        result = client._map_timeframe(Timeframe.ONE_HOUR)
        assert result == '1h'
        client.close()

    def test_context_manager(self, tmp_path):
        """Test that 'with BinanceArchiveClient(...) as client:' works without error and closes connection."""
        config = BinanceArchiveConfig(
            duckdb_path=':memory:',
            cache_dir=str(tmp_path / "cache"),
            tmp_root=str(tmp_path)
        )
        
        with BinanceArchiveClient(config) as client:
            assert client._conn is not None
        
        # After exiting context, connection should be closed
        assert client._conn is None
