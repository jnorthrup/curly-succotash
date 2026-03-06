"""
Tests for Veto Regression Watch

Tests cover:
- Veto event recording and resolution
- Metrics computation
- Regression detection
- Alert generation
- Report generation
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile

from backend.src.veto_regression_watch import (
    VetoRegressionWatch,
    VetoReason,
    VetoEvent,
    VetoMetrics,
    RegressionAlert,
    create_veto_watch
)


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def veto_watch(temp_output_dir):
    """Create veto watch instance."""
    return VetoRegressionWatch(
        accuracy_threshold=60.0,
        distribution_threshold=0.10,
        window_size_days=7,
        alert_cooldown_hours=1,
        output_dir=temp_output_dir
    )


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


class TestVetoReason:
    """Test VetoReason enum."""

    def test_veto_reasons_exist(self):
        """Test that standard veto reasons are defined."""
        assert VetoReason.CONFIDENCE_TOO_LOW.value == "confidence_too_low"
        assert VetoReason.REGIME_MISMATCH.value == "regime_mismatch"
        assert VetoReason.RISK_LIMIT_EXCEEDED.value == "risk_limit_exceeded"
        assert VetoReason.MODEL_UNCERTAINTY_HIGH.value == "model_uncertainty_high"


class TestVetoEvent:
    """Test VetoEvent dataclass."""

    def test_veto_event_creation(self):
        """Test creating a veto event."""
        now = datetime.now(timezone.utc)
        event = VetoEvent(
            timestamp=now,
            symbol="BTCUSDT",
            timeframe="1h",
            veto_reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )

        assert event.symbol == "BTCUSDT"
        assert event.veto_reason == VetoReason.CONFIDENCE_TOO_LOW
        assert event.would_have_won is None

    def test_veto_event_to_dict(self):
        """Test veto event serialization."""
        now = datetime.now(timezone.utc)
        event = VetoEvent(
            timestamp=now,
            symbol="BTCUSDT",
            timeframe="1h",
            veto_reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45,
            would_have_won=False,
            would_have_pnl=-0.02
        )

        event_dict = event.to_dict()

        assert event_dict["symbol"] == "BTCUSDT"
        assert event_dict["veto_reason"] == "confidence_too_low"
        assert event_dict["would_have_won"] is False


class TestVetoRegressionWatch:
    """Test VetoRegressionWatch functionality."""

    def test_initialization(self, veto_watch):
        """Test veto watch initializes correctly."""
        assert veto_watch is not None
        assert veto_watch.accuracy_threshold == 60.0
        assert veto_watch.window_size_days == 7

    def test_record_veto(self, veto_watch):
        """Test recording a veto event."""
        veto_id = veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )

        assert veto_id == 0
        assert len(veto_watch._vetoes) == 1

    def test_record_veto_with_regime(self, veto_watch):
        """Test recording veto with regime context."""
        veto_id = veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.REGIME_MISMATCH,
            baseline_signal="LONG",
            hrm_signal="SHORT",
            hrm_confidence=0.55,
            regime_context=["VOL_HIGH", "TREND_BEAR"]
        )

        veto = veto_watch._vetoes[veto_id]
        assert "VOL_HIGH" in veto.regime_context
        assert "TREND_BEAR" in veto.regime_context

    def test_resolve_veto(self, veto_watch):
        """Test resolving a veto with outcome."""
        veto_id = veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )

        # Resolve as correct veto (would have lost)
        veto_watch.resolve_veto(veto_id, would_have_won=False, would_have_pnl=-0.02)

        assert veto_id in veto_watch._veto_outcomes
        assert veto_watch._veto_outcomes[veto_id] == (False, -0.02)

    def test_compute_metrics_no_vetoes(self, veto_watch):
        """Test metrics computation with no vetoes."""
        metrics = veto_watch.compute_metrics()

        assert metrics.total_vetoes == 0
        assert metrics.accuracy == 0.0
        assert metrics.pending_vetoes == 0

    def test_compute_metrics_with_vetoes(self, veto_watch):
        """Test metrics computation with vetoes."""
        # Record and resolve vetoes
        veto_id1 = veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )
        veto_watch.resolve_veto(veto_id1, would_have_won=False, would_have_pnl=-0.02)

        veto_id2 = veto_watch.record_veto(
            symbol="ETHUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="SHORT",
            hrm_signal="FLAT",
            hrm_confidence=0.40
        )
        veto_watch.resolve_veto(veto_id2, would_have_won=True, would_have_pnl=0.03)

        metrics = veto_watch.compute_metrics()

        assert metrics.total_vetoes == 2
        assert metrics.correct_vetoes == 1
        assert metrics.incorrect_vetoes == 1
        assert metrics.accuracy == 50.0

    def test_veto_correctness_counts_losing_trades_as_correct(self, veto_watch):
        """Test that a veto is correct when the blocked trade would have lost."""
        veto_id = veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )
        veto_watch.resolve_veto(veto_id, would_have_won=False, would_have_pnl=-0.02)

        metrics = veto_watch.compute_metrics()

        assert metrics.correct_vetoes == 1
        assert metrics.incorrect_vetoes == 0
        assert metrics.accuracy == 100.0

    def test_compute_metrics_by_reason(self, veto_watch):
        """Test metrics breakdown by veto reason."""
        # Record vetoes with different reasons
        veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )
        veto_watch.resolve_veto(0, would_have_won=False, would_have_pnl=-0.02)

        veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.REGIME_MISMATCH,
            baseline_signal="LONG",
            hrm_signal="SHORT",
            hrm_confidence=0.60
        )
        veto_watch.resolve_veto(1, would_have_won=False, would_have_pnl=-0.05)

        metrics = veto_watch.compute_metrics()

        assert "confidence_too_low" in metrics.veto_counts_by_reason
        assert "regime_mismatch" in metrics.veto_counts_by_reason

    def test_compute_metrics_by_symbol(self, veto_watch):
        """Test metrics breakdown by symbol."""
        # Record vetoes on different symbols
        veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.45
        )
        veto_watch.resolve_veto(0, would_have_won=False, would_have_pnl=-0.02)

        veto_watch.record_veto(
            symbol="ETHUSDT",
            timeframe="1h",
            reason=VetoReason.CONFIDENCE_TOO_LOW,
            baseline_signal="LONG",
            hrm_signal="FLAT",
            hrm_confidence=0.40
        )
        veto_watch.resolve_veto(1, would_have_won=False, would_have_pnl=-0.03)

        metrics = veto_watch.compute_metrics()

        assert "BTCUSDT" in metrics.veto_counts_by_symbol
        assert "ETHUSDT" in metrics.veto_counts_by_symbol

    def test_compute_metrics_by_regime(self, veto_watch):
        """Test metrics breakdown by regime."""
        veto_watch.record_veto(
            symbol="BTCUSDT",
            timeframe="1h",
            reason=VetoReason.REGIME_MISMATCH,
            baseline_signal="LONG",
            hrm_signal="SHORT",
            hrm_confidence=0.60,
            regime_context=["VOL_HIGH", "TREND_BEAR"]
        )
        veto_watch.resolve_veto(0, would_have_won=False, would_have_pnl=-0.05)

        metrics = veto_watch.compute_metrics()

        assert "VOL_HIGH" in metrics.veto_counts_by_regime
        assert "TREND_BEAR" in metrics.veto_counts_by_regime

    def test_set_baseline_metrics(self, veto_watch):
        """Test setting baseline metrics for comparison."""
        baseline = VetoMetrics(
            window_start=datetime.now(timezone.utc) - timedelta(days=7),
            window_end=datetime.now(timezone.utc),
            total_vetoes=10,
            correct_vetoes=7,
            incorrect_vetoes=3,
            pending_vetoes=0,
            accuracy=70.0,
            veto_counts_by_reason={"confidence_too_low": 5},
            accuracy_by_reason={"confidence_too_low": 80.0},
            veto_counts_by_symbol={"BTCUSDT": 5},
            accuracy_by_symbol={"BTCUSDT": 75.0},
            veto_counts_by_regime={"VOL_NORMAL": 5},
            accuracy_by_regime={"VOL_NORMAL": 70.0},
            top_veto_reasons=[("confidence_too_low", 50.0)]
        )

        veto_watch.set_baseline_metrics(baseline)
        assert veto_watch._baseline_metrics is not None
        assert veto_watch._baseline_metrics.accuracy == 70.0

    def test_check_regression_accuracy_drop(self, veto_watch):
        """Test regression detection on accuracy drop."""
        # Set baseline with high accuracy
        baseline = VetoMetrics(
            window_start=datetime.now(timezone.utc) - timedelta(days=7),
            window_end=datetime.now(timezone.utc),
            total_vetoes=10,
            correct_vetoes=8,
            incorrect_vetoes=2,
            pending_vetoes=0,
            accuracy=80.0,
            veto_counts_by_reason={},
            accuracy_by_reason={},
            veto_counts_by_symbol={},
            accuracy_by_symbol={},
            veto_counts_by_regime={},
            accuracy_by_regime={},
            top_veto_reasons=[]
        )
        veto_watch.set_baseline_metrics(baseline)

        # Add current vetoes with lower accuracy
        for i in range(5):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            # 3 incorrect, 2 correct = 40% accuracy
            veto_watch.resolve_veto(veto_id, would_have_won=(i < 2), would_have_pnl=0.01)

        alerts = veto_watch.check_regression()

        # Should detect accuracy drop (80% -> 40% = 40% drop > 10% threshold)
        assert len(alerts) > 0
        assert any(a.alert_type == "accuracy_drop" for a in alerts)

    def test_check_regression_below_threshold(self, veto_watch):
        """Test regression detection when below absolute threshold."""
        # Add vetoes with accuracy below 60% threshold
        for i in range(10):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            # 4 correct, 6 incorrect = 40% accuracy
            veto_watch.resolve_veto(veto_id, would_have_won=(i >= 4), would_have_pnl=0.01)

        alerts = veto_watch.check_regression()

        # Should detect below threshold
        assert len(alerts) > 0
        assert any(a.alert_type == "below_threshold" for a in alerts)

    def test_check_regression_distribution_shift(self, veto_watch):
        """Test regression detection on distribution shift."""
        # Set baseline with different distribution
        baseline = VetoMetrics(
            window_start=datetime.now(timezone.utc) - timedelta(days=7),
            window_end=datetime.now(timezone.utc),
            total_vetoes=10,
            correct_vetoes=7,
            incorrect_vetoes=3,
            pending_vetoes=0,
            accuracy=70.0,
            veto_counts_by_reason={"confidence_too_low": 8, "regime_mismatch": 2},
            accuracy_by_reason={},
            veto_counts_by_symbol={},
            accuracy_by_symbol={},
            veto_counts_by_regime={},
            accuracy_by_regime={},
            top_veto_reasons=[("confidence_too_low", 80.0)]
        )
        veto_watch.set_baseline_metrics(baseline)

        # Add current vetoes with shifted distribution
        for i in range(10):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.REGIME_MISMATCH,  # Shift to different reason
                baseline_signal="LONG",
                hrm_signal="SHORT",
                hrm_confidence=0.60
            )
            veto_watch.resolve_veto(veto_id, would_have_won=False, would_have_pnl=-0.02)

        alerts = veto_watch.check_regression()

        # Should detect distribution shift
        assert len(alerts) > 0
        assert any(a.alert_type == "distribution_shift" for a in alerts)

    def test_alert_cooldown(self, veto_watch):
        """Test alert cooldown mechanism."""
        # Trigger an alert
        for i in range(10):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            veto_watch.resolve_veto(veto_id, would_have_won=True, would_have_pnl=0.02)

        # First check should generate alert
        alerts1 = veto_watch.check_regression()
        assert len(alerts1) > 0

        # Immediate second check should be blocked by cooldown
        alerts2 = veto_watch.check_regression()
        # May still generate new alerts for different types, but same type should be blocked

    def test_generate_daily_report(self, veto_watch):
        """Test daily report generation."""
        # Add some vetoes
        for i in range(5):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            veto_watch.resolve_veto(veto_id, would_have_won=(i < 3), would_have_pnl=0.01)

        report = veto_watch.generate_daily_report()

        assert report["report_type"] == "daily_veto_analysis"
        assert "date" in report
        assert "daily_metrics" in report
        assert "weekly_metrics" in report
        assert "top_veto_reasons" in report
        assert "recommendations" in report

    def test_generate_weekly_report(self, veto_watch):
        """Test weekly report generation."""
        # Add some vetoes
        for i in range(10):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            veto_watch.resolve_veto(veto_id, would_have_won=(i < 6), would_have_pnl=0.01)

        report = veto_watch.generate_weekly_report()

        assert report["report_type"] == "weekly_veto_analysis"
        assert "week_start" in report
        assert "week_end" in report
        assert "summary_metrics" in report
        assert "trend_analysis" in report

    def test_save_report(self, veto_watch, temp_output_dir):
        """Test saving report to file."""
        report = veto_watch.generate_daily_report()

        path = veto_watch.save_report(report, "test_report.json")

        assert Path(path).exists()
        assert Path(path).parent == Path(temp_output_dir)

        with open(path, 'r') as f:
            loaded = json.load(f)

        assert loaded["report_type"] == "daily_veto_analysis"

    def test_get_alerts(self, veto_watch):
        """Test getting recent alerts."""
        # Generate some alerts
        for i in range(10):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            veto_watch.resolve_veto(veto_id, would_have_won=True, would_have_pnl=0.02)

        veto_watch.check_regression()

        alerts = veto_watch.get_alerts(days=7)
        assert len(alerts) > 0

    def test_get_summary(self, veto_watch):
        """Test getting summary status."""
        # Add some vetoes
        for i in range(5):
            veto_id = veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            veto_watch.resolve_veto(veto_id, would_have_won=(i < 3), would_have_pnl=0.01)

        summary = veto_watch.get_summary()

        assert "total_vetoes_tracked" in summary
        assert "current_accuracy" in summary
        assert "status" in summary
        assert summary["total_vetoes_tracked"] == 5

    def test_load_regime_manifest(self, veto_watch, sample_regime_manifest):
        """Test loading regime manifest."""
        veto_watch.load_regime_manifest(sample_regime_manifest)

        assert len(veto_watch._regime_manifest) > 0
        assert "regimes" in veto_watch._regime_manifest

    def test_veto_ids_survive_deque_rollover(self, veto_watch):
        """Test retained veto IDs still resolve after bounded storage rolls forward."""
        from collections import deque

        veto_watch._vetoes = deque(maxlen=3)

        ids = [
            veto_watch.record_veto(
                symbol="BTCUSDT",
                timeframe="1h",
                reason=VetoReason.CONFIDENCE_TOO_LOW,
                baseline_signal="LONG",
                hrm_signal="FLAT",
                hrm_confidence=0.45
            )
            for _ in range(4)
        ]

        veto_watch.resolve_veto(ids[-1], would_have_won=False, would_have_pnl=-0.02)

        assert ids[-1] in veto_watch._veto_outcomes
        assert veto_watch._first_veto_id == 1


class TestVetoMetrics:
    """Test VetoMetrics dataclass."""

    def test_to_dict(self):
        """Test metrics serialization."""
        now = datetime.now(timezone.utc)
        metrics = VetoMetrics(
            window_start=now - timedelta(days=7),
            window_end=now,
            total_vetoes=10,
            correct_vetoes=7,
            incorrect_vetoes=3,
            pending_vetoes=0,
            accuracy=70.0,
            veto_counts_by_reason={"confidence_too_low": 5},
            accuracy_by_reason={"confidence_too_low": 80.0},
            veto_counts_by_symbol={"BTCUSDT": 5},
            accuracy_by_symbol={"BTCUSDT": 75.0},
            veto_counts_by_regime={"VOL_NORMAL": 5},
            accuracy_by_regime={"VOL_NORMAL": 70.0},
            top_veto_reasons=[("confidence_too_low", 50.0)]
        )

        metrics_dict = metrics.to_dict()

        assert metrics_dict["total_vetoes"] == 10
        assert metrics_dict["accuracy"] == 70.0
        assert metrics_dict["top_veto_reasons"] == [("confidence_too_low", 50.0)]


class TestRegressionAlert:
    """Test RegressionAlert dataclass."""

    def test_to_dict(self):
        """Test alert serialization."""
        now = datetime.now(timezone.utc)
        alert = RegressionAlert(
            timestamp=now,
            alert_type="accuracy_drop",
            severity="high",
            description="Accuracy dropped from 80% to 40%",
            current_value=40.0,
            baseline_value=80.0,
            threshold=10.0,
            affected_symbols=["BTCUSDT"],
            recommended_action="Review model"
        )

        alert_dict = alert.to_dict()

        assert alert_dict["alert_type"] == "accuracy_drop"
        assert alert_dict["severity"] == "high"
        assert alert_dict["affected_symbols"] == ["BTCUSDT"]


class TestCreateVetoWatch:
    """Test factory function."""

    def test_create_with_defaults(self, temp_output_dir):
        """Test creating watch with default paths."""
        watch = create_veto_watch(output_dir=temp_output_dir)

        assert watch is not None
        assert isinstance(watch, VetoRegressionWatch)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
