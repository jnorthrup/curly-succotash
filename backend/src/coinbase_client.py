"""
Coinbase Advanced API Client - READ-ONLY Market Data
SAFETY: This client ONLY accesses public market/candle data endpoints.
        NO trading, account, or order endpoints are implemented.
        This is by design to ensure the simulator never places live trades.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import requests
from .models import Candle, Timeframe

logger = logging.getLogger(__name__)


class CoinbaseMarketDataClient:
    """
    Read-only Coinbase Advanced API client for market data.
    
    SAFETY ENFORCEMENT:
    - Only implements GET endpoints for public market data
    - No authentication credentials stored or used for trading
    - No POST/DELETE methods for orders
    - Cannot place, modify, or cancel orders
    - Cannot access account balances or transfer assets
    """

    BASE_URL = "https://api.coinbase.com/api/v3/brokerage"
    PUBLIC_BASE_URL = "https://api.exchange.coinbase.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._verify_no_trading_capability()

    def _verify_no_trading_capability(self):
        """Explicit verification that this client cannot trade."""
        forbidden_methods = ["place_order", "cancel_order", "create_order", 
                           "withdraw", "deposit", "transfer"]
        for method in forbidden_methods:
            assert not hasattr(self, method), f"SAFETY VIOLATION: {method} must not exist"
        logger.info("[SAFETY] CoinbaseMarketDataClient initialized - READ-ONLY mode verified")

    def get_products(self) -> List[Dict[str, Any]]:
        """Get list of available trading pairs (read-only)."""
        try:
            url = f"{self.PUBLIC_BASE_URL}/products"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            products = response.json()
            logger.info(f"[DATA] Retrieved {len(products)} products from Coinbase")
            return products
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch products: {e}")
            return []

    def get_product_ticker(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get current ticker price for a product (read-only)."""
        try:
            url = f"{self.PUBLIC_BASE_URL}/products/{product_id}/ticker"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            ticker = response.json()
            logger.debug(f"[DATA] Ticker for {product_id}: {ticker.get('price')}")
            return ticker
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch ticker for {product_id}: {e}")
            return None

    def get_candles(
        self,
        product_id: str,
        timeframe: Timeframe,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 300
    ) -> List[Candle]:
        """
        Fetch OHLCV candles for a product (read-only).
        
        Uses the public exchange API for candle data.
        Returns candles sorted oldest to newest.
        """
        try:
            granularity_map = {
                Timeframe.ONE_MINUTE: 60,
                Timeframe.FIVE_MINUTE: 300,
                Timeframe.FIFTEEN_MINUTE: 900,
                Timeframe.THIRTY_MINUTE: 1800,
                Timeframe.ONE_HOUR: 3600,
                Timeframe.TWO_HOUR: 7200,
                Timeframe.SIX_HOUR: 21600,
                Timeframe.ONE_DAY: 86400,
            }
            granularity = granularity_map.get(timeframe, 3600)

            url = f"{self.PUBLIC_BASE_URL}/products/{product_id}/candles"
            params = {"granularity": granularity}

            if start:
                params["start"] = start.isoformat()
            if end:
                params["end"] = end.isoformat()

            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            raw_candles = response.json()

            candles = []
            for c in raw_candles[:limit]:
                candle = Candle(
                    timestamp=datetime.utcfromtimestamp(c[0]),
                    low=float(c[1]),
                    high=float(c[2]),
                    open=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]),
                    symbol=product_id,
                    timeframe=timeframe,
                )
                candles.append(candle)

            candles.sort(key=lambda x: x.timestamp)
            logger.info(f"[DATA] Retrieved {len(candles)} candles for {product_id} ({timeframe.value})")
            return candles

        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch candles for {product_id}: {e}")
            return []

    def get_historical_candles(
        self,
        product_id: str,
        timeframe: Timeframe,
        days_back: int = 90
    ) -> List[Candle]:
        """
        Fetch historical candles with pagination for backfill.
        Coinbase limits to 300 candles per request, so we paginate.
        """
        all_candles: List[Candle] = []
        end = datetime.utcnow()
        start = end - timedelta(days=days_back)
        
        granularity_seconds = Timeframe.to_seconds(timeframe)
        candles_per_request = 300
        seconds_per_request = granularity_seconds * candles_per_request

        current_end = end
        while current_end > start:
            current_start = max(start, current_end - timedelta(seconds=seconds_per_request))
            
            candles = self.get_candles(
                product_id=product_id,
                timeframe=timeframe,
                start=current_start,
                end=current_end,
                limit=candles_per_request
            )
            
            if not candles:
                break
                
            all_candles.extend(candles)
            current_end = current_start - timedelta(seconds=granularity_seconds)

            if len(candles) < 10:
                break

        all_candles.sort(key=lambda x: x.timestamp)
        seen = set()
        unique_candles = []
        for c in all_candles:
            key = (c.timestamp, c.symbol)
            if key not in seen:
                seen.add(key)
                unique_candles.append(c)

        logger.info(f"[DATA] Historical backfill: {len(unique_candles)} candles for {product_id}")
        return unique_candles

    def get_usd_price(self, symbol: str) -> float:
        """
        Get USD valuation for any symbol.
        Handles direct USD pairs and cross-pairs via intermediate conversion.
        """
        if symbol.endswith("-USD"):
            ticker = self.get_product_ticker(symbol)
            if ticker:
                return float(ticker.get("price", 0))
            return 0.0

        base, quote = symbol.split("-") if "-" in symbol else (symbol, "USD")
        
        base_usd_ticker = self.get_product_ticker(f"{base}-USD")
        if base_usd_ticker:
            return float(base_usd_ticker.get("price", 0))

        quote_usd_ticker = self.get_product_ticker(f"{quote}-USD")
        pair_ticker = self.get_product_ticker(symbol)
        
        if quote_usd_ticker and pair_ticker:
            quote_usd = float(quote_usd_ticker.get("price", 0))
            pair_price = float(pair_ticker.get("price", 0))
            return pair_price * quote_usd

        logger.warning(f"[DATA] Could not determine USD price for {symbol}")
        return 0.0

    def validate_symbols(self, symbols: List[str]) -> List[str]:
        """Validate that requested symbols exist on Coinbase."""
        try:
            products = self.get_products()
            available = {p["id"] for p in products if p.get("id")}
            valid = [s for s in symbols if s in available]
            invalid = [s for s in symbols if s not in available]
            
            if invalid:
                logger.warning(f"[DATA] Invalid symbols ignored: {invalid}")
            
            return valid
        except Exception as e:
            logger.error(f"[ERROR] Symbol validation failed: {e}")
            return symbols


