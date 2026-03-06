"""
Training Harness - Orchestrates replay, adversarial agents, and strategy evaluation.

Extends CoinbaseTradingSimulator to support episode-based adversarial training
with Binance archive replay. Manages training episodes with configurable parameters,
coordinates replay engine with adversarial agents, tracks episode metrics and
strategy performance, and supports curriculum learning (progressive difficulty).

Key Features:
- Multi-episode training loop with progress tracking
- Deterministic episodes (seed-based)
- Checkpoint/resume capability
- Real-time and post-hoc metrics
- Strategy leaderboard tracking
- Graceful shutdown on interrupt
- Memory-efficient (stream, don't batch)

Example:
    client = BinanceArchiveClient()
    config = TrainingConfig(
        num_episodes=10000,
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=[Timeframe.ONE_HOUR],
        replay_mode=ReplayMode.INSTANT
    )
    harness = TrainingHarness(client, config)
    result = harness.run_training()
"""

import json
import logging
import math
import os
import pickle
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum

import numpy as np

from .models import Candle, Timeframe, Signal, PerformanceMetrics
from .binance_client import BinanceArchiveClient
from .replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from .adversarial_agents import (
    AdversarialOrchestrator, AdversarialAgent, AgentConfig,
    NoiseInjectionAgent, GapInjectionAgent, RegimeShiftAgent,
    FlashCrashAgent, LatencyInjectionAgent, create_random_orchestrator
)
from .strategies import BaseStrategy, create_all_strategies, StrategyConfig, STRATEGY_REGISTRY
from .backtesting import MetricsCalculator, BacktestConfig
from .paper_trading import PaperTradingEngine, PaperTradingConfig
from .oos_calibration import OOSplitPolicy, OOSplitter, SplitResult
from .calibration_sweep import CalibrationSweepConfig, CalibrationSweeper, SweepResult

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for adversarial training harness.

    Attributes:
        num_episodes: Total number of training episodes to run
        max_training_seconds: Maximum training duration in seconds
        symbols: List of trading pair symbols to train on
        timeframes: List of timeframes to use
        replay_mode: Replay speed mode (default INSTANT for speed)
        bar_sequences_per_episode: Number of bar sequences per episode
        adversarial_config: Configuration dictionary for adversarial agents
        strategy_configs: Strategy-specific configuration overrides
        checkpoint_interval: Episodes between checkpoint saves
        checkpoint_dir: Directory to store checkpoints
        initial_capital: Initial capital for paper trading
        position_size_pct: Position size as percentage of capital
        commission_pct: Commission percentage per trade
        min_bar_window: Minimum bars for episode window
        max_bar_window: Maximum bars for episode window
        enable_adversarial: Whether to enable adversarial perturbations
        adversarial_intensity: Base intensity for adversarial agents (0.0-1.0)
        randomize_episodes: Whether to randomize episode parameters
        track_leaderboard: Whether to maintain strategy leaderboard
        enable_calibration_sweep: Whether to run calibration sensitivity sweep
        calibration_sweep_config: Configuration for calibration sweep
        oos_split_policy: Policy for out-of-sample data splitting
    """
    num_episodes: int = 10000
    max_training_seconds: int = 3600
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    replay_mode: ReplayMode = ReplayMode.INSTANT
    bar_sequences_per_episode: int = 1000
    adversarial_config: Dict[str, Any] = field(default_factory=dict)
    strategy_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    checkpoint_interval: int = 100
    checkpoint_dir: str = "/Users/jim/work/curly-succotash/coordination/runtime/checkpoints"
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    commission_pct: float = 0.1
    min_bar_window: int = 64
    max_bar_window: int = 256
    enable_adversarial: bool = True
    adversarial_intensity: float = 0.5
    randomize_episodes: bool = True
    track_leaderboard: bool = True
    enable_calibration_sweep: bool = False
    calibration_sweep_config: Optional[CalibrationSweepConfig] = None
    oos_split_policy: Optional[OOSplitPolicy] = None

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.num_episodes < 1:
            raise ValueError(f"num_episodes must be >= 1, got {self.num_episodes}")
        if self.max_training_seconds < 1:
            raise ValueError(f"max_training_seconds must be >= 1, got {self.max_training_seconds}")
        if not self.symbols:
            raise ValueError("At least one symbol must be specified")
        if not self.timeframes:
            raise ValueError("At least one timeframe must be specified")
        if not 0.0 <= self.adversarial_intensity <= 1.0:
            raise ValueError(f"adversarial_intensity must be in [0.0, 1.0], got {self.adversarial_intensity}")
        if self.checkpoint_interval < 1:
            self.checkpoint_interval = 1


@dataclass
class EpisodeResult:
    """Results from a single training episode.

    Attributes:
        episode_num: Episode number (0-indexed)
        strategy_results: Dictionary mapping strategy names to their metrics
        adversarial_stats: Statistics about adversarial agent activations
        start_time: Episode start timestamp
        end_time: Episode end timestamp
        candles_processed: Number of candles processed
        seed_used: Random seed used for this episode
        symbol: Symbol used in this episode
        timeframe: Timeframe used in this episode
        start_idx: Starting index in candle sequence
        end_idx: Ending index in candle sequence
        episode_duration_seconds: Duration of episode in seconds
        signals_generated: Total signals generated across all strategies
        trades_executed: Total trades executed across all strategies
    """
    episode_num: int
    strategy_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    adversarial_stats: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    candles_processed: int = 0
    seed_used: int = 0
    symbol: str = ""
    timeframe: Timeframe = Timeframe.ONE_HOUR
    start_idx: int = 0
    end_idx: int = 0
    episode_duration_seconds: float = 0.0
    signals_generated: int = 0
    trades_executed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert episode result to dictionary."""
        return {
            "episode_num": self.episode_num,
            "strategy_results": self.strategy_results,
            "adversarial_stats": self.adversarial_stats,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "candles_processed": self.candles_processed,
            "seed_used": self.seed_used,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "episode_duration_seconds": self.episode_duration_seconds,
            "signals_generated": self.signals_generated,
            "trades_executed": self.trades_executed,
        }


