"""
Adversarial Agents - Market perturbation framework for robust strategy training.

Implements various adversarial agents that inject noise, gaps, regime shifts,
and other market anomalies into candle streams to train robust strategies.
All agents follow the BaseStrategy pattern for consistency.
"""

import logging
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

from .models import Candle, Timeframe


logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for adversarial agents.

    Attributes:
        intensity: Perturbation strength from 0.0 (none) to 1.0 (maximum)
        seed: Random seed for reproducible perturbations
        enabled: Whether this agent is active
        params: Agent-specific configuration parameters
    """
    intensity: float = 0.5
    seed: Optional[int] = None
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError(f"Intensity must be in [0.0, 1.0], got {self.intensity}")


class AdversarialAgent(ABC):
    """Abstract base class for all adversarial agents.

    All adversarial agents inherit from this class and implement the
    perturb() method to apply specific types of market perturbations.
    Agents never modify original candles - they always create copies.

    The pattern follows BaseStrategy from strategies.py for consistency.
    """

    def __init__(self, config: AgentConfig):
        """Initialize the agent with configuration.

        Args:
            config: AgentConfig with intensity, seed, and parameters
        """
        self.config = config
        self._rng = np.random.RandomState(config.seed) if config.seed is not None else np.random.RandomState()
        self._stats = self._init_stats()
        self._enabled = config.enabled
        logger.debug(f"Initialized {self.name} with intensity={config.intensity}, seed={config.seed}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the agent's name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of what this agent does."""
        pass

    @abstractmethod
    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Apply perturbation to a list of candles.

        Args:
            candles: List of Candle objects to perturb

        Returns:
            List of perturbed Candle objects (never modifies input)
        """
        pass

    def perturb_stream(self, candle: Candle) -> Candle:
        """Apply perturbation to a single candle for streaming mode.

        Args:
            candle: Single Candle object to perturb

        Returns:
            Perturbed Candle object (never modifies input)
        """
        result = self.perturb([candle])
        return result[0] if result else candle

    def reset(self) -> None:
        """Reset the agent's internal state and statistics."""
        self._stats = self._init_stats()
        if self.config.seed is not None:
            self._rng = np.random.RandomState(self.config.seed)
        logger.debug(f"Reset {self.name} agent state")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about perturbations applied.

        Returns:
            Dictionary with agent statistics
        """
        return {
            "agent_name": self.name,
            "agent_description": self.description,
            "enabled": self._enabled,
            "intensity": self.config.intensity,
            **self._stats
        }

    def _init_stats(self) -> Dict[str, Any]:
        """Initialize statistics dictionary. Override in subclasses."""
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
        }

    def _copy_candle(self, candle: Candle) -> Candle:
        """Create a deep copy of a candle.

        Args:
            candle: Candle to copy

        Returns:
            New Candle object with same values
        """
        return Candle(
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            symbol=candle.symbol,
            timeframe=candle.timeframe
        )

    def _should_activate(self, probability: float) -> bool:
        """Determine if agent should activate based on probability.

        Args:
            probability: Activation probability (0.0 to 1.0)

        Returns:
            True if agent should activate
        """
        if not self._enabled:
            return False
        return self._rng.random() < (probability * self.config.intensity)


class NoiseInjectionAgent(AdversarialAgent):
    """Adds random price and volume noise to candles.

    Injects Gaussian or uniform noise into OHLCV values to simulate
    bid-ask spreads, tick variations, and volume estimation errors.

    Config params:
        price_noise_pct: Price noise as percentage (default 0.001 = 0.1%)
        volume_noise_pct: Volume noise as percentage (default 0.05 = 5%)
        noise_type: 'gaussian' or 'uniform' (default 'gaussian')
    """

    @property
    def name(self) -> str:
        return "NoiseInjectionAgent"

    @property
    def description(self) -> str:
        return "Adds random price/volume noise to simulate market microstructure"

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.price_noise_pct = config.params.get("price_noise_pct", 0.001)
        self.volume_noise_pct = config.params.get("volume_noise_pct", 0.05)
        self.noise_type = config.params.get("noise_type", "gaussian")

        if self.noise_type not in ("gaussian", "uniform"):
            raise ValueError(f"noise_type must be 'gaussian' or 'uniform', got {self.noise_type}")

    def _init_stats(self) -> Dict[str, Any]:
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
            "price_perturbations": 0,
            "volume_perturbations": 0,
            "avg_price_change_pct": 0.0,
            "avg_volume_change_pct": 0.0,
        }

    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Add noise to OHLCV values.

        Args:
            candles: List of candles to perturb

        Returns:
            List of candles with noise applied
        """
        if not candles or not self._enabled:
            return [self._copy_candle(c) for c in candles]

        result = []
        total_price_change = 0.0
        total_volume_change = 0.0

        for candle in candles:
            new_candle = self._copy_candle(candle)
            self._stats["total_candles_processed"] += 1

            # Generate noise
            if self.noise_type == "gaussian":
                price_noise = self._rng.normal(0, self.price_noise_pct * self.config.intensity)
                volume_noise = self._rng.normal(0, self.volume_noise_pct * self.config.intensity)
            else:  # uniform
                price_noise = self._rng.uniform(
                    -self.price_noise_pct * self.config.intensity,
                    self.price_noise_pct * self.config.intensity
                )
                volume_noise = self._rng.uniform(
                    -self.volume_noise_pct * self.config.intensity,
                    self.volume_noise_pct * self.config.intensity
                )

            # Apply price noise to OHLC
            price_mult = 1 + price_noise
            new_candle.open *= price_mult
            new_candle.high *= price_mult
            new_candle.low *= price_mult
            new_candle.close *= price_mult

            # Ensure high >= max(open, close) and low <= min(open, close)
            new_candle.high = max(new_candle.high, new_candle.open, new_candle.close)
            new_candle.low = min(new_candle.low, new_candle.open, new_candle.close)

            # Apply volume noise
            old_volume = new_candle.volume
            new_candle.volume *= max(0.1, 1 + volume_noise)  # Ensure positive volume

            # Update stats
            self._stats["total_candles_perturbed"] += 1
            self._stats["price_perturbations"] += 1
            self._stats["volume_perturbations"] += 1

            total_price_change += abs(price_noise)
            total_volume_change += abs((new_candle.volume - old_volume) / old_volume if old_volume > 0 else 0)

            result.append(new_candle)

        # Update averages
        n = len(candles)
        self._stats["avg_price_change_pct"] = (self._stats["avg_price_change_pct"] * (self._stats["total_candles_processed"] - n) + total_price_change) / self._stats["total_candles_processed"]
        self._stats["avg_volume_change_pct"] = (self._stats["avg_volume_change_pct"] * (self._stats["total_candles_processed"] - n) + total_volume_change) / self._stats["total_candles_processed"]

        return result


