from fastapi.testclient import TestClient
from backend.src import main as api_main
import backend.src.binance_client as binance_mod
import backend.src.coinbase_client as coinbase_mod


client = TestClient(api_main.app)


def test_binance_symbols(monkeypatch):
    monkeypatch.setattr(binance_mod.BinanceArchiveClient, "get_available_symbols", lambda self: ["BTCUSDT"])
    r = client.get("/api/exchanges/binance/symbols")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["symbols"] == ["BTCUSDT"]


def test_coinbase_ticker(monkeypatch):
    dummy = {"price": "50000"}
    monkeypatch.setattr(coinbase_mod.CoinbaseMarketDataClient, "get_product_ticker", lambda self, pid: dummy)
    r = client.get("/api/exchanges/coinbase/ticker/BTC-USD")
    assert r.status_code == 200
    data = r.json()
    assert data["product_id"] == "BTC-USD"
    assert data["ticker"] == dummy
