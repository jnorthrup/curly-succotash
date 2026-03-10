"""
HRM Synthetic Gates - Competency and Falsification Framework

This module implements synthetic tasks used to validate HRM model competency
before promotion. These gates test basic capabilities like identity mapping,
pattern recognition (sine), and multi-horizon prediction on noise-free data.
"""

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of a synthetic gate evaluation."""
    gate_name: str
    success: bool
    mse: float
    mae: float
    correlation: float
    samples: int
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "success": self.success,
            "mse": float(self.mse),
            "mae": float(self.mae),
            "correlation": float(self.correlation),
            "samples": self.samples,
            "failure_reason": self.failure_reason,
            "metadata": self.metadata,
        }


class SyntheticAgent(ABC):
    """Base class for synthetic baseline agents."""

    @abstractmethod
    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Predict output given input data."""
        pass


class PersistenceBaseline(SyntheticAgent):
    """
    Baseline agent that always predicts the last input value (Persistence).
    """

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return x.copy()


class SyntheticGate(ABC):
    """Base class for synthetic competency gates."""

    def __init__(self, name: str, threshold: float = 0.01, metric: str = "mse"):
        self.name = name
        self.threshold = threshold
        self.metric = metric

    @abstractmethod
    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """Generate (input, target) data for this gate."""
        pass

    def evaluate(
        self,
        predictor: Callable[[np.ndarray], np.ndarray],
        samples: int = 1000
    ) -> GateResult:
        """Evaluate a predictor against this gate."""
        x, y_true = self.generate_data(samples)
        y_pred = predictor(x)

        mse = np.mean((y_true - y_pred)**2)
        mae = np.mean(np.abs(y_true - y_pred))

        from .baselines import persistence_baseline, ema_baseline, linear_baseline
        y_pers = persistence_baseline(x)
        y_ema = ema_baseline(x)
        y_lin = linear_baseline(x)

        def safe_mse(y_b):
            if y_b.shape == y_true.shape:
                return np.mean((y_true - y_b)**2)
            # Naive fallback if shapes don't match
            if y_b.shape[0] == y_true.shape[0]:
                return np.mean((y_true - y_b[:, :y_true.shape[1]])**2)
            return float('inf')

        def safe_mae(y_b):
            if y_b.shape == y_true.shape:
                return np.mean(np.abs(y_true - y_b))
            # Naive fallback if shapes don't match
            if y_b.shape[0] == y_true.shape[0]:
                return np.mean(np.abs(y_true - y_b[:, :y_true.shape[1]]))
            return float('inf')

        mse_pers = safe_mse(y_pers)
        mse_ema = safe_mse(y_ema)
        mse_lin = safe_mse(y_lin)

        mae_pers = safe_mae(y_pers)
        mae_ema = safe_mae(y_ema)
        mae_lin = safe_mae(y_lin)

        # Calculate correlation
        if np.std(y_true) > 0 and np.std(y_pred) > 0:
            correlation = np.corrcoef(y_true.flatten(), y_pred.flatten())[0, 1]
        else:
            correlation = 0.0

        if self.metric == "mae":
            primary_val = mae
            primary_pers = mae_pers
            primary_ema = mae_ema
            primary_lin = mae_lin
        else:
            primary_val = mse
            primary_pers = mse_pers
            primary_ema = mse_ema
            primary_lin = mse_lin

        beats_baselines = primary_val <= primary_pers and primary_val <= primary_ema and primary_val <= primary_lin

        success = bool(primary_val < self.threshold and beats_baselines)
        failure_reason = None
        if not success:
            if primary_val >= self.threshold:
                failure_reason = f"{self.metric.upper()} {primary_val:.6f} exceeds threshold {self.threshold:.6f}"
            else:
                failure_reason = f"Failed to beat baselines. {self.metric.upper()}={primary_val:.6f}, Pers={primary_pers:.6f}, EMA={primary_ema:.6f}, Lin={primary_lin:.6f}"

        return GateResult(
            gate_name=self.name,
            success=success,
            mse=mse,
            mae=mae,
            correlation=correlation,
            samples=samples,
            failure_reason=failure_reason,
            metadata={
                "mse_pers": float(mse_pers),
                "mse_ema": float(mse_ema),
                "mse_lin": float(mse_lin),
                "mae_pers": float(mae_pers),
                "mae_ema": float(mae_ema),
                "mae_lin": float(mae_lin),
                "metric_used": self.metric
            }
        )


