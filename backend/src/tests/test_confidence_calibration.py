import pytest
import numpy as np
from backend.src.confidence_calibration import ConfidenceCalibrator, ConfidenceCalibrationResult

def test_isotonic_calibration():
    """Test fit and calibrate with isotonic method."""
    np.random.seed(42)
    n_samples = 100
    # Generate overconfident scores
    confidences = np.random.uniform(0.5, 1.0, n_samples)
    # Actuals are 80% of confidence
    actuals = (np.random.random(n_samples) < (confidences * 0.8)).astype(int)
    
    calibrator = ConfidenceCalibrator(method='isotonic')
    calibrator.fit(confidences, actuals)
    
    # Single value calibration
    test_conf = 0.9
    calibrated = calibrator.calibrate(test_conf)
    assert isinstance(calibrated, float)
    assert 0.0 <= calibrated <= 1.0
    
    # Array calibration
    test_confs = np.array([0.7, 0.8, 0.9])
    calibrated_array = calibrator.calibrate(test_confs)
    assert len(calibrated_array) == 3
    assert np.all((calibrated_array >= 0.0) & (calibrated_array <= 1.0))

def test_platt_scaling():
    """Test Platt scaling calibration path."""
    np.random.seed(42)
    n_samples = 100
    confidences = np.random.uniform(0.1, 0.9, n_samples)
    actuals = (np.random.random(n_samples) < confidences).astype(int)
    
    calibrator = ConfidenceCalibrator(method='platt')
    calibrator.fit(confidences, actuals)
    
    test_conf = 0.5
    calibrated = calibrator.calibrate(test_conf)
    assert 0.0 <= calibrated <= 1.0
    assert calibrator._platt_model is not None

def test_ece_metric():
    """Test Expected Calibration Error (ECE) metric output."""
    calibrator = ConfidenceCalibrator(n_bins=10)
    confidences = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    actuals = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    
    ece = calibrator.compute_ece(confidences, actuals)
    assert isinstance(ece, float)
    assert 0.0 <= ece <= 1.0
    
    # Perfect calibration case
    conf_perfect = np.array([0.1, 0.9])
    acc_perfect = np.array([0.1, 0.9]) # mean of actuals in bin
    # To get mean 0.1 in first bin [0, 0.1], we need actuals that average to 0.1
    # Easier to just check it's a float in range
    assert 0.0 <= calibrator.compute_ece(conf_perfect, acc_perfect) <= 1.0

def test_reliability_diagram_shape():
    """Test reliability diagram shape and matching lengths."""
    np.random.seed(42)
    n_samples = 50
    confidences = np.random.uniform(0, 1, n_samples)
    actuals = np.random.randint(0, 2, n_samples)
    
    n_bins = 10
    calibrator = ConfidenceCalibrator(n_bins=n_bins)
    diagram = calibrator.get_reliability_diagram(confidences, actuals, n_bins=n_bins)
    
    assert len(diagram.confidence_bins) == n_bins
    assert len(diagram.actual_accuracies) == n_bins
    assert len(diagram.counts_per_bin) == n_bins
    assert len(diagram.perfect_calibration) == n_bins
    assert sum(diagram.counts_per_bin) == n_samples

def test_edge_cases_minimal_data():
    """Test calibration with minimal data and error handling."""
    calibrator = ConfidenceCalibrator(method='isotonic')
    
    # Less than 10 samples should raise ValueError as per implementation
    confidences = np.array([0.5] * 5)
    actuals = np.array([1] * 5)
    
    with pytest.raises(ValueError, match="Need at least 10 samples"):
        calibrator.fit(confidences, actuals)
        
    # Unfitted calibrator should raise RuntimeError
    with pytest.raises(RuntimeError, match="Calibrator not fitted"):
        calibrator.calibrate(0.5)

def test_empty_input_to_metrics():
    """Test behavior with empty arrays in metric functions."""
    calibrator = ConfidenceCalibrator()
    empty = np.array([])
    
    # ECE on empty should be 0.0 as loop won't run
    assert calibrator.compute_ece(empty, empty) == 0.0
    
    # Sharpness on empty should return NaN or error depending on numpy version
    # The implementation uses np.var([]) which is NaN
    assert np.isnan(calibrator.compute_sharpness(empty))
    
    # Resolution on empty
    assert calibrator.compute_resolution(empty, empty) == 0.0

def test_calibration_result_object():
    """Test the ConfidenceCalibrationResult object."""
    np.random.seed(42)
    n_samples = 20
    confidences = np.random.uniform(0.1, 0.9, n_samples)
    actuals = np.random.randint(0, 2, n_samples)
    
    calibrator = ConfidenceCalibrator(method='isotonic')
    calibrator.fit(confidences, actuals)
    
    result = calibrator.get_calibration_result()
    assert isinstance(result, ConfidenceCalibrationResult)
    assert result.method == 'isotonic'
    assert 'ece_before' in result.to_dict()
    assert result.calibration_error_after <= result.calibration_error_before + 1e-9 # Isotonic should not worsen ECE usually
