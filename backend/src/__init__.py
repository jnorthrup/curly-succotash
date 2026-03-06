"""
Curly Succotash Trading Simulator Backend

This package provides a comprehensive trading simulation platform with:
- Live paper trading with Coinbase market data
- Historical backtesting
- Binance archive replay for historical data
- Adversarial training with market perturbations
- Multi-strategy evaluation and ranking
"""

# Core models
from .models import (
    Candle,
    Signal,
    SignalType,
    Timeframe,
    Trade,
    Position,
    PerformanceMetrics,
    SimulatorConfig,
)

# Market data clients
from .coinbase_client import (
    CoinbaseMarketDataClient,
    SafetyEnforcement,
)

# Binance archive components (new)
from .binance_client import (
    BinanceArchiveClient,
    BinanceArchiveConfig,
    CandleSchema,
)

from .archive_ingester import (
    ArchiveIngester,
)

from .replay_engine import (
    ReplayEngine,
    ReplayConfig,
    ReplayMode,
    ReplayStatus,
)

# Adversarial training components (new)
from .adversarial_agents import (
    AdversarialAgent,
    AdversarialOrchestrator,
    AgentConfig,
    NoiseInjectionAgent,
    GapInjectionAgent,
    RegimeShiftAgent,
    FlashCrashAgent,
    LatencyInjectionAgent,
    create_agent,
    create_random_orchestrator,
    AGENT_REGISTRY,
)

from .training_harness import (
    TrainingHarness,
    TrainingConfig,
    TrainingResult,
    EpisodeResult,
    SeededRandom,
    create_training_harness,
)

# Data ingestion
from .data_ingestion import (
    DataIngestionService,
    IngestionConfig,
    IngestionMode,
    CandleBuffer,
    USDValuationService,
)

# Trading engines
from .paper_trading import (
    PaperTradingEngine,
    PaperTradingConfig,
    SignalEmitter,
)

from .backtesting import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    MetricsCalculator,
)

from .hrm_shadow import (
    HRMShadowEngine,
    ShadowConfig,
    ShadowMode,
)

from .killswitch import (
    DrawdownKillSwitch,
    KillSwitchConfig,
    KillSwitchState,
)

from .scoreboard import (
    ScoreboardGenerator,
    DailyScoreboard,
)

# Strategy components
from .strategies import (
    BaseStrategy,
    StrategyConfig,
    STRATEGY_REGISTRY,
    create_all_strategies,
)

from .indicators import (
    IndicatorResult,
)

from .bullpen import (
    BullpenAggregator,
    RankingMetric,
    BullpenFilter,
)

# Main simulator
from .simulator import (
    CoinbaseTradingSimulator,
    SimulatorMode,
    SimulatorState,
    get_simulator,
    reset_simulator,
)

__version__ = "1.0.0"
__all__ = [
    # Core models
    "Candle",
    "Signal",
    "SignalType",
    "Timeframe",
    "Trade",
    "Position",
    "PerformanceMetrics",
    "SimulatorConfig",

    # Market data
    "CoinbaseMarketDataClient",
    "SafetyEnforcement",

    # Binance archive (new)
    "BinanceArchiveClient",
    "BinanceArchiveConfig",
    "CandleSchema",
    "ArchiveIngester",

    # Replay engine (new)
    "ReplayEngine",
    "ReplayConfig",
    "ReplayMode",
    "ReplayStatus",

    # Adversarial agents (new)
    "AdversarialAgent",
    "AdversarialOrchestrator",
    "AgentConfig",
    "NoiseInjectionAgent",
    "GapInjectionAgent",
    "RegimeShiftAgent",
    "FlashCrashAgent",
    "LatencyInjectionAgent",
    "create_agent",
    "create_random_orchestrator",
    "AGENT_REGISTRY",

    # Training harness (new)
    "TrainingHarness",
    "TrainingConfig",
    "TrainingResult",
    "EpisodeResult",
    "SeededRandom",
    "create_training_harness",

    # Data ingestion
    "DataIngestionService",
    "IngestionConfig",
    "IngestionMode",
    "CandleBuffer",
    "USDValuationService",

    # Trading engines
    "PaperTradingEngine",
    "PaperTradingConfig",
    "SignalEmitter",
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "MetricsCalculator",
    "HRMShadowEngine",
    "ShadowConfig",
    "ShadowMode",
    "DrawdownKillSwitch",
    "KillSwitchConfig",
    "KillSwitchState",
    "ScoreboardGenerator",
    "DailyScoreboard",

    # Strategies
    "BaseStrategy",
    "StrategyConfig",
    "STRATEGY_REGISTRY",
    "create_all_strategies",

    # Indicators
    "IndicatorResult",

    # Bullpen
    "BullpenAggregator",
    "RankingMetric",
    "BullpenFilter",

    # Main simulator
    "CoinbaseTradingSimulator",
    "SimulatorMode",
    "SimulatorState",
    "get_simulator",
    "reset_simulator",
]
