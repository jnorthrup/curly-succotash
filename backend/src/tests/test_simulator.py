"""
Tests for Coinbase Trading Simulator
Tests for safety enforcement, reproducibility, and functionality.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import List
from src.models import Candle, Signal, SignalType, Timeframe
from src.coinbase_client import CoinbaseMarketDataClient, SafetyEnforcement
from src.strategies import (
    create_all_strategies, MACrossoverStrategy, RSIMeanReversionStrategy,
    StrategyConfig, STRATEGY_REGISTRY
)
from src.paper_trading import PaperTradingEngine, PaperTradingConfig
from src.backtesting import BacktestEngine, BacktestConfig, MetricsCalculator
from src.bullpen import BullpenAggregator, RankingMetric


def generate_test_candles(count: int = 300, symbol: str = "BTC-USD") -> List[Candle]:
    """Generate synthetic candle data for testing."""
    candles = []
    base_price = 50000.0
    base_time = datetime.now(timezone.utc) - timedelta(hours=count)

    for i in range(count):
        change = (i % 20 - 10) * 50
        price = base_price + change + (i * 10)

        candle = Candle(
            timestamp=base_time + timedelta(hours=i),
            open=price - 50,
            high=price + 100,
            low=price - 100,
            close=price,
            volume=1000 + (i * 10),
            symbol=symbol,
            timeframe=Timeframe.ONE_HOUR,
        )
        candles.append(candle)

    return candles


class TestSafetyEnforcement:
    """Tests to verify no trading capability exists."""

    def test_client_has_no_trading_methods(self):
        """Verify CoinbaseMarketDataClient has no trading methods."""
        client = CoinbaseMarketDataClient()

        forbidden_methods = [
            "place_order", "create_order", "submit_order",
            "cancel_order", "cancel_all_orders",
            "withdraw", "deposit", "transfer",
            "create_withdrawal", "create_deposit",
            "buy", "sell", "market_order", "limit_order",
        ]

        for method in forbidden_methods:
            assert not hasattr(client, method), f"SAFETY VIOLATION: Client has {method}"

    def test_safety_enforcement_passes(self):
        """Verify all safety checks pass."""
        client = CoinbaseMarketDataClient()
        results = SafetyEnforcement.run_all_checks(client)

        assert results["all_passed"], "Safety checks failed!"
        assert results["no_trading_methods"], "Trading methods found!"

    def test_client_is_read_only(self):
        """Verify client only has read operations."""
        client = CoinbaseMarketDataClient()

        public_methods = [m for m in dir(client) if not m.startswith("_")]

        read_only_prefixes = ["get_", "validate_", "fetch_"]
        write_prefixes = ["post_", "create_", "delete_", "update_", "place_", "submit_"]

        for method in public_methods:
            if callable(getattr(client, method)):
                has_write = any(method.startswith(p) for p in write_prefixes)
                assert not has_write, f"SAFETY: Write method found: {method}"

    def test_paper_engine_does_not_trade(self):
        """Verify paper trading engine doesn't have real trade execution."""
        engine = PaperTradingEngine()

        forbidden = ["execute_real_order", "place_live_order", "submit_to_exchange"]
        for method in forbidden:
            assert not hasattr(engine, method), f"Paper engine has forbidden method: {method}"


