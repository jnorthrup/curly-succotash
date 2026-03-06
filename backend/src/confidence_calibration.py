"""
Confidence Calibration

Calibrates model confidence scores using reliability diagrams,
isotonic regression, and Platt scaling. Provides metrics like
Expected Calibration Error (ECE), sharpness, and resolution.

Key Features:
- Reliability diagram generation
- Isotonic regression calibration
- Platt scaling calibration  
- ECE/MCE computation
- Confidence correction mapping

Example:
    calibrator = ConfidenceCalibrator(method='isotonic')
    calibrator.fit(confidences, actuals)
    calibrated = calibrator.calibrate(raw_confidence=0.75)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

import numpy as np
from scipy import stats
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from .models import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class ReliabilityDiagram:
    """Reliability diagram data for visualization."""
    confidence_bins: List[float]  # Bin centers
    actual_accuracies: List[float]
    counts_per_bin: List[int]
    perfect_calibration: List[float]  # Diagonal reference

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "confidence_bins": self.confidence_bins,
            "actual_accuracies": self.actual_accuracies,
            "counts_per_bin": self.counts_per_bin,
            "perfect_calibration": self.perfect_calibration,
        }


@dataclass
class ConfidenceCalibrationResult:
    """Results from confidence calibration."""
    # Reliability diagram
    diagram: ReliabilityDiagram
    
    # Metrics
    calibration_error_before: float  # ECE before calibration
    calibration_error_after: float  # ECE after calibration
    sharpness: float
    resolution: float
    brier_score_before: float
    brier_score_after: float
    
    # Calibration mapping
    method: str
    mapping_params: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "diagram": self.diagram.to_dict(),
            "ece_before": self.calibration_error_before,
            "ece_after": self.calibration_error_after,
            "sharpness": self.sharpness,
            "resolution": self.resolution,
            "brier_score_before": self.brier_score_before,
            "brier_score_after": self.brier_score_after,
            "method": self.method,
            "mapping_params": self.mapping_params,
        }

    def save(self, filepath: str) -> None:
        """Save results to JSON."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[CONF_CAL] Results saved to {filepath}")


