"""
Coinbase Trading Simulator Orchestrator
Main coordinator for all simulator components including adversarial training.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Callable, Tuple
from enum import Enum

from .models import Candle, Signal, SignalType, Timeframe, SimulatorConfig
from .coinbase_client import CoinbaseMarketDataClient, SafetyEnforcement
from .data_ingestion import DataIngestionService, IngestionConfig, IngestionMode, USDValuationService
from .paper_trading import PaperTradingEngine, PaperTradingConfig, SignalEmitter
from .backtesting import BacktestEngine, BacktestConfig, BacktestResult
from .bullpen import BullpenAggregator, RankingMetric, BullpenFilter
from .hrm_shadow import HRMShadowEngine, ShadowConfig, ShadowMode
from .killswitch import DrawdownKillSwitch, KillSwitchConfig
from .scoreboard import ScoreboardGenerator
from .hrm_promotion import HRMPromotionLadder, create_promotion_ladder
from .veto_regression_watch import VetoReason, VetoRegressionWatch, create_veto_watch
from .daily_runbook import DailyRunbookGenerator, create_runbook_generator
from .calibration_governor import CalibrationGovernor, CalibrationTrigger
import numpy as np
from .calibration_support import ThresholdScheduler, CooldownManager, DriftMonitor, DriftLevel, DriftAlert, RegimeThresholdConfig, CooldownConfig
from .confidence_calibration import ConfidenceCalibrator
from .strategies import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S UTC'
)


class SimulatorMode(str, Enum):
    LIVE_PAPER = "live_paper"
    BACKTEST = "backtest"
    HYBRID = "hybrid"
    TRAINING = "training"  # New: Adversarial training mode


@dataclass
class SimulatorState:
    mode: SimulatorMode = SimulatorMode.LIVE_PAPER
    running: bool = False
    started_at: Optional[datetime] = None
    candles_processed: int = 0
    signals_generated: int = 0
    last_error: Optional[str] = None


class CoinbaseTradingSimulator:
    """
    Main simulator orchestrator.

    SAFETY ENFORCEMENT:
    - This simulator NEVER places live trades
    - Only reads market data from Coinbase API
    - All trading signals are paper-only
    """

    def __init__(self, config: SimulatorConfig = None):
        self.config = config or SimulatorConfig()
        self.state = SimulatorState()

        self.client = CoinbaseMarketDataClient()

        self.ingestion = DataIngestionService(IngestionConfig(
            symbols=self.config.symbols,
            timeframes=self.config.timeframes,
            poll_interval_seconds=self.config.poll_interval_seconds,
            backfill_days=self.config.backtest_start_days_ago,
        ))

        self.paper_engine = PaperTradingEngine(PaperTradingConfig(
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
            commission_pct=self.config.commission_pct,
        ))

        self.backtest_engine = BacktestEngine()
        self.bullpen = BullpenAggregator(self.paper_engine)
        self.signal_emitter = SignalEmitter()
        self.valuation_service = USDValuationService(self.client)
        self.shadow_engine: Optional[HRMShadowEngine] = None
        self.killswitch: Optional[DrawdownKillSwitch] = None
        self.scoreboard_generator: Optional[ScoreboardGenerator] = None
        self.promotion_ladder: Optional[HRMPromotionLadder] = None
        self.veto_watch: Optional[VetoRegressionWatch] = None
        self.runbook_generator: Optional[DailyRunbookGenerator] = None

        # Calibration and support components
        self.calibration_governor = CalibrationGovernor()
        self.threshold_scheduler = ThresholdScheduler([])
        self.cooldown_manager = CooldownManager([])
        self.drift_monitor = DriftMonitor()
        self.confidence_calibrator = ConfidenceCalibrator()

        self._price_history: Dict[str, List[float]] = {}
        self._volatility_window: int = 20

        self._recent_confidences: List[float] = []
        self._max_confidence_window: int = 1000
        self._last_drift_alert: Optional[DriftAlert] = None

        self._seen_trade_counts: Dict[str, int] = {}
        self._pending_vetoes: Dict[str, List[Dict[str, Any]]] = {}

        # Synthetic validation state
        self._synthetic_milestone_passed: bool = False

        # Training components (initialized on demand)
        self._training_harness: Optional[Any] = None
        self._training_config: Optional[Any] = None

        self._initialize_runtime_controls()
        self._verify_safety()

        logger.info("[SIMULATOR] Coinbase Trading Simulator initialized")
        logger.info(f"[SIMULATOR] Symbols: {self.config.symbols}")
        logger.info(f"[SIMULATOR] Timeframes: {[tf.value for tf in self.config.timeframes]}")
        logger.info("[SAFETY] ⚠️  PAPER TRADING ONLY - NO LIVE ORDERS")

    def _initialize_runtime_controls(self) -> None:
        """Initialize optional shadow-mode and kill-switch controls."""
        if self.config.enable_hrm_shadow:
            shadow_config = ShadowConfig(
                mode=ShadowMode(self.config.hrm_shadow_mode),
                symbols=self.config.symbols,
                timeframes=self.config.timeframes,
                hrm_model_path=self.config.hrm_model_path,
                hrm_confidence_threshold=self.config.hrm_confidence_threshold,
            )
            self.shadow_engine = HRMShadowEngine(shadow_config)
            self.scoreboard_generator = ScoreboardGenerator()
            self.promotion_ladder = create_promotion_ladder()
            self.veto_watch = create_veto_watch()
            self.runbook_generator = create_runbook_generator()

            if self.config.hrm_model_path:
                self.shadow_engine.load_hrm_model(self.config.hrm_model_path)

        if self.config.enable_killswitch:
            kill_config = KillSwitchConfig(
                daily_loss_limit_pct=self.config.daily_loss_limit_pct,
                cumulative_loss_limit_pct=self.config.cumulative_loss_limit_pct,
                max_consecutive_losses=self.config.max_consecutive_losses,
            )
            if kill_config.cumulative_loss_limit_pct >= 50.0:
                logger.warning("[SAFETY] ⚠️  Kill-switch limit is extremely high (>=50%)")
            
            self.killswitch = DrawdownKillSwitch(kill_config, self.config.initial_capital)

        # Run synthetic validation if shadow mode is enabled
        if self.config.enable_hrm_shadow:
            self._run_synthetic_validation()

    def _run_synthetic_validation(self) -> None:
        """Run strict synthetic validation and baseline benchmarking for HRM."""
        if not self.shadow_engine:
            logger.debug("[SIMULATOR] Skipping synthetic validation: shadow engine not enabled")
            return

        from .synthetic_gates import CompetencyEvaluator, IdentityGate
        import numpy as np

        evaluator = CompetencyEvaluator()

        def hrm_predictor_wrapper(x: np.ndarray) -> np.ndarray:
            # Check if shadow_engine has a predictor or model
            if self.shadow_engine and hasattr(self.shadow_engine, "_hrm_model") and self.shadow_engine._hrm_model:
                try:
                    # In a real scenario, this would involve feature engineering
                    # For synthetic gates, we assume the model takes raw inputs
                    return self.shadow_engine._hrm_model(x)
                except Exception as e:
                    logger.debug(f"[SIMULATOR] Synthetic validation: Model prediction failed: {e}")
            
            # Fallback to zeros (will fail identity gate)
            return np.zeros_like(x)

        logger.info("[SIMULATOR] Running HRM synthetic competency validation...")
        results = evaluator.run_all(hrm_predictor_wrapper)
        
        identity_result = next((r for r in results if r.gate_name == "identity"), None)
        
        if identity_result:
            if not identity_result.success:
                logger.critical("CRITICAL: HRM failed IdentityGate convergence")
            
            mae = identity_result.mae
            mae_pers = identity_result.metadata.get("mae_pers", float('inf'))
            
            if mae > mae_pers:
                logger.critical("CRITICAL: HRM failed to beat PersistenceBaseline on IdentityGate")
                self._synthetic_milestone_passed = False
            elif identity_result.success:
                self._synthetic_milestone_passed = True
            else:
                self._synthetic_milestone_passed = False

            if not self._synthetic_milestone_passed:
                logger.warning("[SIMULATOR] Model promotion blocked: failed synthetic validation")
            else:
                logger.info("[SIMULATOR] Synthetic milestone passed")
        else:
            logger.error("[SIMULATOR] IdentityGate result not found")
            self._synthetic_milestone_passed = False

    def _verify_safety(self):
        """Verify safety constraints are enforced."""
        safety_results = SafetyEnforcement.run_all_checks(self.client)

        if not safety_results["all_passed"]:
            raise RuntimeError("SAFETY VIOLATION: Trading capability detected!")

        logger.info("[SAFETY] ✓ All safety checks passed - READ-ONLY mode confirmed")

    def _detect_regime(self, candle: Candle) -> str:
        """
        Detect current market regime for a candle using rolling volatility.
        
        Uses standard deviation of log returns over a rolling window.
        Maps volatility to 'VOL_LOW', 'VOL_HIGH', or 'VOL_NORMAL'.
        """
        symbol = candle.symbol
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        
        self._price_history[symbol].append(float(candle.close))
        
        # Keep window + 1 prices to compute 'window' returns
        if len(self._price_history[symbol]) > self._volatility_window + 1:
            self._price_history[symbol].pop(0)
            
        if len(self._price_history[symbol]) <= self._volatility_window:
            return "VOL_NORMAL"
            
        prices = np.array(self._price_history[symbol])
        # Compute log returns: ln(P_t / P_{t-1})
        log_returns = np.diff(np.log(prices))
        volatility = np.std(log_returns)
        
        # Fixed thresholds for regime detection (approximate for 1m-5m crypto)
        # VOL_LOW: < 0.05th percentile (~0.0005)
        # VOL_HIGH: > 0.95th percentile (~0.002)
        if volatility < 0.0005:
            return "VOL_LOW"
        elif volatility > 0.002:
            return "VOL_HIGH"
        else:
            return "VOL_NORMAL"

    def _monitor_drift(self, candle: Candle, shadow_signal: Any) -> None:
        """Monitor for calibration drift in HRM predictions."""
        if not self.drift_monitor or not hasattr(shadow_signal, "hrm_confidence"):
            return

        self._recent_confidences.append(shadow_signal.hrm_confidence)
        if len(self._recent_confidences) > self._max_confidence_window:
            self._recent_confidences = self._recent_confidences[-self._max_confidence_window:]

        # Detect drift periodically (every 100 candles) if enough samples
        if self.state.candles_processed > 0 and self.state.candles_processed % 100 == 0:
            if len(self._recent_confidences) >= 100:
                self._last_drift_alert = self.drift_monitor.detect_drift(
                    np.array(self._recent_confidences),
                    current_ece=0.0  # Mock current_ece for now
                )

    def _compute_recent_performance(self) -> float:
        """Calculate the win rate of the last 20 shadow trades from HRMShadowEngine."""
        if not self.shadow_engine:
            return 1.0

        trades = self.shadow_engine.shadow_trades
        if not trades:
            return 1.0

        recent_trades = trades[-20:]
        wins = sum(1 for t in recent_trades if t.net_pnl > 0)
        return wins / len(recent_trades)

    def _check_recalibration(self, candle: Candle) -> None:
        """Check if recalibration is needed based on governor triggers."""
        if not self.calibration_governor:
            return

        # 1. Compute recent performance
        perf = self._compute_recent_performance()
        performance_drop = perf < 0.45  # Recalibrate if win rate drops below 45%

        # 2. Check for drift
        drift_detected = (
            self._last_drift_alert is not None and
            self._last_drift_alert.level in {DriftLevel.HIGH, DriftLevel.CRITICAL}
        )

        # 3. Consult governor
        decision = self.calibration_governor.should_recalibrate(
            current_time=candle.timestamp,
            performance_drop=performance_drop,
            drift_detected=drift_detected,
            force_recalibrate=False
        )

        from .calibration_governor import CalibrationOutcome
        if decision.decision == CalibrationOutcome.CALIBRATE:
            logger.info(f"[CALIBRATION] Recalibration triggered: {decision.reason} (Perf: {perf:.2f}, Drift: {drift_detected})")
            
            # Record that calibration was performed
            self.calibration_governor.record_calibration(candle.timestamp)
            
            # Reset drift alert after triggering
            self._last_drift_alert = None
            
            # Run synthetic validation as a post-calibration competency check
            if self.config.enable_hrm_shadow:
                self._run_synthetic_validation()
            
            # In a real implementation, this would trigger a background task
            # to run the calibration sweep and update models.

    async def start_live_paper_mode(self):
        """Start live paper trading mode with real-time candles."""
        if self.state.running:
            logger.warning("[SIMULATOR] Already running")
            return

        self.state.mode = SimulatorMode.LIVE_PAPER
        self.state.running = True
        self.state.started_at = datetime.now(timezone.utc)

        self.paper_engine.initialize_strategies(
            self.config.symbols,
            self.config.timeframes
        )

        self.ingestion.register_candle_callback(self._on_new_candle)
        self.paper_engine.register_signal_callback(self.signal_emitter.emit)

        await self.ingestion.start()

        logger.info("[SIMULATOR] Live paper trading mode started")

    async def _on_new_candle(self, candle: Candle):
        """Handle new candle from ingestion service."""
        try:
            # 1. Detect current regime
            regime = self._detect_regime(candle)
            
            # 2. Get adjusted thresholds for the regime
            thresholds = self.threshold_scheduler.get_thresholds([regime])
            
            # 3. Check for cooldown or kill-switch
            if self.cooldown_manager.is_in_cooldown(candle.symbol, candle.timestamp, regime=regime):
                logger.debug(f"[SIMULATOR] {candle.symbol} in cooldown, skipping signals")
                self.paper_engine.update_open_positions(candle)
                signals = []
            elif self.killswitch and not self.killswitch.is_trading_allowed():
                logger.warning("[SIMULATOR] Trading halted by kill-switch")
                self.paper_engine.update_open_positions(candle)
                signals = []
            else:
                # 4. Process candle through paper engine
                signals = await self.paper_engine.process_candle(candle)
                
                # 5. Filter signals based on regime-aware thresholds
                signals = [s for s in signals if s.confidence >= thresholds.confidence_threshold]

            baseline_signal = self._baseline_signal_for_candle(candle, signals)

            if self.shadow_engine:
                # 6. Apply confidence calibration if possible
                if self.confidence_calibrator._fitted:
                    # In a real implementation, we'd calibrate the HRM prediction here.
                    # For now, we'll just process as normal.
                    pass

                shadow_signal = self.shadow_engine.process_candle(candle, baseline_signal)
                
                # 7. Monitor for calibration drift
                self._monitor_drift(candle, shadow_signal)
                
                # 8. Check if recalibration is needed
                self._check_recalibration(candle)
                
                self._record_shadow_signal(candle, baseline_signal, shadow_signal)

            # 9. Record closed trades to cooldown manager
            new_closed_trades = self._collect_new_closed_trades()
            for trade in new_closed_trades:
                # Compute entry time from holding period
                entry_time = trade.timestamp - timedelta(seconds=trade.holding_period_seconds)
                self.cooldown_manager.record_trade(
                    symbol=trade.symbol,
                    entry_time=entry_time,
                    exit_time=trade.timestamp,
                    pnl=trade.pnl,
                    pnl_percent=trade.pnl_percent
                )
            
            self._record_closed_trades(new_closed_trades)

            self.state.candles_processed += 1
            self.state.signals_generated += len(signals)

            if signals:
                logger.info(f"[SIMULATOR] Generated {len(signals)} signals from {candle.symbol}")

        except Exception as e:
            self.state.last_error = str(e)
            logger.error(f"[SIMULATOR] Error processing candle: {e}")

    def _record_shadow_signal(self, candle: Candle, baseline_signal: Signal, shadow_signal: Any) -> None:
        """Forward veto-capable shadow decisions into the veto watch."""
        if not self.veto_watch or shadow_signal.action_taken != "hrm_veto":
            return

        veto_id = self.veto_watch.record_veto(
            symbol=candle.symbol,
            timeframe=candle.timeframe.value,
            reason=self._map_veto_reason(shadow_signal.veto_reason),
            baseline_signal=baseline_signal.signal_type.value,
            hrm_signal=shadow_signal.hrm_signal,
            hrm_confidence=shadow_signal.hrm_confidence,
        )
        pending_key = self._pending_veto_key(
            symbol=candle.symbol,
            timeframe=candle.timeframe.value,
            strategy_name=baseline_signal.strategy_name,
        )
        self._pending_vetoes.setdefault(pending_key, []).append(
            {
                "veto_id": veto_id,
                "timestamp": baseline_signal.timestamp,
            }
        )

    def _pending_veto_key(self, symbol: str, timeframe: str, strategy_name: str) -> str:
        return f"{symbol}:{timeframe}:{strategy_name}"

    def _map_veto_reason(self, veto_reason: Optional[str]) -> VetoReason:
        if not veto_reason:
            return VetoReason.UNKNOWN

        reason = veto_reason.lower()
        if "confidence below" in reason:
            return VetoReason.CONFIDENCE_TOO_LOW
        if "regime" in reason:
            return VetoReason.REGIME_MISMATCH
        return VetoReason.UNKNOWN

    def _baseline_signal_for_candle(self, candle: Candle, signals: List[Signal]) -> Signal:
        """Select the leading baseline signal for shadow comparison."""
        if signals:
            return max(
                signals,
                key=lambda signal: (signal.confidence, signal.paper_size, signal.strategy_name),
            )

        return Signal(
            timestamp=candle.timestamp,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            strategy_name="Baseline_None",
            signal_type=SignalType.FLAT,
            entry_price=candle.close,
            stop_loss=None,
            take_profit=None,
            confidence=0.0,
            paper_size=0.0,
            reason="No baseline signal",
        )

    def _collect_new_closed_trades(self) -> List[Dict[str, Any]]:
        """Return newly closed strategy trades since the last poll."""
        new_trades: List[Dict[str, Any]] = []

        for symbol, timeframe_dict in self.paper_engine.trackers.items():
            for timeframe_value, strategy_dict in timeframe_dict.items():
                for strategy_name, tracker in strategy_dict.items():
                    trade_key = f"{symbol}:{timeframe_value}:{strategy_name}"
                    seen_count = self._seen_trade_counts.get(trade_key, 0)
                    current_count = len(tracker.strategy.trades)

                    if current_count > seen_count:
                        for trade in tracker.strategy.trades[seen_count:current_count]:
                            new_trades.append({
                                **trade,
                                "strategy_name": strategy_name,
                                "timeframe": timeframe_value,
                            })

                    self._seen_trade_counts[trade_key] = current_count

        return new_trades

    def _record_closed_trades(self, trades: List[Dict[str, Any]]) -> None:
        """Forward closed baseline trades into the kill-switch."""
        for trade in trades:
            entry_price = float(trade.get("entry_price", 0.0))
            size = float(trade.get("size", 0.0))
            notional = entry_price * size
            pnl = float(trade.get("pnl", 0.0))
            pnl_pct = (pnl / notional) * 100.0 if notional > 0 else 0.0
            exit_time = trade.get("exit_time")

            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)

            if self.killswitch:
                self.killswitch.record_trade(
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    symbol=trade.get("symbol", "UNKNOWN"),
                    timestamp=exit_time,
                )

            self._resolve_pending_veto(trade)

    def _resolve_pending_veto(self, trade: Dict[str, Any]) -> None:
        """Resolve the earliest matching veto against a closed baseline trade."""
        if not self.veto_watch:
            return

        exact_key = self._pending_veto_key(
            symbol=trade.get("symbol", "UNKNOWN"),
            timeframe=str(trade.get("timeframe", "unknown")),
            strategy_name=trade.get("strategy_name", "UNKNOWN"),
        )
        key_prefix = f"{trade.get('symbol', 'UNKNOWN')}:{trade.get('timeframe', 'unknown')}:"
        candidate_keys = [exact_key]
        candidate_keys.extend(
            key for key in self._pending_vetoes
            if key.startswith(key_prefix) and key != exact_key
        )

        entry_time = trade.get("entry_time")
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)

        for key in candidate_keys:
            pending = self._pending_vetoes.get(key, [])
            for index, veto in enumerate(pending):
                if entry_time is None or veto["timestamp"] <= entry_time:
                    pnl = float(trade.get("pnl", 0.0))
                    self.veto_watch.resolve_veto(
                        veto["veto_id"],
                        would_have_won=pnl > 0,
                        would_have_pnl=pnl,
                    )
                    pending.pop(index)
                    if not pending:
                        self._pending_vetoes.pop(key, None)
                    return

    async def stop(self):
        """Stop the simulator."""
        self.state.running = False
        await self.ingestion.stop()
        logger.info("[SIMULATOR] Simulator stopped")

    def generate_shadow_scoreboard(
        self,
        date: Optional[datetime] = None,
    ) -> Optional[Dict[str, str]]:
        """Generate shadow-mode comparison artifacts for the current session."""
        if not self.shadow_engine or not self.scoreboard_generator:
            return None

        run_date = date or datetime.now(timezone.utc)
        metrics = []
        start_time = run_date - timedelta(days=1)

        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                baseline_trades = self.paper_engine.get_completed_trades(symbol, timeframe)
                metrics.append(
                    self.shadow_engine.compute_metrics(
                        symbol=symbol,
                        timeframe=timeframe,
                        baseline_trades=baseline_trades,
                        start_time=start_time,
                        end_time=run_date,
                    )
                )

        scoreboard = self.scoreboard_generator.generate(
            date=run_date,
            metrics=metrics,
            mode=self.shadow_engine.mode.value,
        )
        paths = self.scoreboard_generator.save_all_formats(scoreboard)
        self.evaluate_hrm_promotion(run_date)
        self.shadow_engine.save_daily_log(run_date)

        if self.killswitch:
            self.killswitch.save_daily_log(run_date)

        return paths

    def evaluate_hrm_promotion(
        self,
        date: Optional[datetime] = None,
    ) -> List[Any]:
        """Update and evaluate promotion state from the latest shadow metrics."""
        if not self.shadow_engine or not self.promotion_ladder:
            return []

        run_date = date or datetime.now(timezone.utc)
        start_time = run_date - timedelta(days=1)
        regimes_detected: List[str] = []

        if self.veto_watch:
            veto_report = self.veto_watch.generate_daily_report(run_date)
            regimes_detected = veto_report.get("regime_analysis", {}).get("regimes_detected", [])
            self.veto_watch.save_report(
                veto_report,
                f"veto_report_{run_date.strftime('%Y-%m-%d')}.json",
            )

        evaluations = []
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                baseline_trades = self.paper_engine.get_completed_trades(symbol, timeframe)
                metrics = self.shadow_engine.compute_metrics(
                    symbol=symbol,
                    timeframe=timeframe,
                    baseline_trades=baseline_trades,
                    start_time=start_time,
                    end_time=run_date,
                )
                self.promotion_ladder.update_state(
                    symbol=symbol,
                    timeframe=timeframe,
                    metrics=metrics,
                    regimes_detected=regimes_detected,
                )
                evaluations.append(
                    self.promotion_ladder.evaluate_promotion(
                        symbol=symbol,
                        timeframe=timeframe,
                        metrics=metrics,
                        regimes_detected=regimes_detected,
                    )
                )

        self.promotion_ladder.save_daily_report(run_date)
        return evaluations

    def generate_daily_runbook(
        self,
        date: Optional[datetime] = None,
    ) -> Optional[Dict[str, str]]:
        """Generate operator-facing daily artifacts for the current runtime state."""
        if (
            not self.shadow_engine or
            not self.runbook_generator or
            not self.promotion_ladder or
            not self.veto_watch
        ):
            return None

        run_date = date or datetime.now(timezone.utc)
        self.evaluate_hrm_promotion(run_date)
        runbook = self.runbook_generator.generate_from_simulator(
            simulator=self,
            shadow_engine=self.shadow_engine,
            promotion_ladder=self.promotion_ladder,
            veto_watch=self.veto_watch,
            killswitch=self.killswitch,
            date=run_date,
        )

        date_suffix = run_date.strftime("%Y-%m-%d")
        return {
            "markdown": self.runbook_generator.save_markdown(runbook, f"daily_runbook_{date_suffix}.md"),
            "json": self.runbook_generator.save_json(runbook, f"daily_runbook_{date_suffix}.json"),
            "csv": self.runbook_generator.save_csv(runbook, f"daily_runbook_{date_suffix}.csv"),
        }

    def run_backtest(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None,
        days_back: int = 90,
        initial_capital: float = 10000.0
    ) -> List[BacktestResult]:
        """Run backtest on historical data."""
        symbols = symbols or self.config.symbols
        timeframes = timeframes or self.config.timeframes

        logger.info(f"[SIMULATOR] Starting backtest: {symbols} for {days_back} days")

        all_results = []

        for symbol in symbols:
            for timeframe in timeframes:
                candles = self.ingestion.get_historical_candles(
                    symbol, timeframe, days_back
                )

                if not candles:
                    logger.warning(f"[SIMULATOR] No candles for {symbol} {timeframe.value}")
                    continue

                config = BacktestConfig(
                    symbols=[symbol],
                    timeframes=[timeframe],
                    initial_capital=initial_capital,
                    position_size_pct=self.config.position_size_pct,
                    commission_pct=self.config.commission_pct,
                )

                results = self.backtest_engine.run_backtest(candles, config)
                all_results.extend(results)

        return all_results

    def get_bullpen_view(
        self,
        ranking_metric: RankingMetric = RankingMetric.TOTAL_RETURN,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None
    ) -> Dict[str, Any]:
        """Get current bullpen view."""
        filter_config = BullpenFilter(
            symbols=symbols,
            timeframes=timeframes,
        )
        return self.bullpen.get_bullpen_view(ranking_metric, filter_config)

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signals across all strategies."""
        return self.paper_engine.get_recent_signals(limit)

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open paper positions."""
        return self.paper_engine.get_positions()

    def get_status(self) -> Dict[str, Any]:
        """Get simulator status."""
        return {
            "mode": self.state.mode.value,
            "running": self.state.running,
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "candles_processed": self.state.candles_processed,
            "signals_generated": self.state.signals_generated,
            "last_error": self.state.last_error,
            "config": self.config.to_dict(),
            "ingestion_status": self.ingestion.get_status(),
            "safety_verified": True,
            "strategies_count": len(STRATEGY_REGISTRY),
            "strategy_names": list(STRATEGY_REGISTRY.keys()),
            "hrm_runtime": {
                "shadow_enabled": self.shadow_engine is not None,
                "killswitch_enabled": self.killswitch is not None,
                "promotion_enabled": self.promotion_ladder is not None,
                "veto_watch_enabled": self.veto_watch is not None,
                "runbook_enabled": self.runbook_generator is not None,
            },
        }

    def get_strategy_info(self) -> List[Dict[str, str]]:
        """Get information about all 12 strategies."""
        from .strategies import create_all_strategies

        strategies = create_all_strategies()
        return [
            {
                "name": s.name,
                "description": s.description,
            }
            for s in strategies
        ]

    def get_usd_valuation(self, symbol: str, amount: float = 1.0) -> Dict[str, Any]:
        """Get USD valuation for a symbol."""
        return self.valuation_service.convert_to_usd(symbol, amount)

    # =========================================================================
    # Training Mode Methods
    # =========================================================================

    async def start_training_mode(
        self,
        num_episodes: int = 1000,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None,
        enable_adversarial: bool = True,
        adversarial_intensity: float = 0.5,
        max_training_seconds: int = 3600,
        duckdb_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start adversarial training mode with Binance archive replay.

        Uses TrainingHarness to run episode-based training with adversarial
        agents injecting market perturbations for robust strategy evaluation.

        Args:
            num_episodes: Number of training episodes to run
            symbols: List of symbols to train on (uses config default if None)
            timeframes: List of timeframes to use (uses config default if None)
            enable_adversarial: Whether to enable adversarial perturbations
            adversarial_intensity: Intensity of adversarial effects (0.0-1.0)
            max_training_seconds: Maximum training duration
            duckdb_path: Path to DuckDB database (uses default if None)

        Returns:
            Dictionary with training results and status
        """
        if self.state.running and self.state.mode == SimulatorMode.TRAINING:
            logger.warning("[SIMULATOR] Training mode already running")
            return {"status": "already_running"}

        # Import training components
        from .training_harness import TrainingHarness, TrainingConfig
        from .binance_client import BinanceArchiveClient, BinanceArchiveConfig

        self.state.mode = SimulatorMode.TRAINING
        self.state.running = True
        self.state.started_at = datetime.now(timezone.utc)

        # Create Binance archive client
        archive_config = BinanceArchiveConfig()
        if duckdb_path:
            archive_config.duckdb_path = duckdb_path

        archive_client = BinanceArchiveClient(archive_config)

        # Create training configuration
        self._training_config = TrainingConfig(
            num_episodes=num_episodes,
            max_training_seconds=max_training_seconds,
            symbols=symbols or self.config.symbols,
            timeframes=timeframes or self.config.timeframes,
            enable_adversarial=enable_adversarial,
            adversarial_intensity=adversarial_intensity,
            initial_capital=self.config.initial_capital,
            position_size_pct=self.config.position_size_pct,
            commission_pct=self.config.commission_pct,
        )

        # Create and run training harness
        self._training_harness = TrainingHarness(archive_client, self._training_config)

        logger.info(f"[SIMULATOR] Starting training mode: {num_episodes} episodes")
        logger.info(f"[SIMULATOR] Symbols: {self._training_config.symbols}")
        logger.info(f"[SIMULATOR] Adversarial: {'enabled' if enable_adversarial else 'disabled'}")

        # Run training in executor to avoid blocking
        loop = asyncio.get_event_loop()
        training_result = await loop.run_in_executor(
            None, self._training_harness.run_training
        )

        # Update state
        self.state.running = False

        # Build result
        result = {
            "status": "completed",
            "episodes_completed": training_result.episodes_completed,
            "best_strategy": training_result.best_strategy,
            "best_sharpe": training_result.best_sharpe,
            "total_candles": training_result.total_candles,
            "training_duration_seconds": training_result.training_duration_seconds,
            "final_leaderboard": training_result.final_leaderboard,
        }

        logger.info(f"[SIMULATOR] Training complete: {result['episodes_completed']} episodes")
        logger.info(f"[SIMULATOR] Best strategy: {result['best_strategy']} (Sharpe: {result['best_sharpe']:.2f})")

        return result

    def get_training_status(self) -> Dict[str, Any]:
        """
        Get current training status.

        Returns:
            Dictionary with training progress and status information
        """
        if self.state.mode != SimulatorMode.TRAINING:
            return {
                "mode": self.state.mode.value,
                "training_active": False,
                "message": "Not in training mode",
            }

        if not self._training_harness:
            return {
                "mode": "training",
                "training_active": self.state.running,
                "status": "initializing",
            }

        # Get harness status
        harness_status = self._training_harness.get_status()

        return {
            "mode": "training",
            "training_active": harness_status["is_running"],
            "is_paused": harness_status["is_paused"],
            "current_episode": harness_status["current_episode"],
            "total_episodes": harness_status["total_episodes"],
            "episodes_completed": harness_status["episodes_completed"],
            "total_candles": harness_status["total_candles"],
            "best_strategy": harness_status["best_strategy"],
            "best_sharpe": harness_status["best_sharpe"],
            "leaderboard": harness_status["leaderboard"][:5] if harness_status["leaderboard"] else [],
            "config": harness_status["config"],
        }

    def pause_training(self) -> bool:
        """
        Pause the current training session.

        Returns:
            True if training was paused, False otherwise
        """
        if self._training_harness and self.state.mode == SimulatorMode.TRAINING:
            self._training_harness.pause_training()
            logger.info("[SIMULATOR] Training paused")
            return True
        return False

    def resume_training(self) -> bool:
        """
        Resume a paused training session.

        Returns:
            True if training was resumed, False otherwise
        """
        if self._training_harness and self.state.mode == SimulatorMode.TRAINING:
            self._training_harness.resume_training()
            logger.info("[SIMULATOR] Training resumed")
            return True
        return False

    def stop_training(self) -> bool:
        """
        Stop the current training session gracefully.

        Returns:
            True if training stop was requested, False otherwise
        """
        if self._training_harness and self.state.mode == SimulatorMode.TRAINING:
            self._training_harness.stop_training()
            logger.info("[SIMULATOR] Training stop requested")
            return True
        return False

    def get_training_leaderboard(self) -> List[Tuple[str, float]]:
        """
        Get the current strategy leaderboard from training.

        Returns:
            List of (strategy_name, average_sharpe) tuples sorted by performance
        """
        if self._training_harness:
            return self._training_harness.get_leaderboard()
        return []

    def get_best_training_strategy(self) -> Tuple[str, float]:
        """
        Get the best performing strategy from training.

        Returns:
            Tuple of (strategy_name, sharpe_ratio)
        """
        if self._training_harness:
            return self._training_harness.get_best_strategy()
        return ("", 0.0)


_simulator_instance: Optional[CoinbaseTradingSimulator] = None


def get_simulator() -> CoinbaseTradingSimulator:
    """Get or create the global simulator instance."""
    global _simulator_instance

    if _simulator_instance is None:
        _simulator_instance = CoinbaseTradingSimulator()

    return _simulator_instance


def reset_simulator(config: SimulatorConfig = None) -> CoinbaseTradingSimulator:
    """Reset and create a new simulator instance."""
    global _simulator_instance

    if _simulator_instance and _simulator_instance.state.running:
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_simulator_instance.stop())

    _simulator_instance = CoinbaseTradingSimulator(config)
    return _simulator_instance