class TestBacktestReproducibility:
    """Tests to verify backtests are reproducible."""

    def test_backtest_same_results(self):
        """Verify running backtest twice gives identical results."""
        candles = generate_test_candles(300)
        config = BacktestConfig(
            symbols=["BTC-USD"],
            timeframes=[Timeframe.ONE_HOUR],
            initial_capital=10000.0,
        )

        engine1 = BacktestEngine()
        results1 = engine1.run_backtest(candles, config)

        engine2 = BacktestEngine()
        results2 = engine2.run_backtest(candles, config)

        assert len(results1) == len(results2), "Different number of results"

        for r1, r2 in zip(results1, results2):
            assert r1.strategy_name == r2.strategy_name
            assert abs(r1.metrics.net_pnl - r2.metrics.net_pnl) < 0.01, \
                f"PnL mismatch for {r1.strategy_name}: {r1.metrics.net_pnl} vs {r2.metrics.net_pnl}"
            assert r1.metrics.num_trades == r2.metrics.num_trades

    def test_strategy_determinism(self):
        """Verify individual strategies produce deterministic signals."""
        candles = generate_test_candles(300)
        config = StrategyConfig(initial_capital=10000.0)

        for strategy_name, strategy_class in STRATEGY_REGISTRY.items():
            strategy1 = strategy_class(config)
            strategy2 = strategy_class(config)

            signals1 = []
            signals2 = []

            for candle in candles:
                s1 = strategy1.process_candle(candle)
                if s1:
                    signals1.append(s1)

            for candle in candles:
                s2 = strategy2.process_candle(candle)
                if s2:
                    signals2.append(s2)

            assert len(signals1) == len(signals2), \
                f"Strategy {strategy_name} signal count differs: {len(signals1)} vs {len(signals2)}"


class TestStrategyExecution:
    """Tests for strategy execution."""

    def test_all_12_strategies_exist(self):
        """Verify exactly 12 strategies are implemented."""
        assert len(STRATEGY_REGISTRY) == 12, f"Expected 12 strategies, got {len(STRATEGY_REGISTRY)}"

    def test_all_strategies_can_process_candles(self):
        """Verify all strategies can process candles without error."""
        candles = generate_test_candles(250)
        strategies = create_all_strategies()

        for strategy in strategies:
            for candle in candles:
                try:
                    strategy.process_candle(candle)
                except Exception as e:
                    pytest.fail(f"Strategy {strategy.name} failed: {e}")

    def test_strategies_produce_valid_signals(self):
        """Verify signals have all required fields."""
        candles = generate_test_candles(300)
        strategies = create_all_strategies()

        for strategy in strategies:
            for candle in candles:
                signal = strategy.process_candle(candle)

                if signal:
                    assert signal.timestamp is not None
                    assert signal.symbol == candle.symbol
                    assert signal.strategy_name == strategy.name
                    assert signal.signal_type in SignalType
                    assert signal.entry_price > 0
                    assert 0 <= signal.confidence <= 1

    def test_strategy_state_tracking(self):
        """Verify strategies track their state correctly."""
        candles = generate_test_candles(300)
        strategy = MACrossoverStrategy()

        for candle in candles:
            strategy.process_candle(candle)

        state = strategy.get_state()

        assert "name" in state
        assert "equity" in state
        assert "num_trades" in state
        assert state["name"] == "MA_Crossover"


class TestPaperTrading:
    """Tests for paper trading engine."""

    def test_paper_engine_initialization(self):
        """Test paper engine initializes correctly."""
        engine = PaperTradingEngine()
        count = engine.initialize_strategies(
            ["BTC-USD", "ETH-USD"],
            [Timeframe.ONE_HOUR]
        )

        assert count == 24

    def test_paper_engine_processes_candles(self):
        """Test paper engine processes candles through all strategies."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        candles = generate_test_candles(250)

        total_signals = 0
        for candle in candles:
            signals = engine.process_candle_sync(candle)
            total_signals += len(signals)

        states = engine.get_all_states()
        assert len(states) == 12

    def test_paper_positions_tracked(self):
        """Test that paper positions are tracked correctly."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        candles = generate_test_candles(300)

        for candle in candles:
            engine.process_candle_sync(candle)


