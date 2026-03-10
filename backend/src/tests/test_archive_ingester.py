
import pytest
import hashlib
import io
import zipfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from backend.src.archive_ingester import ArchiveIngester
from backend.src.binance_client import BinanceArchiveClient, BinanceArchiveConfig
from backend.src.models import Candle, Timeframe

@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceArchiveClient)
    client.config = BinanceArchiveConfig(
        cache_dir="/tmp/archive_cache",
        tmp_root="/tmp/archive_tmp",
        strict_checksum=True
    )
    return client

@pytest.fixture
def ingester(mock_client):
    with patch.object(BinanceArchiveClient, 'ensure_schema'):
        return ArchiveIngester(mock_client)

def test_verify_checksum_valid(ingester):
    data = b"test data"
    url = "http://example.com/file.zip"
    expected_checksum = hashlib.sha256(data).hexdigest()
    
    mock_response = MagicMock()
    mock_response.text = f"{expected_checksum}  file.zip"
    mock_response.status_code = 200
    
    with patch.object(ingester.session, 'get', return_value=mock_response):
        assert ingester._verify_checksum(data, url) is True

def test_verify_checksum_invalid(ingester):
    data = b"test data"
    url = "http://example.com/file.zip"
    
    mock_response = MagicMock()
    mock_response.text = "wrong_checksum  file.zip"
    mock_response.status_code = 200
    
    with patch.object(ingester.session, 'get', return_value=mock_response):
        assert ingester._verify_checksum(data, url) is False

def test_verify_checksum_not_strict(ingester):
    ingester.config.strict_checksum = False
    data = b"test data"
    url = "http://example.com/file.zip"
    
    # Even if it fails or doesn't match, it should return True when not strict
    assert ingester._verify_checksum(data, url) is True

def test_parse_csv_to_candles_cleanup_and_columns(ingester):
    # Test trailing zero cleanup and 11 vs 12 columns
    # Row 1: 11 columns, trailing zeros
    # Row 2: 12 columns, trailing zeros
    csv_content = (
        "1672531200000,27500.0000,27600.5000,27400.1230,27550.0000,100.5000,1672534799999,2763750.0000,1000,50.2500,1381875.0000\n"
        "1672534800000,27550.0000,27650.5000,27450.1230,27600.0000,110.5000,1672538399999,3049800.0000,1100,55.2500,1524900.0000,0\n"
    )
    csv_data = csv_content.encode('utf-8')
    
    candles = ingester._parse_csv_to_candles(csv_data, "BTCUSDT", "1h")
    
    assert len(candles) == 2
    
    # Verify Row 1 (11 columns)
    assert candles[0].open == 27500.0
    assert candles[0].high == 27600.5
    assert candles[0].low == 27400.123
    assert candles[0].close == 27550.0
    assert candles[0].volume == 100.5
    
    # Verify Row 2 (12 columns)
    assert candles[1].open == 27550.0
    assert candles[1].high == 27650.5
    assert candles[1].low == 27450.123
    assert candles[1].close == 27600.0
    assert candles[1].volume == 110.5

def test_download_monthly_file_retry(ingester):
    symbol, timeframe, year, month = "BTCUSDT", "1h", 2023, 1
    
    # Create a dummy zip content
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("BTCUSDT-1h-2023-01.csv", "dummy,csv,data")
    zip_data = zip_buffer.getvalue()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [zip_data]
    
    # Mock session.get to fail twice then succeed
    side_effects = [
        Exception("Network failure 1"),
        Exception("Network failure 2"),
        mock_response
    ]
    
    with patch.object(ingester.session, 'get', side_effect=side_effects) as mock_get:
        # Mock checksum verification to always pass
        with patch.object(ingester, '_verify_checksum', return_value=True):
            # Mock time.sleep to speed up test
            with patch('time.sleep'):
                result = ingester._download_monthly_file(symbol, timeframe, year, month)
                
                assert result == b"dummy,csv,data"
                assert mock_get.call_count == 3

def test_ingest_symbol_timeframe_dry_run(ingester):
    symbol, timeframe = "BTCUSDT", "1h"
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    
    # Mock client.has_data to return False so it tries to ingest
    ingester.client.has_data.return_value = False
    
    with patch.object(ingester, '_download_monthly_file') as mock_download:
        with patch.object(ingester, '_insert_candles') as mock_insert:
            downloaded, inserted = ingester.ingest_symbol_timeframe(
                symbol, timeframe, start_date, end_date, dry_run=True
            )
            
            assert downloaded == 0
            assert inserted == 0
            mock_download.assert_not_called()
            mock_insert.assert_not_called()
