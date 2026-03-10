import unittest
from unittest.mock import MagicMock, patch, CallableMixin
import numpy as np
import logging

from backend.src.synthetic_gates import PersistenceBaseline, IdentityGate, CompetencyEvaluator, GateResult
from backend.src.simulator import CoinbaseTradingSimulator

class TestSyntheticValidation(unittest.TestCase):
    
    def test_persistence_baseline(self):
        """Verify it returns exactly the input array."""
        baseline = PersistenceBaseline()
        x = np.random.uniform(-1, 1, (10, 5))
        y = baseline(x)
        
        np.testing.assert_array_equal(x, y)
        self.assertIsNot(x, y)  # Ensure it's a copy

    def test_identity_gate(self):
        """Verify IdentityGate properties and evaluation logic."""
        gate = IdentityGate(threshold=1e-5)
        
        # Verify it has metric='mae'
        self.assertEqual(gate.metric, 'mae')
        self.assertEqual(gate.name, 'identity')
        
        # Verify it succeeds for a perfect predictor (identity function)
        def perfect_predictor(x):
            return x.copy()
            
        result = gate.evaluate(perfect_predictor, samples=100)
        self.assertTrue(result.success)
        self.assertLess(result.mae, 1e-5)
        self.assertEqual(result.mae, 0.0)
        
        # Verify it fails for a predictor that adds significant noise
        def noisy_predictor(x):
            return x + 0.1
            
        result = gate.evaluate(noisy_predictor, samples=100)
        self.assertFalse(result.success)
        self.assertGreater(result.mae, 0.05)
        self.assertIn("exceeds threshold", result.failure_reason)

    @patch('backend.src.simulator.logger')
    def test_simulator_synthetic_validation(self, mock_logger):
        """Test CoinbaseTradingSimulator._run_synthetic_validation logic."""
        # 1. Setup a simulator with HRM shadow enabled
        config = MagicMock()
        config.enable_hrm_shadow = True
        
        # Mocking CoinbaseTradingSimulator instead of creating a real one to avoid side effects
        sim = CoinbaseTradingSimulator.__new__(CoinbaseTradingSimulator)
        sim.config = config
        sim.shadow_engine = MagicMock()
        sim._synthetic_milestone_passed = False
        
        # Case 1: Shadow engine's _hrm_model returns identity (success)
        def identity_model(x):
            if len(x.shape) > 1 and x.shape[1] > 1:
                return x[:, 0:1].copy()
            return x.copy()
            
        sim.shadow_engine._hrm_model = identity_model
        
        # Need to call the actual method
        CoinbaseTradingSimulator._run_synthetic_validation(sim)
        
        # Verify that _synthetic_milestone_passed is set correctly
        self.assertTrue(sim._synthetic_milestone_passed)
        
        # Case 2: Shadow engine's _hrm_model returns zeros (failure)
        def zeros_model(x):
            if len(x.shape) > 1 and x.shape[1] > 1:
                return np.zeros((x.shape[0], 1))
            return np.zeros_like(x)
            
        sim.shadow_engine._hrm_model = zeros_model
        sim._synthetic_milestone_passed = False
        
        CoinbaseTradingSimulator._run_synthetic_validation(sim)
        
        self.assertFalse(sim._synthetic_milestone_passed)
        # Verify that CRITICAL errors are logged on failure
        critical_calls = [call for call in mock_logger.critical.call_args_list if "HRM failed" in call[0][0]]
        self.assertTrue(len(critical_calls) > 0)
        
        # Case 3: Failed to beat PersistenceBaseline
        # PersistenceBaseline on IdentityGate has 0 MAE.
        # Any model with > 0 MAE should fail with "failed to beat PersistenceBaseline"
        def slightly_off_model(x):
            if len(x.shape) > 1 and x.shape[1] > 1:
                return x[:, 0:1].copy() + 1e-6
            return x + 1e-6 # Within 1e-5 threshold, but NOT beating 0 MAE persistence
            
        sim.shadow_engine._hrm_model = slightly_off_model
        sim._synthetic_milestone_passed = False
        mock_logger.critical.reset_mock()
        
        CoinbaseTradingSimulator._run_synthetic_validation(sim)
        
        self.assertFalse(sim._synthetic_milestone_passed)
        critical_calls = [call for call in mock_logger.critical.call_args_list if "failed to beat PersistenceBaseline" in call[0][0]]
        self.assertTrue(len(critical_calls) > 0)

if __name__ == '__main__':
    unittest.main()
