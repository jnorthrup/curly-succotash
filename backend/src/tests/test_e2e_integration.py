
import pytest
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from backend.src.models import Candle, Signal, SignalType, Timeframe, SimulatorConfig
from backend.src.replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from backend.src.simulator import CoinbaseTradingSimulator
from backend.src.hrm_shadow import ShadowMode

def make_candle(price: float, timestamp: datetime, symbol: str = "BTC-USD") -> Candle:
    return Candle(
        timestamp=timestamp,
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price,
        volume=1000.0,
        symbol=symbol,
        timeframe=Timeframe.ONE_HOUR,
    )

def make_signal(
    candle: Candle,
    signal_type: SignalType = SignalType.LONG,
    paper_size: float = 1.0,
) -> Signal:
    return Signal(
        timestamp=candle.timestamp,
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        strategy_name="Baseline_Test",
        signal_type=signal_type,
        entry_price=candle.close,
        stop_loss=None,
        take_profit=None,
        confidence=0.8,
        paper_size=paper_size,
        reason="test baseline signal",
    )

@pytest.mark.asyncio
async def test_e2e_replay_to_runbook(tmp_path: Path, monkeypatch):
    # 1. Setup Mock Data
    base_time = datetime(2026, 3, 6, tzinfo=timezone.utc)
    # Create 24 hours of candles to ensure we cover a "day" for runbook
    candles = [
        make_candle(100.0 + i, base_time + timedelta(hours=i))
        for i in range(25)
    ]

    # 2. Mock BinanceArchiveClient
    mock_client = MagicMock()
    mock_client.get_date_range.return_value = (candles[0].timestamp, candles[-1].timestamp)
    mock_client.query_candles.return_value = candles

    # 3. Setup ReplayEngine
    replay_config = ReplayConfig(
        mode=ReplayMode.STEP_THROUGH,
        symbols=["BTC-USD"],
        timeframes=[Timeframe.ONE_HOUR],
        start_time=candles[0].timestamp,
        end_time=candles[-1].timestamp,
    )
    engine = ReplayEngine(mock_client, replay_config)
    # Manually load candles to avoid threading/async issues with start() in tests
    engine._load_candles()
    loaded_candles = engine._candles
    assert len(loaded_candles) > 0

    # 4. Setup Simulator
    monkeypatch.setattr(
        "backend.src.simulator.SafetyEnforcement.run_all_checks",
        lambda client: {"all_passed": True, "no_trading_methods": True},
    )

    sim_config = SimulatorConfig(
        symbols=["BTC-USD"],
        timeframes=[Timeframe.ONE_HOUR],
        enable_hrm_shadow=True,
        enable_killswitch=False,
        hrm_shadow_mode="veto_only",
        hrm_confidence_threshold=0.6,
    )    
    # Override directories to use tmp_path
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    
    simulator = CoinbaseTradingSimulator(sim_config)
    simulator.paper_engine.initialize_strategies(sim_config.symbols, sim_config.timeframes)
    
    # Configure simulator components to use tmp_path
    simulator.shadow_engine.config.output_dir = str(log_dir / "shadow")
    simulator.scoreboard_generator.output_dir = log_dir / "scoreboards"
    simulator.promotion_ladder.output_dir = log_dir / "promotion"
    simulator.veto_watch.output_dir = log_dir / "veto_watch"
    simulator.runbook_generator.output_dir = log_dir / "runbooks"
    
    for path in [
        Path(simulator.shadow_engine.config.output_dir),
        simulator.scoreboard_generator.output_dir,
        simulator.promotion_ladder.output_dir,
        simulator.veto_watch.output_dir,
        simulator.runbook_generator.output_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    # 5. Mock HRM Predictor to trigger a veto
    # When baseline is LONG, HRM says SHORT -> Veto
    simulator.shadow_engine.config.predictor = lambda candle, _: ("SHORT", 0.9)

    # 6. Mock PaperEngine to generate baseline signals
    async def fake_process_candle(candle: Candle):
        # Generate a LONG signal on the first candle
        if candle.timestamp == candles[0].timestamp:
            return [make_signal(candle, signal_type=SignalType.LONG, paper_size=1.0)]
        return []

    simulator.paper_engine.process_candle = fake_process_candle

    # 7. Feed candles from ReplayEngine to Simulator
    for candle in loaded_candles:
        await simulator._on_new_candle(candle)

    # 8. Assertions
    # Check that shadow engine processed candles
    assert simulator.state.candles_processed == len(loaded_candles)
    
    # Check for veto
    veto_summary = simulator.veto_watch.get_summary()
    assert veto_summary["total_vetoes_tracked"] >= 1
    
    # Trigger runbook generation
    # Use the last candle's date
    report_date = loaded_candles[-1].timestamp
    runbook_paths = simulator.generate_daily_runbook(date=report_date)
    
    assert runbook_paths is not None
    assert Path(runbook_paths["json"]).exists()
    assert Path(runbook_paths["markdown"]).exists()
    
    # Verify runbook content
    with open(runbook_paths["json"], "r") as f:
        runbook_data = json.load(f)

    assert "daily_snapshot" in runbook_data
    assert runbook_data["daily_snapshot"]["veto_accuracy"] is not None
    assert "daily_snapshot" in runbook_data

    print("E2E Integration Test Passed!")
