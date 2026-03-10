"""
Calibration Sensitivity Sweep

Sweep calibration parameters to understand sensitivity and find optimal settings.
Tests combinations of min-scale, confidence bins, and sample windows to identify
robust calibration configurations.

Key Features:
- Grid search over calibration parameters
- Sensitivity analysis (how metrics change per parameter)
- Best parameter identification
- Results export to JSON/CSV
- Visualization data generation

Example:
    config = CalibrationSweepConfig(
        min_scale_values=[0.1, 0.5, 1.0],
        confidence_bin_edges=[0.0, 0.5, 1.0],
        sample_windows=[64, 128, 256]
    )
    sweeper = CalibrationSweeper()
    result = sweeper.run_sweep(config)
    result.save("/path/to/sweep_results.json")
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

import numpy as np

from .models import Timeframe

logger = logging.getLogger(__name__)


class CalibrationMetric(Enum):
    """Metrics tracked during calibration sweep."""
    ECE = "expected_calibration_error"
    MCE = "maximum_calibration_error"
    SHARPNESS = "sharpness"
    RESOLUTION = "resolution"
    BRIER_SCORE = "brier_score"
    LOG_LOSS = "log_loss"


@dataclass
class CalibrationSweepConfig:
    """Configuration for calibration sensitivity sweep.

    Attributes:
        min_scale_values: List of min-scale values to test
        confidence_bin_edges: Confidence bin edges to test
        sample_windows: List of sample window sizes to test
        symbols: Symbols to sweep over
        timeframes: Timeframes to sweep over
        output_dir: Directory for sweep results
        random_seed: Random seed for reproducibility
        n_bootstrap_samples: Number of bootstrap samples for confidence intervals
    """
    min_scale_values: List[float] = field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0])
    confidence_bin_edges: List[List[float]] = field(default_factory=lambda: [
        [0.0, 0.3, 0.5, 0.7, 1.0],
        [0.0, 0.25, 0.5, 0.75, 1.0],
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    ])
    sample_windows: List[int] = field(default_factory=lambda: [64, 128, 256, 512])
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    output_dir: str = "/Users/jim/work/curly-succotash/logs/calibration_sweep"
    random_seed: int = 42
    n_bootstrap_samples: int = 100

    def __post_init__(self):
        """Validate configuration."""
        if not self.min_scale_values:
            raise ValueError("At least one min_scale_value required")
        if not self.confidence_bin_edges:
            raise ValueError("At least one confidence_bin_edges configuration required")
        if not self.sample_windows:
            raise ValueError("At least one sample_window required")
        if not self.symbols:
            raise ValueError("At least one symbol required")
        if not self.timeframes:
            raise ValueError("At least one timeframe required")

        # Validate bin edges are sorted
        for edges in self.confidence_bin_edges:
            if edges != sorted(edges):
                raise ValueError(f"Confidence bin edges must be sorted: {edges}")
            if edges[0] != 0.0 or edges[-1] != 1.0:
                raise ValueError(f"Bin edges must start at 0.0 and end at 1.0: {edges}")

    def get_parameter_combinations(self) -> List[Dict[str, Any]]:
        """Get all parameter combinations for grid search."""
        combinations = []
        for min_scale, bin_edges, window, symbol, timeframe in product(
            self.min_scale_values,
            self.confidence_bin_edges,
            self.sample_windows,
            self.symbols,
            self.timeframes
        ):
            combinations.append({
                "min_scale": min_scale,
                "confidence_bin_edges": bin_edges,
                "sample_window": window,
                "symbol": symbol,
                "timeframe": timeframe.value,
            })
        return combinations

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "min_scale_values": self.min_scale_values,
            "confidence_bin_edges": self.confidence_bin_edges,
            "sample_windows": self.sample_windows,
            "symbols": self.symbols,
            "timeframes": [tf.value for tf in self.timeframes],
            "output_dir": self.output_dir,
            "random_seed": self.random_seed,
            "n_bootstrap_samples": self.n_bootstrap_samples,
        }


@dataclass
class CalibrationMetrics:
    """Calibration metrics for a single parameter combination."""
    parameter_config: Dict[str, Any]
    expected_calibration_error: float
    maximum_calibration_error: float
    sharpness: float
    resolution: float
    brier_score: float
    log_loss: float
    samples_evaluated: int
    confidence_intervals: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "parameter_config": self.parameter_config,
            "ece": self.expected_calibration_error,
            "mce": self.maximum_calibration_error,
            "sharpness": self.sharpness,
            "resolution": self.resolution,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "samples_evaluated": self.samples_evaluated,
            "confidence_intervals": {
                k: {"lower": v[0], "upper": v[1]}
                for k, v in self.confidence_intervals.items()
            },
        }


@dataclass
class SensitivityAnalysis:
    """Sensitivity analysis results."""
    parameter_name: str
    sensitivity_score: float  # How much metrics change per unit change in parameter
    optimal_range: Tuple[float, float]  # Range where metrics are best
    robust: bool  # Whether parameter is robust (low sensitivity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "sensitivity_score": self.sensitivity_score,
            "optimal_range": {"lower": self.optimal_range[0], "upper": self.optimal_range[1]},
            "robust": self.robust,
        }


@dataclass
class SweepResult:
    """Results from calibration sensitivity sweep."""
    config: CalibrationSweepConfig
    metrics_per_combination: List[CalibrationMetrics]
    best_parameters: Dict[str, Any]
    best_metrics: CalibrationMetrics
    sensitivity_analysis: List[SensitivityAnalysis]
    start_time: datetime
    end_time: datetime
    total_combinations: int
    failed_combinations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "config": self.config.to_dict(),
            "metrics_per_combination": [m.to_dict() for m in self.metrics_per_combination],
            "best_parameters": self.best_parameters,
            "best_metrics": self.best_metrics.to_dict(),
            "sensitivity_analysis": [s.to_dict() for s in self.sensitivity_analysis],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_combinations": self.total_combinations,
            "failed_combinations": self.failed_combinations,
        }

    def save(self, filepath: str) -> None:
        """Save sweep result to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[SWEEP] Results saved to {filepath}")

    def save_summary_csv(self, filepath: str) -> None:
        """Save summary to CSV."""
        import csv

        if not self.metrics_per_combination:
            logger.warning("[SWEEP] No metrics to save")
            return

        fieldnames = [
            "min_scale", "confidence_bin_edges", "sample_window", "symbol", "timeframe",
            "ece", "mce", "sharpness", "resolution", "brier_score", "log_loss", "samples"
        ]

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for metrics in self.metrics_per_combination:
                row = {
                    "min_scale": metrics.parameter_config["min_scale"],
                    "confidence_bin_edges": str(metrics.parameter_config["confidence_bin_edges"]),
                    "sample_window": metrics.parameter_config["sample_window"],
                    "symbol": metrics.parameter_config["symbol"],
                    "timeframe": metrics.parameter_config["timeframe"],
                    "ece": metrics.expected_calibration_error,
                    "mce": metrics.maximum_calibration_error,
                    "sharpness": metrics.sharpness,
                    "resolution": metrics.resolution,
                    "brier_score": metrics.brier_score,
                    "log_loss": metrics.log_loss,
                    "samples": metrics.samples_evaluated,
                }
                writer.writerow(row)

        logger.info(f"[SWEEP] Summary saved to {filepath}")


