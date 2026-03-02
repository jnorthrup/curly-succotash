"""
Data Ingestion Service
Handles historical candle backfills and live polling updates.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
from collections import defaultdict
from enum import Enum

from .models import Candle, Timeframe
from .coinbase_client import CoinbaseMarketDataClient

logger = logging.getLogger(__name__)


class IngestionMode(str, Enum):
    LIVE = "live"
    BACKTEST = "backtest"
    HYBRID = "hybrid"


@dataclass
class IngestionConfig:
    symbols: List[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD", "SOL-USD"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    poll_interval_seconds: int = 60
    backfill_days: int = 90
    mode: IngestionMode = IngestionMode.LIVE


class CandleBuffer:
    """Buffer for candle data with deduplication."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.candles: Dict[str, List[Candle]] = defaultdict(list)
        self._seen: Dict[str, set] = defaultdict(set)
    
    def add(self, candle: Candle) -> bool:
        """Add candle to buffer. Returns True if new, False if duplicate."""
        key = f"{candle.symbol}_{candle.timeframe.value}"
        candle_id = f"{candle.timestamp.isoformat()}_{candle.symbol}"
        
        if candle_id in self._seen[key]:
            return False
        
        self._seen[key].add(candle_id)
        self.candles[key].append(candle)
        
        if len(self.candles[key]) > self.max_size:
            old_candle = self.candles[key].pop(0)
            old_id = f"{old_candle.timestamp.isoformat()}_{old_candle.symbol}"
            self._seen[key].discard(old_id)
        
        return True
    
    def add_many(self, candles: List[Candle]) -> int:
        """Add multiple candles. Returns count of new candles added."""
        count = 0
        for candle in candles:
            if self.add(candle):
                count += 1
        return count
    
    def get(self, symbol: str, timeframe: Timeframe) -> List[Candle]:
        """Get all candles for symbol/timeframe."""
        key = f"{symbol}_{timeframe.value}"
        return sorted(self.candles[key], key=lambda c: c.timestamp)
    
    def get_latest(self, symbol: str, timeframe: Timeframe) -> Optional[Candle]:
        """Get most recent candle."""
        candles = self.get(symbol, timeframe)
        return candles[-1] if candles else None
    
    def clear(self, symbol: Optional[str] = None, timeframe: Optional[Timeframe] = None):
        """Clear buffer, optionally filtered."""
        if symbol and timeframe:
            key = f"{symbol}_{timeframe.value}"
            self.candles[key] = []
            self._seen[key] = set()
        elif symbol:
            keys_to_clear = [k for k in self.candles.keys() if k.startswith(symbol)]
            for key in keys_to_clear:
                self.candles[key] = []
                self._seen[key] = set()
        else:
            self.candles = defaultdict(list)
            self._seen = defaultdict(set)