class GapInjectionAgent(AdversarialAgent):
    """Creates artificial gaps and missing data in the candle stream.

    Simulates flash crashes, pumps, and missing data scenarios by
    removing candles or creating price discontinuities.

    Config params:
        gap_probability: Chance of gap at any candle (default 0.001 = 0.1%)
        max_gap_size: Max consecutive missing candles (default 5)
        gap_type: 'missing' (None) or 'price_jump' (default 'missing')
        jump_range: (min, max) tuple for price jump magnitude (default (0.02, 0.10))
    """

    @property
    def name(self) -> str:
        return "GapInjectionAgent"

    @property
    def description(self) -> str:
        return "Creates artificial gaps and missing data in candle streams"

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.gap_probability = config.params.get("gap_probability", 0.001)
        self.max_gap_size = config.params.get("max_gap_size", 5)
        self.gap_type = config.params.get("gap_type", "missing")
        self.jump_range = config.params.get("jump_range", (0.02, 0.10))
        self._in_gap = False
        self._gap_remaining = 0

    def _init_stats(self) -> Dict[str, Any]:
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
            "gaps_created": 0,
            "candles_removed": 0,
            "price_jumps_created": 0,
        }

    def reset(self) -> None:
        """Reset gap state."""
        super().reset()
        self._in_gap = False
        self._gap_remaining = 0

    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Create gaps in the candle stream.

        Args:
            candles: List of candles to process

        Returns:
            List with gaps applied (candles removed or None inserted)
        """
        if not candles or not self._enabled:
            return [self._copy_candle(c) for c in candles]

        result = []

        for candle in candles:
            self._stats["total_candles_processed"] += 1

            # Check if we're in an active gap
            if self._in_gap:
                if self._gap_remaining > 0:
                    self._gap_remaining -= 1
                    self._stats["candles_removed"] += 1
                    self._stats["total_candles_perturbed"] += 1
                    if self.gap_type == "missing":
                        continue  # Skip this candle (gap)
                    else:
                        # For price_jump, we still include but with modified price
                        new_candle = self._copy_candle(candle)
                        result.append(new_candle)
                        continue
                else:
                    self._in_gap = False

            # Check if we should start a new gap
            if self._should_activate(self.gap_probability):
                self._in_gap = True
                self._gap_remaining = self._rng.randint(1, self.max_gap_size + 1)
                self._stats["gaps_created"] += 1

                if self.gap_type == "price_jump":
                    # Create a price jump
                    jump_pct = self._rng.uniform(self.jump_range[0], self.jump_range[1])
                    if self._rng.random() < 0.5:
                        jump_pct = -jump_pct  # 50% chance of gap down

                    new_candle = self._copy_candle(candle)
                    mult = 1 + jump_pct
                    new_candle.open = new_candle.close  # Gap from previous close
                    new_candle.high *= mult
                    new_candle.low *= mult
                    new_candle.close *= mult
                    new_candle.high = max(new_candle.high, new_candle.open, new_candle.close)
                    new_candle.low = min(new_candle.low, new_candle.open, new_candle.close)

                    self._stats["price_jumps_created"] += 1
                    self._stats["total_candles_perturbed"] += 1
                    result.append(new_candle)
                    continue
                else:
                    # Missing data gap - skip this candle
                    self._stats["candles_removed"] += 1
                    self._stats["total_candles_perturbed"] += 1
                    continue

            # No gap, copy normally
            result.append(self._copy_candle(candle))

        return result


class RegimeShiftAgent(AdversarialAgent):
    """Simulates market regime changes (trending, choppy, high volatility).

    Applies multipliers to price and volume to simulate different market
    conditions like trending up/down, choppy markets, or high volatility periods.

    Config params:
        shift_probability: Probability of regime change per candle (default 0.0001)
        regimes: List of regime names to use (default all)
        min_duration: Minimum candles in a regime (default 50)
        max_duration: Maximum candles in a regime (default 200)
    """

    REGIME_MULTIPLIERS = {
        "trending_up": {"price": 1.001, "volume": 1.2, "volatility": 0.8},
        "trending_down": {"price": 0.999, "volume": 1.3, "volatility": 0.9},
        "choppy": {"price": 1.0, "volume": 0.8, "volatility": 1.5},
        "high_volatility": {"price": 1.0, "volume": 2.0, "volatility": 2.5},
        "low_volatility": {"price": 1.0, "volume": 0.5, "volatility": 0.4},
        "accumulation": {"price": 1.0002, "volume": 0.9, "volatility": 0.6},
        "distribution": {"price": 0.9998, "volume": 1.1, "volatility": 0.7},
    }

    @property
    def name(self) -> str:
        return "RegimeShiftAgent"

    @property
    def description(self) -> str:
        return "Simulates market regime changes (trending, choppy, volatile)"

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.shift_probability = config.params.get("shift_probability", 0.0001)
        self.regimes = config.params.get("regimes", list(self.REGIME_MULTIPLIERS.keys()))
        self.min_duration = config.params.get("min_duration", 50)
        self.max_duration = config.params.get("max_duration", 200)

        self._current_regime: Optional[str] = None
        self._regime_duration = 0
        self._regime_remaining = 0
        self._price_multiplier = 1.0
        self._volume_multiplier = 1.0
        self._volatility_multiplier = 1.0

    def _init_stats(self) -> Dict[str, Any]:
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
            "regime_changes": 0,
            "regimes_entered": {},
            "current_regime": None,
            "regime_duration": 0,
        }

    def reset(self) -> None:
        """Reset regime state."""
        super().reset()
        self._current_regime = None
        self._regime_duration = 0
        self._regime_remaining = 0
        self._price_multiplier = 1.0
        self._volume_multiplier = 1.0
        self._volatility_multiplier = 1.0

    def _enter_regime(self, regime: str) -> None:
        """Enter a new market regime."""
        self._current_regime = regime
        self._regime_duration = self._rng.randint(self.min_duration, self.max_duration + 1)
        self._regime_remaining = self._regime_duration

        multipliers = self.REGIME_MULTIPLIERS[regime]
        self._price_multiplier = multipliers["price"]
        self._volume_multiplier = multipliers["volume"]
        self._volatility_multiplier = multipliers["volatility"]

        # Scale by intensity
        if self._price_multiplier != 1.0:
            self._price_multiplier = 1 + (self._price_multiplier - 1) * self.config.intensity
        self._volume_multiplier = 1 + (self._volume_multiplier - 1) * self.config.intensity
        self._volatility_multiplier = 1 + (self._volatility_multiplier - 1) * self.config.intensity

        self._stats["regime_changes"] += 1
        self._stats["regimes_entered"][regime] = self._stats["regimes_entered"].get(regime, 0) + 1
        logger.debug(f"Entered {regime} regime for {self._regime_duration} candles")

    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Apply regime multipliers to candles.

        Args:
            candles: List of candles to process

        Returns:
            List of candles with regime effects applied
        """
        if not candles or not self._enabled:
            return [self._copy_candle(c) for c in candles]

        result = []

        for candle in candles:
            self._stats["total_candles_processed"] += 1

            # Check for regime change
            if self._regime_remaining <= 0 or self._should_activate(self.shift_probability):
                new_regime = self._rng.choice(self.regimes)
                if new_regime != self._current_regime:
                    self._enter_regime(new_regime)

            # Apply regime effects
            if self._current_regime and self._regime_remaining > 0:
                self._regime_remaining -= 1
                new_candle = self._copy_candle(candle)

                # Apply cumulative price drift
                open_close_diff = new_candle.close - new_candle.open
                high_mult = (new_candle.high - new_candle.open) / (new_candle.close - new_candle.open) if new_candle.close != new_candle.open else 1.0
                low_mult = (new_candle.open - new_candle.low) / (new_candle.close - new_candle.open) if new_candle.close != new_candle.open else 1.0

                new_candle.close *= self._price_multiplier
                new_candle.open = new_candle.close - open_close_diff * self._price_multiplier

                # Apply volatility multiplier to range
                range_size = abs(new_candle.close - new_candle.open)
                new_candle.high = max(new_candle.open, new_candle.close) + range_size * self._volatility_multiplier * abs(high_mult)
                new_candle.low = min(new_candle.open, new_candle.close) - range_size * self._volatility_multiplier * abs(low_mult)

                # Apply volume multiplier
                new_candle.volume *= self._volume_multiplier

                self._stats["total_candles_perturbed"] += 1
                result.append(new_candle)
            else:
                result.append(self._copy_candle(candle))

        self._stats["current_regime"] = self._current_regime
        self._stats["regime_duration"] = self._regime_duration - self._regime_remaining

        return result