class ConfidenceCalibrator:
    """Calibrate model confidence scores.

    Methods:
    - isotonic: Isotonic regression (non-parametric, flexible)
    - platt: Platt scaling (logistic regression)
    - histogram: Histogram binning (simple averaging)

    Example:
        calibrator = ConfidenceCalibrator(method='isotonic')
        calibrator.fit(confidences, actuals)
        calibrated = calibrator.calibrate(0.75)
    """

    def __init__(self, method: str = 'isotonic', n_bins: int = 10):
        """Initialize calibrator.

        Args:
            method: Calibration method ('isotonic', 'platt', 'histogram')
            n_bins: Number of bins for histogram method
        """
        if method not in ['isotonic', 'platt', 'histogram']:
            raise ValueError(f"Unknown method: {method}")

        self.method = method
        self.n_bins = n_bins
        self._fitted = False

        # Calibration models
        self._isotonic_model: Optional[IsotonicRegression] = None
        self._platt_model: Optional[LogisticRegression] = None
        self._histogram_mapping: Optional[Dict[int, float]] = None

        # Training data
        self._train_confidences: Optional[np.ndarray] = None
        self._train_actuals: Optional[np.ndarray] = None

    def fit(self, confidences: np.ndarray, actuals: np.ndarray) -> 'ConfidenceCalibrator':
        """Fit calibration model.

        Args:
            confidences: Raw confidence scores (0.0-1.0)
            actuals: Binary outcomes (0 or 1)
        """
        confidences = np.asarray(confidences)
        actuals = np.asarray(actuals)

        if len(confidences) != len(actuals):
            raise ValueError("confidences and actuals must have same length")

        if len(confidences) < 10:
            raise ValueError("Need at least 10 samples for calibration")

        self._train_confidences = confidences
        self._train_actuals = actuals

        if self.method == 'isotonic':
            self._fit_isotonic(confidences, actuals)
        elif self.method == 'platt':
            self._fit_platt(confidences, actuals)
        elif self.method == 'histogram':
            self._fit_histogram(confidences, actuals)

        self._fitted = True
        logger.info(f"[CONF_CAL] Fitted {self.method} calibrator with {len(confidences)} samples")
        return self

    def _fit_isotonic(self, confidences: np.ndarray, actuals: np.ndarray) -> None:
        """Fit isotonic regression model."""
        model = IsotonicRegression(out_of_bounds='clip')
        model.fit(confidences, actuals)
        self._isotonic_model = model

    def _fit_platt(self, confidences: np.ndarray, actuals: np.ndarray) -> None:
        """Fit Platt scaling (logistic regression)."""
        # Reshape for sklearn
        X = confidences.reshape(-1, 1)
        model = LogisticRegression()
        model.fit(X, actuals)
        self._platt_model = model

    def _fit_histogram(self, confidences: np.ndarray, actuals: np.ndarray) -> None:
        """Fit histogram binning."""
        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        mapping = {}

        for i in range(self.n_bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if i == self.n_bins - 1:  # Include right edge in last bin
                mask = (confidences >= bin_edges[i]) & (confidences <= bin_edges[i + 1])

            if np.sum(mask) > 0:
                mapping[i] = float(np.mean(actuals[mask]))
            else:
                mapping[i] = (bin_edges[i] + bin_edges[i + 1]) / 2  # Use bin center

        self._histogram_mapping = mapping

    def calibrate(self, confidence: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Apply calibration to confidence scores.

        Args:
            confidence: Raw confidence score(s)

        Returns:
            Calibrated confidence score(s)
        """
        if not self._fitted:
            raise RuntimeError("Calibrator not fitted. Call fit() first.")

        if isinstance(confidence, (list, np.ndarray)):
            return self._calibrate_array(np.asarray(confidence))
        else:
            return float(self._calibrate_single(float(confidence)))

    def _calibrate_single(self, confidence: float) -> float:
        """Calibrate a single confidence value."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {confidence}")

        if self.method == 'isotonic' and self._isotonic_model:
            return float(self._isotonic_model.predict([confidence])[0])
        elif self.method == 'platt' and self._platt_model:
            return float(self._platt_model.predict_proba([[confidence]])[0, 1])
        elif self.method == 'histogram' and self._histogram_mapping:
            bin_idx = min(int(confidence * self.n_bins), self.n_bins - 1)
            return self._histogram_mapping.get(bin_idx, confidence)
        else:
            return confidence  # Fallback

    def _calibrate_array(self, confidences: np.ndarray) -> np.ndarray:
        """Calibrate an array of confidence values."""
        return np.array([self._calibrate_single(c) for c in confidences])

    def get_reliability_diagram(
        self,
        confidences: Optional[np.ndarray] = None,
        actuals: Optional[np.ndarray] = None,
        n_bins: int = 10
    ) -> ReliabilityDiagram:
        """Generate reliability diagram data.

        Args:
            confidences: Confidence scores (uses training data if None)
            actuals: Actual outcomes (uses training data if None)
            n_bins: Number of bins

        Returns:
            ReliabilityDiagram data
        """
        if confidences is None or actuals is None:
            if self._train_confidences is None or self._train_actuals is None:
                raise ValueError("No data provided and no training data available")
            confidences = self._train_confidences
            actuals = self._train_actuals

        confidences = np.asarray(confidences)
        actuals = np.asarray(actuals)

        bin_edges = np.linspace(0, 1, n_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        accuracies = []
        counts = []

        for i in range(n_bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if i == n_bins - 1:
                mask = (confidences >= bin_edges[i]) & (confidences <= bin_edges[i + 1])

            count = np.sum(mask)
            counts.append(int(count))

            if count > 0:
                accuracies.append(float(np.mean(actuals[mask])))
            else:
                accuracies.append(0.0)

        return ReliabilityDiagram(
            confidence_bins=bin_centers.tolist(),
            actual_accuracies=accuracies,
            counts_per_bin=counts,
            perfect_calibration=bin_centers.tolist(),  # Diagonal
        )

    def compute_ece(
        self,
        confidences: np.ndarray,
        actuals: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """Compute Expected Calibration Error."""
        confidences = np.asarray(confidences)
        actuals = np.asarray(actuals)

        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        n = len(confidences)

        for i in range(n_bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if i == n_bins - 1:
                mask = (confidences >= bin_edges[i]) & (confidences <= bin_edges[i + 1])

            if np.sum(mask) == 0:
                continue

            bin_conf = np.mean(confidences[mask])
            bin_acc = np.mean(actuals[mask])
            bin_weight = np.sum(mask) / n

            ece += bin_weight * abs(bin_acc - bin_conf)

        return float(ece)

    def compute_sharpness(self, confidences: np.ndarray) -> float:
        """Compute sharpness (variance of confidences)."""
        return float(np.var(confidences))

    def compute_resolution(
        self,
        confidences: np.ndarray,
        actuals: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """Compute resolution (variance of bin accuracies)."""
        bin_edges = np.linspace(0, 1, n_bins + 1)
        bin_accuracies = []

        for i in range(n_bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if i == n_bins - 1:
                mask = (confidences >= bin_edges[i]) & (confidences <= bin_edges[i + 1])

            if np.sum(mask) > 0:
                bin_accuracies.append(np.mean(actuals[mask]))

        if len(bin_accuracies) < 2:
            return 0.0

        return float(np.var(bin_accuracies))

    def compute_brier_score(self, confidences: np.ndarray, actuals: np.ndarray) -> float:
        """Compute Brier score (MSE of probabilities)."""
        return float(np.mean((confidences - actuals) ** 2))

    def get_calibration_result(self) -> Optional[ConfidenceCalibrationResult]:
        """Get comprehensive calibration results."""
        if not self._fitted or self._train_confidences is None:
            return None

        confidences = self._train_confidences
        actuals = self._train_actuals

        # Metrics before calibration
        ece_before = self.compute_ece(confidences, actuals)
        brier_before = self.compute_brier_score(confidences, actuals)

        # Calibrate
        calibrated = self.calibrate(confidences)

        # Metrics after calibration
        ece_after = self.compute_ece(np.array(calibrated), actuals)
        brier_after = self.compute_brier_score(np.array(calibrated), actuals)

        # Get diagram
        diagram = self.get_reliability_diagram()

        # Compute sharpness and resolution
        sharpness = self.compute_sharpness(confidences)
        resolution = self.compute_resolution(confidences, actuals)

        # Get mapping params
        params = {}
        if self.method == 'isotonic' and self._isotonic_model:
            params = {"x_thresholds": self._isotonic_model.X_thresholds_.tolist()}
        elif self.method == 'platt' and self._platt_model:
            params = {
                "coefficients": self._platt_model.coef_.tolist(),
                "intercept": self._platt_model.intercept_.tolist()
            }

        return ConfidenceCalibrationResult(
            diagram=diagram,
            calibration_error_before=ece_before,
            calibration_error_after=ece_after,
            sharpness=sharpness,
            resolution=resolution,
            brier_score_before=brier_before,
            brier_score_after=brier_after,
            method=self.method,
            mapping_params=params,
        )


def create_confidence_calibrator(
    method: str = 'isotonic',
    n_bins: int = 10
) -> ConfidenceCalibrator:
    """Factory function to create calibrator."""
    return ConfidenceCalibrator(method=method, n_bins=n_bins)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Generate synthetic data
    np.random.seed(42)
    n_samples = 1000

    # Overconfident predictions
    confidences = np.random.beta(2, 0.5, n_samples)  # Skewed toward 1.0
    actuals = np.random.binomial(1, confidences * 0.8)  # Actually less accurate

    # Calibrate
    calibrator = ConfidenceCalibrator(method='isotonic')
    calibrator.fit(confidences, actuals)

    # Get results
    result = calibrator.get_calibration_result()
    if result:
        print(f"ECE before: {result.calibration_error_before:.4f}")
        print(f"ECE after: {result.calibration_error_after:.4f}")
        print(f"Sharpness: {result.sharpness:.4f}")
        print(f"Resolution: {result.resolution:.4f}")

        # Test calibration
        raw_conf = 0.85
        calibrated = calibrator.calibrate(raw_conf)
        print(f"\nRaw confidence: {raw_conf:.2f} -> Calibrated: {calibrated:.2f}")