class IdentityGate(SyntheticGate):
    """
    Identity synthetic gate.
    The model must output the exact same value as the input.
    Tests basic signal propagation and convergence near zero.
    """

    def __init__(self, threshold: float = 1e-5):
        super().__init__("identity", threshold, metric="mae")

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        x = np.random.uniform(-1, 1, (samples, 1))
        return x, x


class SineGate(SyntheticGate):
    """
    Standard sine wave synthetic gate.
    The model must predict the next value in a sine wave.
    Tests pattern recognition, frequency, and phase tracking.
    """

    def __init__(self, threshold: float = 0.01):
        super().__init__("sine", threshold)

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 4 * np.pi, samples + 1)
        data = np.sin(t)
        x = data[:-1].reshape(-1, 1)
        y = data[1:].reshape(-1, 1)
        return x, y


class AmplitudeSineGate(SyntheticGate):
    """
    Sine gate with varying amplitude.
    Tests if the model can handle signals with different scales.
    """

    def __init__(self, amplitude: float = 2.0, threshold: float = 0.02):
        super().__init__(f"sine_amplitude_{amplitude}", threshold)
        self.amplitude = amplitude

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 4 * np.pi, samples + 1)
        data = self.amplitude * np.sin(t)
        x = data[:-1].reshape(-1, 1)
        y = data[1:].reshape(-1, 1)
        return x, y


class FrequencySineGate(SyntheticGate):
    """
    Sine gate with varying frequency.
    Tests if the model can adapt to faster or slower oscillations.
    """

    def __init__(self, frequency: float = 2.0, threshold: float = 0.05):
        super().__init__(f"sine_frequency_{frequency}", threshold)
        self.frequency = frequency

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 4 * np.pi * self.frequency, samples + 1)
        data = np.sin(t)
        x = data[:-1].reshape(-1, 1)
        y = data[1:].reshape(-1, 1)
        return x, y


class PhaseSineGate(SyntheticGate):
    """
    Sine gate with a phase shift.
    Tests if the model can handle shifted starting points.
    """

    def __init__(self, phase: float = math.pi / 2, threshold: float = 0.01):
        super().__init__("sine_phase_shift", threshold)
        self.phase = phase

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 4 * np.pi, samples + 1)
        data = np.sin(t + self.phase)
        x = data[:-1].reshape(-1, 1)
        y = data[1:].reshape(-1, 1)
        return x, y


class NoisySineGate(SyntheticGate):
    """
    Sine gate with added Gaussian noise.
    Tests model robustness to imperfect signals.
    """

    def __init__(self, noise_std: float = 0.05, threshold: float = 0.1):
        super().__init__("sine_noisy", threshold)
        self.noise_std = noise_std

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 4 * np.pi, samples + 1)
        signal = np.sin(t)
        noise = np.random.normal(0, self.noise_std, samples + 1)
        data = signal + noise
        x = data[:-1].reshape(-1, 1)
        y = signal[1:].reshape(-1, 1)  # Target is the clean signal
        return x, y


class MultiHorizonGate(SyntheticGate):
    """
    Multi-horizon prediction gate.
    The model must predict multiple future steps.
    """

    def __init__(self, horizon: int = 5, threshold: float = 0.05):
        super().__init__(f"feature+{horizon}", threshold)
        self.horizon = horizon

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, 10 * np.pi, samples + self.horizon)
        data = np.sin(t) + 0.5 * np.sin(2.5 * t) # Multi-frequency

        x = []
        y = []
        for i in range(samples):
            x.append(data[i])
            y.append(data[i + self.horizon])

        return np.array(x).reshape(-1, 1), np.array(y).reshape(-1, 1)


