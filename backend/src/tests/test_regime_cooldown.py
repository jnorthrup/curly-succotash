import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np

from backend.src.calibration_support import (
    ThresholdScheduler, 
    RegimeThresholdConfig, 
    CooldownManager, 
    CooldownConfig
)
from backend.src.models import Candle, Timeframe, SimulatorConfig
from backend.src.simulator import CoinbaseTradingSimulator

class TestRegimeCooldown:
    
    def test_threshold_scheduler(self):
        """
        Verify ThresholdScheduler picks correct thresholds based on regime.
        """
        configs = [
            RegimeThresholdConfig(regime="VOL_LOW", confidence_threshold=0.6),
            RegimeThresholdConfig(regime="VOL_HIGH", confidence_threshold=0.8),
        ]
        scheduler = ThresholdScheduler(configs, strategy="restrictive")
        
        # Verify it returns 0.8 confidence for ['VOL_HIGH'] and 0.6 for ['VOL_LOW']
        assert scheduler.get_thresholds(["VOL_HIGH"]).confidence_threshold == 0.8
        assert scheduler.get_thresholds(["VOL_LOW"]).confidence_threshold == 0.6
        
        # Verify 'restrictive' strategy picks 0.8 when passed ['VOL_LOW', 'VOL_HIGH']
        assert scheduler.get_thresholds(["VOL_LOW", "VOL_HIGH"]).confidence_threshold == 0.8

    def test_cooldown_manager(self):
        """
        Verify CooldownManager scales cooldown by regime and handles consecutive losses.
        """
        config = CooldownConfig(
            symbol="BTC-USD",
            min_cooldown_minutes=60,
            max_cooldown_minutes=240,
            max_consecutive_losses=3
        )
        manager = CooldownManager([config])
        
        now = datetime.now(timezone.utc)
        
        # Record a trade to start cooldown
        manager.record_trade(
            symbol="BTC-USD",
            entry_time=now - timedelta(minutes=10),
            exit_time=now,
            pnl=-10.0,
            pnl_percent=-0.01
        )
        
        # Verify it scales cooldown by 1.5x in VOL_HIGH (60 * 1.5 = 90 min)
        assert manager.is_in_cooldown("BTC-USD", now + timedelta(minutes=89), regime="VOL_HIGH") is True
        assert manager.is_in_cooldown("BTC-USD", now + timedelta(minutes=91), regime="VOL_HIGH") is False
        
        # Verify it scales cooldown by 0.75x in VOL_LOW (60 * 0.75 = 45 min)
        assert manager.is_in_cooldown("BTC-USD", now + timedelta(minutes=44), regime="VOL_LOW") is True
        assert manager.is_in_cooldown("BTC-USD", now + timedelta(minutes=46), regime="VOL_LOW") is False
        
        # Verify it correctly handles consecutive losses (3+) with extended cooldown
        # We already recorded 1 loss. Record 2 more.
        manager.record_trade("BTC-USD", now, now + timedelta(minutes=1), -10.0, -0.01)
        manager.record_trade("BTC-USD", now + timedelta(minutes=1), now + timedelta(minutes=2), -10.0, -0.01)
        
        last_exit = now + timedelta(minutes=2)
        
        # Extended cooldown: max_cooldown_minutes * 1.5 * multiplier
        # For VOL_NORMAL (multiplier 1.0): 240 * 1.5 = 360 minutes
        assert manager.is_in_cooldown("BTC-USD", last_exit + timedelta(minutes=359), regime="VOL_NORMAL") is True
        assert manager.is_in_cooldown("BTC-USD", last_exit + timedelta(minutes=361), regime="VOL_NORMAL") is False

    @pytest.mark.asyncio
    async def test_simulator_integration(self):
        """
        Integration test verifying simulator interacts with scheduler and cooldown manager using detected regimes.
        """
        # Mocking dependencies to isolate the simulator's logic
        with patch("backend.src.simulator.PaperTradingEngine"), \
             patch("backend.src.simulator.DataIngestionService"), \
             patch("backend.src.simulator.CoinbaseMarketDataClient"), \
             patch("backend.src.simulator.SafetyEnforcement.run_all_checks", return_value={"all_passed": True}):
            
            config = SimulatorConfig(symbols=["BTC-USD"])
            simulator = CoinbaseTradingSimulator(config)
            
            # Setup scheduler and cooldown manager with mocks to verify calls
            simulator.threshold_scheduler = MagicMock(wraps=simulator.threshold_scheduler)
            simulator.cooldown_manager = MagicMock(wraps=simulator.cooldown_manager)
            
            # Helper to create candles
            def create_candle(price, ts):
                return Candle(
                    timestamp=ts,
                    open=price,
                    high=price * 1.001,
                    low=price * 0.999,
                    close=price,
                    volume=100.0,
                    symbol="BTC-USD",
                    timeframe=Timeframe.ONE_MINUTE
                )
            
            start_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
            
            # 1. VOL_LOW regime: constant prices (std of log returns = 0 < 0.0005)
            # We need at least window (20) + 1 candles to compute volatility
            for i in range(25):
                candle = create_candle(100.0, start_ts + timedelta(minutes=i))
                await simulator._on_new_candle(candle)
            
            # Verify simulator calls threshold_scheduler and cooldown_manager with expected regime
            # The last few candles should have triggered VOL_LOW
            simulator.threshold_scheduler.get_thresholds.assert_called_with(["VOL_LOW"])
            simulator.cooldown_manager.is_in_cooldown.assert_called_with(
                "BTC-USD", start_ts + timedelta(minutes=24), regime="VOL_LOW"
            )
            
            # 2. VOL_HIGH regime: large price swings (std of log returns > 0.002)
            simulator.threshold_scheduler.get_thresholds.reset_mock()
            simulator.cooldown_manager.is_in_cooldown.reset_mock()
            
            # Process more candles with high volatility
            current_ts = start_ts + timedelta(minutes=25)
            for i in range(25):
                # Alternating large swings to ensure high std of log returns
                price = 100.0 * (1.1 if i % 2 == 0 else 0.9)
                candle = create_candle(price, current_ts + timedelta(minutes=i))
                await simulator._on_new_candle(candle)
                
            # Eventually it should hit VOL_HIGH
            simulator.threshold_scheduler.get_thresholds.assert_called_with(["VOL_HIGH"])
            simulator.cooldown_manager.is_in_cooldown.assert_called_with(
                "BTC-USD", current_ts + timedelta(minutes=24), regime="VOL_HIGH"
            )