class CalibrationSweeper:
    """Run calibration sensitivity sweeps.

    Performs grid search over calibration parameters to identify optimal
    settings and understand parameter sensitivity.

    Example:
        config = CalibrationSweepConfig()
        sweeper = CalibrationSweeper()
        result = sweeper.run_sweep(config)
    """

    def __init__(self, seed: int = 42):
        """Initialize sweeper.

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        self._current_combination = 0
        self._total_combinations = 0

    def run_sweep(
        self,
        config: CalibrationSweepConfig,
        synthetic_data: Optional[Dict[str, Any]] = None
    ) -> SweepResult:
        """Run calibration sensitivity sweep.

        Args:
            config: Sweep configuration
            synthetic_data: Optional synthetic data for testing.
                           If None, generates synthetic data.

        Returns:
            SweepResult with all metrics and analysis
        """
        start_time = datetime.now(timezone.utc)
        logger.info(f"[SWEEP] Starting calibration sweep")
        logger.info(f"[SWEEP] Total combinations: {len(config.get_parameter_combinations())}")

        self._total_combinations = len(config.get_parameter_combinations())
        self._current_combination = 0

        metrics_list = []
        failed_count = 0

        for combo in config.get_parameter_combinations():
            try:
                metrics = self._evaluate_combination(combo, synthetic_data)
                metrics_list.append(metrics)
            except Exception as e:
                logger.error(f"[SWEEP] Failed to evaluate {combo}: {e}")
                failed_count += 1

            self._current_combination += 1
            if self._current_combination % 10 == 0:
                logger.info(f"[SWEEP] Progress: {self._current_combination}/{self._total_combinations}")

        end_time = datetime.now(timezone.utc)

        if not metrics_list:
            raise RuntimeError("[SWEEP] No successful combinations")

        # Find best parameters (lowest ECE)
        best_metrics = min(metrics_list, key=lambda m: m.expected_calibration_error)
        best_parameters = best_metrics.parameter_config.copy()

        # Run sensitivity analysis
        sensitivity_results = self._analyze_sensitivity(metrics_list, config)

        result = SweepResult(
            config=config,
            metrics_per_combination=metrics_list,
            best_parameters=best_parameters,
            best_metrics=best_metrics,
            sensitivity_analysis=sensitivity_results,
            start_time=start_time,
            end_time=end_time,
            total_combinations=self._total_combinations,
            failed_combinations=failed_count,
        )

        logger.info(f"[SWEEP] Sweep completed in {(end_time - start_time).total_seconds():.2f}s")
        logger.info(f"[SWEEP] Best ECE: {best_metrics.expected_calibration_error:.4f}")
        logger.info(f"[SWEEP] Best parameters: {best_parameters}")

        return result

    def _evaluate_combination(
        self,
        combo: Dict[str, Any],
        synthetic_data: Optional[Dict[str, Any]]
    ) -> CalibrationMetrics:
        """Evaluate a single parameter combination.

        Args:
            combo: Parameter combination
            synthetic_data: Optional synthetic data

        Returns:
            CalibrationMetrics for this combination
        """
        # Generate or use provided synthetic data
        if synthetic_data is None:
            predictions, confidences, actuals = self._generate_synthetic_data(
                n_samples=combo["sample_window"] * 4
            )
        else:
            predictions = np.array(synthetic_data["predictions"])
            confidences = np.array(synthetic_data["confidences"])
            actuals = np.array(synthetic_data["actuals"])

        # Apply min-scale to confidences
        min_scale = combo["min_scale"]
        scaled_confidences = self._apply_min_scale(confidences, min_scale)

        # Compute calibration metrics
        bin_edges = combo["confidence_bin_edges"]
        ece, mce = self._compute_calibration_error(scaled_confidences, actuals, bin_edges)
        sharpness = self._compute_sharpness(scaled_confidences)
        resolution = self._compute_resolution(scaled_confidences, actuals, bin_edges)
        brier = self._compute_brier_score(scaled_confidences, actuals)
        log_loss = self._compute_log_loss(scaled_confidences, actuals)

        # Bootstrap confidence intervals
        ci = self._bootstrap_confidence_intervals(
            scaled_confidences, actuals, bin_edges, n_samples=100
        )

        return CalibrationMetrics(
            parameter_config=combo,
            expected_calibration_error=ece,
            maximum_calibration_error=mce,
            sharpness=sharpness,
            resolution=resolution,
            brier_score=brier,
            log_loss=log_loss,
            samples_evaluated=len(predictions),
            confidence_intervals=ci,
        )

    def _apply_min_scale(self, confidences: np.ndarray, min_scale: float) -> np.ndarray:
        """Apply min-scale transformation to confidences.

        Pushes confidences toward 0.5 by min_scale factor.
        """
        # Confidence toward 0.5
        scaled = 0.5 + (confidences - 0.5) * (1.0 - min_scale)
        # Clip to [0, 1]
        return np.clip(scaled, 0.0, 1.0)

    def _generate_synthetic_data(
        self,
        n_samples: int = 1024
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate synthetic calibration data.

        Returns:
            predictions, confidences, actuals
        """
        # Generate predictions (continuous values)
        predictions = self.rng.normal(0, 1, n_samples)

        # Generate confidences (uniform distribution)
        confidences = self.rng.uniform(0, 1, n_samples)

        # Generate actuals based on predictions + noise
        # This creates a realistic calibration scenario
        noise = self.rng.normal(0, 0.5, n_samples)
        actuals = (predictions + noise > 0).astype(float)

        return predictions, confidences, actuals

    def _compute_calibration_error(
        self,
        confidences: np.ndarray,
        actuals: np.ndarray,
        bin_edges: List[float]
    ) -> Tuple[float, float]:
        """Compute Expected Calibration Error (ECE) and Maximum Calibration Error (MCE).

        ECE = weighted average of |accuracy - confidence| per bin
        MCE = maximum |accuracy - confidence| across bins
        """
        n = len(confidences)
        ece = 0.0
        mce = 0.0

        for i in range(len(bin_edges) - 1):
            lower, upper = bin_edges[i], bin_edges[i + 1]
            mask = (confidences >= lower) & (confidences < upper)
            if i == len(bin_edges) - 2:  # Include right edge in last bin
                mask = (confidences >= lower) & (confidences <= upper)

            if np.sum(mask) == 0:
                continue

            bin_confidences = confidences[mask]
            bin_actuals = actuals[mask]

            avg_confidence = np.mean(bin_confidences)
            avg_accuracy = np.mean(bin_actuals)

            calibration_error = abs(avg_accuracy - avg_confidence)
            bin_weight = np.sum(mask) / n

            ece += bin_weight * calibration_error
            mce = max(mce, calibration_error)

        return ece, mce

    def _compute_sharpness(self, confidences: np.ndarray) -> float:
        """Compute sharpness (variance of confidences).

        Higher is better - means model is more decisive.
        """
        return float(np.var(confidences))

    def _compute_resolution(
        self,
        confidences: np.ndarray,
        actuals: np.ndarray,
        bin_edges: List[float]
    ) -> float:
        """Compute resolution (how well confidence discriminates).

        Higher is better - means different confidence levels have different accuracies.
        """
        bin_accuracies = []
        for i in range(len(bin_edges) - 1):
            lower, upper = bin_edges[i], bin_edges[i + 1]
            mask = (confidences >= lower) & (confidences < upper)
            if i == len(bin_edges) - 2:
                mask = (confidences >= lower) & (confidences <= upper)

            if np.sum(mask) > 0:
                bin_accuracies.append(np.mean(actuals[mask]))

        if len(bin_accuracies) < 2:
            return 0.0

        return float(np.var(bin_accuracies))

    def _compute_brier_score(self, confidences: np.ndarray, actuals: np.ndarray) -> float:
        """Compute Brier score (mean squared error of probabilities).

        Lower is better.
        """
        return float(np.mean((confidences - actuals) ** 2))

    def _compute_log_loss(self, confidences: np.ndarray, actuals: np.ndarray) -> float:
        """Compute log loss (cross-entropy).

        Lower is better.
        """
        eps = 1e-15
        confidences = np.clip(confidences, eps, 1 - eps)
        return float(-np.mean(actuals * np.log(confidences) + (1 - actuals) * np.log(1 - confidences)))

    def _bootstrap_confidence_intervals(
        self,
        confidences: np.ndarray,
        actuals: np.ndarray,
        bin_edges: List[float],
        n_samples: int = 100
    ) -> Dict[str, Tuple[float, float]]:
        """Compute bootstrap confidence intervals for metrics."""
        ece_samples = []
        brier_samples = []

        n = len(confidences)
        for _ in range(n_samples):
            indices = self.rng.choice(n, size=n, replace=True)
            boot_conf = confidences[indices]
            boot_actuals = actuals[indices]

            ece, _ = self._compute_calibration_error(boot_conf, boot_actuals, bin_edges)
            brier = self._compute_brier_score(boot_conf, boot_actuals)

            ece_samples.append(ece)
            brier_samples.append(brier)

        return {
            "ece": (float(np.percentile(ece_samples, 2.5)), float(np.percentile(ece_samples, 97.5))),
            "brier_score": (float(np.percentile(brier_samples, 2.5)), float(np.percentile(brier_samples, 97.5))),
        }

    def _analyze_sensitivity(
        self,
        metrics_list: List[CalibrationMetrics],
        config: CalibrationSweepConfig
    ) -> List[SensitivityAnalysis]:
        """Analyze parameter sensitivity.

        Measures how much metrics change when each parameter changes.
        """
        sensitivity_results = []

        # Analyze min_scale sensitivity
        min_scale_scores = self._compute_parameter_sensitivity(
            metrics_list, "min_scale", config.min_scale_values
        )
        sensitivity_results.append(min_scale_scores)

        # Analyze sample_window sensitivity
        window_scores = self._compute_parameter_sensitivity(
            metrics_list, "sample_window", config.sample_windows
        )
        sensitivity_results.append(window_scores)

        return sensitivity_results

    def _compute_parameter_sensitivity(
        self,
        metrics_list: List[CalibrationMetrics],
        parameter_name: str,
        parameter_values: List[float]
    ) -> SensitivityAnalysis:
        """Compute sensitivity for a single parameter."""
        # Group metrics by parameter value
        metrics_by_value = {}
        for value in parameter_values:
            metrics_by_value[value] = []

        for metrics in metrics_list:
            value = metrics.parameter_config[parameter_name]
            metrics_by_value[value].append(metrics.expected_calibration_error)

        # Compute average ECE for each value
        avg_ece_by_value = {
            value: np.mean(ece_list)
            for value, ece_list in metrics_by_value.items()
        }

        # Sensitivity = max change in ECE / change in parameter
        values = sorted(avg_ece_by_value.keys())
        ece_values = [avg_ece_by_value[v] for v in values]

        if len(values) < 2:
            return SensitivityAnalysis(
                parameter_name=parameter_name,
                sensitivity_score=0.0,
                optimal_range=(values[0], values[0]),
                robust=True,
            )

        # Compute sensitivity as max slope
        max_slope = 0.0
        for i in range(len(values) - 1):
            delta_param = values[i + 1] - values[i]
            delta_ece = abs(ece_values[i + 1] - ece_values[i])
            if delta_param > 0:
                slope = delta_ece / delta_param
                max_slope = max(max_slope, slope)

        # Find optimal range (values with lowest ECE)
        min_ece = min(ece_values)
        optimal_values = [v for v, ece in zip(values, ece_values) if ece <= min_ece * 1.05]  # Within 5% of best

        # Robust if sensitivity is low (slope < 0.1)
        robust = max_slope < 0.1

        return SensitivityAnalysis(
            parameter_name=parameter_name,
            sensitivity_score=max_slope,
            optimal_range=(min(optimal_values), max(optimal_values)),
            robust=bool(robust),
        )


