"""
Tests for Calibration Sensitivity Sweep

Test coverage:
- Configuration validation
- Synthetic data generation
- Calibration metrics computation
- Sensitivity analysis
- Full sweep execution
- Result export
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import numpy as np

from backend.src.calibration_sweep import (
    CalibrationSweepConfig,
    CalibrationMetrics,
    CalibrationSweeper,
    SweepResult,
    SensitivityAnalysis,
    create_calibration_sweeper,
    run_calibration_sweep,
    CalibrationMetric,
)
from backend.src.models import Timeframe


class TestCalibrationSweepConfig:
    """Test calibration sweep configuration."""

    def test_default_config(self):
        """Test default configuration creation."""
        config = CalibrationSweepConfig()

        assert len(config.min_scale_values) > 0
        assert len(config.confidence_bin_edges) > 0
        assert len(config.sample_windows) > 0
        assert len(config.symbols) > 0
        assert len(config.timeframes) > 0

    def test_custom_config(self):
        """Test custom configuration."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5, 1.0],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[128, 256],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        assert config.min_scale_values == [0.5, 1.0]
        assert len(config.confidence_bin_edges) == 1
        assert config.sample_windows == [128, 256]
        assert config.symbols == ["BTCUSDT"]
        assert config.timeframes == [Timeframe.ONE_HOUR]

    def test_invalid_min_scale_values(self):
        """Test validation of min_scale_values."""
        with pytest.raises(ValueError, match="At least one min_scale_value"):
            CalibrationSweepConfig(min_scale_values=[])

    def test_invalid_confidence_bin_edges(self):
        """Test validation of confidence_bin_edges."""
        with pytest.raises(ValueError, match="At least one confidence_bin_edges"):
            CalibrationSweepConfig(confidence_bin_edges=[])

    def test_invalid_sample_windows(self):
        """Test validation of sample_windows."""
        with pytest.raises(ValueError, match="At least one sample_window"):
            CalibrationSweepConfig(sample_windows=[])

    def test_unsorted_bin_edges(self):
        """Test that bin edges must be sorted."""
        with pytest.raises(ValueError, match="must be sorted"):
            CalibrationSweepConfig(
                confidence_bin_edges=[[0.0, 1.0, 0.5]]  # Unsorted
            )

    def test_bin_edges_must_start_at_0(self):
        """Test that bin edges must start at 0.0."""
        with pytest.raises(ValueError, match="start at 0.0"):
            CalibrationSweepConfig(
                confidence_bin_edges=[[0.1, 0.5, 1.0]]
            )

    def test_bin_edges_must_end_at_1(self):
        """Test that bin edges must end at 1.0."""
        with pytest.raises(ValueError, match="end at 1.0"):
            CalibrationSweepConfig(
                confidence_bin_edges=[[0.0, 0.5, 0.9]]
            )

    def test_get_parameter_combinations(self):
        """Test parameter combination generation."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5, 1.0],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[128, 256],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        combinations = config.get_parameter_combinations()

        # Should have 2 * 1 * 2 * 1 * 1 = 4 combinations
        assert len(combinations) == 4

        # Check structure
        for combo in combinations:
            assert "min_scale" in combo
            assert "confidence_bin_edges" in combo
            assert "sample_window" in combo
            assert "symbol" in combo
            assert "timeframe" in combo

    def test_to_dict(self):
        """Test config serialization."""
        config = CalibrationSweepConfig()
        config_dict = config.to_dict()

        assert "min_scale_values" in config_dict
        assert "confidence_bin_edges" in config_dict
        assert "sample_windows" in config_dict
        assert "symbols" in config_dict
        assert "timeframes" in config_dict
        assert "output_dir" in config_dict
        assert "random_seed" in config_dict


class TestCalibrationMetrics:
    """Test calibration metrics."""

    def test_metrics_creation(self):
        """Test metrics dataclass."""
        params = {
            "min_scale": 0.5,
            "confidence_bin_edges": [0.0, 0.5, 1.0],
            "sample_window": 128,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        }

        metrics = CalibrationMetrics(
            parameter_config=params,
            expected_calibration_error=0.05,
            maximum_calibration_error=0.15,
            sharpness=0.08,
            resolution=0.12,
            brier_score=0.18,
            log_loss=0.55,
            samples_evaluated=512,
        )

        assert metrics.expected_calibration_error == 0.05
        assert metrics.maximum_calibration_error == 0.15
        assert metrics.samples_evaluated == 512

    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        params = {"min_scale": 0.5}
        metrics = CalibrationMetrics(
            parameter_config=params,
            expected_calibration_error=0.05,
            maximum_calibration_error=0.15,
            sharpness=0.08,
            resolution=0.12,
            brier_score=0.18,
            log_loss=0.55,
            samples_evaluated=512,
            confidence_intervals={"ece": (0.03, 0.07)},
        )

        metrics_dict = metrics.to_dict()

        assert "ece" in metrics_dict
        assert "mce" in metrics_dict
        assert "confidence_intervals" in metrics_dict
        assert metrics_dict["ece"] == 0.05


class TestCalibrationSweeper:
    """Test calibration sweeper."""

    def test_sweeper_creation(self):
        """Test sweeper creation."""
        sweeper = create_calibration_sweeper(seed=42)
        assert sweeper is not None
        assert sweeper.seed == 42

    def test_synthetic_data_generation(self):
        """Test synthetic data generation."""
        sweeper = CalibrationSweeper(seed=42)
        predictions, confidences, actuals = sweeper._generate_synthetic_data(n_samples=1000)

        assert len(predictions) == 1000
        assert len(confidences) == 1000
        assert len(actuals) == 1000

        # Check ranges
        assert np.all(confidences >= 0) and np.all(confidences <= 1)
        assert np.all((actuals == 0) | (actuals == 1))

    def test_min_scale_application(self):
        """Test min-scale transformation."""
        sweeper = CalibrationSweeper(seed=42)

        # Test with min_scale = 0 (no change)
        confidences = np.array([0.0, 0.3, 0.5, 0.7, 1.0])
        scaled = sweeper._apply_min_scale(confidences, min_scale=0.0)
        np.testing.assert_array_almost_equal(scaled, confidences)

        # Test with min_scale = 1 (all pushed to 0.5)
        scaled = sweeper._apply_min_scale(confidences, min_scale=1.0)
        np.testing.assert_array_almost_equal(scaled, np.array([0.5, 0.5, 0.5, 0.5, 0.5]))

        # Test with min_scale = 0.5 (partial push)
        scaled = sweeper._apply_min_scale(confidences, min_scale=0.5)
        expected = np.array([0.25, 0.4, 0.5, 0.6, 0.75])
        np.testing.assert_array_almost_equal(scaled, expected)

    def test_calibration_error_computation(self):
        """Test ECE and MCE computation."""
        sweeper = CalibrationSweeper(seed=42)

        # Perfect calibration: confidence = accuracy
        confidences = np.array([0.5, 0.5, 0.5, 0.5])
        actuals = np.array([0.5, 0.5, 0.5, 0.5])
        bin_edges = [0.0, 0.5, 1.0]

        ece, mce = sweeper._compute_calibration_error(confidences, actuals, bin_edges)
        assert ece == 0.0
        assert mce == 0.0

        # Poor calibration: high confidence but wrong
        confidences = np.array([0.9, 0.9, 0.9, 0.9])
        actuals = np.array([0.0, 0.0, 0.0, 0.0])

        ece, mce = sweeper._compute_calibration_error(confidences, actuals, bin_edges)
        assert ece > 0.3  # High ECE
        assert mce > 0.3  # High MCE

    def test_sharpness_computation(self):
        """Test sharpness computation."""
        sweeper = CalibrationSweeper(seed=42)

        # Low sharpness (all predictions near 0.5)
        confidences_low = np.array([0.45, 0.5, 0.55, 0.5, 0.5])
        sharpness_low = sweeper._compute_sharpness(confidences_low)

        # High sharpness (predictions at extremes)
        confidences_high = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
        sharpness_high = sweeper._compute_sharpness(confidences_high)

        assert sharpness_high > sharpness_low

    def test_brier_score_computation(self):
        """Test Brier score computation."""
        sweeper = CalibrationSweeper(seed=42)

        # Perfect predictions
        confidences = np.array([1.0, 0.0, 1.0, 0.0])
        actuals = np.array([1, 0, 1, 0])
        brier = sweeper._compute_brier_score(confidences, actuals)
        assert brier == 0.0

        # Worst predictions
        confidences = np.array([1.0, 0.0, 1.0, 0.0])
        actuals = np.array([0, 1, 0, 1])
        brier = sweeper._compute_brier_score(confidences, actuals)
        assert brier == 1.0

    def test_log_loss_computation(self):
        """Test log loss computation."""
        sweeper = CalibrationSweeper(seed=42)

        # Perfect predictions (low log loss)
        confidences = np.array([0.99, 0.01, 0.99, 0.01])
        actuals = np.array([1, 0, 1, 0])
        log_loss = sweeper._compute_log_loss(confidences, actuals)
        assert log_loss < 0.1

        # Poor predictions (high log loss)
        confidences = np.array([0.01, 0.99, 0.01, 0.99])
        actuals = np.array([1, 0, 1, 0])
        log_loss = sweeper._compute_log_loss(confidences, actuals)
        assert log_loss > 2.0

    def test_bootstrap_confidence_intervals(self):
        """Test bootstrap confidence interval computation."""
        sweeper = CalibrationSweeper(seed=42)

        confidences = np.random.uniform(0, 1, 1000)
        actuals = np.random.binomial(1, 0.5, 1000)
        bin_edges = [0.0, 0.5, 1.0]

        ci = sweeper._bootstrap_confidence_intervals(
            confidences, actuals, bin_edges, n_samples=50
        )

        assert "ece" in ci
        assert "brier_score" in ci

        # CI should have lower < upper
        assert ci["ece"][0] < ci["ece"][1]
        assert ci["brier_score"][0] < ci["brier_score"][1]

    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        sweeper = CalibrationSweeper(seed=42)
        config = CalibrationSweepConfig(
            min_scale_values=[0.5, 1.0],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[128, 256],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        # Generate some mock metrics
        metrics_list = []
        for combo in config.get_parameter_combinations():
            metrics = CalibrationMetrics(
                parameter_config=combo,
                expected_calibration_error=0.05 + np.random.uniform(0, 0.02),
                maximum_calibration_error=0.15,
                sharpness=0.08,
                resolution=0.12,
                brier_score=0.18,
                log_loss=0.55,
                samples_evaluated=512,
            )
            metrics_list.append(metrics)

        sensitivity_results = sweeper._analyze_sensitivity(metrics_list, config)

        assert len(sensitivity_results) > 0
        for result in sensitivity_results:
            assert isinstance(result, SensitivityAnalysis)
            assert result.parameter_name in ["min_scale", "sample_window"]
            assert result.sensitivity_score >= 0.0


class TestSweepExecution:
    """Test full sweep execution."""

    def test_run_single_combination(self):
        """Test evaluating a single combination."""
        sweeper = CalibrationSweeper(seed=42)
        combo = {
            "min_scale": 0.5,
            "confidence_bin_edges": [0.0, 0.5, 1.0],
            "sample_window": 128,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        }

        metrics = sweeper._evaluate_combination(combo, synthetic_data=None)

        assert isinstance(metrics, CalibrationMetrics)
        assert metrics.parameter_config == combo
        assert metrics.samples_evaluated > 0
        assert metrics.expected_calibration_error >= 0.0

    def test_run_full_sweep_small(self):
        """Test running a small sweep."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5, 1.0],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[64, 128],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        sweeper = CalibrationSweeper(seed=42)
        result = sweeper.run_sweep(config)

        assert isinstance(result, SweepResult)
        assert len(result.metrics_per_combination) == 4  # 2 * 1 * 2 * 1 * 1
        assert result.total_combinations == 4
        assert result.best_parameters is not None
        assert result.best_metrics is not None

    def test_sweep_with_synthetic_data(self):
        """Test sweep with provided synthetic data."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[64],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        # Generate synthetic data
        sweeper = CalibrationSweeper(seed=42)
        predictions, confidences, actuals = sweeper._generate_synthetic_data(512)
        synthetic_data = {
            "predictions": predictions.tolist(),
            "confidences": confidences.tolist(),
            "actuals": actuals.tolist(),
        }

        result = sweeper.run_sweep(config, synthetic_data=synthetic_data)

        assert isinstance(result, SweepResult)
        assert len(result.metrics_per_combination) == 1

    def test_sweep_result_serialization(self):
        """Test sweep result serialization."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[64],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        sweeper = CalibrationSweeper(seed=42)
        result = sweeper.run_sweep(config)

        # Test JSON serialization
        result_dict = result.to_dict()
        assert "config" in result_dict
        assert "metrics_per_combination" in result_dict
        assert "best_parameters" in result_dict
        assert "sensitivity_analysis" in result_dict

        # Test file save
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_result.json")
            result.save(filepath)
            assert os.path.exists(filepath)

            # Verify valid JSON
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert loaded["best_parameters"] == result.best_parameters

    def test_sweep_result_csv_export(self):
        """Test CSV export of sweep results."""
        config = CalibrationSweepConfig(
            min_scale_values=[0.5, 1.0],
            confidence_bin_edges=[[0.0, 0.5, 1.0]],
            sample_windows=[64],
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
        )

        sweeper = CalibrationSweeper(seed=42)
        result = sweeper.run_sweep(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_summary.csv")
            result.save_summary_csv(filepath)

            assert os.path.exists(filepath)

            # Verify CSV has correct structure
            with open(filepath, 'r') as f:
                lines = f.readlines()
            assert len(lines) == 3  # Header + 2 data rows
            assert "ece" in lines[0]
            assert "mce" in lines[0]


class TestRunCalibrationSweep:
    """Test high-level sweep runner."""

    def test_run_calibration_sweep(self):
        """Test run_calibration_sweep function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_calibration_sweep(
                config=CalibrationSweepConfig(
                    min_scale_values=[0.5],
                    confidence_bin_edges=[[0.0, 0.5, 1.0]],
                    sample_windows=[64],
                    symbols=["BTCUSDT"],
                    timeframes=[Timeframe.ONE_HOUR],
                ),
                output_dir=tmpdir,
                seed=42,
            )

            assert isinstance(result, SweepResult)

            # Check files were created
            files = os.listdir(tmpdir)
            assert any(f.endswith('.json') for f in files)
            assert any(f.endswith('.csv') for f in files)


class TestSensitivityAnalysis:
    """Test sensitivity analysis specifically."""

    def test_robust_parameter_detection(self):
        """Test detection of robust parameters."""
        sweeper = CalibrationSweeper(seed=42)

        # Create metrics with very little variation (robust parameter)
        metrics_list = []
        for value in [0.1, 0.5, 1.0]:
            metrics = CalibrationMetrics(
                parameter_config={"min_scale": value, "sample_window": 128},
                expected_calibration_error=0.05 + np.random.uniform(-0.001, 0.001),
                maximum_calibration_error=0.15,
                sharpness=0.08,
                resolution=0.12,
                brier_score=0.18,
                log_loss=0.55,
                samples_evaluated=512,
            )
            metrics_list.append(metrics)

        config = CalibrationSweepConfig(min_scale_values=[0.1, 0.5, 1.0])
        result = sweeper._compute_parameter_sensitivity(
            metrics_list, "min_scale", config.min_scale_values
        )

        assert result.robust  # Should be robust (low sensitivity)
        assert result.sensitivity_score < 0.1

    def test_sensitive_parameter_detection(self):
        """Test detection of sensitive parameters."""
        sweeper = CalibrationSweeper(seed=42)

        # Create metrics with large variation (sensitive parameter)
        metrics_list = []
        for value in [0.1, 0.5, 1.0]:
            ece = value * 0.2  # Large variation
            metrics = CalibrationMetrics(
                parameter_config={"min_scale": value, "sample_window": 128},
                expected_calibration_error=ece,
                maximum_calibration_error=0.15,
                sharpness=0.08,
                resolution=0.12,
                brier_score=0.18,
                log_loss=0.55,
                samples_evaluated=512,
            )
            metrics_list.append(metrics)

        config = CalibrationSweepConfig(min_scale_values=[0.1, 0.5, 1.0])
        result = sweeper._compute_parameter_sensitivity(
            metrics_list, "min_scale", config.min_scale_values
        )

        assert not result.robust  # Should not be robust (high sensitivity)
        assert result.sensitivity_score > 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