class FlashCrashAgent(AdversarialAgent):
    """Simulates flash crash events with sudden drops and recoveries.

    Creates realistic flash crash patterns: sudden sharp price drops
    followed by gradual or rapid recoveries over specified periods.

    Config params:
        crash_probability: Chance of crash starting (default 0.0005 = 0.05%)
        max_crash_pct: Maximum price drop (default 0.20 = 20%)
        recovery_candles: Candles for recovery phase (default 10)
        crash_candles: Candles for crash phase (default 3)
    """

    @property
    def name(self) -> str:
        return "FlashCrashAgent"

    @property
    def description(self) -> str:
        return "Simulates flash crash events with drops and recoveries"

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.crash_probability = config.params.get("crash_probability", 0.0005)
        self.max_crash_pct = config.params.get("max_crash_pct", 0.20)
        self.recovery_candles = config.params.get("recovery_candles", 10)
        self.crash_candles = config.params.get("crash_candles", 3)

        self._in_crash = False
        self._in_recovery = False
        self._crash_remaining = 0
        self._recovery_remaining = 0
        self._crash_mult = 1.0
        self._recovery_mult = 1.0
        self._target_drop = 0.0

    def _init_stats(self) -> Dict[str, Any]:
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
            "crashes_triggered": 0,
            "recoveries_completed": 0,
            "max_drop_achieved": 0.0,
        }

    def reset(self) -> None:
        """Reset crash state."""
        super().reset()
        self._in_crash = False
        self._in_recovery = False
        self._crash_remaining = 0
        self._recovery_remaining = 0
        self._crash_mult = 1.0
        self._recovery_mult = 1.0
        self._target_drop = 0.0

    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Apply flash crash patterns to candles.

        Args:
            candles: List of candles to process

        Returns:
            List of candles with crash/recovery patterns applied
        """
        if not candles or not self._enabled:
            return [self._copy_candle(c) for c in candles]

        result = []

        for candle in candles:
            self._stats["total_candles_processed"] += 1

            # Check if we should start a new crash
            if not self._in_crash and not self._in_recovery:
                if self._should_activate(self.crash_probability):
                    self._in_crash = True
                    self._crash_remaining = self.crash_candles
                    self._target_drop = self._rng.uniform(0.05, self.max_crash_pct) * self.config.intensity
                    self._crash_mult = 1 - (self._target_drop / self.crash_candles)
                    self._stats["crashes_triggered"] += 1
                    logger.debug(f"Flash crash triggered: {self._target_drop*100:.1f}% drop over {self.crash_candles} candles")

            new_candle = self._copy_candle(candle)

            if self._in_crash:
                # Apply crash multiplier
                mult = self._crash_mult ** (self.crash_candles - self._crash_remaining + 1)
                new_candle.open *= mult
                new_candle.high *= mult
                new_candle.low *= mult
                new_candle.close *= mult

                self._crash_remaining -= 1
                if self._crash_remaining <= 0:
                    self._in_crash = False
                    self._in_recovery = True
                    self._recovery_remaining = self.recovery_candles
                    # Calculate recovery multiplier to return to baseline
                    final_mult = (1 - self._target_drop) ** self.crash_candles
                    self._recovery_mult = (1 / final_mult) ** (1 / self.recovery_candles)
                    self._stats["max_drop_achieved"] = max(self._stats["max_drop_achieved"], self._target_drop)

                self._stats["total_candles_perturbed"] += 1

            elif self._in_recovery:
                # Apply recovery multiplier
                recovery_progress = (self.recovery_candles - self._recovery_remaining) / self.recovery_candles
                mult = (1 - self._target_drop * self.crash_candles) * (self._recovery_mult ** recovery_progress)
                # Ensure we don't exceed original price
                mult = min(mult, 1.0)

                new_candle.open *= mult
                new_candle.high *= mult
                new_candle.low *= mult
                new_candle.close *= mult

                self._recovery_remaining -= 1
                if self._recovery_remaining <= 0:
                    self._in_recovery = False
                    self._stats["recoveries_completed"] += 1

                self._stats["total_candles_perturbed"] += 1

            result.append(new_candle)

        return result


class LatencyInjectionAgent(AdversarialAgent):
    """Simulates delayed data delivery and out-of-order candles.

    Creates realistic network latency effects by reordering candles,
    delaying delivery, or duplicating candles to simulate packet loss
    and retransmission.

    Config params:
        latency_probability: Chance of latency event (default 0.01 = 1%)
        max_latency_candles: Max candles to delay (default 3)
        reorder_probability: Chance of out-of-order delivery (default 0.005)
        duplicate_probability: Chance of duplicate candle (default 0.002)
    """

    @property
    def name(self) -> str:
        return "LatencyInjectionAgent"

    @property
    def description(self) -> str:
        return "Simulates delayed data and out-of-order candle delivery"

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.latency_probability = config.params.get("latency_probability", 0.01)
        self.max_latency_candles = config.params.get("max_latency_candles", 3)
        self.reorder_probability = config.params.get("reorder_probability", 0.005)
        self.duplicate_probability = config.params.get("duplicate_probability", 0.002)

        self._delayed_buffer: List[Candle] = []
        self._pending_reorder: Optional[Candle] = None

    def _init_stats(self) -> Dict[str, Any]:
        return {
            "total_candles_processed": 0,
            "total_candles_perturbed": 0,
            "candles_delayed": 0,
            "candles_reordered": 0,
            "candles_duplicated": 0,
            "max_delay_observed": 0,
        }

    def reset(self) -> None:
        """Reset latency state."""
        super().reset()
        self._delayed_buffer = []
        self._pending_reorder = None

    def perturb(self, candles: List[Candle]) -> List[Candle]:
        """Apply latency effects to candles.

        Args:
            candles: List of candles to process

        Returns:
            List of candles with latency effects applied
        """
        if not candles:
            return []

        if not self._enabled:
            return [self._copy_candle(c) for c in candles]

        result = []
        buffer_to_process = list(candles)  # Work with a copy

        for candle in buffer_to_process:
            self._stats["total_candles_processed"] += 1
            new_candle = self._copy_candle(candle)

            # Handle pending reorder
            if self._pending_reorder is not None:
                if self._rng.random() < 0.5:
                    # Deliver pending candle first (out of order)
                    result.append(self._pending_reorder)
                    result.append(new_candle)
                    self._stats["candles_reordered"] += 2
                else:
                    # Deliver in order
                    result.append(new_candle)
                    result.append(self._pending_reorder)
                self._pending_reorder = None
                self._stats["total_candles_perturbed"] += 2
                continue

            # Check for reorder event
            if self._should_activate(self.reorder_probability):
                self._pending_reorder = new_candle
                continue

            # Check for duplicate
            if self._should_activate(self.duplicate_probability):
                result.append(new_candle)
                result.append(self._copy_candle(new_candle))
                self._stats["candles_duplicated"] += 1
                self._stats["total_candles_perturbed"] += 1
                continue

            # Check for delay
            if self._should_activate(self.latency_probability):
                delay_candles = self._rng.randint(1, self.max_latency_candles + 1)
                self._delayed_buffer.append((new_candle, delay_candles))
                self._stats["candles_delayed"] += 1
                self._stats["max_delay_observed"] = max(self._stats["max_delay_observed"], delay_candles)
                continue

            # Release any delayed candles whose time has come
            newly_delayed = []
            for delayed_candle, remaining in self._delayed_buffer:
                remaining -= 1
                if remaining <= 0:
                    result.append(delayed_candle)
                    self._stats["total_candles_perturbed"] += 1
                else:
                    newly_delayed.append((delayed_candle, remaining))
            self._delayed_buffer = newly_delayed

            result.append(new_candle)

        # Release remaining delayed candles at end of batch
        for delayed_candle, _ in self._delayed_buffer:
            result.append(delayed_candle)
            self._stats["total_candles_perturbed"] += 1
        self._delayed_buffer = []

        return result

    def perturb_stream(self, candle: Candle) -> Candle:
        """Streaming version that handles single candle at a time.

        For latency agent, we need special handling in streaming mode
        to properly manage the delayed buffer.
        """
        if not self._enabled:
            return self._copy_candle(candle)

        # In streaming mode, we return the current candle and manage delay state
        # The delayed candles will be returned in future calls
        self._stats["total_candles_processed"] += 1

        # Process delayed buffer
        if self._delayed_buffer:
            # Return oldest delayed candle and add new one to buffer
            oldest_candle, remaining = self._delayed_buffer[0]
            self._delayed_buffer = self._delayed_buffer[1:]

            # Add current candle with delay
            if self._should_activate(self.latency_probability):
                delay = self._rng.randint(1, self.max_latency_candles + 1)
                self._delayed_buffer.append((self._copy_candle(candle), delay))
                self._stats["candles_delayed"] += 1
            else:
                self._delayed_buffer.append((self._copy_candle(candle), 0))

            if remaining <= 0:
                self._stats["total_candles_perturbed"] += 1
                return oldest_candle
            else:
                self._delayed_buffer.append((oldest_candle, remaining - 1))

        # Check for delay
        if self._should_activate(self.latency_probability):
            delay = self._rng.randint(1, self.max_latency_candles + 1)
            self._delayed_buffer.append((self._copy_candle(candle), delay))
            self._stats["candles_delayed"] += 1
            # Return the candle anyway in streaming mode to not block
            return self._delayed_buffer[0][0]

        return self._copy_candle(candle)


class AdversarialOrchestrator:
    """Orchestrates multiple adversarial agents for combined perturbations.

    Manages a collection of agents and applies them sequentially to
    candle streams. Provides unified statistics and control interface.

    Example:
        orchestrator = AdversarialOrchestrator([
            NoiseInjectionAgent(AgentConfig(intensity=0.5)),
            FlashCrashAgent(AgentConfig(intensity=0.3)),
        ])
        perturbed = orchestrator.apply_all(candles)
    """

    def __init__(self, agents: List[AdversarialAgent]):
        """Initialize orchestrator with a list of agents.

        Args:
            agents: List of AdversarialAgent instances to apply
        """
        self.agents = agents
        logger.info(f"Initialized AdversarialOrchestrator with {len(agents)} agents: "
                   f"{[a.name for a in agents]}")

    def apply_all(self, candles: List[Candle]) -> List[Candle]:
        """Apply all agents sequentially to a list of candles.

        Agents are applied in the order they were added. Each agent
        receives the output of the previous agent.

        Args:
            candles: List of Candle objects to perturb

        Returns:
            List of perturbed Candle objects
        """
        if not candles:
            return []

        result = candles
        for agent in self.agents:
            result = agent.perturb(result)
        return result

    def apply_to_stream(self, candle: Candle) -> Candle:
        """Apply all agents to a single candle for streaming.

        Args:
            candle: Single Candle object to perturb

        Returns:
            Perturbed Candle object
        """
        result = candle
        for agent in self.agents:
            result = agent.perturb_stream(result)
        return result

    def reset_all(self) -> None:
        """Reset all agents to their initial state."""
        for agent in self.agents:
            agent.reset()
        logger.debug("Reset all adversarial agents")

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics from all agents.

        Returns:
            Dictionary mapping agent names to their statistics
        """
        return {agent.name: agent.get_stats() for agent in self.agents}

    def add_agent(self, agent: AdversarialAgent) -> None:
        """Add a new agent to the orchestrator.

        Args:
            agent: AdversarialAgent to add
        """
        self.agents.append(agent)
        logger.info(f"Added agent {agent.name} to orchestrator")

    def remove_agent(self, agent_name: str) -> bool:
        """Remove an agent by name.

        Args:
            agent_name: Name of agent to remove

        Returns:
            True if agent was found and removed
        """
        for i, agent in enumerate(self.agents):
            if agent.name == agent_name:
                self.agents.pop(i)
                logger.info(f"Removed agent {agent_name} from orchestrator")
                return True
        logger.warning(f"Agent {agent_name} not found in orchestrator")
        return False

    def enable_agent(self, agent_name: str) -> bool:
        """Enable a specific agent.

        Args:
            agent_name: Name of agent to enable

        Returns:
            True if agent was found and enabled
        """
        for agent in self.agents:
            if agent.name == agent_name:
                agent._enabled = True
                return True
        return False

    def disable_agent(self, agent_name: str) -> bool:
        """Disable a specific agent.

        Args:
            agent_name: Name of agent to disable

        Returns:
            True if agent was found and disabled
        """
        for agent in self.agents:
            if agent.name == agent_name:
                agent._enabled = False
                return True
        return False


