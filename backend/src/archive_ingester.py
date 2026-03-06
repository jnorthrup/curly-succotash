"""
Archive Ingester - Download and ingest Binance Vision data.

Downloads monthly CSV.gz files from Binance Vision and ingests
them into DuckDB for efficient querying.

Supports incremental updates - only downloads missing months.
"""

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests

from .binance_client import BinanceArchiveClient, BinanceArchiveConfig
from .models import Candle, Timeframe

logger = logging.getLogger(__name__)


class ArchiveIngester:
    """
    Handles downloading and ingesting Binance Vision archives.

    Supports incremental updates - only downloads missing months.
    Uses streaming for large files to minimize memory usage.

    Binance CSV format:
    open_time, open, high, low, close, volume, close_time, quote_volume,
    count, taker_buy_volume, taker_buy_quote_volume, ignore
    """

    def __init__(self, client: BinanceArchiveClient):
        """
        Initialize the Archive Ingester.

        Args:
            client: BinanceArchiveClient instance for database operations
        """
        self.client = client
        self.config = client.config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/zip, application/octet-stream",
            "User-Agent": "BinanceArchiveIngester/1.0",
        })

        # Ensure cache directory exists
        Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)

        # Ensure temp directory exists
        Path(self.config.tmp_root).mkdir(parents=True, exist_ok=True)

        # Ensure schema exists
        self.client.ensure_schema()

        logger.info(f"[INIT] ArchiveIngester initialized with cache: {self.config.cache_dir}")

    def _build_url(self, symbol: str, timeframe: str, year: int, month: int) -> str:
        """
        Build the download URL for a monthly archive file.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe string (e.g., "1h")
            year: Year (e.g., 2023)
            month: Month (1-12)

        Returns:
            Full URL to the .zip file
        """
        month_str = f"{year}-{month:02d}"
        filename = f"{symbol}-{timeframe}-{year}-{month:02d}.zip"
        url = f"{self.config.base_url}/{symbol}/{timeframe}/{filename}"
        return url

    def _download_monthly_file(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int
    ) -> Optional[bytes]:
        """
        Download a single month's archive file.

        Uses streaming to handle large files efficiently.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe string (e.g., "1h")
            year: Year (e.g., 2023)
            month: Month (1-12)

        Returns:
            Decompressed CSV data as bytes, or None if download failed
        """
        url = self._build_url(symbol, timeframe, year, month)
        month_str = f"{year}-{month:02d}"

        logger.info(f"[DOWNLOAD] Starting download for {symbol} {timeframe} {month_str}")

        try:
            response = self.session.get(url, timeout=120, stream=True)
            response.raise_for_status()

            # Stream download to handle large files
            chunks = []
            total_size = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    chunks.append(chunk)
                    total_size += len(chunk)
                    if total_size % (10 * 1024 * 1024) == 0:  # Log every 10MB
                        logger.debug(f"[DOWNLOAD] Downloaded {total_size / 1024 / 1024:.1f}MB...")

            compressed_data = b"".join(chunks)
            logger.info(f"[DOWNLOAD] Downloaded {total_size / 1024 / 1024:.1f}MB for {symbol} {timeframe} {month_str}")

            # Extract CSV from ZIP
            try:
                with zipfile.ZipFile(io.BytesIO(compressed_data)) as z:
                    # Expecting only one CSV file in the ZIP
                    csv_filename = z.namelist()[0]
                    with z.open(csv_filename) as f:
                        decompressed = f.read()
                        logger.info(f"[DOWNLOAD] Extracted {csv_filename}, size {len(decompressed) / 1024 / 1024:.1f}MB")
                        return decompressed
            except zipfile.BadZipFile:
                logger.error(f"[ERROR] Invalid ZIP file for {symbol} {timeframe} {month_str}")
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"[DOWNLOAD] File not found (404): {url}")
            else:
                logger.error(f"[ERROR] HTTP error downloading {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Failed to download {url}: {e}")
            return None

    def _parse_csv_to_candles(
        self,
        csv_data: bytes,
        symbol: str,
        timeframe_str: str
    ) -> List[Candle]:
        """
        Parse CSV data into Candle objects.

        Binance CSV columns:
        0: open_time (milliseconds)
        1: open
        2: high
        3: low
        4: close
        5: volume
        6: close_time
        7: quote_volume
        8: count
        9: taker_buy_volume
        10: taker_buy_quote_volume
        11: ignore

        Args:
            csv_data: Raw CSV data as bytes
            symbol: Trading pair symbol
            timeframe_str: Timeframe string for mapping

        Returns:
            List of Candle objects
        """
        candles = []
        timeframe = self._map_timeframe_string(timeframe_str)

        try:
            # Decode and parse CSV
            csv_text = csv_data.decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_text))

            for row in csv_reader:
                if len(row) < 6:
                    continue  # Skip incomplete rows

                try:
                    # Parse timestamp (Binance uses milliseconds)
                    open_time_ms = int(row[0])
                    timestamp = datetime.fromtimestamp(open_time_ms / 1000, timezone.utc)

                    candle = Candle(
                        timestamp=timestamp,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    candles.append(candle)

                except (ValueError, IndexError) as e:
                    logger.warning(f"[PARSE] Skipping invalid row: {row}, error: {e}")
                    continue

            logger.info(f"[PARSE] Parsed {len(candles)} candles from CSV")
            return candles

        except Exception as e:
            logger.error(f"[ERROR] Failed to parse CSV: {e}")
            return []

    def _map_timeframe_string(self, timeframe_str: str) -> Timeframe:
        """Map Binance timeframe string to Timeframe enum."""
        mapping = {
            "1m": Timeframe.ONE_MINUTE,
            "3m": Timeframe.FIVE_MINUTE,  # Approximation
            "5m": Timeframe.FIVE_MINUTE,
            "15m": Timeframe.FIFTEEN_MINUTE,
            "30m": Timeframe.THIRTY_MINUTE,
            "1h": Timeframe.ONE_HOUR,
            "2h": Timeframe.TWO_HOUR,
            "4h": Timeframe.FOUR_HOUR if hasattr(Timeframe, 'FOUR_HOUR') else Timeframe.SIX_HOUR,
            "6h": Timeframe.SIX_HOUR,
            "8h": Timeframe.SIX_HOUR,  # Approximation
            "12h": Timeframe.SIX_HOUR,  # Approximation
            "1d": Timeframe.ONE_DAY,
            "3d": Timeframe.ONE_DAY,  # Approximation
            "1w": Timeframe.ONE_DAY,  # Approximation
            "1M": Timeframe.ONE_DAY,  # Approximation
        }
        return mapping.get(timeframe_str, Timeframe.ONE_HOUR)

    def _insert_candles(self, candles: List[Candle], timeframe_str: str) -> int:
        """
        Insert candles into DuckDB.

        Uses bulk insert for efficiency.

        Args:
            candles: List of Candle objects to insert
            timeframe_str: Timeframe string for storage

        Returns:
            Number of candles inserted
        """
        if not candles:
            return 0

        try:
            conn = self.client._ensure_connection()

            # Prepare data for bulk insert
            data = []
            for c in candles:
                data.append((
                    c.symbol,
                    timeframe_str,
                    c.timestamp,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                ))

            # Use INSERT OR IGNORE to handle duplicates
            insert_query = """
                INSERT OR IGNORE INTO candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

            conn.executemany(insert_query, data)

            # Get number of rows actually inserted
            result = conn.execute("SELECT changes()").fetchone()
            inserted = result[0] if result else len(candles)

            logger.info(f"[INSERT] Inserted {inserted}/{len(candles)} candles")
            return inserted

        except Exception as e:
            logger.error(f"[ERROR] Failed to insert candles: {e}")
            return 0

    def ingest_symbol_timeframe(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> Tuple[int, int]:
        """
        Ingest data for a specific symbol and timeframe.

        Supports resumable ingestion by checking what already exists.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Timeframe string (e.g., "1h")
            start_date: Start date for ingestion
            end_date: End date for ingestion (defaults to current month)

        Returns:
            Tuple of (total_candles_downloaded, total_candles_inserted)
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        logger.info(f"[INGEST] Starting ingestion for {symbol} {timeframe} from {start_date} to {end_date}")

        total_downloaded = 0
        total_inserted = 0

        current_year = start_date.year
        current_month = start_date.month

        while (current_year, current_month) <= (end_date.year, end_date.month):
            month_str = f"{current_year}-{current_month:02d}"

            # Check if data already exists (resumable ingestion)
            timeframe_enum = self._map_timeframe_string(timeframe)
            if self.client.has_data(symbol, timeframe_enum, current_year, current_month):
                logger.info(f"[INGEST] Data already exists for {symbol} {timeframe} {month_str}, skipping")
            else:
                logger.info(f"[INGEST] Downloading {symbol} {timeframe} {month_str}")

                # Download
                csv_data = self._download_monthly_file(symbol, timeframe, current_year, current_month)

                if csv_data:
                    # Parse
                    candles = self._parse_csv_to_candles(csv_data, symbol, timeframe)
                    total_downloaded += len(candles)

                    if candles:
                        # Insert
                        inserted = self._insert_candles(candles, timeframe)
                        total_inserted += inserted

                        # Cache the file if desired
                        self._cache_file(symbol, timeframe, current_year, current_month, csv_data)
                else:
                    logger.warning(f"[INGEST] No data available for {symbol} {timeframe} {month_str}")

            # Move to next month
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        logger.info(f"[INGEST] Completed ingestion for {symbol} {timeframe}: {total_downloaded} downloaded, {total_inserted} inserted")
        return (total_downloaded, total_inserted)

    def _cache_file(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
        csv_data: bytes
    ) -> None:
        """
        Cache the downloaded file to disk.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string
            year: Year
            month: Month
            csv_data: Raw CSV data
        """
        try:
            cache_path = Path(self.config.cache_dir)
            symbol_dir = cache_path / symbol / timeframe
            symbol_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{symbol}-{timeframe}-{year}-{month:02d}.csv"
            filepath = symbol_dir / filename

            with open(filepath, 'wb') as f:
                f.write(csv_data)

            logger.debug(f"[CACHE] Cached file to {filepath}")

        except Exception as e:
            logger.warning(f"[CACHE] Failed to cache file: {e}")

    def ingest_all_configured(self) -> dict:
        """
        Ingest all symbols and timeframes from configuration.

        Returns:
            Dictionary with ingestion statistics
        """
        logger.info("[INGEST] Starting batch ingestion of all configured symbols/timeframes")

        stats = {
            "symbols_processed": 0,
            "timeframes_processed": 0,
            "total_downloaded": 0,
            "total_inserted": 0,
            "errors": [],
        }

        # Parse start month from config
        start_year, start_month = map(int, self.config.start_month.split("-"))
        start_date = datetime(start_year, start_month, 1, tzinfo=timezone.utc)

        for symbol in self.config.symbols:
            symbol_downloaded = 0
            symbol_inserted = 0

            for timeframe in self.config.timeframes:
                try:
                    downloaded, inserted = self.ingest_symbol_timeframe(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_date=start_date,
                    )
                    symbol_downloaded += downloaded
                    symbol_inserted += inserted
                    stats["timeframes_processed"] += 1

                except Exception as e:
                    error_msg = f"Failed to ingest {symbol} {timeframe}: {e}"
                    logger.error(f"[INGEST] {error_msg}")
                    stats["errors"].append(error_msg)

            stats["symbols_processed"] += 1
            stats["total_downloaded"] += symbol_downloaded
            stats["total_inserted"] += symbol_inserted

            logger.info(f"[INGEST] Symbol {symbol} complete: {symbol_downloaded} downloaded, {symbol_inserted} inserted")

        logger.info(f"[INGEST] Batch ingestion complete: {stats['symbols_processed']} symbols, "
                   f"{stats['total_downloaded']} total candles downloaded, "
                   f"{stats['total_inserted']} total candles inserted")

        return stats

    def get_available_months(self, symbol: str, timeframe: str) -> List[str]:
        """
        Get list of months available on Binance Vision for a symbol/timeframe.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string

        Returns:
            List of month strings in format "YYYY-MM"
        """
        # This would require scraping the directory listing or known date range
        # For now, return a reasonable default range
        logger.warning("[DEPRECATED] get_available_months requires directory listing support")
        return []

    def get_ingested_months(self, symbol: str, timeframe: str) -> List[str]:
        """
        Get list of months already ingested for a symbol/timeframe.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string

        Returns:
            List of month strings in format "YYYY-MM"
        """
        try:
            conn = self.client._ensure_connection()

            query = """
                SELECT DISTINCT
                    CAST(EXTRACT(YEAR FROM timestamp) AS INTEGER) as year,
                    CAST(EXTRACT(MONTH FROM timestamp) AS INTEGER) as month
                FROM candles
                WHERE symbol = ?
                  AND timeframe = ?
                ORDER BY year, month
            """

            result = conn.execute(query, [symbol, timeframe]).fetchall()

            months = [f"{row[0]}-{row[1]:02d}" for row in result]
            return months

        except Exception as e:
            logger.error(f"[ERROR] Failed to get ingested months: {e}")
            return []

    def get_missing_months(
        self,
        symbol: str,
        timeframe: str,
        start_year: int = 2020,
        start_month: int = 1,
        end_year: Optional[int] = None,
        end_month: Optional[int] = None,
    ) -> List[str]:
        """
        Get list of months that haven't been ingested yet.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string
            start_year: Start year for range check
            start_month: Start month for range check
            end_year: End year for range check (defaults to current)
            end_month: End month for range check (defaults to current)

        Returns:
            List of month strings in format "YYYY-MM" that need ingestion
        """
        if end_year is None:
            now = datetime.now(timezone.utc)
            end_year = now.year
            end_month = now.month

        # Build expected months list
        expected = set()
        year, month = start_year, start_month
        while (year, month) <= (end_year, end_month or 12):
            expected.add(f"{year}-{month:02d}")
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

        # Get already ingested
        ingested = set(self.get_ingested_months(symbol, timeframe))

        # Return difference
        missing = sorted(expected - ingested)
        return missing