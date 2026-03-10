from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.src.hrm_shadow import HRMShadowEngine, ShadowConfig, ShadowMetrics, ShadowMode
from backend.src.killswitch import DrawdownKillSwitch, KillSwitchConfig, KillSwitchState
from backend.src.models import Candle, Signal, SignalType, SimulatorConfig, Timeframe
from backend.src.scoreboard import ScoreboardGenerator
from backend.src.simulator import CoinbaseTradingSimulator


def make_candle(price: float, offset_hours: int = 0) -> Candle:
    return Candle(
        timestamp=datetime(2026, 3, 6, tzinfo=timezone.utc) + timedelta(hours=offset_hours),
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price,
        volume=1000.0,
        symbol="BTC-USD",
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


def test_shadow_engine_records_counterfactual_trade(tmp_path: Path):
    config = ShadowConfig(
        mode=ShadowMode.SHADOW,
        hrm_confidence_threshold=0.6,
        output_dir=str(tmp_path / "shadow"),
        predictor=lambda candle, _: ("LONG", 0.9) if candle.close < 105.0 else ("FLAT", 0.9),
    )
    engine = HRMShadowEngine(config)

    first_candle = make_candle(100.0, 0)
    second_candle = make_candle(110.0, 1)

    engine.process_candle(first_candle, make_signal(first_candle, SignalType.LONG, paper_size=2.0))
    engine.process_candle(second_candle, make_signal(second_candle, SignalType.FLAT, paper_size=0.0))

    assert len(engine.shadow_signals) == 2
    assert len(engine.shadow_trades) == 1
    assert engine.shadow_trades[0].side == "LONG"
    assert engine.shadow_trades[0].net_pnl > 0

    metrics = engine.compute_metrics(
        symbol="BTC-USD",
        timeframe=Timeframe.ONE_HOUR,
        baseline_trades=[{"pnl": 5.0}],
        start_time=first_candle.timestamp,
        end_time=second_candle.timestamp,
    )
    assert metrics.hrm_shadow_trades == 1


def test_killswitch_triggers_on_daily_loss(tmp_path: Path):
    killswitch = DrawdownKillSwitch(
        KillSwitchConfig(
            daily_loss_limit_pct=1.0,
            cumulative_loss_limit_pct=10.0,
            output_dir=str(tmp_path / "killswitch"),
        ),
        initial_capital=1000.0,
    )

    killswitch.record_trade(pnl=-15.0, pnl_pct=-1.5, symbol="BTC-USD")

    metrics = killswitch.get_metrics()
    assert metrics.daily_pnl_pct == pytest.approx(-1.5)
    assert metrics.state == KillSwitchState.TRIGGERED


def test_scoreboard_generator_saves_all_formats(tmp_path: Path):
    generator = ScoreboardGenerator(output_dir=str(tmp_path / "scoreboards"))
    now = datetime(2026, 3, 6, tzinfo=timezone.utc)
    metrics = [
        ShadowMetrics(
            symbol="BTC-USD",
            timeframe=Timeframe.ONE_HOUR,
            start_time=now - timedelta(days=1),
            end_time=now,
            baseline_trades=1,
            baseline_net_pnl=10.0,
            baseline_sharpe=1.0,
            baseline_max_drawdown=2.0,
            baseline_win_rate=1.0,
            hrm_shadow_trades=1,
            hrm_shadow_net_pnl=12.5,
            hrm_shadow_sharpe=1.2,
            hrm_shadow_max_drawdown=1.5,
            hrm_shadow_win_rate=1.0,
            pnl_difference=2.5,
            sharpe_difference=0.2,
            hrm_outperformance=True,
            vetoes_issued=0,
            vetoed_trades_would_have_won=0,
            vetoed_trades_would_have_lost=0,
            veto_accuracy=0.0,
        )
    ]

    scoreboard = generator.generate(date=now, metrics=metrics, mode="shadow")
    paths = generator.save_all_formats(scoreboard)

    assert scoreboard.total_pnl_difference == pytest.approx(2.5)
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert Path(paths["csv"]).exists()


@pytest.mark.asyncio
async def test_simulator_wires_shadow_and_generates_scoreboard(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "backend.src.simulator.SafetyEnforcement.run_all_checks",
        lambda client: {"all_passed": True, "no_trading_methods": True},
    )

    config = SimulatorConfig(
        symbols=["BTC-USD"],
        timeframes=[Timeframe.ONE_HOUR],
        enable_hrm_shadow=True,
        enable_killswitch=True,
        hrm_confidence_threshold=0.6,
    )
    simulator = CoinbaseTradingSimulator(config)
    simulator.paper_engine.initialize_strategies(config.symbols, config.timeframes)

    simulator.shadow_engine.config.output_dir = str(tmp_path / "shadow")
    simulator.scoreboard_generator.output_dir = tmp_path / "scoreboards"
    simulator.killswitch.config.output_dir = str(tmp_path / "killswitch")
    Path(simulator.shadow_engine.config.output_dir).mkdir(parents=True, exist_ok=True)
    simulator.scoreboard_generator.output_dir.mkdir(parents=True, exist_ok=True)
    Path(simulator.killswitch.config.output_dir).mkdir(parents=True, exist_ok=True)

    simulator.shadow_engine.config.predictor = (
        lambda candle, _: ("LONG", 0.9) if candle.close < 105.0 else ("FLAT", 0.9)
    )

    first_candle = make_candle(100.0, 0)
    second_candle = make_candle(110.0, 1)

    async def fake_process_candle(candle: Candle):
        signal_type = SignalType.LONG if candle.close < 105.0 else SignalType.FLAT
        paper_size = 1.0 if signal_type == SignalType.LONG else 0.0
        return [make_signal(candle, signal_type=signal_type, paper_size=paper_size)]

    simulator.paper_engine.process_candle = fake_process_candle

    await simulator._on_new_candle(first_candle)
    await simulator._on_new_candle(second_candle)

    tracker = next(
        iter(
            next(
                iter(
                    next(iter(simulator.paper_engine.trackers.values())).values()
                )
            ).values()
        )
    )
    tracker.strategy.trades.append({
        "entry_time": first_candle.timestamp,
        "exit_time": second_candle.timestamp.isoformat(),
        "symbol": "BTC-USD",
        "side": "LONG",
        "entry_price": 100.0,
        "exit_price": 99.0,
        "size": 1.0,
        "pnl": -1.0,
        "reason": "test close",
    })

    simulator._record_closed_trades(simulator._collect_new_closed_trades())
    scoreboard_paths = simulator.generate_shadow_scoreboard(date=second_candle.timestamp)

    assert len(simulator.shadow_engine.shadow_signals) == 2
    assert len(simulator.shadow_engine.shadow_trades) == 1
    assert simulator.killswitch.get_metrics().cumulative_pnl_pct < 0
    assert scoreboard_paths is not None
    assert Path(scoreboard_paths["json"]).exists()


@pytest.mark.asyncio
async def test_simulator_integrates_promotion_veto_and_runbook(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "backend.src.simulator.SafetyEnforcement.run_all_checks",
        lambda client: {"all_passed": True, "no_trading_methods": True},
    )

    config = SimulatorConfig(
        symbols=["BTC-USD"],
        timeframes=[Timeframe.ONE_HOUR],
        enable_hrm_shadow=True,
        enable_killswitch=True,
        hrm_shadow_mode="veto_only",
        hrm_confidence_threshold=0.6,
    )
    simulator = CoinbaseTradingSimulator(config)
    simulator.paper_engine.initialize_strategies(config.symbols, config.timeframes)

    simulator.shadow_engine.config.output_dir = str(tmp_path / "shadow")
    simulator.scoreboard_generator.output_dir = tmp_path / "scoreboards"
    simulator.killswitch.config.output_dir = str(tmp_path / "killswitch")
    simulator.promotion_ladder.output_dir = tmp_path / "promotion"
    simulator.veto_watch.output_dir = tmp_path / "veto_watch"
    simulator.runbook_generator.output_dir = tmp_path / "runbooks"

    for path in [
        Path(simulator.shadow_engine.config.output_dir),
        simulator.scoreboard_generator.output_dir,
        Path(simulator.killswitch.config.output_dir),
        simulator.promotion_ladder.output_dir,
        simulator.veto_watch.output_dir,
        simulator.runbook_generator.output_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    simulator.shadow_engine.config.predictor = lambda candle, _: ("SHORT", 0.9)

    first_candle = make_candle(100.0, 0)
    second_candle = make_candle(95.0, 1)

    async def fake_process_candle(candle: Candle):
        signal_type = SignalType.LONG if candle.close > 95.0 else SignalType.FLAT
        paper_size = 1.0 if signal_type == SignalType.LONG else 0.0
        return [make_signal(candle, signal_type=signal_type, paper_size=paper_size)]

    simulator.paper_engine.process_candle = fake_process_candle

    await simulator._on_new_candle(first_candle)
    await simulator._on_new_candle(second_candle)

    tracker = next(
        iter(
            next(
                iter(
                    next(iter(simulator.paper_engine.trackers.values())).values()
                )
            ).values()
        )
    )
    tracker.strategy.trades.append({
        "entry_time": first_candle.timestamp,
        "exit_time": second_candle.timestamp.isoformat(),
        "symbol": "BTC-USD",
        "side": "LONG",
        "entry_price": 100.0,
        "exit_price": 95.0,
        "size": 1.0,
        "pnl": -5.0,
        "reason": "test close",
    })

    simulator._record_closed_trades(simulator._collect_new_closed_trades())
    scoreboard_paths = simulator.generate_shadow_scoreboard(date=second_candle.timestamp)
    runbook_paths = simulator.generate_daily_runbook(date=second_candle.timestamp)

    assert scoreboard_paths is not None
    assert runbook_paths is not None
    assert Path(runbook_paths["json"]).exists()
    assert simulator.veto_watch.get_summary()["total_vetoes_tracked"] == 1
    assert simulator.veto_watch.get_summary()["resolved_vetoes"] == 1
    assert simulator.promotion_ladder.get_all_states()


@pytest.mark.asyncio
async def test_killswitch_halt_still_updates_open_positions(monkeypatch):
    monkeypatch.setattr(
        "backend.src.simulator.SafetyEnforcement.run_all_checks",
        lambda client: {"all_passed": True, "no_trading_methods": True},
    )

    config = SimulatorConfig(
        symbols=["BTC-USD"],
        timeframes=[Timeframe.ONE_HOUR],
        enable_killswitch=True,
    )
    simulator = CoinbaseTradingSimulator(config)

    called = {"updated": 0}

    def fake_update_open_positions(candle: Candle) -> int:
        called["updated"] += 1
        return 1

    async def fail_process_candle(candle: Candle):
        raise AssertionError("new-entry path should not run while kill-switch is active")

    simulator.paper_engine.update_open_positions = fake_update_open_positions
    simulator.paper_engine.process_candle = fail_process_candle
    simulator.killswitch.manual_halt()

    await simulator._on_new_candle(make_candle(100.0, 0))

    assert called["updated"] == 1
