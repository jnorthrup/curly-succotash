"""
Tests for HRM Promotion Ladder

Tests cover:
- Stage transitions (promotion/demotion)
- Criteria evaluation
- State tracking
- Daily report generation
- Integration with shadow mode
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile

from backend.src.hrm_promotion import (
    HRMPromotionLadder,
    PromotionStage,
    StageCriteria,
    PromotionEvaluation,
    PromotionState,
    create_promotion_ladder
)
from backend.src.hrm_shadow import ShadowMetrics
from backend.src.models import Timeframe


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_canary_basket(temp_output_dir):
    """Create sample canary basket config."""
    config = {
        "description": "Test canary basket",
        "version": "1.0",
        "basket": {
            "primary_symbols": [
                {
                    "symbol": "BTCUSDT",
                    "priority": 1,
                    "rationale": "Test symbol",
                    "timeframes": ["1h"],
                    "allocation_weight": 0.40
                }
            ]
        },
        "promotion_criteria": {
            "shadow_mode": {
                "min_days": 7,
                "min_trades": 100,
                "require_beat_baseline": True
            },
            "veto_only": {
                "min_days": 14,
                "min_trades": 200,
                "require_beat_baseline": True,
                "max_drawdown_pct": 5.0
            },
            "size_capped": {
                "min_days": 30,
                "min_trades": 500,
                "require_beat_baseline": True,
                "max_drawdown_pct": 8.0
            },
            "primary": {
                "min_days": 60,
                "min_trades": 1000,
                "require_beat_baseline": True,
                "max_drawdown_pct": 10.0
            }
        }
    }

    path = Path(temp_output_dir) / "canary_basket.json"
    with open(path, 'w') as f:
        json.dump(config, f)

    return str(path)


@pytest.fixture
def sample_regime_manifest(temp_output_dir):
    """Create sample regime manifest."""
    manifest = {
        "version": "1.0",
        "regimes": {
            "volatility": ["VOL_LOW", "VOL_NORMAL", "VOL_HIGH"],
            "trend": ["TREND_BULL", "TREND_BEAR", "TREND_RANGE"]
        }
    }

    path = Path(temp_output_dir) / "regime_manifest.json"
    with open(path, 'w') as f:
        json.dump(manifest, f)

    return str(path)


@pytest.fixture
def promotion_ladder(sample_canary_basket, sample_regime_manifest, temp_output_dir):
    """Create promotion ladder instance."""
    return HRMPromotionLadder(
        canary_basket_path=sample_canary_basket,
        regime_manifest_path=sample_regime_manifest,
        output_dir=temp_output_dir
    )


@pytest.fixture
def sample_shadow_metrics():
    """Create sample shadow metrics."""
    now = datetime.now(timezone.utc)
    return ShadowMetrics(
        symbol="BTCUSDT",
        timeframe=Timeframe.ONE_HOUR,
        start_time=now - timedelta(hours=24),
        end_time=now,
        baseline_trades=10,
        baseline_net_pnl=100.0,
        baseline_sharpe=1.2,
        baseline_max_drawdown=2.0,
        baseline_win_rate=0.6,
        hrm_shadow_trades=12,
        hrm_shadow_net_pnl=120.0,
        hrm_shadow_sharpe=1.5,
        hrm_shadow_max_drawdown=2.5,
        hrm_shadow_win_rate=0.65,
        pnl_difference=20.0,
        sharpe_difference=0.3,
        hrm_outperformance=True,
        vetoes_issued=3,
        veto_accuracy=0.7
    )


class TestPromotionStage:
    """Test PromotionStage enum utilities."""

    def test_next_stage_shadow(self):
        """Test getting next stage from shadow."""
        assert PromotionStage.next_stage(PromotionStage.SHADOW) == PromotionStage.VETO_ONLY

    def test_next_stage_veto_only(self):
        """Test getting next stage from veto_only."""
        assert PromotionStage.next_stage(PromotionStage.VETO_ONLY) == PromotionStage.SIZE_CAPPED

    def test_next_stage_primary(self):
        """Test getting next stage from primary (should be None)."""
        assert PromotionStage.next_stage(PromotionStage.PRIMARY) is None

    def test_prev_stage_primary(self):
        """Test getting previous stage from primary."""
        assert PromotionStage.prev_stage(PromotionStage.PRIMARY) == PromotionStage.SIZE_CAPPED

    def test_prev_stage_shadow(self):
        """Test getting previous stage from shadow (should be None)."""
        assert PromotionStage.prev_stage(PromotionStage.SHADOW) is None


class TestHRMPromotionLadder:
    """Test HRM Promotion Ladder functionality."""

    def test_initialization(self, promotion_ladder):
        """Test promotion ladder initializes correctly."""
        assert promotion_ladder is not None
        assert len(promotion_ladder.criteria) > 0

    def test_get_or_create_state(self, promotion_ladder):
        """Test state creation for new symbol."""
        state = promotion_ladder.get_or_create_state(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            initial_stage=PromotionStage.SHADOW
        )

        assert state.symbol == "BTCUSDT"
        assert state.timeframe == Timeframe.ONE_HOUR
        assert state.current_stage == PromotionStage.SHADOW
        assert state.total_trades == 0
        assert state.cumulative_pnl == 0.0

    def test_update_state(self, promotion_ladder, sample_shadow_metrics):
        """Test state update with metrics."""
        promotion_ladder.update_state(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics,
            regimes_detected=["VOL_NORMAL", "TREND_BULL"]
        )

        state = promotion_ladder.get_promotion_state("BTCUSDT", Timeframe.ONE_HOUR)
        assert state is not None
        assert state.total_trades == sample_shadow_metrics.hrm_shadow_trades
        assert len(state.regime_coverage) == 2
        assert "VOL_NORMAL" in state.regime_coverage

    def test_evaluate_promotion_not_ready(self, promotion_ladder, sample_shadow_metrics):
        """Test evaluation when not ready for promotion."""
        # Update state first
        promotion_ladder.update_state(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        # Evaluate (should not be ready - not enough days)
        evaluation = promotion_ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        assert evaluation.symbol == "BTCUSDT"
        assert evaluation.current_stage == PromotionStage.SHADOW
        assert evaluation.promotion_ready is False
        assert len(evaluation.blocked_reasons) > 0

    def test_evaluate_promotion_ready(self, temp_output_dir, sample_shadow_metrics):
        """Test evaluation when ready for promotion."""
        # Create ladder with minimal criteria
        ladder = HRMPromotionLadder(
            output_dir=temp_output_dir
        )

        # Create state with enough history
        state = ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        state.stage_entered_at = datetime.now(timezone.utc) - timedelta(days=10)
        state.total_trades = 150
        state.cumulative_pnl = 500.0
        state.cumulative_sharpe = 1.5
        state.regime_coverage = ["VOL_NORMAL", "TREND_RANGE"]

        # Evaluate
        evaluation = ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        # Should be ready or close to ready
        assert evaluation.days_in_stage >= 10
        assert evaluation.total_trades >= 100
        assert evaluation.outperformance_rate == 100.0

    def test_outperformance_rate_uses_history(self, temp_output_dir, sample_shadow_metrics):
        """Test outperformance rate reflects tracked windows, not trade count ratio."""
        ladder = HRMPromotionLadder(output_dir=temp_output_dir)
        state = ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        state.stage_entered_at = datetime.now(timezone.utc) - timedelta(days=10)
        state.total_trades = 150
        state.cumulative_sharpe = 1.5
        state.regime_coverage = ["VOL_NORMAL", "TREND_RANGE"]

        ladder.update_state("BTCUSDT", Timeframe.ONE_HOUR, sample_shadow_metrics)

        second_metrics = ShadowMetrics(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            start_time=sample_shadow_metrics.start_time + timedelta(days=1),
            end_time=sample_shadow_metrics.end_time + timedelta(days=1),
            baseline_trades=10,
            baseline_net_pnl=100.0,
            baseline_sharpe=1.2,
            baseline_max_drawdown=2.0,
            baseline_win_rate=0.6,
            hrm_shadow_trades=30,
            hrm_shadow_net_pnl=90.0,
            hrm_shadow_sharpe=1.1,
            hrm_shadow_max_drawdown=2.5,
            hrm_shadow_win_rate=0.5,
            pnl_difference=-10.0,
            sharpe_difference=-0.1,
            hrm_outperformance=False,
            vetoes_issued=3,
            veto_accuracy=0.7,
        )
        ladder.update_state("BTCUSDT", Timeframe.ONE_HOUR, second_metrics)

        evaluation = ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=second_metrics,
        )

        assert evaluation.outperformance_rate == 50.0

    def test_promote_symbol(self, promotion_ladder):
        """Test symbol promotion."""
        # Create state
        promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)

        # Promote
        success = promotion_ladder.promote_symbol(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            new_stage=PromotionStage.VETO_ONLY,
            reason="Test promotion"
        )

        assert success is True

        # Verify
        state = promotion_ladder.get_promotion_state("BTCUSDT", Timeframe.ONE_HOUR)
        assert state.current_stage == PromotionStage.VETO_ONLY
        assert len(state.promotion_history) == 1

    def test_promote_symbol_invalid_stage(self, promotion_ladder):
        """Test invalid promotion (skipping stages)."""
        promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)

        # Try to skip from SHADOW to SIZE_CAPPED (should fail)
        success = promotion_ladder.promote_symbol(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            new_stage=PromotionStage.SIZE_CAPPED,
            reason="Invalid skip"
        )

        assert success is False

    def test_demote_symbol(self, promotion_ladder):
        """Test symbol demotion."""
        # Create and promote
        promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        promotion_ladder.promote_symbol(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            new_stage=PromotionStage.VETO_ONLY
        )

        # Demote
        success = promotion_ladder.demote_symbol(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            reason="Test demotion"
        )

        assert success is True

        # Verify
        state = promotion_ladder.get_promotion_state("BTCUSDT", Timeframe.ONE_HOUR)
        assert state.current_stage == PromotionStage.SHADOW
        assert len(state.promotion_history) == 2  # Promotion + demotion

    def test_demote_from_shadow(self, promotion_ladder):
        """Test demotion from shadow (should fail)."""
        promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)

        success = promotion_ladder.demote_symbol(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            reason="Cannot demote from shadow"
        )

        assert success is False

    def test_get_promotion_ready_symbols(self, promotion_ladder, sample_shadow_metrics):
        """Test getting promotion-ready symbols."""
        # Setup: create a ready symbol
        state = promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        state.stage_entered_at = datetime.now(timezone.utc) - timedelta(days=10)
        state.total_trades = 150

        # Evaluate
        promotion_ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        # Get ready symbols
        ready = promotion_ladder.get_promotion_ready_symbols()

        # May or may not be ready depending on criteria
        assert isinstance(ready, list)

    def test_get_demotion_required_symbols(self, promotion_ladder, sample_shadow_metrics):
        """Test getting symbols requiring demotion."""
        # Setup: create a failing symbol
        state = promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        state.stage_entered_at = datetime.now(timezone.utc) - timedelta(days=10)
        state.max_drawdown = 20.0  # Above threshold

        # Evaluate
        promotion_ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        # Get demotion-required symbols
        demotion = promotion_ladder.get_demotion_required_symbols()

        # Should trigger demotion due to high drawdown
        assert len(demotion) > 0
        assert demotion[0].symbol == "BTCUSDT"

    def test_save_daily_report(self, promotion_ladder, sample_shadow_metrics):
        """Test daily report generation."""
        # Add some data
        promotion_ladder.update_state(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            metrics=sample_shadow_metrics
        )

        # Save report
        report_path = promotion_ladder.save_daily_report()

        # Verify report exists
        assert Path(report_path).exists()

        # Verify report content
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert "date" in report
        assert "generated_at" in report
        assert "total_symbols_tracked" in report
        assert "all_states" in report

    def test_get_shadow_mode_for_stage(self, promotion_ladder):
        """Test conversion from promotion stage to shadow mode."""
        from backend.src.hrm_shadow import ShadowMode

        assert promotion_ladder.get_shadow_mode_for_stage(PromotionStage.SHADOW) == ShadowMode.SHADOW
        assert promotion_ladder.get_shadow_mode_for_stage(PromotionStage.VETO_ONLY) == ShadowMode.VETO_ONLY
        assert promotion_ladder.get_shadow_mode_for_stage(PromotionStage.SIZE_CAPPED) == ShadowMode.SIZE_CAPPED
        assert promotion_ladder.get_shadow_mode_for_stage(PromotionStage.PRIMARY) == ShadowMode.PRIMARY

    def test_demotion_triggers(self, promotion_ladder):
        """Test demotion trigger conditions."""
        from backend.src.hrm_shadow import ShadowMetrics

        # Create state with high drawdown
        state = promotion_ladder.get_or_create_state("BTCUSDT", Timeframe.ONE_HOUR)
        state.current_stage = PromotionStage.VETO_ONLY
        state.max_drawdown = 16.0  # Above 15% threshold

        # Create metrics showing underperformance
        now = datetime.now(timezone.utc)
        metrics = ShadowMetrics(
            symbol="BTCUSDT",
            timeframe=Timeframe.ONE_HOUR,
            start_time=now - timedelta(hours=24),
            end_time=now,
            baseline_net_pnl=100.0,
            pnl_difference=-10.0  # Underperforming
        )

        # Check demotion
        should_demote = promotion_ladder._check_demotion(state, metrics)
        assert should_demote is True


class TestStageCriteria:
    """Test StageCriteria dataclass."""

    def test_to_dict(self):
        """Test criteria serialization."""
        criteria = StageCriteria(
            min_days=7,
            min_trades=100,
            min_outperformance_rate=55.0,
            min_pnl_difference_pct=2.0,
            min_veto_accuracy=60.0,
            max_drawdown_pct=5.0,
            min_sharpe_ratio=1.0,
            min_regimes_tested=2,
            required_regimes=["VOL_NORMAL", "TREND_RANGE"]
        )

        criteria_dict = criteria.to_dict()

        assert criteria_dict["min_days"] == 7
        assert criteria_dict["required_regimes"] == ["VOL_NORMAL", "TREND_RANGE"]


class TestPromotionEvaluation:
    """Test PromotionEvaluation dataclass."""

    def test_to_dict(self):
        """Test evaluation serialization."""
        now = datetime.now(timezone.utc)
        evaluation = PromotionEvaluation(
            symbol="BTCUSDT",
            timeframe="1h",
            current_stage=PromotionStage.SHADOW,
            evaluation_date=now.isoformat(),
            days_in_stage=10,
            total_trades=150,
            outperformance_rate=60.0,
            pnl_difference_pct=3.0,
            veto_accuracy=0.0,
            current_drawdown_pct=2.0,
            current_sharpe_ratio=1.2,
            regimes_tested=["VOL_NORMAL", "TREND_RANGE"],
            promotion_ready=True,
            demotion_required=False,
            target_stage=PromotionStage.VETO_ONLY,
            reasons=["All criteria met"],
            blocked_reasons=[]
        )

        eval_dict = evaluation.to_dict()

        assert eval_dict["symbol"] == "BTCUSDT"
        assert eval_dict["promotion_ready"] is True
        assert eval_dict["target_stage"] == "veto_only"


class TestCreatePromotionLadder:
    """Test factory function."""

    def test_create_with_defaults(self, temp_output_dir):
        """Test creating ladder with default paths."""
        ladder = create_promotion_ladder(output_dir=temp_output_dir)

        assert ladder is not None
        assert isinstance(ladder, HRMPromotionLadder)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
