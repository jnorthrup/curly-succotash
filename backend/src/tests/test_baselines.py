"""Unit tests for backend/src/baselines.py"""
import numpy as np
import pytest

from backend.src.baselines import persistence_baseline, ema_baseline, linear_baseline


class TestPersistenceBaseline:
    """Tests for persistence_baseline (identity function)."""
    
    def test_output_equals_input_values_and_shape(self):
        """persistence_baseline: output equals input (same values, same shape)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = persistence_baseline(x)
        
        assert result.shape == x.shape
        np.testing.assert_array_equal(result, x)
    
    def test_2d_array(self):
        """Test with 2D array."""
        x = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        result = persistence_baseline(x)
        
        assert result.shape == x.shape
        np.testing.assert_array_equal(result, x)


class TestEmaBaseline:
    """Tests for ema_baseline (exponential moving average)."""
    
    def test_alpha_equals_one_collapses_to_identity(self):
        """ema_baseline with alpha=1.0: each output[i] == input[i] (collapses to identity)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ema_baseline(x, alpha=1.0)
        
        # With alpha=1.0, ema[i] = 1.0 * x[i] + 0.0 * ema[i-1] = x[i]
        np.testing.assert_array_equal(result.flatten(), x)
    
    def test_alpha_half_constant_array_converges(self):
        """ema_baseline with alpha=0.5 on a constant array: output converges toward that constant."""
        x = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
        result = ema_baseline(x, alpha=0.5)
        
        # All values should equal the constant
        np.testing.assert_array_equal(result.flatten(), x)
    
    def test_1d_input_produces_2d_output(self):
        """ema_baseline with 1D input: output shape is (n, 1) not (n,) — check it runs without error."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ema_baseline(x)
        
        # Should be (n, 1) not (n,)
        assert result.shape == (5, 1)
    
    def test_ema_values_correctly_computed(self):
        """Verify EMA computation is correct."""
        x = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
        result = ema_baseline(x, alpha=0.5)
        
        # ema[0] = 1.0
        # ema[1] = 0.5 * 3.0 + 0.5 * 1.0 = 2.0
        # ema[2] = 0.5 * 5.0 + 0.5 * 2.0 = 3.5
        # ema[3] = 0.5 * 7.0 + 0.5 * 3.5 = 5.25
        # ema[4] = 0.5 * 9.0 + 0.5 * 5.25 = 7.125
        expected = np.array([[1.0], [2.0], [3.5], [5.25], [7.125]])
        np.testing.assert_array_almost_equal(result, expected)


class TestLinearBaseline:
    """Tests for linear_baseline (OLS sliding window linear projection)."""
    
    def test_early_samples_identity_fallback(self):
        """linear_baseline early samples (i < window): output[0] equals input[0] (identity fallback)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        window = 5
        result = linear_baseline(x, window=window)
        
        # For i < window, should return identity
        np.testing.assert_array_equal(result[:window].flatten(), x[:window])
    
    def test_perfect_linear_sequence_prediction(self):
        """linear_baseline on a perfect linear sequence: for i >= window the predicted value should be close to the true linear extrapolation."""
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
        window = 5
        result = linear_baseline(x, window=window)
        
        # For a perfect linear sequence y = t (slope=1, intercept=0),
        # the prediction at i=5 should be 5.0, at i=6 should be 6.0, etc.
        # The prediction uses t=window as the next step
        for i in range(window, len(x)):
            # The prediction should be very close to the true value
            np.testing.assert_almost_equal(result[i, 0], x[i], decimal=5)
    
    def test_2d_input_same_shape_output(self):
        """linear_baseline with 2D input: output has same shape as input."""
        x = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0], [5.0, 6.0], [6.0, 7.0]])
        window = 3
        result = linear_baseline(x, window=window)
        
        # Output should have same shape as input
        assert result.shape == x.shape
    
    def test_2d_input_early_samples_identity(self):
        """For 2D input, early samples (i < window) should also use identity fallback."""
        x = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0], [5.0, 6.0], [7.0, 8.0]])
        window = 3
        result = linear_baseline(x, window=window)
        
        # For i < window, should return identity
        np.testing.assert_array_equal(result[:window], x[:window])
    
    def test_1d_input_produces_2d_output(self):
        """linear_baseline with 1D input: output shape is (n, 1) not (n,)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = linear_baseline(x, window=5)
        
        # Should be (n, 1) not (n,)
        assert result.shape == (10, 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
