"""
Tests for Daily Operator Runbook Generator

Tests cover:
- Report generation from simulator components
- Markdown conversion
- JSON export
- CSV export
- Narrative generation
- Action item generation
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile
from unittest.mock import Mock, MagicMock

from backend.src.daily_runbook import (
    DailyRunbookGenerator,
    ReportFormat,
    DailySnapshot,
    TradeSummary,
    create_runbook_generator
)
from backend.src.hrm_shadow import ShadowTrade
from backend.src.killswitch import KillSwitchReason, KillSwitchState
from backend.src.models import Timeframe


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def runbook_generator(temp_output_dir):
    """Create runbook generator instance."""
    return DailyRunbookGenerator(output_dir=temp_output_dir)


@pytest.fixture
def sample_snapshot():
    """Create sample daily snapshot."""
    return DailySnapshot(
        date="2026-03-06",
        total_trading_hours=24.0,
        symbols_tracked=["BTCUSDT", "ETHUSDT"],
        timeframes_tracked=["1h"],
        baseline_trades=50,
        baseline_net_pnl=500.0,
        baseline_win_rate=60.0,
        baseline_sharpe=1.5,
        baseline_max_drawdown=3.0,
        hrm_shadow_trades=60,
        hrm_shadow_net_pnl=600.0,
        hrm_shadow_win_rate=65.0,
        hrm_shadow_sharpe=1.8,
        hrm_shadow_max_drawdown=3.5,
        pnl_difference=100.0,
        hrm_outperformance=True,
        outperformance_rate=100.0,
        total_vetoes=10,
        veto_accuracy=70.0,
        top_veto_reasons=[("confidence_too_low", 40.0), ("regime_mismatch", 30.0)],
        regimes_detected=["VOL_NORMAL", "TREND_BULL"],
        regime_coverage_pct=80.0,
        killswitch_active=False,
        killswitch_triggers=[],
        symbols_ready_promotion=["BTCUSDT/1h"],
        symbols_require_demotion=[]
    )


@pytest.fixture
def mock_simulator():
    """Create mock simulator."""
    sim = Mock()
    sim.config = Mock(symbols=["BTCUSDT", "ETHUSDT"], timeframes=[Timeframe.ONE_HOUR])
    sim.paper_engine = Mock()
    sim.paper_engine.get_completed_trades.return_value = [
        {
            "entry_time": datetime(2026, 3, 6, 1, tzinfo=timezone.utc),
            "exit_time": datetime(2026, 3, 6, 2, tzinfo=timezone.utc),
            "symbol": "BTCUSDT",
            "timeframe": Timeframe.ONE_HOUR.value,
            "pnl": 300.0,
            "strategy_name": "Baseline_A",
        },
        {
            "entry_time": datetime(2026, 3, 6, 3, tzinfo=timezone.utc),
            "exit_time": datetime(2026, 3, 6, 4, tzinfo=timezone.utc),
            "symbol": "ETHUSDT",
            "timeframe": Timeframe.ONE_HOUR.value,
            "pnl": 200.0,
            "strategy_name": "Baseline_B",
        },
    ]
    return sim


@pytest.fixture
def mock_shadow_engine():
    """Create mock shadow engine."""
    shadow = Mock()
    shadow.shadow_trades = [
        ShadowTrade(
            timestamp=datetime(2026, 3, 6, 2, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            side="LONG",
            entry_price=100.0,
            exit_price=105.0,
            size=1.0,
            pnl=5.0,
            pnl_percent=5.0,
            fees=0.1,
            slippage=0.05,
            net_pnl=350.0,
            holding_period_seconds=3600,
        ),
        ShadowTrade(
            timestamp=datetime(2026, 3, 6, 4, tzinfo=timezone.utc),
            symbol="ETHUSDT",
            timeframe=Timeframe.ONE_HOUR,
            side="LONG",
            entry_price=200.0,
            exit_price=205.0,
            size=1.0,
            pnl=5.0,
            pnl_percent=2.5,
            fees=0.1,
            slippage=0.05,
            net_pnl=250.0,
            holding_period_seconds=3600,
        ),
    ]
    shadow.shadow_signals = []
    return shadow


@pytest.fixture
def mock_promotion_ladder():
    """Create mock promotion ladder."""
    ladder = Mock()

    # Mock states
    state = Mock()
    state.symbol = "BTCUSDT"
    state.timeframe = Mock()
    state.timeframe.value = "1h"
    state.current_stage = Mock()
    state.current_stage.value = "shadow"
    state.stage_entered_at = datetime.now(timezone.utc) - timedelta(days=10)
    state.total_trades = 150
    state.cumulative_pnl = 500.0

    ladder.get_all_states.return_value = {"BTCUSDT_1h": state}
    ladder.get_promotion_ready_symbols.return_value = []
    ladder.get_demotion_required_symbols.return_value = []

    return ladder


@pytest.fixture
def mock_veto_watch():
    """Create mock veto watch."""
    watch = Mock()

    summary = {
        "total_vetoes_tracked": 10,
        "current_accuracy": 70.0,
        "accuracy_threshold": 60.0,
        "status": "HEALTHY",
        "active_alerts": 0
    }

    watch.get_summary.return_value = summary
    watch.generate_daily_report.return_value = {
        "daily_metrics": {"total_vetoes": 10, "accuracy": 70.0},
        "top_veto_reasons": [("confidence_too_low", 40.0)],
        "regime_analysis": {"regimes_detected": ["VOL_NORMAL", "TREND_BULL"]},
        "symbol_breakdown": {},
        "recommendations": ["Continue monitoring"],
        "summary": {"total_vetoes": 10, "accuracy": 70.0}
    }

    return watch


@pytest.fixture
def mock_killswitch():
    """Create mock kill-switch."""
    ks = Mock()

    metrics = Mock()
    metrics.state = KillSwitchState.ACTIVE
    metrics.triggered_at = None
    metrics.cooldown_ends_at = None
    metrics.last_trigger_event = None

    ks.get_metrics.return_value = metrics
    return ks


class TestDailySnapshot:
    """Test DailySnapshot dataclass."""

    def test_snapshot_creation(self, sample_snapshot):
        """Test snapshot creation with all fields."""
        assert sample_snapshot.date == "2026-03-06"
        assert sample_snapshot.hrm_outperformance is True
        assert sample_snapshot.pnl_difference == 100.0

    def test_snapshot_to_dict(self, sample_snapshot):
        """Test snapshot serialization."""
        snapshot_dict = sample_snapshot.to_dict()

        assert snapshot_dict["date"] == "2026-03-06"
        assert snapshot_dict["hrm_outperformance"] is True
        assert snapshot_dict["baseline_trades"] == 50


class TestTradeSummary:
    """Test TradeSummary dataclass."""

    def test_trade_summary_creation(self):
        """Test trade summary creation."""
        summary = TradeSummary(
            symbol="BTCUSDT",
            timeframe="1h",
            baseline_trades=30,
            baseline_pnl=300.0,
            hrm_shadow_trades=35,
            hrm_shadow_pnl=350.0,
            vetoes_issued=5,
            veto_accuracy=0.70,
            winner="hrm"
        )

        assert summary.symbol == "BTCUSDT"
        assert summary.winner == "hrm"

    def test_trade_summary_to_dict(self):
        """Test trade summary serialization."""
        summary = TradeSummary(
            symbol="BTCUSDT",
            timeframe="1h",
            baseline_trades=30,
            baseline_pnl=300.0,
            hrm_shadow_trades=35,
            hrm_shadow_pnl=350.0,
            vetoes_issued=5,
            veto_accuracy=0.70,
            winner="hrm"
        )

        summary_dict = summary.to_dict()

        assert summary_dict["symbol"] == "BTCUSDT"
        assert summary_dict["winner"] == "hrm"


class TestDailyRunbookGenerator:
    """Test DailyRunbookGenerator functionality."""

    def test_initialization(self, runbook_generator, temp_output_dir):
        """Test generator initializes correctly."""
        assert runbook_generator is not None
        assert runbook_generator.output_dir == Path(temp_output_dir)

    def test_generate_from_simulator(
        self,
        runbook_generator,
        mock_simulator,
        mock_shadow_engine,
        mock_promotion_ladder,
        mock_veto_watch,
        mock_killswitch
    ):
        """Test runbook generation from simulator components."""
        runbook = runbook_generator.generate_from_simulator(
            simulator=mock_simulator,
            shadow_engine=mock_shadow_engine,
            promotion_ladder=mock_promotion_ladder,
            veto_watch=mock_veto_watch,
            killswitch=mock_killswitch
        )

        assert runbook["report_type"] == "daily_operator_runbook"
        assert "generated_at" in runbook
        assert "report_date" in runbook
        assert "executive_summary" in runbook
        assert "daily_snapshot" in runbook
        assert "trade_summaries" in runbook
        assert "promotion_status" in runbook
        assert "veto_analysis" in runbook
        assert "narrative" in runbook
        assert "action_items" in runbook

    def test_generate_runbook_hrm_outperformance(
        self,
        runbook_generator,
        mock_simulator,
        mock_shadow_engine,
        mock_promotion_ladder,
        mock_veto_watch,
        mock_killswitch
    ):
        """Test runbook when HRM outperforms."""
        runbook = runbook_generator.generate_from_simulator(
            simulator=mock_simulator,
            shadow_engine=mock_shadow_engine,
            promotion_ladder=mock_promotion_ladder,
            veto_watch=mock_veto_watch,
            killswitch=mock_killswitch
        )

        snapshot = runbook["daily_snapshot"]
        assert snapshot["hrm_outperformance"] is True
        assert snapshot["pnl_difference"] > 0

        # Check narrative reflects outperformance
        assert "HRM shadow mode outperformed" in runbook["narrative"]["performance"]

    def test_generate_runbook_killswitch_active(
        self,
        runbook_generator,
        mock_simulator,
        mock_shadow_engine,
        mock_promotion_ladder,
        mock_veto_watch
    ):
        """Test runbook when kill-switch is active."""
        # Mock kill-switch as active
        mock_ks = Mock()
        metrics = Mock()
        metrics.state = KillSwitchState.TRIGGERED
        metrics.triggered_at = datetime.now(timezone.utc)
        metrics.cooldown_ends_at = datetime.now(timezone.utc) + timedelta(hours=12)
        metrics.last_trigger_event = Mock(
            reason=KillSwitchReason.DAILY_LOSS_LIMIT,
            timestamp=datetime.now(timezone.utc),
        )
        mock_ks.get_metrics.return_value = metrics

        runbook = runbook_generator.generate_from_simulator(
            simulator=mock_simulator,
            shadow_engine=mock_shadow_engine,
            promotion_ladder=mock_promotion_ladder,
            veto_watch=mock_veto_watch,
            killswitch=mock_ks
        )

        snapshot = runbook["daily_snapshot"]
        assert snapshot["killswitch_active"] is True

        # Check narrative reflects kill-switch
        assert "KILL-SWITCH IS ACTIVE" in runbook["narrative"]["killswitch"]

        # Check action items include kill-switch resolution
        action_items = runbook["action_items"]
        assert any("kill-switch" in item["action"].lower() for item in action_items)

    def test_save_markdown(self, runbook_generator, mock_simulator, mock_shadow_engine,
                          mock_promotion_ladder, mock_veto_watch, mock_killswitch,
                          temp_output_dir):
        """Test saving runbook as Markdown."""
        runbook = runbook_generator.generate_from_simulator(
            simulator=mock_simulator,
            shadow_engine=mock_shadow_engine,
            promotion_ladder=mock_promotion_ladder,
            veto_watch=mock_veto_watch,
            killswitch=mock_killswitch
        )

        path = runbook_generator.save_markdown(runbook, "test_runbook.md")

        assert Path(path).exists()
        assert Path(path).suffix == ".md"

        with open(path, 'r') as f:
            content = f.read()

        assert "# Daily Operator Runbook" in content
        assert "Executive Summary" in content
        assert "Baseline Performance" in content

    def test_save_json(self, runbook_generator, mock_simulator, mock_shadow_engine,
                      mock_promotion_ladder, mock_veto_watch, mock_killswitch,
                      temp_output_dir):
        """Test saving runbook as JSON."""
        runbook = runbook_generator.generate_from_simulator(
            simulator=mock_simulator,
            shadow_engine=mock_shadow_engine,
            promotion_ladder=mock_promotion_ladder,
            veto_watch=mock_veto_watch,
            killswitch=mock_killswitch
        )

        path = runbook_generator.save_json(runbook, "test_runbook.json")

        assert Path(path).exists()
        assert Path(path).suffix == ".json"

        with open(path, 'r') as f:
            loaded = json.load(f)

        assert loaded["report_type"] == "daily_operator_runbook"
        assert "executive_summary" in loaded

    def test_save_csv(self, runbook_generator, temp_output_dir):
        """Test saving trade summaries as CSV."""
        runbook = {
            "trade_summaries": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "baseline_trades": 30,
                    "baseline_pnl": 300.0,
                    "hrm_shadow_trades": 35,
                    "hrm_shadow_pnl": 350.0,
                    "vetoes_issued": 5,
                    "veto_accuracy": 0.70,
                    "winner": "hrm"
                }
            ]
        }

        path = runbook_generator.save_csv(runbook, "test_summaries.csv")

        assert Path(path).exists()
        assert Path(path).suffix == ".csv"

        with open(path, 'r') as f:
            content = f.read()

        assert "symbol,timeframe,baseline_trades" in content
        assert "BTCUSDT" in content

    def test_convert_to_markdown(self, runbook_generator):
        """Test Markdown conversion."""
        runbook = {
            "report_date": "2026-03-06",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "executive_summary": "Test summary",
            "daily_snapshot": {
                "baseline_trades": 50,
                "baseline_net_pnl": 500.0,
                "baseline_win_rate": 60.0,
                "baseline_sharpe": 1.5,
                "baseline_max_drawdown": 3.0,
                "hrm_shadow_trades": 60,
                "hrm_shadow_net_pnl": 600.0,
                "hrm_shadow_win_rate": 65.0,
                "hrm_shadow_sharpe": 1.8,
                "hrm_shadow_max_drawdown": 3.5,
                "pnl_difference": 100.0,
                "hrm_outperformance": True,
                "outperformance_rate": 100.0,
                "total_vetoes": 10,
                "veto_accuracy": 70.0,
                "top_veto_reasons": [],
                "killswitch_active": False,
                "killswitch_triggers": [],
                "regimes_detected": [],
                "regime_coverage_pct": 80.0,
                "symbols_tracked": [],
                "timeframes_tracked": [],
                "symbols_ready_promotion": [],
                "symbols_require_demotion": []
            },
            "narrative": {
                "performance": "HRM outperformed",
                "vetoes": "10 vetoes issued",
                "promotion": "No promotions ready",
                "killswitch": "Inactive",
                "regime_analysis": "Good coverage"
            },
            "promotion_status": {
                "total_symbols_tracked": 2,
                "by_stage": {"shadow": 2, "veto_only": 0, "size_capped": 0, "primary": 0},
                "ready_for_promotion": [],
                "require_demotion": []
            },
            "action_items": [],
            "veto_analysis": {
                "summary": {"total_vetoes": 10, "accuracy": 70.0, "status": "HEALTHY"},
                "top_veto_reasons": []
            }
        }

        md = runbook_generator._convert_to_markdown(runbook)

        assert "# Daily Operator Runbook" in md
        assert "## Executive Summary" in md
        assert "## Daily Snapshot" in md
        assert "Baseline Performance" in md
        assert "HRM Shadow Performance" in md

    def test_generate_narrative(self, runbook_generator, sample_snapshot):
        """Test narrative generation."""
        promotion_status = {
            "ready_for_promotion": [],
            "require_demotion": []
        }
        veto_analysis = {
            "recommendations": []
        }

        narrative = runbook_generator._generate_narrative(
            snapshot=sample_snapshot,
            promotion_status=promotion_status,
            veto_analysis=veto_analysis
        )

        assert "performance" in narrative
        assert "vetoes" in narrative
        assert "promotion" in narrative
        assert "killswitch" in narrative

        # Check HRM outperformance narrative
        assert "outperformed" in narrative["performance"]

    def test_generate_narrative_baseline_wins(self, runbook_generator):
        """Test narrative when baseline wins."""
        snapshot = DailySnapshot(
            date="2026-03-06",
            total_trading_hours=24.0,
            symbols_tracked=["BTCUSDT"],
            timeframes_tracked=["1h"],
            baseline_trades=50,
            baseline_net_pnl=600.0,
            baseline_win_rate=60.0,
            baseline_sharpe=1.5,
            baseline_max_drawdown=3.0,
            hrm_shadow_trades=60,
            hrm_shadow_net_pnl=500.0,
            hrm_shadow_win_rate=55.0,
            hrm_shadow_sharpe=1.2,
            hrm_shadow_max_drawdown=4.0,
            pnl_difference=-100.0,
            hrm_outperformance=False,
            outperformance_rate=80.0,
            total_vetoes=5,
            veto_accuracy=60.0,
            top_veto_reasons=[("confidence_too_low", 50.0)],
            regimes_detected=["VOL_NORMAL"],
            regime_coverage_pct=50.0,
            killswitch_active=False,
            killswitch_triggers=[],
            symbols_ready_promotion=[],
            symbols_require_demotion=[]
        )

        narrative = runbook_generator._generate_narrative(
            snapshot=snapshot,
            promotion_status={"ready_for_promotion": [], "require_demotion": []},
            veto_analysis={"recommendations": []}
        )

        assert "Baseline trading outperformed" in narrative["performance"]

    def test_generate_executive_summary(self, runbook_generator, sample_snapshot):
        """Test executive summary generation."""
        narrative = {
            "performance": "HRM outperformed",
            "vetoes": "10 vetoes",
            "promotion": "No promotions",
            "killswitch": "Inactive"
        }

        summary = runbook_generator._generate_executive_summary(
            snapshot=sample_snapshot,
            narrative=narrative
        )

        assert "✅" in summary  # Outperformance emoji
        assert "HRM Performance" in summary
        assert "Kill-Switch" in summary

    def test_generate_action_items(self, runbook_generator, sample_snapshot):
        """Test action item generation."""
        promotion_status = {
            "ready_for_promotion": [
                {"symbol": "BTCUSDT", "timeframe": "1h", "target_stage": "veto_only"}
            ],
            "require_demotion": []
        }
        veto_analysis = {
            "recommendations": []
        }

        actions = runbook_generator._generate_action_items(
            snapshot=sample_snapshot,
            promotion_status=promotion_status,
            veto_analysis=veto_analysis
        )

        assert len(actions) > 0
        assert any("BTCUSDT" in item["action"] for item in actions)

    def test_generate_action_items_critical_killswitch(self, runbook_generator):
        """Test action items when kill-switch is active."""
        snapshot = DailySnapshot(
            date="2026-03-06",
            total_trading_hours=24.0,
            symbols_tracked=["BTCUSDT"],
            timeframes_tracked=["1h"],
            baseline_trades=50,
            baseline_net_pnl=-200.0,
            baseline_win_rate=40.0,
            baseline_sharpe=-0.5,
            baseline_max_drawdown=5.0,
            hrm_shadow_trades=60,
            hrm_shadow_net_pnl=-150.0,
            hrm_shadow_win_rate=45.0,
            hrm_shadow_sharpe=-0.3,
            hrm_shadow_max_drawdown=4.5,
            pnl_difference=50.0,
            hrm_outperformance=True,
            outperformance_rate=80.0,
            total_vetoes=5,
            veto_accuracy=60.0,
            top_veto_reasons=[],
            regimes_detected=["VOL_HIGH"],
            regime_coverage_pct=30.0,
            killswitch_active=True,
            killswitch_triggers=["daily_loss_limit"],
            symbols_ready_promotion=[],
            symbols_require_demotion=[]
        )

        actions = runbook_generator._generate_action_items(
            snapshot=snapshot,
            promotion_status={"ready_for_promotion": [], "require_demotion": []},
            veto_analysis={"recommendations": []}
        )

        # Should have CRITICAL priority action for kill-switch
        assert any(item["priority"] == "CRITICAL" for item in actions)
        assert any("kill-switch" in item["action"].lower() for item in actions)

    def test_collect_promotion_status(self, runbook_generator, mock_promotion_ladder):
        """Test promotion status collection."""
        status = runbook_generator._collect_promotion_status(mock_promotion_ladder)

        assert "total_symbols_tracked" in status
        assert "by_stage" in status
        assert "symbols" in status
        assert status["total_symbols_tracked"] == 1

    def test_collect_veto_analysis(self, runbook_generator, mock_veto_watch):
        """Test veto analysis collection."""
        analysis = runbook_generator._collect_veto_analysis(
            mock_veto_watch,
            datetime(2026, 3, 6, tzinfo=timezone.utc),
        )

        assert "summary" in analysis
        assert "daily_metrics" in analysis
        assert "recommendations" in analysis

    def test_collect_trade_summaries(self, runbook_generator, mock_simulator, mock_shadow_engine):
        """Test trade summary collection."""
        summaries = runbook_generator._collect_trade_summaries(
            mock_simulator,
            mock_shadow_engine,
            {"symbol_breakdown": {}},
            datetime(2026, 3, 6, tzinfo=timezone.utc),
        )

        assert len(summaries) == 2  # BTC and ETH
        assert all(isinstance(s, TradeSummary) for s in summaries)

    def test_determine_winner(self, runbook_generator):
        """Test winner determination."""
        assert runbook_generator._determine_winner(100.0, 120.0) == "hrm"
        assert runbook_generator._determine_winner(100.0, 80.0) == "baseline"
        assert runbook_generator._determine_winner(100.0, 100.0) == "tie"
        # Note: 100.05 is outside tolerance, so it's actually a win for HRM
        assert runbook_generator._determine_winner(100.0, 100.05) == "hrm"

    def test_collect_killswitch_status(self, runbook_generator, mock_killswitch):
        """Test kill-switch status collection."""
        status = runbook_generator._collect_killswitch_status(mock_killswitch)

        assert "is_active" in status
        assert "active_triggers" in status
        assert "cooldown_remaining_hours" in status

    def test_collect_regime_analysis(self, runbook_generator, sample_snapshot):
        """Test regime analysis collection."""
        analysis = runbook_generator._collect_regime_analysis(sample_snapshot)

        assert "regimes_detected" in analysis
        assert "coverage_percentage" in analysis
        assert "missing_regimes" in analysis

    def test_identify_missing_regimes(self, runbook_generator):
        """Test missing regime identification."""
        detected = ["VOL_NORMAL", "TREND_BULL"]
        missing = runbook_generator._identify_missing_regimes(detected)

        assert isinstance(missing, list)
        assert "VOL_LOW" in missing
        assert "VOL_HIGH" in missing

    def test_get_methodology_notes(self, runbook_generator):
        """Test methodology notes."""
        notes = runbook_generator._get_methodology_notes()

        assert "PnL Difference" in notes
        assert "Promotion Criteria" in notes
        assert "Shadow → Veto Only" in notes


class TestCreateRunbookGenerator:
    """Test factory function."""

    def test_create_with_defaults(self, temp_output_dir):
        """Test creating generator with default paths."""
        generator = create_runbook_generator(output_dir=temp_output_dir)

        assert generator is not None
        assert isinstance(generator, DailyRunbookGenerator)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