# Agent registry for factory function
AGENT_REGISTRY: Dict[str, type] = {
    "noise": NoiseInjectionAgent,
    "noise_injection": NoiseInjectionAgent,
    "gap": GapInjectionAgent,
    "gap_injection": GapInjectionAgent,
    "regime": RegimeShiftAgent,
    "regime_shift": RegimeShiftAgent,
    "flash_crash": FlashCrashAgent,
    "crash": FlashCrashAgent,
    "latency": LatencyInjectionAgent,
    "latency_injection": LatencyInjectionAgent,
}


def create_agent(agent_type: str, config: AgentConfig) -> AdversarialAgent:
    """Factory function to create agents by type string.

    Args:
        agent_type: Type of agent to create (e.g., 'noise', 'flash_crash')
        config: AgentConfig with initialization parameters

    Returns:
        Instantiated AdversarialAgent subclass

    Raises:
        ValueError: If agent_type is not recognized

    Example:
        agent = create_agent("noise", AgentConfig(intensity=0.5, seed=42))
    """
    agent_type_lower = agent_type.lower()
    if agent_type_lower not in AGENT_REGISTRY:
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available types: {list(AGENT_REGISTRY.keys())}"
        )

    agent_class = AGENT_REGISTRY[agent_type_lower]
    return agent_class(config)


