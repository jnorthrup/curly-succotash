"""
Binance Archive Client - DuckDB-based historical data access.

Extends the pattern from coinbase_client.py to provide efficient
querying of historical candle data stored in DuckDB.

SAFETY: This client is read-only. It cannot modify the database directly,
but it provides schema management methods for the ArchiveIngester.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Iterator
from pathlib import Path

import duckdb

from .models import Candle, Timeframe

logger = logging.getLogger(__name__)


@dataclass
class BinanceArchiveConfig:
    """Configuration for Binance Archive Client."""
    base_url: str = "https://data.binance.vision/data/spot/monthly/klines"
    cache_dir: str = "/Users/jim/work/moneyfan/data/binance/archive_cache"
    duckdb_path: str = "/Users/jim/work/moneyfan/data/binance/hrm_data.duckdb"
    tmp_root: str = "/tmp"
    tmp_prefix: str = "curly-binance"
    start_month: str = "2026-01"
    symbols: List[str] = None
    timeframes: List[str] = None

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]
        if self.timeframes is None:
            self.timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]


@dataclass
class CandleSchema:
    """DuckDB schema for candle storage."""

    TABLE_NAME = "candles"

    COLUMNS = {
        "symbol": "VARCHAR",
        "timeframe": "VARCHAR",
        "timestamp": "TIMESTAMP",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "DOUBLE",
    }

    PRIMARY_KEY = "(symbol, timeframe, timestamp)"

    @classmethod
    def get_create_table_sql(cls) -> str:
        """Generate CREATE TABLE SQL."""
        columns_sql = ", ".join([f"{name} {dtype}" for name, dtype in cls.COLUMNS.items()])
        return f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                {columns_sql},
                PRIMARY KEY {cls.PRIMARY_KEY}
            )
        """

    @classmethod
    def get_create_index_sql(cls) -> str:
        """Generate CREATE INDEX SQL."""
        return f"""
            CREATE INDEX IF NOT EXISTS idx_symbol_timeframe
            ON {cls.TABLE_NAME}(symbol, timeframe, timestamp)
        """


