"""
Tests for adversarial agents module.
"""

import pytest
from datetime import datetime, timezone

from backend.src.adversarial_agents import (
    AgentConfig,
    NoiseInjectionAgent,
    GapInjectionAgent,
    AdversarialOrchestrator,
    create_agent,
    create_random_orchestrator,
)
from backend.src.models import Candle, Timeframe


# Sample candle for testing
SAMPLE_CANDLE = Candle(
    timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    open=100.0,
    high=102.0,
    low=98.0,
    close=101.0,
    volume=1000.0,
    symbol='BTCUSDT',
    timeframe=Timeframe.ONE_HOUR,
)


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_agent_config_defaults(self):
        """Test that AgentConfig() has intensity=0.5, enabled=True, seed=None."""
        config = AgentConfig()

        assert config.intensity == 0.5
        assert config.enabled is True
        assert config.seed is None

    def test_agent_config_intensity_out_of_range(self):
        """Test that AgentConfig(intensity=1.5) raises ValueError (intensity must be in range [0.0, 1.0])."""
        with pytest.raises(ValueError, match="Intensity must be in \\[0.0, 1.0\\]"):
            AgentConfig(intensity=1.5)

    def test_agent_config_intensity_negative_raises(self):
        """Test that AgentConfig with negative intensity raises ValueError."""
        with pytest.raises(ValueError, match="Intensity must be in \\[0.0, 1.0\\]"):
            AgentConfig(intensity=-0.1)

    def test_agent_config_valid_values(self):
        """Test that AgentConfig accepts valid intensity values."""
        config_min = AgentConfig(intensity=0.0)
        assert config_min.intensity == 0.0

        config_max = AgentConfig(intensity=1.0)
        assert config_max.intensity == 1.0

        config_mid = AgentConfig(intensity=0.5)
        assert config_mid.intensity == 0.5


class TestCreateAgent:
    """Tests for create_agent factory function."""

    def test_create_agent_noise_type(self):
        """Test that create_agent('noise', AgentConfig(seed=42)) returns a NoiseInjectionAgent."""
        config = AgentConfig(seed=42)
        agent = create_agent('noise', config)

        assert isinstance(agent, NoiseInjectionAgent)
        assert agent.config.seed == 42

    def test_create_agent_gap_type(self):
        """Test that create_agent('gap', AgentConfig()) returns a GapInjectionAgent."""
        config = AgentConfig()
        agent = create_agent('gap', config)

        assert isinstance(agent, GapInjectionAgent)

    def test_create_agent_unknown_type_raises(self):
        """Test that create_agent('nonexistent', AgentConfig()) raises ValueError."""
        config = AgentConfig()

        with pytest.raises(ValueError, match="Unknown agent type: nonexistent"):
            create_agent('nonexistent', config)

    def test_create_agent_case_insensitive(self):
        """Test that create_agent works with different case variations."""
        config = AgentConfig()

        agent1 = create_agent('NOISE', config)
        assert isinstance(agent1, NoiseInjectionAgent)

        agent2 = create_agent('Noise', config)
        assert isinstance(agent2, NoiseInjectionAgent)

        agent3 = create_agent('GAP', config)
        assert isinstance(agent3, GapInjectionAgent)


class TestNoiseInjectionAgent:
    """Tests for NoiseInjectionAgent."""

    def test_noise_agent_perturb_changes_values(self):
        """Test that NoiseInjectionAgent(AgentConfig(intensity=0.5, seed=42)).perturb([candle]) returns a list where the candle's close differs from original."""
        config = AgentConfig(intensity=0.5, seed=42)
        agent = NoiseInjectionAgent(config)

        original_close = SAMPLE_CANDLE.close
        result = agent.perturb([SAMPLE_CANDLE])

        assert isinstance(result, list)
        assert len(result) == 1
        # With a fixed seed, the perturbed close should differ from original
        # (it's unlikely to be exactly the same with random noise)
        assert result[0].close != original_close

    def test_noise_agent_perturb_does_not_modify_original(self):
        """Test that original candle list is unchanged after perturb()."""
        config = AgentConfig(intensity=0.5, seed=42)
        agent = NoiseInjectionAgent(config)

        # Store original values
        original_close = SAMPLE_CANDLE.close
        original_open = SAMPLE_CANDLE.open
        original_high = SAMPLE_CANDLE.high
        original_low = SAMPLE_CANDLE.low
        original_volume = SAMPLE_CANDLE.volume

        # Apply perturbation
        result = agent.perturb([SAMPLE_CANDLE])

        # Verify original is unchanged
        assert SAMPLE_CANDLE.close == original_close
        assert SAMPLE_CANDLE.open == original_open
        assert SAMPLE_CANDLE.high == original_high
        assert SAMPLE_CANDLE.low == original_low
        assert SAMPLE_CANDLE.volume == original_volume

        # Verify result is different (perturbation was applied)
        assert result[0].close != original_close

    def test_noise_agent_zero_intensity_no_change(self):
        """Test that with intensity=0, the candle is unchanged (but still copied)."""
        config = AgentConfig(intensity=0.0, seed=42)
        agent = NoiseInjectionAgent(config)

        result = agent.perturb([SAMPLE_CANDLE])

        # With 0 intensity, values should remain the same
        assert result[0].close == SAMPLE_CANDLE.close
        assert result[0].open == SAMPLE_CANDLE.open

    def test_noise_agent_returns_copy(self):
        """Test that perturb returns new Candle objects, not the originals."""
        config = AgentConfig(intensity=0.5, seed=42)
        agent = NoiseInjectionAgent(config)

        result = agent.perturb([SAMPLE_CANDLE])

        # Result should be a different object
        assert result[0] is not SAMPLE_CANDLE