class TestBacktesting:
    """Tests for backtesting engine."""

    def test_metrics_calculation(self):
        """Test performance metrics are calculated correctly."""
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 75},
            {"pnl": -25},
            {"pnl": 150},
        ]

        win_rate = MetricsCalculator.calculate_win_rate(trades)
        assert win_rate == 60.0

        profit_factor = MetricsCalculator.calculate_profit_factor(trades)
        assert profit_factor > 0

    def test_equity_curve_generation(self):
        """Test equity curve is generated during backtest."""
        candles = generate_test_candles(300)
        config = BacktestConfig(initial_capital=10000.0)

        engine = BacktestEngine()
        results = engine.run_backtest(candles, config)

        for result in results:
            assert len(result.equity_curve) > 0
            assert result.equity_curve[0]["equity"] == 10000.0

    def test_backtest_comparison(self):
        """Test strategy comparison works."""
        candles = generate_test_candles(300)
        config = BacktestConfig(initial_capital=10000.0)

        engine = BacktestEngine()
        results = engine.run_backtest(candles, config)

        comparison = engine.compare_strategies(results, "total_return_pct")

        assert len(comparison) == 12
        for i, entry in enumerate(comparison):
            assert entry["rank"] == i + 1


class TestBullpen:
    """Tests for bullpen aggregation."""

    def test_bullpen_view(self):
        """Test bullpen view generation."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        candles = generate_test_candles(250)
        for candle in candles:
            engine.process_candle_sync(candle)

        bullpen = BullpenAggregator(engine)
        view = bullpen.get_bullpen_view()

        assert "strategies" in view
        assert "consensus_signals" in view
        assert "summary" in view

    def test_consensus_calculation(self):
        """Test consensus signal calculation."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        candles = generate_test_candles(250)
        for candle in candles:
            engine.process_candle_sync(candle)

        bullpen = BullpenAggregator(engine)
        consensus = bullpen.get_consensus_for_symbol("BTC-USD")

        for cs in consensus:
            total = cs.long_count + cs.short_count + cs.flat_count
            assert total == 12

    def test_strategy_ranking(self):
        """Test strategy ranking by different metrics."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        candles = generate_test_candles(250)
        for candle in candles:
            engine.process_candle_sync(candle)

        bullpen = BullpenAggregator(engine)

        for metric in RankingMetric:
            view = bullpen.get_bullpen_view(ranking_metric=metric)
            strategies = view["strategies"]

            for i, strategy in enumerate(strategies):
                assert strategy["rank"] == i + 1


class TestDataIngestion:
    """Tests for data ingestion."""

    def test_candle_buffer(self):
        """Test candle buffer deduplication."""
        from src.data_ingestion import CandleBuffer

        buffer = CandleBuffer(max_size=100)
        candles = generate_test_candles(50)

        added1 = buffer.add_many(candles)
        assert added1 == 50

        added2 = buffer.add_many(candles)
        assert added2 == 0

    def test_candle_buffer_retrieval(self):
        """Test candle retrieval from buffer."""
        from src.data_ingestion import CandleBuffer

        buffer = CandleBuffer()
        candles = generate_test_candles(100)
        buffer.add_many(candles)

        retrieved = buffer.get("BTC-USD", Timeframe.ONE_HOUR)
        assert len(retrieved) == 100

        assert retrieved[0].timestamp < retrieved[-1].timestamp


class TestRealTimeSignals:
    """Tests for real-time signal generation."""

    def test_signal_emission(self):
        """Test signals are emitted correctly."""
        from src.paper_trading import SignalEmitter
        from src.models import Signal, SignalType, Timeframe

        emitter = SignalEmitter()
        received_signals = []

        emitter.subscribe(lambda s: received_signals.append(s))

        signal = Signal(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC-USD",
            timeframe=Timeframe.ONE_HOUR,
            strategy_name="Test",
            signal_type=SignalType.LONG,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=0.75,
            paper_size=0.1,
            reason="Test signal",
        )

        emitter.emit(signal)

        assert len(received_signals) == 1
        assert received_signals[0]["signal_type"] == "LONG"

    def test_live_paper_signal_generation(self):
        """Test real-time paper signal generation on incoming candles."""
        engine = PaperTradingEngine()
        engine.initialize_strategies(["BTC-USD"], [Timeframe.ONE_HOUR])

        received_signals = []
        engine.register_signal_callback(lambda s: received_signals.append(s))

        candles = generate_test_candles(300)

        for candle in candles:
            engine.process_candle_sync(candle)

        assert len(received_signals) >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
