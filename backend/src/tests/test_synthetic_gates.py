import numpy as np
import pytest

from backend.src.synthetic_gates import (
    IdentityGate,
    SineGate,
    AmplitudeSineGate,
    FrequencySineGate,
    PhaseSineGate,
    NoisySineGate,
    MultiHorizonGate,
    MaskedReconstructionGate,
    RegimeShiftGate,
    PersistenceBaseline,
    CompetencyEvaluator
)

def test_persistence_baseline():
    baseline = PersistenceBaseline()
    x = np.array([[1.0], [2.0], [3.0]])
    y_pred = baseline(x)
    assert np.array_equal(x, y_pred)

def test_identity_gate():
    gate = IdentityGate(threshold=1e-5)
    def perfect_predictor(x):
        return x

    result = gate.evaluate(perfect_predictor, samples=100)
    assert result.success is True
    assert result.mae < 1e-5
    assert result.metadata["metric_used"] == "mae"

def test_identity_gate_failure():
    gate = IdentityGate(threshold=1e-5)
    def bad_predictor(x):
        return x + 0.1

    result = gate.evaluate(bad_predictor, samples=100)
    assert result.success is False

def test_sine_gate():
    gate = SineGate(threshold=0.01)

    # We can fake a predictor that just knows the answer
    # but the simplest test is just to check data generation shapes
    x, y = gate.generate_data(samples=100)
    assert x.shape == (100, 1)
    assert y.shape == (100, 1)

def test_amplitude_sine_gate():
    gate = AmplitudeSineGate(amplitude=5.0)
    x, y = gate.generate_data(samples=100)
    assert np.max(np.abs(x)) <= 5.0
    assert np.max(np.abs(x)) > 4.0

def test_frequency_sine_gate():
    gate = FrequencySineGate(frequency=0.5)
    x, y = gate.generate_data(samples=100)
    assert x.shape == (100, 1)

def test_phase_sine_gate():
    gate = PhaseSineGate(phase=np.pi)
    x, y = gate.generate_data(samples=100)
    assert x.shape == (100, 1)

def test_noisy_sine_gate():
    gate = NoisySineGate(noise_std=0.1)
    x, y = gate.generate_data(samples=100)
    # x should have noise, y should be clean
    assert not np.array_equal(x, y)
    assert x.shape == (100, 1)
    assert y.shape == (100, 1)

def test_multi_horizon_gate():
    gate = MultiHorizonGate(horizon=5, threshold=0.05)
    x, y = gate.generate_data(samples=100)
    assert x.shape == (100, 1)
    assert y.shape == (100, 1)

def test_masked_reconstruction_gate():
    gate = MaskedReconstructionGate(threshold=0.02)
    x, y = gate.generate_data(samples=100)
    # x has 3 features, y is the recovered feature
    assert x.shape == (100, 3)
    assert y.shape == (100, 1)
    # the second column of x should be masked (zeros)
    assert np.all(x[:, 1] == 0)

def test_competency_evaluator():
    evaluator = CompetencyEvaluator()

    def dummy_predictor(x):
        # A predictor that just returns zeros for shapes that match y_true
        if x.shape[1] == 3:
            return np.zeros((x.shape[0], 1))
        return np.zeros((x.shape[0], 1))

    results = evaluator.run_all(dummy_predictor)
    assert len(results) == 10

    report = evaluator.generate_report()
    assert "all_passed" in report
    assert report["all_passed"] is False