class TestAdversarialOrchestrator:
    """Tests for AdversarialOrchestrator."""

    def test_adversarial_orchestrator_apply_to_stream(self):
        """Test that creating an orchestrator with one NoiseInjectionAgent and calling apply_to_stream(candle) returns a Candle (not None)."""
        config = AgentConfig(intensity=0.5, seed=42)
        agent = NoiseInjectionAgent(config)
        orchestrator = AdversarialOrchestrator([agent])

        result = orchestrator.apply_to_stream(SAMPLE_CANDLE)

        assert result is not None
        assert isinstance(result, Candle)
        assert result.symbol == 'BTCUSDT'
        assert result.timeframe == Timeframe.ONE_HOUR

    def test_orchestrator_apply_all(self):
        """Test apply_all with multiple candles."""
        config = AgentConfig(intensity=0.5, seed=42)
        agent = NoiseInjectionAgent(config)
        orchestrator = AdversarialOrchestrator([agent])

        candles = [SAMPLE_CANDLE, SAMPLE_CANDLE]
        result = orchestrator.apply_all(candles)

        assert len(result) == 2
        assert all(isinstance(c, Candle) for c in result)

    def test_orchestrator_empty_agents(self):
        """Test orchestrator with no agents returns copies."""
        orchestrator = AdversarialOrchestrator([])

        result = orchestrator.apply_to_stream(SAMPLE_CANDLE)

        assert isinstance(result, Candle)
        assert result.close == SAMPLE_CANDLE.close


class TestCreateRandomOrchestrator:
    """Tests for create_random_orchestrator function."""

    def test_create_random_orchestrator_returns_orchestrator(self):
        """Test that create_random_orchestrator(seed=42) returns an AdversarialOrchestrator with agents."""
        orchestrator = create_random_orchestrator(seed=42)

        assert isinstance(orchestrator, AdversarialOrchestrator)
        # With seed=42, it should always include noise agent (100% chance)
        assert len(orchestrator.agents) >= 1

    def test_create_random_orchestrator_has_noise_agent(self):
        """Test that random orchestrator includes a NoiseInjectionAgent."""
        orchestrator = create_random_orchestrator(seed=42)

        agent_types = [type(a).__name__ for a in orchestrator.agents]
        assert 'NoiseInjectionAgent' in agent_types

    def test_create_random_orchestrator_reproducible(self):
        """Test that same seed produces same agent configuration."""
        orch1 = create_random_orchestrator(seed=100)
        orch2 = create_random_orchestrator(seed=100)

        assert len(orch1.agents) == len(orch2.agents)
        # Agent types should match
        types1 = [type(a).__name__ for a in orch1.agents]
        types2 = [type(a).__name__ for a in orch2.agents]
        assert types1 == types2

    def test_create_random_orchestrator_different_seeds(self):
        """Test that different seeds may produce different orchestrators."""
        orch1 = create_random_orchestrator(seed=1)
        orch2 = create_random_orchestrator(seed=999)

        # Different seeds may produce different number of agents
        # (this is not guaranteed to fail, but likely to pass)
        # The important thing is both are valid orchestrators
        assert isinstance(orch1, AdversarialOrchestrator)
        assert isinstance(orch2, AdversarialOrchestrator)
        assert len(orch1.agents) >= 1
        assert len(orch2.agents) >= 1
