"""
Coinbase Trading Simulator Orchestrator
Main coordinator for all simulator components.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Callable
from enum import Enum

from .models import Candle, Signal, Timeframe, SimulatorConfig
from .coinbase_client import CoinbaseMarketDataClient, SafetyEnforcement
from .data_ingestion import DataIngestionService, IngestionConfig, IngestionMode, USDValuationService
from .paper_trading import PaperTradingEngine, PaperTradingConfig, SignalEmitter
from .backtesting import BacktestEngine, BacktestConfig, BacktestResult
from .bullpen import BullpenAggregator, RankingMetric, BullpenFilter
from .strategies import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S UTC'
)


class SimulatorMode(str, Enum):
    LIVE_PAPER = "live_paper"
    BACKTEST = "backtest"
    HYBRID = "hybrid"


@dataclass
class SimulatorState:
    mode: SimulatorMode = SimulatorMode.LIVE_PAPER
    running: bool = False
    started_at: Optional[datetime] = None
    candles_processed: int = 0
    signals_generated: int = 0
    last_error: Optional[str] = None


class CoinbaseTradingSimulator:
    """
    Main simulator orchestrator.
    
    SAFETY ENFORCEMENT:
    - This simulator NEVER places live trades
    - Only reads market data from Coinbase API
    - All trading signals are paper-only
    """
    
    def __init__(self, config: SimulatorConfig = None):
        self.config = config or SimulatorConfig()
        self.state = SimulatorState()
        
        self.client = CoinbaseMarketDataClient()
        
        self.ingestion = DataIngestionService(IngestionConfig(
            symbols=self.config.symbols,
            timeframes=self.config.timeframes,
            poll_interval_seconds=self.config.poll_interval_seconds,
            backfill_days=self.config.backtest_start_days_ago,
        ))
        
        self.paper_engine = PaperTradingEngine(PaperTradingConfig(
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
            commission_pct=self.config.commission_pct,
        ))
        
        self.backtest_engine = BacktestEngine()
        self.bullpen = BullpenAggregator(self.paper_engine)
        self.signal_emitter = SignalEmitter()
        self.valuation_service = USDValuationService(self.client)
        
        self._verify_safety()
        
        logger.info("[SIMULATOR] Coinbase Trading Simulator initialized")
        logger.info(f"[SIMULATOR] Symbols: {self.config.symbols}")
        logger.info(f"[SIMULATOR] Timeframes: {[tf.value for tf in self.config.timeframes]}")
        logger.info("[SAFETY] ⚠️  PAPER TRADING ONLY - NO LIVE ORDERS")
    
    def _verify_safety(self):
        """Verify safety constraints are enforced."""
        safety_results = SafetyEnforcement.run_all_checks(self.client)
        
        if not safety_results["all_passed"]:
            raise RuntimeError("SAFETY VIOLATION: Trading capability detected!")
        
        logger.info("[SAFETY] ✓ All safety checks passed - READ-ONLY mode confirmed")
    
    async def start_live_paper_mode(self):
        """Start live paper trading mode with real-time candles."""
        if self.state.running:
            logger.warning("[SIMULATOR] Already running")
            return
        
        self.state.mode = SimulatorMode.LIVE_PAPER
        self.state.running = True
        self.state.started_at = datetime.now(timezone.utc)
        
        self.paper_engine.initialize_strategies(
            self.config.symbols,
            self.config.timeframes
        )
        
        self.ingestion.register_candle_callback(self._on_new_candle)
        self.paper_engine.register_signal_callback(self.signal_emitter.emit)
        
        await self.ingestion.start()
        
        logger.info("[SIMULATOR] Live paper trading mode started")
    
    async def _on_new_candle(self, candle: Candle):
        """Handle new candle from ingestion service."""
        try:
            signals = await self.paper_engine.process_candle(candle)
            
            self.state.candles_processed += 1
            self.state.signals_generated += len(signals)
            
            if signals:
                logger.info(f"[SIMULATOR] Generated {len(signals)} signals from {candle.symbol}")
                
        except Exception as e:
            self.state.last_error = str(e)
            logger.error(f"[SIMULATOR] Error processing candle: {e}")
    
    async def stop(self):
        """Stop the simulator."""
        self.state.running = False
        await self.ingestion.stop()
        logger.info("[SIMULATOR] Simulator stopped")
    
    def run_backtest(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None,
        days_back: int = 90,
        initial_capital: float = 10000.0
    ) -> List[BacktestResult]:
        """Run backtest on historical data."""
        symbols = symbols or self.config.symbols
        timeframes = timeframes or self.config.timeframes
        
        logger.info(f"[SIMULATOR] Starting backtest: {symbols} for {days_back} days")
        
        all_results = []
        
        for symbol in symbols:
            for timeframe in timeframes:
                candles = self.ingestion.get_historical_candles(
                    symbol, timeframe, days_back
                )
                
                if not candles:
                    logger.warning(f"[SIMULATOR] No candles for {symbol} {timeframe.value}")
                    continue
                
                config = BacktestConfig(
                    symbols=[symbol],
                    timeframes=[timeframe],
                    initial_capital=initial_capital,
                    position_size_pct=self.config.position_size_pct,
                    commission_pct=self.config.commission_pct,
                )
                
                results = self.backtest_engine.run_backtest(candles, config)
                all_results.extend(results)
        
        return all_results
    
    def get_bullpen_view(
        self,
        ranking_metric: RankingMetric = RankingMetric.TOTAL_RETURN,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None
    ) -> Dict[str, Any]:
        """Get current bullpen view."""
        filter_config = BullpenFilter(
            symbols=symbols,
            timeframes=timeframes,
        )
        return self.bullpen.get_bullpen_view(ranking_metric, filter_config)
    
    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signals across all strategies."""
        return self.paper_engine.get_recent_signals(limit)
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open paper positions."""
        return self.paper_engine.get_positions()
    
    def get_status(self) -> Dict[str, Any]:
        """Get simulator status."""
        return {
            "mode": self.state.mode.value,
            "running": self.state.running,
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "candles_processed": self.state.candles_processed,
            "signals_generated": self.state.signals_generated,
            "last_error": self.state.last_error,
            "config": self.config.to_dict(),
            "ingestion_status": self.ingestion.get_status(),
            "safety_verified": True,
            "strategies_count": len(STRATEGY_REGISTRY),
            "strategy_names": list(STRATEGY_REGISTRY.keys()),
        }
    
    def get_strategy_info(self) -> List[Dict[str, str]]:
        """Get information about all 12 strategies."""
        from .strategies import create_all_strategies
        
        strategies = create_all_strategies()
        return [
            {
                "name": s.name,
                "description": s.description,
            }
            for s in strategies
        ]
    
    def get_usd_valuation(self, symbol: str, amount: float = 1.0) -> Dict[str, Any]:
        """Get USD valuation for a symbol."""
        return self.valuation_service.convert_to_usd(symbol, amount)


_simulator_instance: Optional[CoinbaseTradingSimulator] = None


def get_simulator() -> CoinbaseTradingSimulator:
    """Get or create the global simulator instance."""
    global _simulator_instance
    
    if _simulator_instance is None:
        _simulator_instance = CoinbaseTradingSimulator()
    
    return _simulator_instance


def reset_simulator(config: SimulatorConfig = None) -> CoinbaseTradingSimulator:
    """Reset and create a new simulator instance."""
    global _simulator_instance
    
    if _simulator_instance and _simulator_instance.state.running:
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_simulator_instance.stop())
    
    _simulator_instance = CoinbaseTradingSimulator(config)
    return _simulator_instance