class SafetyEnforcement:
    """
    Static safety checks to verify no trading capability exists.
    Call these methods in tests to validate system safety.
    """

    @staticmethod
    def verify_no_trading_methods(client: CoinbaseMarketDataClient) -> bool:
        """Verify the client has no trading methods."""
        forbidden = [
            "place_order", "create_order", "submit_order",
            "cancel_order", "cancel_all_orders",
            "withdraw", "deposit", "transfer",
            "create_withdrawal", "create_deposit",
        ]
        
        for method in forbidden:
            if hasattr(client, method):
                raise AssertionError(f"SAFETY VIOLATION: Client has forbidden method: {method}")
        
        return True

    @staticmethod
    def verify_read_only_endpoints(client: CoinbaseMarketDataClient) -> bool:
        """Verify all client methods are read-only (GET requests only)."""
        import inspect
        
        for name, method in inspect.getmembers(client, predicate=inspect.ismethod):
            if name.startswith("_"):
                continue
            source = inspect.getsource(method)
            if "post(" in source.lower() or "delete(" in source.lower():
                if "order" in source.lower() or "trade" in source.lower():
                    raise AssertionError(f"SAFETY VIOLATION: {name} may place trades")
        
        return True

    @staticmethod
    def run_all_checks(client: CoinbaseMarketDataClient) -> Dict[str, bool]:
        """Run all safety checks and return results."""
        results = {}
        
        try:
            results["no_trading_methods"] = SafetyEnforcement.verify_no_trading_methods(client)
        except AssertionError as e:
            results["no_trading_methods"] = False
            logger.error(str(e))

        try:
            results["read_only_endpoints"] = SafetyEnforcement.verify_read_only_endpoints(client)
        except AssertionError as e:
            results["read_only_endpoints"] = False
            logger.error(str(e))

        results["all_passed"] = all(results.values())
        logger.info(f"[SAFETY] Check results: {results}")
        return results