def create_calibration_sweeper(seed: int = 42) -> CalibrationSweeper:
    """Factory function to create calibration sweeper."""
    return CalibrationSweeper(seed=seed)


def run_calibration_sweep(
    config: Optional[CalibrationSweepConfig] = None,
    output_dir: Optional[str] = None,
    seed: int = 42
) -> SweepResult:
    """Run calibration sweep with default or custom config.

    Args:
        config: Optional custom config
        output_dir: Optional output directory override
        seed: Random seed

    Returns:
        SweepResult
    """
    if config is None:
        config = CalibrationSweepConfig()

    if output_dir:
        config.output_dir = output_dir

    # Ensure output directory exists
    os.makedirs(config.output_dir, exist_ok=True)

    # Run sweep
    sweeper = create_calibration_sweeper(seed=seed)
    result = sweeper.run_sweep(config)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result.save(os.path.join(config.output_dir, f"sweep_result_{timestamp}.json"))
    result.save_summary_csv(os.path.join(config.output_dir, f"sweep_summary_{timestamp}.csv"))

    return result


if __name__ == "__main__":
    # Run sweep with defaults
    logging.basicConfig(level=logging.INFO)
    result = run_calibration_sweep()
    print(f"Best ECE: {result.best_metrics.expected_calibration_error:.4f}")
    print(f"Best parameters: {result.best_parameters}")