class DataIngestionService:
    """
    Service for ingesting candle data from Coinbase.
    Supports historical backfill and live polling.
    """
    
    def __init__(self, config: IngestionConfig = None):
        self.config = config or IngestionConfig()
        self.client = CoinbaseMarketDataClient()
        self.buffer = CandleBuffer()
        self.candle_callbacks: List[Callable[[Candle], None]] = []
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_poll: Dict[str, datetime] = {}
        
        logger.info(f"[INGESTION] Service initialized - Mode: {self.config.mode.value}")
    
    async def start(self):
        """Start the data ingestion service."""
        if self._running:
            logger.warning("[INGESTION] Service already running")
            return
        
        self._running = True
        logger.info("[INGESTION] Starting data ingestion service")
        
        self.config.symbols = self.client.validate_symbols(self.config.symbols)
        
        if self.config.mode in [IngestionMode.LIVE, IngestionMode.HYBRID]:
            await self._perform_initial_backfill()
        
        if self.config.mode in [IngestionMode.LIVE, IngestionMode.HYBRID]:
            self._poll_task = asyncio.create_task(self._polling_loop())
        
        logger.info("[INGESTION] Service started successfully")
    
    async def stop(self):
        """Stop the data ingestion service."""
        self._running = False
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[INGESTION] Service stopped")
    
    async def _perform_initial_backfill(self):
        """Perform initial historical backfill for all symbols/timeframes."""
        logger.info(f"[INGESTION] Starting backfill for {self.config.backfill_days} days")
        
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                try:
                    candles = await asyncio.to_thread(
                        self.client.get_historical_candles,
                        symbol,
                        timeframe,
                        self.config.backfill_days
                    )
                    
                    added = self.buffer.add_many(candles)
                    logger.info(f"[INGESTION] Backfilled {added} candles for {symbol} {timeframe.value}")
                    
                except Exception as e:
                    logger.error(f"[INGESTION] Backfill failed for {symbol}: {e}")
        
        logger.info("[INGESTION] Initial backfill complete")
    
    async def _polling_loop(self):
        """Main polling loop for live data."""
        logger.info(f"[INGESTION] Starting polling loop (interval: {self.config.poll_interval_seconds}s)")
        
        while self._running:
            try:
                await self._poll_all_symbols()
                await asyncio.sleep(self.config.poll_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[INGESTION] Polling error: {e}")
                await asyncio.sleep(5)
    
    async def _poll_all_symbols(self):
        """Poll latest candles for all configured symbols/timeframes."""
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                try:
                    candles = await asyncio.to_thread(
                        self.client.get_candles,
                        symbol,
                        timeframe,
                        limit=10
                    )
                    
                    for candle in candles:
                        if self.buffer.add(candle):
                            await self._emit_candle(candle)
                    
                    key = f"{symbol}_{timeframe.value}"
                    self._last_poll[key] = datetime.utcnow()
                    
                except Exception as e:
                    logger.error(f"[INGESTION] Poll failed for {symbol}: {e}")
    
    async def _emit_candle(self, candle: Candle):
        """Emit new candle to all registered callbacks."""
        for callback in self.candle_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(candle)
                else:
                    callback(candle)
            except Exception as e:
                logger.error(f"[INGESTION] Callback error: {e}")
        
        logger.debug(f"[INGESTION] New candle: {candle.symbol} {candle.timestamp}")
    
    def register_candle_callback(self, callback: Callable[[Candle], None]):
        """Register callback for new candles."""
        self.candle_callbacks.append(callback)
    
    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: Optional[int] = None
    ) -> List[Candle]:
        """Get candles from buffer."""
        candles = self.buffer.get(symbol, timeframe)
        if limit:
            return candles[-limit:]
        return candles
    
    def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        days_back: int = 90
    ) -> List[Candle]:
        """Fetch historical candles directly (bypasses buffer)."""
        return self.client.get_historical_candles(symbol, timeframe, days_back)
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        return self.client.get_usd_price(symbol)
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        buffer_stats = {}
        for key, candles in self.buffer.candles.items():
            if candles:
                buffer_stats[key] = {
                    "count": len(candles),
                    "oldest": candles[0].timestamp.isoformat(),
                    "newest": candles[-1].timestamp.isoformat(),
                }
        
        return {
            "running": self._running,
            "mode": self.config.mode.value,
            "symbols": self.config.symbols,
            "timeframes": [tf.value for tf in self.config.timeframes],
            "poll_interval": self.config.poll_interval_seconds,
            "last_polls": {k: v.isoformat() for k, v in self._last_poll.items()},
            "buffer_stats": buffer_stats,
            "callback_count": len(self.candle_callbacks),
        }


class USDValuationService:
    """
    Service for USD valuations across different counter-coins.
    """
    
    def __init__(self, client: CoinbaseMarketDataClient):
        self.client = client
        self._price_cache: Dict[str, float] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(seconds=30)
    
    def get_usd_value(self, symbol: str, amount: float = 1.0) -> float:
        """Get USD value for an amount of a symbol."""
        price = self._get_cached_price(symbol)
        return price * amount
    
    def _get_cached_price(self, symbol: str) -> float:
        """Get price with caching."""
        now = datetime.utcnow()
        
        if symbol in self._price_cache:
            cache_age = now - self._cache_time.get(symbol, datetime.min)
            if cache_age < self._cache_ttl:
                return self._price_cache[symbol]
        
        price = self.client.get_usd_price(symbol)
        self._price_cache[symbol] = price
        self._cache_time[symbol] = now
        
        return price
    
    def convert_to_usd(
        self,
        from_symbol: str,
        amount: float
    ) -> Dict[str, Any]:
        """Convert amount to USD with metadata."""
        price = self._get_cached_price(from_symbol)
        usd_value = price * amount
        
        return {
            "from_symbol": from_symbol,
            "amount": amount,
            "price_usd": price,
            "usd_value": usd_value,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_portfolio_usd_value(
        self,
        holdings: Dict[str, float]
    ) -> Dict[str, Any]:
        """Calculate total USD value of a portfolio."""
        valuations = []
        total_usd = 0.0
        
        for symbol, amount in holdings.items():
            valuation = self.convert_to_usd(symbol, amount)
            valuations.append(valuation)
            total_usd += valuation["usd_value"]
        
        return {
            "holdings": valuations,
            "total_usd_value": total_usd,
            "timestamp": datetime.utcnow().isoformat(),
        }