class BinanceArchiveClient:
    """
    Client for querying Binance historical data from DuckDB.

    This client provides efficient querying of candle data stored in DuckDB,
    following the same interface pattern as CoinbaseMarketDataClient.

    SAFETY: This client is read-only. It queries but does not modify data.
    Schema management methods are provided for use by ArchiveIngester.
    """

    def __init__(self, config: Optional[BinanceArchiveConfig] = None):
        """
        Initialize the Binance Archive Client.

        Args:
            config: Configuration for the archive client. If None, uses defaults.
        """
        self.config = config or BinanceArchiveConfig()
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._connect()
        logger.info(f"[INIT] BinanceArchiveClient initialized with DuckDB: {self.config.duckdb_path}")

    def _connect(self) -> None:
        """Establish connection to DuckDB database."""
        try:
            # Ensure parent directory exists
            db_path = Path(self.config.duckdb_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            self._conn = duckdb.connect(str(db_path))
            logger.debug(f"[DB] Connected to DuckDB: {self.config.duckdb_path}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to DuckDB: {e}")
            raise

    def _ensure_connection(self) -> duckdb.DuckDBPyConnection:
        """Ensure database connection is active."""
        if self._conn is None:
            self._connect()
        return self._conn

    def close(self) -> None:
        """Close the DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("[DB] DuckDB connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def ensure_schema(self) -> None:
        """
        Create tables and indexes if they don't exist.

        This method is intended to be called by ArchiveIngester.
        """
        try:
            conn = self._ensure_connection()

            # Create table
            conn.execute(CandleSchema.get_create_table_sql())
            logger.info(f"[SCHEMA] Ensured table exists: {CandleSchema.TABLE_NAME}")

            # Create index
            conn.execute(CandleSchema.get_create_index_sql())
            logger.info("[SCHEMA] Ensured index exists: idx_symbol_timeframe")

        except Exception as e:
            logger.error(f"[ERROR] Failed to ensure schema: {e}")
            raise

    def _map_timeframe(self, timeframe: Timeframe) -> str:
        """Map Timeframe enum to Binance timeframe string."""
        mapping = {
            Timeframe.ONE_MINUTE: "1m",
            Timeframe.FIVE_MINUTE: "5m",
            Timeframe.FIFTEEN_MINUTE: "15m",
            Timeframe.THIRTY_MINUTE: "30m",
            Timeframe.ONE_HOUR: "1h",
            Timeframe.TWO_HOUR: "2h",
            Timeframe.SIX_HOUR: "6h",
            Timeframe.ONE_DAY: "1d",
        }
        return mapping.get(timeframe, "1h")

    def query_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Candle]:
        """
        Query candles for a specific symbol and timeframe.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe enum
            start_time: Start of query range (inclusive)
            end_time: End of query range (inclusive)

        Returns:
            List of Candle objects sorted by timestamp (oldest first)
        """
        try:
            conn = self._ensure_connection()
            tf_str = self._map_timeframe(timeframe)

            query = """
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp ASC
            """

            result = conn.execute(query, [symbol, tf_str, start_time, end_time]).fetchall()

            candles = []
            for row in result:
                candle = Candle(
                    symbol=row[0],
                    timeframe=timeframe,  # Use the enum passed in
                    timestamp=row[2].replace(tzinfo=timezone.utc) if row[2].tzinfo is None else row[2],
                    open=float(row[3]),
                    high=float(row[4]),
                    low=float(row[5]),
                    close=float(row[6]),
                    volume=float(row[7]),
                )
                candles.append(candle)

            logger.info(f"[DATA] Retrieved {len(candles)} candles for {symbol} ({tf_str})")
            return candles

        except Exception as e:
            logger.error(f"[ERROR] Failed to query candles for {symbol}: {e}")
            return []

    def get_candles_stream(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> Iterator[Candle]:
        """
        Stream candles one at a time for memory efficiency.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe enum
            start_time: Start of query range (inclusive)
            end_time: End of query range (inclusive)

        Yields:
            Candle objects in chronological order
        """
        try:
            conn = self._ensure_connection()
            tf_str = self._map_timeframe(timeframe)

            query = """
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp ASC
            """

            result = conn.execute(query, [symbol, tf_str, start_time, end_time])

            count = 0
            for row in result.fetchall():
                candle = Candle(
                    symbol=row[0],
                    timeframe=timeframe,
                    timestamp=row[2].replace(tzinfo=timezone.utc) if row[2].tzinfo is None else row[2],
                    open=float(row[3]),
                    high=float(row[4]),
                    low=float(row[5]),
                    close=float(row[6]),
                    volume=float(row[7]),
                )
                count += 1
                yield candle

            logger.info(f"[DATA] Streamed {count} candles for {symbol} ({tf_str})")

        except Exception as e:
            logger.error(f"[ERROR] Failed to stream candles for {symbol}: {e}")
            return iter([])

    def get_available_symbols(self) -> List[str]:
        """
        Get list of all symbols that have data in the database.

        Returns:
            List of symbol strings (e.g., ["BTCUSDT", "ETHUSDT"])
        """
        try:
            conn = self._ensure_connection()

            query = "SELECT DISTINCT symbol FROM candles ORDER BY symbol"
            result = conn.execute(query).fetchall()

            symbols = [row[0] for row in result]
            logger.info(f"[DATA] Found {len(symbols)} symbols in database")
            return symbols

        except Exception as e:
            logger.error(f"[ERROR] Failed to get available symbols: {e}")
            return []

    def get_available_timeframes(self, symbol: str) -> List[str]:
        """
        Get list of all timeframes available for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            List of timeframe strings (e.g., ["1m", "5m", "1h"])
        """
        try:
            conn = self._ensure_connection()

            query = "SELECT DISTINCT timeframe FROM candles WHERE symbol = ? ORDER BY timeframe"
            result = conn.execute(query, [symbol]).fetchall()

            timeframes = [row[0] for row in result]
            logger.info(f"[DATA] Found {len(timeframes)} timeframes for {symbol}")
            return timeframes

        except Exception as e:
            logger.error(f"[ERROR] Failed to get available timeframes for {symbol}: {e}")
            return []

    def get_date_range(self, symbol: str, timeframe: Timeframe) -> Tuple[datetime, datetime]:
        """
        Get the date range of available data for a symbol and timeframe.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe enum

        Returns:
            Tuple of (min_timestamp, max_timestamp)
        """
        try:
            conn = self._ensure_connection()
            tf_str = self._map_timeframe(timeframe)

            query = """
                SELECT MIN(timestamp), MAX(timestamp)
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
            """
            result = conn.execute(query, [symbol, tf_str]).fetchone()

            if result and result[0] and result[1]:
                min_ts = result[0].replace(tzinfo=timezone.utc) if result[0].tzinfo is None else result[0]
                max_ts = result[1].replace(tzinfo=timezone.utc) if result[1].tzinfo is None else result[1]
                logger.info(f"[DATA] Date range for {symbol} ({tf_str}): {min_ts} to {max_ts}")
                return (min_ts, max_ts)
            else:
                logger.warning(f"[DATA] No data found for {symbol} ({tf_str})")
                return (datetime.min.replace(tzinfo=timezone.utc), datetime.min.replace(tzinfo=timezone.utc))

        except Exception as e:
            logger.error(f"[ERROR] Failed to get date range for {symbol}: {e}")
            return (datetime.min.replace(tzinfo=timezone.utc), datetime.min.replace(tzinfo=timezone.utc))

    def get_candle_count(self, symbol: str, timeframe: Timeframe) -> int:
        """
        Get the total number of candles for a symbol and timeframe.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe enum

        Returns:
            Number of candles
        """
        try:
            conn = self._ensure_connection()
            tf_str = self._map_timeframe(timeframe)

            query = """
                SELECT COUNT(*)
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
            """
            result = conn.execute(query, [symbol, tf_str]).fetchone()

            count = result[0] if result else 0
            logger.info(f"[DATA] Candle count for {symbol} ({tf_str}): {count}")
            return count

        except Exception as e:
            logger.error(f"[ERROR] Failed to get candle count for {symbol}: {e}")
            return 0

    def has_data(self, symbol: str, timeframe: Timeframe, year: int, month: int) -> bool:
        """
        Check if data exists for a specific symbol, timeframe, and month.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe enum
            year: Year (e.g., 2023)
            month: Month (1-12)

        Returns:
            True if data exists for that month
        """
        try:
            conn = self._ensure_connection()
            tf_str = self._map_timeframe(timeframe)

            start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                end_dt = datetime(year, month + 1, 1, tzinfo=timezone.utc)

            query = """
                SELECT COUNT(*)
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
                  AND timestamp >= ?
                  AND timestamp < ?
            """
            result = conn.execute(query, [symbol, tf_str, start_dt, end_dt]).fetchone()

            return result[0] > 0 if result else False

        except Exception as e:
            logger.error(f"[ERROR] Failed to check data existence for {symbol}: {e}")
            return False