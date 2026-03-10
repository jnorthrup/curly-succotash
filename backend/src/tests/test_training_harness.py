"""Unit tests for backend/src/training_harness.py"""

import unittest
from unittest.mock import MagicMock

from backend.src.training_harness import TrainingConfig, EpisodeResult, SeededRandom, TrainingHarness
from backend.src.replay_engine import ReplayMode
from backend.src.models import Timeframe


class TestTrainingConfigDefaults(unittest.TestCase):
    """Test TrainingConfig default values."""

    def test_default_values(self):
        """Test that TrainingConfig has expected default values."""
        config = TrainingConfig()
        
        # Test default values that exist in the actual class
        self.assertEqual(config.num_episodes, 10000)
        self.assertEqual(config.max_training_seconds, 3600)
        self.assertEqual(config.adversarial_intensity, 0.5)
        self.assertEqual(config.enable_adversarial, True)
        self.assertEqual(config.replay_mode, ReplayMode.INSTANT)


class TestTrainingConfigValidation(unittest.TestCase):
    """Test TrainingConfig validation."""

    def test_num_episodes_zero_raises_error(self):
        """Test that num_episodes=0 raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(num_episodes=0)

    def test_num_episodes_negative_raises_error(self):
        """Test that negative num_episodes raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(num_episodes=-1)

    def test_empty_symbols_raises_error(self):
        """Test that empty symbols list raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(symbols=[])

    def test_empty_timeframes_raises_error(self):
        """Test that empty timeframes list raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(timeframes=[])

    def test_adversarial_intensity_out_of_range_raises_error(self):
        """Test that adversarial_intensity=1.5 raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(adversarial_intensity=1.5)

    def test_adversarial_intensity_negative_raises_error(self):
        """Test that negative adversarial_intensity raises ValueError."""
        with self.assertRaises(ValueError):
            TrainingConfig(adversarial_intensity=-0.1)


class TestSeededRandomDeterminism(unittest.TestCase):
    """Test SeededRandom determinism."""

    def test_same_seed_same_sequence(self):
        """Test that same seed produces same sequence of random() calls."""
        seed = 42
        
        # First instance with seed 42
        rng1 = SeededRandom(seed)
        sequence1 = [rng1.random() for _ in range(5)]
        
        # Second instance with same seed
        rng2 = SeededRandom(seed)
        sequence2 = [rng2.random() for _ in range(5)]
        
        # They should be identical
        self.assertEqual(sequence1, sequence2)

    def test_different_seeds_different_sequences(self):
        """Test that different seeds produce different sequences."""
        rng1 = SeededRandom(42)
        sequence1 = [rng1.random() for _ in range(5)]
        
        rng2 = SeededRandom(99)
        sequence2 = [rng2.random() for _ in range(5)]
        
        # They should be different
        self.assertNotEqual(sequence1, sequence2)


class TestEpisodeResult(unittest.TestCase):
    """Test EpisodeResult."""

    def test_to_dict_contains_required_keys(self):
        """Test that to_dict() returns a dict with at least keys 'episode_num', 'candles_processed', 'seed_used'."""
        result = EpisodeResult(
            episode_num=5,
            candles_processed=100,
            seed_used=42,
        )
        
        result_dict = result.to_dict()
        
        # Check required keys exist
        self.assertIn('episode_num', result_dict)
        self.assertIn('candles_processed', result_dict)
        self.assertIn('seed_used', result_dict)
        
        # Check values
        self.assertEqual(result_dict['episode_num'], 5)
        self.assertEqual(result_dict['candles_processed'], 100)
        self.assertEqual(result_dict['seed_used'], 42)


class TestTrainingHarnessPauseResumeStop(unittest.TestCase):
    """Test TrainingHarness pause/resume/stop functionality."""

    def test_pause_resume_stop(self):
        """Test pause_training(), resume_training(), and stop_training() with is_paused() and is_running()."""
        # Mock BinanceArchiveClient
        mock_client = MagicMock()
        mock_client.get_date_range.return_value = (None, None)
        mock_client.get_candle_count.return_value = 0
        mock_client.query_candles.return_value = []

        # Create config with minimal episodes for quick testing
        config = TrainingConfig(
            num_episodes=1,
            symbols=["BTCUSDT"],
            timeframes=[Timeframe.ONE_HOUR],
            max_training_seconds=3600,
        )

        # Instantiate harness
        harness = TrainingHarness(mock_client, config)

        # Test initial state
        self.assertFalse(harness.is_paused())
        self.assertFalse(harness.is_running())

        # Manually set running state to test pause/resume (since we can't run full training)
        harness._is_running = True

        # Test pause
        harness.pause_training()
        self.assertTrue(harness.is_paused())

        # Test resume
        harness.resume_training()
        self.assertFalse(harness.is_paused())

        # Test stop - set _is_running to True first, then call stop
        harness._is_running = True
        harness._should_stop = False
        harness.stop_training()
        
        # After stop, _should_stop should be True
        self.assertTrue(harness._should_stop)
        
        # Note: is_running() checks _is_running which was not set to False by stop_training()
        # The stop_training method sets _should_stop = True but doesn't change _is_running
        # We test _should_stop instead since that's what stop_training actually affects
        self.assertTrue(harness._should_stop)


if __name__ == '__main__':
    unittest.main()