def create_random_orchestrator(seed: int, intensity: float = 0.5) -> AdversarialOrchestrator:
    """Create an orchestrator with a random selection of agents.

    Creates a diverse set of agents with randomized configurations
    for maximum training variety.

    Args:
        seed: Random seed for reproducibility
        intensity: Base intensity for all agents (0.0 to 1.0)

    Returns:
        AdversarialOrchestrator with randomly configured agents

    Example:
        orchestrator = create_random_orchestrator(seed=42, intensity=0.3)
    """
    rng = np.random.RandomState(seed)
    agents = []

    # Always include noise injection
    noise_config = AgentConfig(
        intensity=intensity,
        seed=seed,
        enabled=True,
        params={
            "price_noise_pct": rng.uniform(0.0005, 0.002),
            "volume_noise_pct": rng.uniform(0.02, 0.08),
            "noise_type": rng.choice(["gaussian", "uniform"]),
        }
    )
    agents.append(NoiseInjectionAgent(noise_config))

    # Randomly include other agents
    if rng.random() < 0.7:  # 70% chance
        gap_config = AgentConfig(
            intensity=intensity,
            seed=seed + 1,
            enabled=True,
            params={
                "gap_probability": rng.uniform(0.0005, 0.002),
                "max_gap_size": rng.randint(2, 8),
                "gap_type": rng.choice(["missing", "price_jump"]),
            }
        )
        agents.append(GapInjectionAgent(gap_config))

    if rng.random() < 0.6:  # 60% chance
        regime_config = AgentConfig(
            intensity=intensity,
            seed=seed + 2,
            enabled=True,
            params={
                "shift_probability": rng.uniform(0.00005, 0.0002),
                "min_duration": rng.randint(30, 100),
                "max_duration": rng.randint(100, 300),
            }
        )
        agents.append(RegimeShiftAgent(regime_config))

    if rng.random() < 0.4:  # 40% chance
        crash_config = AgentConfig(
            intensity=intensity,
            seed=seed + 3,
            enabled=True,
            params={
                "crash_probability": rng.uniform(0.0002, 0.001),
                "max_crash_pct": rng.uniform(0.10, 0.30),
                "recovery_candles": rng.randint(5, 20),
            }
        )
        agents.append(FlashCrashAgent(crash_config))

    if rng.random() < 0.5:  # 50% chance
        latency_config = AgentConfig(
            intensity=intensity,
            seed=seed + 4,
            enabled=True,
            params={
                "latency_probability": rng.uniform(0.005, 0.02),
                "max_latency_candles": rng.randint(2, 5),
            }
        )
        agents.append(LatencyInjectionAgent(latency_config))

    logger.info(f"Created random orchestrator with {len(agents)} agents (seed={seed})")
    return AdversarialOrchestrator(agents)
