# Binance Replay + Adversarial Training System

A high-performance historical data replay and adversarial training framework for robust trading strategy development.

## Overview

The Binance Replay system provides:

- **Historical Data Access**: Efficient DuckDB-based storage and querying of Binance Vision archives
- **High-Throughput Replay**: Stream historical candles at configurable speeds (real-time to instant)
- **Adversarial Training**: Inject market perturbations (noise, gaps, flash crashes, regime shifts) to train robust strategies
- **Multi-Episode Training**: Episode-based training with deterministic seeding and checkpoint/resume capability
- **Strategy Leaderboard**: Track and rank strategy performance across episodes

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BINANCE REPLAY SYSTEM                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐   │
│  │  Binance Vision │───▶│ ArchiveIngester │───▶│     DuckDB        │   │
│  │   (CSV.gz)      │    │  (Download)     │    │  (Local Storage)  │   │
│  └─────────────────┘    └─────────────────┘    └───────────────────┘   │
│                                                           │             │
│                                                           ▼             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐   │
│  │ TrainingHarness │◄───│  ReplayEngine   │◄───│ BinanceArchive    │   │
│  │  (Orchestrator) │    │  (Streaming)    │    │     Client        │   │
│  └────────┬────────┘    └─────────────────┘    └───────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                    AdversarialOrchestrator                      │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │    │
│  │  │  Noise   │ │   Gap    │ │  Regime  │ │  Flash   │          │    │
│  │  │Injection │ │Injection │ │  Shift   │ │  Crash   │          │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │    │
│  └────────────────────────────────────────────────────────────────┘    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐   │
│  │  Strategy Pool  │───▶│ Paper Trading   │───▶│  Leaderboard      │   │
│  │   (12 agents)   │    │   Engine        │    │  (Rankings)       │   │
│  └─────────────────┘    └─────────────────┘    └───────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Setup

```python
from src.binance_client import BinanceArchiveClient, BinanceArchiveConfig
from src.archive_ingester import ArchiveIngester
from src.training_harness import TrainingHarness, TrainingConfig

# Create client with default configuration
client = BinanceArchiveClient()

# Or with custom configuration
config = BinanceArchiveConfig(
    duckdb_path="/path/to/your/data.duckdb",
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    timeframes=["1h", "4h", "1d"],
)
client = BinanceArchiveClient(config)
```

### 2. Ingest Historical Data

```python
from datetime import datetime, timezone

# Create ingester
ingester = ArchiveIngester(client)

# Ingest specific symbol/timeframe
downloaded, inserted = ingester.ingest_symbol_timeframe(
    symbol="BTCUSDT",
    timeframe="1h",
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
)

# Or ingest all configured symbols/timeframes
stats = ingester.ingest_all_configured()
print(f"Downloaded: {stats['total_downloaded']}, Inserted: {stats['total_inserted']}")
```

### 3. Run Adversarial Training

```python
from src.training_harness import create_training_harness

# Create training harness with sensible defaults
harness = create_training_harness(
    num_episodes=1000,
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=[Timeframe.ONE_HOUR],
    enable_adversarial=True,
)

# Run training
result = harness.run_training()

# View results
print(f"Best Strategy: {result.best_strategy} (Sharpe: {result.best_sharpe:.2f})")
print(f"Episodes: {result.episodes_completed}")
print(f"Total Candles: {result.total_candles}")
```

### 4. Use Replay Engine Standalone

```python
from src.replay_engine import ReplayEngine, ReplayConfig, ReplayMode
from src.models import Timeframe

# Configure replay
config = ReplayConfig(
    mode=ReplayMode.COMPRESSED,  # or REALTIME, INSTANT, STEP_THROUGH
    compression_factor=100.0,     # 100x speed for COMPRESSED mode
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=[Timeframe.ONE_HOUR],
    start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2024, 6, 1, tzinfo=timezone.utc),
)

# Create and start replay engine
engine = ReplayEngine(client, config)

# Set up callbacks
def on_candle(candle):
    print(f"{candle.symbol} @ {candle.timestamp}: ${candle.close:.2f}")

def on_complete():
    print("Replay complete!")

engine.set_callbacks(on_candle, on_complete)
engine.start()
```

## Configuration Reference

### BinanceArchiveConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | str | Binance Vision URL | Base URL for archive downloads |
| `cache_dir` | str | `/tmp/binance_cache` | Directory for cached CSV files |
| `duckdb_path` | str | `hrm_data.duckdb` | Path to DuckDB database |
| `start_month` | str | `2026-01` | Starting month for ingestion |
| `symbols` | List[str] | Major pairs | Trading pairs to track |
| `timeframes` | List[str] | `["1m", "5m", "1h"]` | Candle timeframes |

### ReplayConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | ReplayMode | `COMPRESSED` | Replay speed mode |
| `compression_factor` | float | `100.0` | Speed multiplier (1-1000) |
| `symbols` | List[str] | `[]` | Symbols to replay |
| `timeframes` | List[Timeframe] | `[ONE_HOUR]` | Timeframes to replay |
| `start_time` | datetime | `None` | Replay start timestamp |
| `end_time` | datetime | `None` | Replay end timestamp |
| `seed` | int | `None` | Random seed for deterministic replay |

### ReplayMode

- **`REALTIME`**: Actual delays between candles (1x speed)
- **`COMPRESSED`**: Fast-forward with time compression (Nx speed)
- **`STEP_THROUGH`**: Manual stepping for debugging/analysis
- **`INSTANT`**: Process as fast as possible (max throughput)

### TrainingConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `num_episodes` | int | `10000` | Total training episodes |
| `max_training_seconds` | int | `3600` | Maximum training duration |
| `symbols` | List[str] | `["BTCUSDT"]` | Symbols to train on |
| `timeframes` | List[Timeframe] | `[ONE_HOUR]` | Timeframes to use |
| `replay_mode` | ReplayMode | `INSTANT` | Replay speed for training |
| `enable_adversarial` | bool | `True` | Enable adversarial agents |
| `adversarial_intensity` | float | `0.5` | Agent intensity (0.0-1.0) |
| `checkpoint_interval` | int | `100` | Episodes between checkpoints |
| `bar_sequences_per_episode` | int | `1000` | Candles per episode |

## Adversarial Agents

### Available Agents

1. **NoiseInjectionAgent**: Adds random price/volume noise
   - Simulates bid-ask spreads and tick variations
   - Configurable noise type (gaussian/uniform) and magnitude

2. **GapInjectionAgent**: Creates artificial gaps and missing data
   - Simulates flash crashes and pumps
   - Configurable gap size and probability

3. **RegimeShiftAgent**: Simulates market regime changes
   - Trending up/down, choppy, high/low volatility
   - Duration-based regime persistence

4. **FlashCrashAgent**: Simulates flash crash events
   - Sharp drops followed by recovery patterns
   - Configurable crash magnitude and duration

5. **LatencyInjectionAgent**: Simulates network effects
   - Delayed delivery and out-of-order candles
   - Configurable latency parameters

### Agent Configuration

```python
from src.adversarial_agents import AgentConfig, NoiseInjectionAgent, AdversarialOrchestrator

# Configure noise agent
noise_config = AgentConfig(
    intensity=0.5,              # Perturbation strength (0.0-1.0)
    seed=42,                    # Random seed for reproducibility
    enabled=True,
    params={
        "price_noise_pct": 0.001,    # 0.1% price noise
        "volume_noise_pct": 0.05,    # 5% volume noise
        "noise_type": "gaussian",
    }
)

# Create orchestrator with multiple agents
orchestrator = AdversarialOrchestrator([
    NoiseInjectionAgent(noise_config),
    GapInjectionAgent(AgentConfig(intensity=0.3, params={
        "gap_probability": 0.001,
        "max_gap_size": 5,
    })),
])

# Apply to candles
perturbed_candles = orchestrator.apply_all(candles)

# Or apply to stream
for candle in candle_stream:
    perturbed = orchestrator.apply_to_stream(candle)
```

## Integration with Simulator

The simulator now supports training mode:

```python
from src.simulator import CoinbaseTradingSimulator, SimulatorMode

# Create simulator
sim = CoinbaseTradingSimulator()

# Start training mode
result = await sim.start_training_mode(
    num_episodes=1000,
    symbols=["BTCUSDT", "ETHUSDT"],
    enable_adversarial=True,
    adversarial_intensity=0.5,
)

# Check training status
status = sim.get_training_status()
print(f"Episode: {status['current_episode']}/{status['total_episodes']}")

# Get leaderboard
leaderboard = sim.get_training_leaderboard()
for rank, (strategy, score) in enumerate(leaderboard[:5], 1):
    print(f"{rank}. {strategy}: {score:.2f}")

# Pause/resume/stop
sim.pause_training()
sim.resume_training()
sim.stop_training()
```

## Integration with Data Ingestion

The data ingestion service supports REPLAY mode:

```python
from src.data_ingestion import DataIngestionService, IngestionConfig, IngestionMode
from src.replay_engine import ReplayConfig, ReplayMode

# Create replay configuration
replay_config = ReplayConfig(
    mode=ReplayMode.COMPRESSED,
    compression_factor=100.0,
    symbols=["BTCUSDT", "ETHUSDT"],
)

# Create ingestion service in REPLAY mode
service = DataIngestionService(IngestionConfig(
    mode=IngestionMode.REPLAY,
    symbols=["BTCUSDT", "ETHUSDT"],
    replay_client=client,           # BinanceArchiveClient
    replay_config=replay_config,
))

# Register callbacks
service.register_candle_callback(on_candle)

# Start replay
await service.start()

# Get replay status
status = service.get_replay_status()
print(f"Progress: {status['progress_pct']:.1f}%")

# Control replay
service.pause_replay()
service.resume_replay()
service.stop_replay()
```

## Example Usage

See [`examples/training_example.py`](examples/training_example.py) for a complete working example that demonstrates:

1. Loading configuration from `coordination/config.toml`
2. Setting up the BinanceArchiveClient
3. Ingesting historical data from Binance Vision
4. Running adversarial training
5. Displaying results and leaderboard

Run the example:

```bash
cd backend
python examples/training_example.py
```

## Performance Considerations

- **DuckDB Storage**: Efficient columnar storage with indexes for fast queries
- **Streaming Replay**: Memory-efficient streaming for large datasets
- **Batch Processing**: Batch inserts for historical data ingestion
- **Checkpointing**: Automatic checkpoint saves for long training runs
- **Async Support**: Non-blocking replay and training operations

## Safety

- The BinanceArchiveClient is **read-only** - it cannot modify the database directly
- All trading during replay/training is paper-only
- No live orders are placed
- Schema management methods are provided for ArchiveIngester use only

## Dependencies

- `duckdb>=0.9.0`: High-performance analytical database
- `requests`: HTTP client for downloading archives
- `numpy`: Numerical operations for adversarial agents

See [`requirements.txt`](requirements.txt) for full dependency list.

## License

MIT License - See LICENSE file for details.