class MaskedReconstructionGate(SyntheticGate):
    """
    Masked reconstruction gate.
    The model must recover missing (masked) features.
    """

    def __init__(self, threshold: float = 0.02):
        super().__init__("masked_reconstruction", threshold)

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        # Generate 3 correlated features
        t = np.linspace(0, 10, samples)
        f1 = np.sin(t)
        f2 = np.cos(t)
        f3 = f1 + f2

        data = np.stack([f1, f2, f3], axis=1)

        # Mask f2 (set to 0)
        x = data.copy()
        x[:, 1] = 0

        # Target is the original f2
        y = data[:, 1].reshape(-1, 1)

        return x, y


class RegimeShiftGate(SyntheticGate):
    """
    Shock and regime-shift synthetic task.
    Tests adaptation to sudden changes in signal distribution.
    """

    def __init__(self, threshold: float = 0.1):
        super().__init__("regime_shift", threshold)

    def generate_data(self, samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        mid = samples // 2

        # Regime 1: Low freq sine
        t1 = np.linspace(0, 5 * np.pi, mid)
        y1 = np.sin(t1)

        # Regime 2: High freq square-ish wave
        t2 = np.linspace(0, 20 * np.pi, samples - mid)
        y2 = np.sign(np.sin(t2)) * 0.5

        data = np.concatenate([y1, y2])

        x = data[:-1].reshape(-1, 1)
        y = data[1:].reshape(-1, 1)

        return x, y


class CompetencyEvaluator:
    """
    Orchestrates HRM competency evaluation across multiple gates.
    """

    def __init__(self):
        self.gates = [
            IdentityGate(),
            SineGate(),
            AmplitudeSineGate(),
            FrequencySineGate(),
            PhaseSineGate(),
            NoisySineGate(),
            MultiHorizonGate(horizon=1),
            MultiHorizonGate(horizon=5),
            MaskedReconstructionGate(),
            RegimeShiftGate()
        ]
        self.results: List[GateResult] = []

    def run_all(self, predictor: Callable[[np.ndarray], np.ndarray]) -> List[GateResult]:
        """Run all synthetic gates against the predictor."""
        self.results = []
        for gate in self.gates:
            logger.info(f"[GATE] Evaluating {gate.name}...")
            result = gate.evaluate(predictor)
            self.results.append(result)
            status = "PASS" if result.success else "FAIL"
            logger.info(f"[GATE] {gate.name}: {status} (MSE: {result.mse:.6f})")

        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """Generate a summary report of all gate results."""
        if not self.results:
            return {"status": "NO_RESULTS"}

        all_passed = all(r.success for r in self.results)

        # Record explicit failure outcomes
        failure_outcomes = []
        if not all_passed:
            for r in self.results:
                if not r.success:
                    if "identity" in r.gate_name:
                        failure_outcomes.append("FAIL_ARCH")
                    elif "feature" in r.gate_name:
                        failure_outcomes.append("FAIL_SCALE")
                    elif "regime" in r.gate_name:
                        failure_outcomes.append("FAIL_TRANSFER")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "all_passed": all_passed,
            "passed_count": sum(1 for r in self.results if r.success),
            "total_count": len(self.results),
            "failure_outcomes": list(set(failure_outcomes)),
            "results": [r.to_dict() for r in self.results]
        }

    def save_report(self, path: str) -> None:
        """Save report to JSON file."""
        report = self.generate_report()
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"[GATE] Competency report saved to {path}")


def run_competency_check(
    predictor: Callable[[np.ndarray], np.ndarray],
    output_path: Optional[str] = None
) -> bool:
    """
    Convenience function to run full competency suite.
    """
    evaluator = CompetencyEvaluator()
    evaluator.run_all(predictor)

    if output_path:
        evaluator.save_report(output_path)

    return all(r.success for r in evaluator.results)
