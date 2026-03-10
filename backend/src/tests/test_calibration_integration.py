"""
Integration tests for CalibrationGovernor within CoinbaseTradingSimulator.
Ensures that the simulator correctly invokes the governor and handles recalibration triggers.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from backend.src.simulator import CoinbaseTradingSimulator
from backend.src.models import SimulatorConfig, Candle, Timeframe
from backend.src.calibration_governor import CalibrationOutcome, CalibrationTrigger
from backend.src.calibration_support import DriftAlert, DriftLevel


def make_candle(price: float, timestamp: datetime) -> Candle:
    """Helper to create a test candle."""
    return Candle(
        timestamp=timestamp,
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price,
        volume=1000.0,
        symbol="BTC-USD",
        timeframe=Timeframe.ONE_HOUR,
    )


def test_calibration_governor_integration():
    """
    Verify CalibrationGovernor integration in CoinbaseTradingSimulator.
    1. Setup a test with CoinbaseTradingSimulator and HRM shadow enabled.
    2. Mock/Configure CalibrationGovernor with a small cadence (e.g. 5 cycles).
    3. Process 4 candles and verify that CalibrationGovernor history shows 'Cadence not met' skips.
    4. On the 5th candle, verify it does a 'full check' (result might be 'SKIP' with 'No triggers met' if everything is fine).
    5. Inject low performance (e.g. mock shadow trades with losses) or drift.
    6. Process candles until the next cadence hit (e.g. 10th candle).
    7. Verify recalibration is triggered.
    8. Verify governor.record_calibration is called and resets cycle counter.
    """
    # 1. Setup a test with CoinbaseTradingSimulator and HRM shadow enabled.
    config = SimulatorConfig(
        symbols=["BTC-USD"],
        enable_hrm_shadow=True,
        hrm_shadow_mode="shadow"
    )
    
    # Mock dependencies that might hit the network or fail due to lack of real data
    # Mock SafetyEnforcement to allow simulator initialization
    with patch("backend.src.simulator.CoinbaseMarketDataClient"), \
         patch("backend.src.simulator.SafetyEnforcement.run_all_checks") as mock_safety:
        
        mock_safety.return_value = {"all_passed": True}
        sim = CoinbaseTradingSimulator(config)
        
        # 2. Mock/Configure CalibrationGovernor with a small cadence (e.g. 5 cycles).
        # We access the governor directly on the simulator instance
        sim.calibration_governor.config.check_cadence_cycles = 5
        sim.calibration_governor.config.min_hours_between_calibration = 0
        sim.calibration_governor.config.cooldown_after_calibration_hours = 0
        
        start_time = datetime(2026, 3, 11, tzinfo=timezone.utc)
        
        # Initial state check: last_calibration is None
        assert sim.calibration_governor.get_last_calibration() is None
        
        # Process first candle to get past initial calibration
        # This will trigger an INITIAL calibration and call record_calibration
        c1 = make_candle(100.0, start_time)
        sim._check_recalibration(c1)
        assert sim.calibration_governor.get_last_calibration() == c1.timestamp
        
        history = sim.calibration_governor.get_decision_history()
        assert len(history) == 1
        assert history[0].decision == CalibrationOutcome.CALIBRATE
        assert history[0].trigger == CalibrationTrigger.INITIAL
        
        # 3. Process 4 candles and verify that CalibrationGovernor history shows 'Cadence not met' skips.
        for i in range(1, 5):
            candle = make_candle(100.0, start_time + timedelta(hours=i))
            sim._check_recalibration(candle)
            
            history = sim.calibration_governor.get_decision_history()
            assert len(history) == i + 1
            # Last decision should be 'Cadence not met'
            assert "Cadence not met" in history[i].reason
            assert history[i].decision == CalibrationOutcome.SKIP

        # 4. On the 5th candle (which is the 6th total candle including initial), 
        # verify it does a 'full check' (result should be 'SKIP' with 'No triggers met' if everything is fine).
        c6 = make_candle(100.0, start_time + timedelta(hours=5))
        sim._check_recalibration(c6)
        
        history = sim.calibration_governor.get_decision_history()
        assert len(history) == 6
        assert "No triggers met" in history[5].reason
        assert history[5].decision == CalibrationOutcome.SKIP
        
        # 5. Inject low performance (e.g. mock shadow trades with losses) or drift.
        # We'll mock _compute_recent_performance to return a low win rate (< 0.45)
        with patch.object(sim, '_compute_recent_performance', return_value=0.2):
            
            # 6. Process candles until the next cadence hit (e.g. 5 more cycles).
            # We are currently at cycle 0 (since it was reset at cycle 5).
            # Cycles 1, 2, 3, 4 should skip.
            for i in range(6, 10):
                 candle = make_candle(100.0, start_time + timedelta(hours=i))
                 sim._check_recalibration(candle)
                 history = sim.calibration_governor.get_decision_history()
                 assert len(history) == i + 1
                 assert "Cadence not met" in history[i].reason
                 
            # 7. Verify recalibration is triggered at the next cadence hit (11th total candle).
            c11 = make_candle(100.0, start_time + timedelta(hours=10))
            sim._check_recalibration(c11)
            
            history = sim.calibration_governor.get_decision_history()
            assert len(history) == 11
            assert history[10].decision == CalibrationOutcome.CALIBRATE
            assert history[10].trigger == CalibrationTrigger.PERFORMANCE_DROP
            
            # 8. Verify governor.record_calibration is called and resets cycle counter.
            assert sim.calibration_governor.get_last_calibration() == c11.timestamp
            assert sim.calibration_governor._cycles_since_last_check == 0


def test_calibration_drift_trigger():
    """Verify that drift detection triggers recalibration."""
    config = SimulatorConfig(
        symbols=["BTC-USD"],
        enable_hrm_shadow=True,
        hrm_shadow_mode="shadow"
    )
    
    with patch("backend.src.simulator.CoinbaseMarketDataClient"), \
         patch("backend.src.simulator.SafetyEnforcement.run_all_checks") as mock_safety:
        
        mock_safety.return_value = {"all_passed": True}
        sim = CoinbaseTradingSimulator(config)
        
        # Setup governor with cadence = 1 for immediate testing
        sim.calibration_governor.config.check_cadence_cycles = 1
        sim.calibration_governor.config.min_hours_between_calibration = 0
        sim.calibration_governor.config.cooldown_after_calibration_hours = 0
        
        start_time = datetime(2026, 3, 11, tzinfo=timezone.utc)
        
        # 1. Initial calibration
        c1 = make_candle(100.0, start_time)
        sim._check_recalibration(c1)
        assert sim.calibration_governor.get_last_calibration() == c1.timestamp
        
        # 2. Normal operation (no drift)
        c2 = make_candle(100.0, start_time + timedelta(hours=1))
        sim._check_recalibration(c2)
        history = sim.calibration_governor.get_decision_history()
        assert history[-1].decision == CalibrationOutcome.SKIP
        
        # 3. Inject drift
        sim._last_drift_alert = DriftAlert(
            level=DriftLevel.HIGH,
            drift_type="PSI=0.25",
            description="Significant drift detected",
            recommended_action="Recalibrate"
        )
        
        # 4. Process next candle and verify recalibration
        c3 = make_candle(100.0, start_time + timedelta(hours=2))
        sim._check_recalibration(c3)
        
        history = sim.calibration_governor.get_decision_history()
        assert history[-1].decision == CalibrationOutcome.CALIBRATE
        assert history[-1].trigger == CalibrationTrigger.DRIFT_DETECTED
        
        # 5. Verify drift alert is reset after recalibration
        assert sim._last_drift_alert is None