@dataclass
class TrainingResult:
    """Aggregate results from full training run.

    Attributes:
        config: Training configuration used
        episodes: List of all episode results
        best_strategy: Name of best performing strategy
        best_sharpe: Best Sharpe ratio achieved
        total_candles: Total candles processed across all episodes
        training_duration_seconds: Total training duration
        start_time: Training start timestamp
        end_time: Training end timestamp
        episodes_completed: Number of episodes actually completed
        episodes_planned: Number of episodes originally planned
        final_leaderboard: Final strategy rankings
    """
    config: TrainingConfig
    episodes: List[EpisodeResult] = field(default_factory=list)
    best_strategy: str = ""
    best_sharpe: float = 0.0
    total_candles: int = 0
    training_duration_seconds: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    episodes_completed: int = 0
    episodes_planned: int = 0
    final_leaderboard: List[Tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert training result to dictionary."""
        return {
            "config": {
                "num_episodes": self.config.num_episodes,
                "max_training_seconds": self.config.max_training_seconds,
                "symbols": self.config.symbols,
                "timeframes": [tf.value for tf in self.config.timeframes],
                "replay_mode": self.config.replay_mode.value,
                "bar_sequences_per_episode": self.config.bar_sequences_per_episode,
            },
            "episodes": [ep.to_dict() for ep in self.episodes],
            "best_strategy": self.best_strategy,
            "best_sharpe": self.best_sharpe,
            "total_candles": self.total_candles,
            "training_duration_seconds": self.training_duration_seconds,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "episodes_completed": self.episodes_completed,
            "episodes_planned": self.episodes_planned,
            "final_leaderboard": self.final_leaderboard,
        }

    def save(self, filepath: str) -> None:
        """Save training result to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[TRAINING] Results saved to {filepath}")


class SeededRandom:
    """Deterministic random number generator for reproducible episodes.

    Uses Python's random module with a fixed seed to ensure that
the same episode parameters are selected given the same seed.
    """

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

    def choice(self, options: List[Any]) -> Any:
        """Select a random element from a list."""
        return self.rng.choice(options)

    def randint(self, min_val: int, max_val: int) -> int:
        """Generate a random integer in range [min_val, max_val]."""
        return self.rng.randint(min_val, max_val)

    def random(self) -> float:
        """Generate a random float in [0.0, 1.0)."""
        return self.rng.random()

    def uniform(self, min_val: float, max_val: float) -> float:
        """Generate a random float in [min_val, max_val]."""
        return self.rng.uniform(min_val, max_val)


class TrainingHarness:
    """Orchestrates replay, adversarial agents, and strategy evaluation.

    The TrainingHarness manages the full training lifecycle:
    1. Initialize replay engine with Binance archive data
    2. Configure adversarial agents for market perturbations
    3. Run episodes with deterministic parameters
    4. Track strategy performance and maintain leaderboard
    5. Save checkpoints for resume capability
    6. Emit progress and handle graceful shutdown

    Thread Safety:
    - All state mutations are protected by _state_lock
    - Pause/resume/stop operations are thread-safe
    - Checkpoint operations are atomic

    Example:
        client = BinanceArchiveClient()
        config = TrainingConfig(num_episodes=1000)
        harness = TrainingHarness(client, config)
        result = harness.run_training()
    """

    def __init__(self, client: BinanceArchiveClient, config: TrainingConfig):
        """Initialize the training harness.

        Args:
            client: BinanceArchiveClient for data access
            config: TrainingConfig with training parameters
        """
        self.client = client
        self.config = config

        # State management
        self._state_lock = threading.Lock()
        self._is_running = False
        self._is_paused = False
        self._should_stop = False
        self._current_episode = 0

        # Episode tracking
        self.episodes: List[EpisodeResult] = []
        self._episode_results: Dict[int, EpisodeResult] = {}

        # Strategy tracking
        self._strategies: List[BaseStrategy] = []
        self._strategy_scores: Dict[str, List[float]] = {}
        self._leaderboard: List[Tuple[str, float]] = []

        # Replay and adversarial components
        self._replay_engine: Optional[ReplayEngine] = None
        self._adversarial_orchestrator: Optional[AdversarialOrchestrator] = None
        self._paper_engine: Optional[PaperTradingEngine] = None

        # Calibration and splitting components
        self._calibration_sweeper = CalibrationSweeper()
        self._oos_splitter = OOSplitter(self.config.oos_split_policy or OOSplitPolicy())
        self._last_sweep_result: Optional[SweepResult] = None
        self._last_split_result: Optional[SplitResult] = None

        # Metrics
        self._metrics_calculator = MetricsCalculator()
        self._total_candles = 0
        self._training_start_time: Optional[datetime] = None

        # Progress callbacks
        self._progress_callbacks: List[Callable[[int, int, Dict[str, Any]], None]] = []

        # Checkpointing
        self._last_checkpoint_episode = 0
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)

        # Signal handling
        self._setup_signal_handlers()

        # Initialize components
        self._setup_strategies()

        logger.info(f"[HARNESS] TrainingHarness initialized")
        logger.info(f"[HARNESS] Episodes: {config.num_episodes}, Max time: {config.max_training_seconds}s")
        logger.info(f"[HARNESS] Symbols: {config.symbols}, Timeframes: {[tf.value for tf in config.timeframes]}")
        logger.info(f"[HARNESS] Replay mode: {config.replay_mode.value}")
        logger.info(f"[HARNESS] Adversarial: {'enabled' if config.enable_adversarial else 'disabled'}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.warning(f"[HARNESS] Received signal {signum}, initiating graceful shutdown...")
            self.stop_training()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _setup_strategies(self) -> None:
        """Initialize all strategies for training."""
        strategy_config = StrategyConfig(
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
        )

        self._strategies = create_all_strategies(strategy_config)

        # Initialize strategy score tracking
        for strategy in self._strategies:
            self._strategy_scores[strategy.name] = []

        logger.info(f"[HARNESS] Initialized {len(self._strategies)} strategies")

    def _setup_adversarial_orchestrator(self, seed: int) -> Optional[AdversarialOrchestrator]:
        """Create and configure adversarial orchestrator for an episode.

        Args:
            seed: Random seed for deterministic agent behavior

        Returns:
            AdversarialOrchestrator or None if adversarial is disabled
        """
        if not self.config.enable_adversarial:
            return None

        # Use configuration to create agents or use random orchestrator
        if self.config.adversarial_config:
            agents = self._create_agents_from_config(seed)
            orchestrator = AdversarialOrchestrator(agents)
        else:
            orchestrator = create_random_orchestrator(
                seed=seed,
                intensity=self.config.adversarial_intensity
            )

        return orchestrator

    def _create_agents_from_config(self, seed: int) -> List[AdversarialAgent]:
        """Create adversarial agents from configuration dictionary.

        Args:
            seed: Random seed for agent initialization

        Returns:
            List of configured AdversarialAgent instances
        """
        agents = []
        agent_registry = {
            "noise": NoiseInjectionAgent,
            "gap": GapInjectionAgent,
            "regime": RegimeShiftAgent,
            "flash_crash": FlashCrashAgent,
            "latency": LatencyInjectionAgent,
        }

        for agent_name, agent_params in self.config.adversarial_config.items():
            if agent_name not in agent_registry:
                logger.warning(f"[HARNESS] Unknown agent type: {agent_name}")
                continue

            agent_class = agent_registry[agent_name]
            config = AgentConfig(
                intensity=agent_params.get("intensity", self.config.adversarial_intensity),
                seed=seed + len(agents),
                enabled=agent_params.get("enabled", True),
                params=agent_params.get("params", {})
            )
            agents.append(agent_class(config))

        return agents

    def _setup_replay_engine(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime,
        seed: Optional[int] = None
    ) -> ReplayEngine:
        """Configure and create replay engine for an episode.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            start_time: Episode start time
            end_time: Episode end time
            seed: Optional seed for deterministic replay

        Returns:
            Configured ReplayEngine instance
        """
        replay_config = ReplayConfig(
            mode=self.config.replay_mode,
            symbols=[symbol],
            timeframes=[timeframe],
            start_time=start_time,
            end_time=end_time,
            seed=seed,
        )

        engine = ReplayEngine(self.client, replay_config)
        return engine

    def run_training(self) -> TrainingResult:
        """Run the main training loop.

        Executes the full training run across all configured episodes,
        handling pause/resume, checkpoints, and graceful shutdown.

        Returns:
            TrainingResult with aggregate results from all episodes
        """
        with self._state_lock:
            if self._is_running:
                raise RuntimeError("Training is already running")
            self._is_running = True
            self._should_stop = False
            self._is_paused = False

        self._training_start_time = datetime.now(timezone.utc)
        logger.info(f"[TRAINING] Starting training run at {self._training_start_time}")

        try:
            for episode_num in range(self.config.num_episodes):
                with self._state_lock:
                    if self._should_stop:
                        logger.info(f"[TRAINING] Stop requested after {episode_num} episodes")
                        break

                    # Handle pause
                    while self._is_paused and not self._should_stop:
                        time.sleep(0.1)

                    if self._should_stop:
                        break

                    self._current_episode = episode_num

                # Check training timeout
                elapsed = (datetime.now(timezone.utc) - self._training_start_time).total_seconds()
                if elapsed > self.config.max_training_seconds:
                    logger.info(f"[TRAINING] Timeout reached after {elapsed:.1f}s, {episode_num} episodes completed")
                    break

                # Run episode
                seed = episode_num  # Deterministic seed based on episode number
                result = self.run_single_episode(episode_num, seed)
                self.episodes.append(result)

                # Update leaderboard
                if self.config.track_leaderboard:
                    self._update_leaderboard(result)

                # Emit progress
                self._emit_progress(episode_num, self.config.num_episodes, result)

                # Checkpoint if needed
                if (episode_num + 1) % self.config.checkpoint_interval == 0:
                    self._save_checkpoint_internal()

        except Exception as e:
            logger.error(f"[TRAINING] Error during training: {e}")
            raise
        finally:
            with self._state_lock:
                self._is_running = False

            # Final checkpoint
            if self.episodes:
                self._save_checkpoint_internal()

        # Build and return final result
        return self._build_training_result()

    def run_single_episode(self, episode_num: int, seed: int) -> EpisodeResult:
        """Run a single training episode.

        Args:
            episode_num: Episode number (0-indexed)
            seed: Random seed for deterministic episode

        Returns:
            EpisodeResult with metrics and statistics
        """
        start_time = datetime.now(timezone.utc)

        # Initialize seeded random for this episode
        rng = SeededRandom(seed)

        # Select episode parameters
        if self.config.randomize_episodes:
            symbol = rng.choice(self.config.symbols)
            timeframe = rng.choice(self.config.timeframes)
            bar_window = rng.randint(self.config.min_bar_window, self.config.max_bar_window)
        else:
            symbol = self.config.symbols[0]
            timeframe = self.config.timeframes[0]
            bar_window = self.config.bar_sequences_per_episode

        # Get date range for symbol/timeframe
        db_start, db_end = self.client.get_date_range(symbol, timeframe)

        if db_start == db_end:
            logger.warning(f"[EPISODE {episode_num}] No data available for {symbol} {timeframe.value}")
            return EpisodeResult(
                episode_num=episode_num,
                seed_used=seed,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
            )

        # Calculate episode window
        available_candles = self.client.get_candle_count(symbol, timeframe)
        if available_candles <= bar_window:
            start_idx = 0
            end_idx = available_candles
        else:
            max_start = available_candles - bar_window
            start_idx = rng.randint(0, max_start)
            end_idx = start_idx + bar_window

        # Setup replay engine
        # Note: We need to map indices to timestamps
        # For simplicity, we'll query the candles and use the timestamps
        candles = self.client.query_candles(symbol, timeframe, db_start, db_end)
        if start_idx < len(candles) and end_idx <= len(candles):
            episode_candles = candles[start_idx:end_idx]
            episode_start = episode_candles[0].timestamp
            episode_end = episode_candles[-1].timestamp
        else:
            episode_start = db_start
            episode_end = db_end

        self._replay_engine = self._setup_replay_engine(
            symbol=symbol,
            timeframe=timeframe,
            start_time=episode_start,
            end_time=episode_end,
            seed=seed
        )

        # Setup adversarial orchestrator
        self._adversarial_orchestrator = self._setup_adversarial_orchestrator(seed)

        # Setup paper trading engine for this episode
        paper_config = PaperTradingConfig(
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
            commission_pct=self.config.commission_pct,
        )
        self._paper_engine = PaperTradingEngine(paper_config)
        self._paper_engine.initialize_strategies([symbol], [timeframe])

        # Process episode candles
        strategy_results, adversarial_stats = self._process_episode_candles(
            symbol, timeframe, episode_start, episode_end
        )

        # Handle OOS splitting and calibration sweep if enabled
        if self.config.oos_split_policy or self.config.enable_calibration_sweep:
            self._handle_episode_calibration(symbol, timeframe, episode_start, episode_end, seed)

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Count signals and trades
        signals_generated = sum(
            r.get("num_signals", 0) for r in strategy_results.values()
        )
        trades_executed = sum(
            r.get("num_trades", 0) for r in strategy_results.values()
        )

        result = EpisodeResult(
            episode_num=episode_num,
            strategy_results=strategy_results,
            adversarial_stats=adversarial_stats,
            start_time=start_time,
            end_time=end_time,
            candles_processed=len(episode_candles) if 'episode_candles' in dir() else 0,
            seed_used=seed,
            symbol=symbol,
            timeframe=timeframe,
            start_idx=start_idx,
            end_idx=end_idx,
            episode_duration_seconds=duration,
            signals_generated=signals_generated,
            trades_executed=trades_executed,
        )

        # Update total candles
        self._total_candles += result.candles_processed

        logger.info(
            f"[EPISODE {episode_num}] Completed: {symbol} {timeframe.value} | "
            f"Candles: {result.candles_processed} | Duration: {duration:.2f}s | "
            f"Signals: {signals_generated} | Trades: {trades_executed}"
        )

        return result

    def _process_episode_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """Process candles for a single episode."""
        # Query candles for this episode
        candles = self.client.query_candles(symbol, timeframe, start_time, end_time)

        if not candles:
            return {}, {}

        # Process each candle through adversarial agents and strategies
        for candle in candles:
            # Apply adversarial perturbations if enabled
            if self._adversarial_orchestrator:
                candle = self._adversarial_orchestrator.apply_to_stream(candle)

            # Process through paper trading engine
            self._paper_engine.process_candle_sync(candle)

        # Calculate strategy results
        strategy_results = self._calculate_rewards(symbol, timeframe, candles)

        # Get adversarial stats
        adversarial_stats = {}
        if self._adversarial_orchestrator:
            adversarial_stats = self._adversarial_orchestrator.get_all_stats()

        return strategy_results, adversarial_stats

    def _handle_episode_calibration(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime,
        seed: int
    ) -> None:
        """Handle OOS splitting and calibration sweep for an episode."""
        # Query all candles in the window
        candles = self.client.query_candles(symbol, timeframe, start_time, end_time)
        if not candles:
            return

        # Get regime labels for the candles
        regime_labels = self._get_regime_labels(candles)

        # Perform OOS splitting if policy is provided
        if self.config.oos_split_policy:
            try:
                self._last_split_result = self._oos_splitter.create_splits(candles, regime_labels)
                logger.info(f"[HARNESS] Created OOS splits for episode: "
                           f"train={self._last_split_result.train.n_samples}, "
                           f"cal={self._last_split_result.calibration.n_samples}, "
                           f"test={self._last_split_result.test.n_samples}")
            except Exception as e:
                logger.warning(f"[HARNESS] OOS splitting failed for episode: {e}")

        # Perform calibration sweep if enabled
        if self.config.enable_calibration_sweep:
            sweep_config = self.config.calibration_sweep_config or CalibrationSweepConfig(
                symbols=[symbol],
                timeframes=[timeframe],
                random_seed=seed,
            )

            # Use the calibration set from OOS split if available, otherwise use all candles
            cal_candles = candles
            if self._last_split_result:
                cal_candles = self._last_split_result.calibration.data

            # Prepare synthetic data for sweep (using actual prices for realistic sweep)
            # In a real HRM scenario, this would use model predictions and confidences
            synthetic_data = self._prepare_sweep_data(cal_candles)

            try:
                self._last_sweep_result = self._calibration_sweeper.run_sweep(sweep_config, synthetic_data)
                logger.info(f"[HARNESS] Calibration sweep completed for episode. Best ECE: {self._last_sweep_result.best_metrics.expected_calibration_error:.4f}")
            except Exception as e:
                logger.warning(f"[HARNESS] Calibration sweep failed for episode: {e}")

    def _get_regime_labels(self, candles: List[Candle]) -> List[str]:
        """Get volatility-based regime labels for candles."""
        if not candles:
            return []

        # Simple volatility-based regime classification
        closes = np.array([c.close for c in candles])
        returns = np.diff(closes) / closes[:-1]
        
        # Calculate rolling volatility
        window = min(20, len(returns))
        if window < 2:
            return ["VOL_NORMAL"] * len(candles)
            
        vol = np.zeros(len(returns))
        for i in range(window, len(returns) + 1):
            vol[i-1] = np.std(returns[i-window:i])
            
        # Pad beginning
        vol[:window-1] = vol[window-1]
        
        # Classify by volatility percentiles
        low_thresh = np.percentile(vol, 25)
        high_thresh = np.percentile(vol, 75)
        extreme_thresh = np.percentile(vol, 95)
        
        labels = []
        for v in vol:
            if v >= extreme_thresh:
                labels.append("VOL_EXTREME")
            elif v >= high_thresh:
                labels.append("VOL_HIGH")
            elif v >= low_thresh:
                labels.append("VOL_NORMAL")
            else:
                labels.append("VOL_LOW")
                
        # Pad last label to match candle count
        labels.append(labels[-1])
        
        return labels

    def _prepare_sweep_data(self, candles: List[Candle]) -> Dict[str, Any]:
        """Prepare data for calibration sweep from actual candles."""
        # This is a mock implementation since we don't have a real HRM model yet.
        # It generates "predictions" and "confidences" correlated with actual future returns.
        n = len(candles)
        if n < 2:
            return {"predictions": [], "confidences": [], "actuals": []}

        closes = np.array([c.close for c in candles])
        future_returns = np.zeros(n)
        future_returns[:-1] = (closes[1:] - closes[:-1]) / closes[:-1]

        # "Predictions" are correlated with future returns
        noise_level = 0.5
        predictions = future_returns + np.random.normal(0, noise_level * np.std(future_returns), n)
        
        # "Confidences" are absolute magnitude of predictions (scaled to 0-1)
        confidences = np.abs(predictions)
        if np.max(confidences) > 0:
            confidences = confidences / np.max(confidences)
        
        # "Actuals" are 1 if future return > 0, else 0
        actuals = (future_returns > 0).astype(float)

        return {
            "predictions": predictions.tolist(),
            "confidences": confidences.tolist(),
            "actuals": actuals.tolist(),
        }

    def _calculate_rewards(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate strategy rewards and metrics.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            candles: List of processed candles

        Returns:
            Dictionary mapping strategy names to their metrics
        """
        results = {}

        for strategy_name, tracker in self._paper_engine.trackers.get(symbol, {}).get(timeframe.value, {}).items():
            strategy = tracker.strategy

            # Build equity curve from history
            equity_curve = tracker.equity_history

            if not equity_curve:
                results[strategy_name] = {
                    "strategy_name": strategy_name,
                    "symbol": symbol,
                    "timeframe": timeframe.value,
                    "net_pnl": 0.0,
                    "total_return_pct": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "win_rate": 0.0,
                    "num_trades": 0,
                    "num_signals": len(strategy.signals),
                }
                continue

            # Calculate metrics using BacktestEngine's calculator
            start_date = candles[0].timestamp if candles else datetime.now(timezone.utc)
            end_date = candles[-1].timestamp if candles else datetime.now(timezone.utc)

            metrics = self._metrics_calculator.calculate_metrics(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                trades=strategy.trades,
                equity_curve=equity_curve,
                initial_capital=self.config.initial_capital,
                start_date=start_date,
                end_date=end_date,
            )

            results[strategy_name] = {
                "strategy_name": metrics.strategy_name,
                "symbol": metrics.symbol,
                "timeframe": metrics.timeframe.value,
                "net_pnl": metrics.net_pnl,
                "total_return_pct": metrics.total_return_pct,
                "cagr": metrics.cagr,
                "max_drawdown": metrics.max_drawdown,
                "sharpe_ratio": metrics.sharpe_ratio,
                "win_rate": metrics.win_rate,
                "avg_trade_pnl": metrics.avg_trade_pnl,
                "num_trades": metrics.num_trades,
                "profit_factor": metrics.profit_factor,
                "num_signals": len(strategy.signals),
            }

        return results

    def _update_leaderboard(self, episode_result: EpisodeResult) -> None:
        """Update strategy leaderboard based on episode results.

        Args:
            episode_result: Results from the completed episode
        """
        # Extract Sharpe ratios from episode results
        for strategy_name, metrics in episode_result.strategy_results.items():
            sharpe = metrics.get("sharpe_ratio", 0.0)
            if strategy_name not in self._strategy_scores:
                self._strategy_scores[strategy_name] = []
            self._strategy_scores[strategy_name].append(sharpe)

        # Calculate average Sharpe for each strategy
        avg_scores = {}
        for strategy_name, scores in self._strategy_scores.items():
            if scores:
                avg_scores[strategy_name] = sum(scores) / len(scores)

        # Sort by average Sharpe ratio (descending)
        self._leaderboard = sorted(
            avg_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

    def _emit_progress(self, episode_num: int, total_episodes: int, result: EpisodeResult) -> None:
        """Emit training progress information.

        Args:
            episode_num: Current episode number
            total_episodes: Total number of episodes
            result: Results from current episode
        """
        progress_pct = ((episode_num + 1) / total_episodes) * 100
        elapsed = (datetime.now(timezone.utc) - self._training_start_time).total_seconds() if self._training_start_time else 0

        # Calculate best strategy in this episode
        best_strategy = ""
        best_sharpe = -float('inf')
        for name, metrics in result.strategy_results.items():
            sharpe = metrics.get("sharpe_ratio", 0.0)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_strategy = name

        logger.info(
            f"[PROGRESS] Episode {episode_num + 1}/{total_episodes} ({progress_pct:.1f}%) | "
            f"Elapsed: {elapsed:.1f}s | Best: {best_strategy} (Sharpe: {best_sharpe:.2f})"
        )

        # Call registered progress callbacks
        progress_info = {
            "episode": episode_num,
            "total": total_episodes,
            "progress_pct": progress_pct,
            "elapsed_seconds": elapsed,
            "best_strategy": best_strategy,
            "best_sharpe": best_sharpe,
            "candles_processed": result.candles_processed,
        }

        for callback in self._progress_callbacks:
            try:
                callback(episode_num, total_episodes, progress_info)
            except Exception as e:
                logger.error(f"[PROGRESS] Callback error: {e}")

    def _build_training_result(self) -> TrainingResult:
        """Build final TrainingResult from accumulated episodes.

        Returns:
            TrainingResult with aggregate results
        """
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self._training_start_time).total_seconds() if self._training_start_time else 0

        # Find best strategy overall
        best_strategy = ""
        best_sharpe = -float('inf')

        for strategy_name, scores in self._strategy_scores.items():
            if scores:
                avg_sharpe = sum(scores) / len(scores)
                if avg_sharpe > best_sharpe:
                    best_sharpe = avg_sharpe
                    best_strategy = strategy_name

        result = TrainingResult(
            config=self.config,
            episodes=self.episodes,
            best_strategy=best_strategy,
            best_sharpe=best_sharpe,
            total_candles=self._total_candles,
            training_duration_seconds=duration,
            start_time=self._training_start_time,
            end_time=end_time,
            episodes_completed=len(self.episodes),
            episodes_planned=self.config.num_episodes,
            final_leaderboard=self._leaderboard,
        )

        return result

    def _save_checkpoint_internal(self) -> None:
        """Save internal checkpoint state."""
        if not self.episodes:
            return

        checkpoint_path = os.path.join(
            self.config.checkpoint_dir,
            f"checkpoint_{self._current_episode}.pkl"
        )

        checkpoint_data = {
            "config": self.config,
            "episodes": self.episodes,
            "current_episode": self._current_episode,
            "strategy_scores": self._strategy_scores,
            "leaderboard": self._leaderboard,
            "total_candles": self._total_candles,
        }

        try:
            with open(checkpoint_path, 'wb') as f:
                pickle.dump(checkpoint_data, f)
            self._last_checkpoint_episode = self._current_episode
            logger.info(f"[CHECKPOINT] Saved to {checkpoint_path}")
        except Exception as e:
            logger.error(f"[CHECKPOINT] Failed to save: {e}")

    def save_checkpoint(self, filename: str) -> None:
        """Save checkpoint to specified filename.

        Args:
            filename: Path to save checkpoint
        """
        checkpoint_data = {
            "config": self.config,
            "episodes": self.episodes,
            "current_episode": self._current_episode,
            "strategy_scores": self._strategy_scores,
            "leaderboard": self._leaderboard,
            "total_candles": self._total_candles,
        }

        with open(filename, 'wb') as f:
            pickle.dump(checkpoint_data, f)

        logger.info(f"[CHECKPOINT] Saved to {filename}")

    def load_checkpoint(self, filename: str) -> None:
        """Load checkpoint from specified filename.

        Args:
            filename: Path to load checkpoint from
        """
        with open(filename, 'rb') as f:
            checkpoint_data = pickle.load(f)

        self.episodes = checkpoint_data.get("episodes", [])
        self._current_episode = checkpoint_data.get("current_episode", 0)
        self._strategy_scores = checkpoint_data.get("strategy_scores", {})
        self._leaderboard = checkpoint_data.get("leaderboard", [])
        self._total_candles = checkpoint_data.get("total_candles", 0)

        logger.info(f"[CHECKPOINT] Loaded from {filename}: {len(self.episodes)} episodes, "
                   f"resuming from episode {self._current_episode + 1}")

    def get_best_strategy(self) -> Tuple[str, float]:
        """Get the best performing strategy and its Sharpe ratio.

        Returns:
            Tuple of (strategy_name, sharpe_ratio)
        """
        if not self._leaderboard:
            return ("", 0.0)
        return self._leaderboard[0]

    def get_leaderboard(self) -> List[Tuple[str, float]]:
        """Get the full strategy leaderboard.

        Returns:
            List of (strategy_name, average_sharpe) tuples sorted by Sharpe
        """
        return self._leaderboard.copy()

    def pause_training(self) -> None:
        """Pause the training loop."""
        with self._state_lock:
            if self._is_running and not self._is_paused:
                self._is_paused = True
                logger.info("[HARNESS] Training paused")

    def resume_training(self) -> None:
        """Resume the training loop."""
        with self._state_lock:
            if self._is_running and self._is_paused:
                self._is_paused = False
                logger.info("[HARNESS] Training resumed")

    def stop_training(self) -> None:
        """Stop the training loop gracefully."""
        with self._state_lock:
            self._should_stop = True
            logger.info("[HARNESS] Training stop requested")

    def is_running(self) -> bool:
        """Check if training is currently running.

        Returns:
            True if training is running
        """
        with self._state_lock:
            return self._is_running

    def is_paused(self) -> bool:
        """Check if training is currently paused.

        Returns:
            True if training is paused
        """
        with self._state_lock:
            return self._is_paused

    def get_progress(self) -> Dict[str, Any]:
        """Get current training progress.

        Returns:
            Dictionary with progress information
        """
        with self._state_lock:
            elapsed = 0.0
            if self._training_start_time:
                elapsed = (datetime.now(timezone.utc) - self._training_start_time).total_seconds()

            progress_pct = 0.0
            if self.config.num_episodes > 0:
                progress_pct = (self._current_episode / self.config.num_episodes) * 100

            return {
                "is_running": self._is_running,
                "is_paused": self._is_paused,
                "current_episode": self._current_episode,
                "total_episodes": self.config.num_episodes,
                "progress_pct": progress_pct,
                "elapsed_seconds": elapsed,
                "episodes_completed": len(self.episodes),
                "total_candles": self._total_candles,
                "leaderboard": self._leaderboard[:5] if self._leaderboard else [],
            }

    def register_progress_callback(self, callback: Callable[[int, int, Dict[str, Any]], None]) -> None:
        """Register a callback for training progress updates.

        Args:
            callback: Function called with (episode_num, total_episodes, progress_info)
        """
        self._progress_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive harness status.

        Returns:
            Dictionary with full status information
        """
        best_strategy, best_sharpe = self.get_best_strategy()

        return {
            "is_running": self._is_running,
            "is_paused": self._is_paused,
            "current_episode": self._current_episode,
            "total_episodes": self.config.num_episodes,
            "episodes_completed": len(self.episodes),
            "total_candles": self._total_candles,
            "best_strategy": best_strategy,
            "best_sharpe": best_sharpe,
            "leaderboard": self._leaderboard,
            "config": {
                "symbols": self.config.symbols,
                "timeframes": [tf.value for tf in self.config.timeframes],
                "replay_mode": self.config.replay_mode.value,
                "enable_adversarial": self.config.enable_adversarial,
            },
        }


def create_training_harness(
    duckdb_path: Optional[str] = None,
    num_episodes: int = 1000,
    symbols: Optional[List[str]] = None,
    timeframes: Optional[List[Timeframe]] = None,
    enable_adversarial: bool = True,
) -> TrainingHarness:
    """Factory function to create a TrainingHarness with sensible defaults.

    Args:
        duckdb_path: Path to DuckDB database (uses default if None)
        num_episodes: Number of training episodes
        symbols: List of symbols (uses default if None)
        timeframes: List of timeframes (uses default if None)
        enable_adversarial: Whether to enable adversarial training

    Returns:
        Configured TrainingHarness instance

    Example:
        harness = create_training_harness(
            num_episodes=5000,
            symbols=["BTCUSDT", "ETHUSDT"],
            enable_adversarial=True
        )
        result = harness.run_training()
    """
    from .binance_client import BinanceArchiveConfig

    # Create client
    config = BinanceArchiveConfig()
    if duckdb_path:
        config.duckdb_path = duckdb_path

    client = BinanceArchiveClient(config)

    # Create training config
    training_config = TrainingConfig(
        num_episodes=num_episodes,
        symbols=symbols or ["BTCUSDT", "ETHUSDT"],
        timeframes=timeframes or [Timeframe.ONE_HOUR],
        enable_adversarial=enable_adversarial,
    )

    return TrainingHarness(client, training_config)
