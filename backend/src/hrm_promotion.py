"""
HRM Promotion Ladder System

Implements the 4-stage promotion system for HRM models:
  shadow -> veto_only -> size_capped -> primary

Each stage has specific criteria for promotion and demotion based on:
- Minimum days in current stage
- Outperformance rate vs baseline (>55%)
- PnL difference after fees/slippage (>2%)
- Veto accuracy (>60% for veto_only stage)
- Maximum drawdown limits
- Sharpe ratio requirements

Promotion is gated by the canary basket criteria and regime coverage requirements.
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .models import Timeframe
from .hrm_shadow import ShadowMetrics, ShadowMode

logger = logging.getLogger(__name__)


class PromotionStage(str, Enum):
    """HRM promotion ladder stages."""
    SHADOW = "shadow"  # Pure observation, no authority
    VETO_ONLY = "veto_only"  # Can block baseline trades
    SIZE_CAPPED = "size_capped"  # Can trade with size limits
    PRIMARY = "primary"  # Full trading authority

    @classmethod
    def next_stage(cls, current: "PromotionStage") -> Optional["PromotionStage"]:
        """Get the next promotion stage."""
        order = [cls.SHADOW, cls.VETO_ONLY, cls.SIZE_CAPPED, cls.PRIMARY]
        try:
            idx = order.index(current)
            return order[idx + 1] if idx < len(order) - 1 else None
        except ValueError:
            return None

    @classmethod
    def prev_stage(cls, current: "PromotionStage") -> Optional["PromotionStage"]:
        """Get the previous (demotion) stage."""
        order = [cls.SHADOW, cls.VETO_ONLY, cls.SIZE_CAPPED, cls.PRIMARY]
        try:
            idx = order.index(current)
            return order[idx - 1] if idx > 0 else None
        except ValueError:
            return None


@dataclass
class StageCriteria:
    """Criteria for promotion from a specific stage."""
    min_days: int
    min_trades: int
    min_outperformance_rate: float  # % of symbols where HRM beats baseline
    min_pnl_difference_pct: float  # HRM PnL - Baseline PnL as % of baseline
    min_veto_accuracy: float  # % of vetoes that were correct
    max_drawdown_pct: float  # Maximum allowed drawdown
    min_sharpe_ratio: float  # Minimum Sharpe ratio
    min_regimes_tested: int  # Minimum market regimes tested
    required_regimes: List[str]  # Specific regimes that must be tested

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolPromotionCriteria:
    """Symbol-specific promotion criteria from canary basket."""
    symbol: str
    priority: int
    timeframes: List[str]
    allocation_weight: float
    rationale: str

    # Stage-specific criteria
    shadow_criteria: StageCriteria
    veto_only_criteria: StageCriteria
    size_capped_criteria: StageCriteria
    primary_criteria: StageCriteria

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "priority": self.priority,
            "timeframes": self.timeframes,
            "allocation_weight": self.allocation_weight,
            "rationale": self.rationale,
            "shadow_criteria": self.shadow_criteria.to_dict(),
            "veto_only_criteria": self.veto_only_criteria.to_dict(),
            "size_capped_criteria": self.size_capped_criteria.to_dict(),
            "primary_criteria": self.primary_criteria.to_dict(),
        }


@dataclass
class PromotionEvaluation:
    """Result of promotion evaluation for a symbol."""
    symbol: str
    timeframe: str
    current_stage: PromotionStage
    evaluation_date: str

    # Current metrics
    days_in_stage: int
    total_trades: int
    outperformance_rate: float
    pnl_difference_pct: float
    veto_accuracy: float
    current_drawdown_pct: float
    current_sharpe_ratio: float
    regimes_tested: List[str]

    # Evaluation result
    promotion_ready: bool
    demotion_required: bool
    target_stage: Optional[PromotionStage]
    reasons: List[str]
    blocked_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "current_stage": self.current_stage.value,
            "evaluation_date": self.evaluation_date,
            "metrics": {
                "days_in_stage": self.days_in_stage,
                "total_trades": self.total_trades,
                "outperformance_rate": self.outperformance_rate,
                "pnl_difference_pct": self.pnl_difference_pct,
                "veto_accuracy": self.veto_accuracy,
                "current_drawdown_pct": self.current_drawdown_pct,
                "current_sharpe_ratio": self.current_sharpe_ratio,
                "regimes_tested": self.regimes_tested,
            },
            "promotion_ready": self.promotion_ready,
            "demotion_required": self.demotion_required,
            "target_stage": self.target_stage.value if self.target_stage else None,
            "reasons": self.reasons,
            "blocked_reasons": self.blocked_reasons,
        }


@dataclass
class PromotionState:
    """Tracks promotion state for all symbols."""
    symbol: str
    timeframe: Timeframe
    current_stage: PromotionStage
    stage_entered_at: datetime
    total_days_tracked: int
    total_trades: int
    cumulative_pnl: float
    cumulative_sharpe: float
    max_drawdown: float
    veto_accuracy_history: List[float] = field(default_factory=list)
    outperformance_history: List[bool] = field(default_factory=list)
    regime_coverage: List[str] = field(default_factory=list)
    promotion_history: List[Dict[str, Any]] = field(default_factory=list)
    last_update_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "current_stage": self.current_stage.value,
            "stage_entered_at": self.stage_entered_at.isoformat(),
            "total_days_tracked": self.total_days_tracked,
            "total_trades": self.total_trades,
            "cumulative_pnl": self.cumulative_pnl,
            "cumulative_sharpe": self.cumulative_sharpe,
            "max_drawdown": self.max_drawdown,
            "veto_accuracy_history": self.veto_accuracy_history,
            "outperformance_history": self.outperformance_history,
            "regime_coverage": self.regime_coverage,
            "promotion_history": self.promotion_history,
            "last_update_date": self.last_update_date,
        }


class HRMPromotionLadder:
    """
    Manages HRM promotion ladder across all symbols.

    Implements the 4-stage promotion system with configurable criteria
    based on the canary basket configuration.

    Example:
        ladder = HRMPromotionLadder(
            canary_basket_path="/path/to/canary_basket.json",
            regime_manifest_path="/path/to/regime_manifest.json"
        )

        # Evaluate promotion readiness
        evaluation = ladder.evaluate_promotion(
            symbol="BTCUSDT",
            timeframe="1h",
            metrics=shadow_metrics
        )

        # Promote if ready
        if evaluation.promotion_ready:
            ladder.promote_symbol(
                symbol="BTCUSDT",
                timeframe="1h",
                new_stage=evaluation.target_stage
            )
    """

    # Default criteria (overridden by canary basket config)
    DEFAULT_CRITERIA = {
        PromotionStage.SHADOW: StageCriteria(
            min_days=7,
            min_trades=100,
            min_outperformance_rate=55.0,
            min_pnl_difference_pct=2.0,
            min_veto_accuracy=0.0,  # Not applicable in shadow
            max_drawdown_pct=5.0,
            min_sharpe_ratio=0.0,  # Not required for shadow
            min_regimes_tested=2,
            required_regimes=["VOL_NORMAL", "TREND_RANGE"],
        ),
        PromotionStage.VETO_ONLY: StageCriteria(
            min_days=14,
            min_trades=200,
            min_outperformance_rate=55.0,
            min_pnl_difference_pct=2.0,
            min_veto_accuracy=60.0,
            max_drawdown_pct=5.0,
            min_sharpe_ratio=1.0,
            min_regimes_tested=3,
            required_regimes=["VOL_NORMAL", "VOL_HIGH", "TREND_BULL_STRONG"],
        ),
        PromotionStage.SIZE_CAPPED: StageCriteria(
            min_days=30,
            min_trades=500,
            min_outperformance_rate=55.0,
            min_pnl_difference_pct=2.0,
            min_veto_accuracy=60.0,
            max_drawdown_pct=8.0,
            min_sharpe_ratio=1.5,
            min_regimes_tested=4,
            required_regimes=["VOL_NORMAL", "VOL_HIGH", "TREND_BULL_STRONG", "TREND_BEAR_STRONG"],
        ),
        PromotionStage.PRIMARY: StageCriteria(
            min_days=60,
            min_trades=1000,
            min_outperformance_rate=55.0,
            min_pnl_difference_pct=2.0,
            min_veto_accuracy=60.0,
            max_drawdown_pct=10.0,
            min_sharpe_ratio=1.5,
            min_regimes_tested=6,
            required_regimes=[],  # All major regimes
        ),
    }

    def __init__(
        self,
        canary_basket_path: Optional[str] = None,
        regime_manifest_path: Optional[str] = None,
        output_dir: str = "/Users/jim/work/curly-succotash/logs/promotion"
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self.criteria: Dict[str, Dict[PromotionStage, StageCriteria]] = {}
        self.symbol_configs: Dict[str, SymbolPromotionCriteria] = {}

        if canary_basket_path:
            self._load_canary_basket(canary_basket_path)
        else:
            # Use default criteria
            self._use_default_criteria()

        if regime_manifest_path:
            self._load_regime_manifest(regime_manifest_path)

        # State tracking
        self._states: Dict[str, PromotionState] = {}
        self._evaluations: List[PromotionEvaluation] = []

        logger.info(f"[PROMOTION] HRM Promotion Ladder initialized")
        logger.info(f"[PROMOTION] Output directory: {output_dir}")

    def _load_canary_basket(self, path: str) -> None:
        """Load promotion criteria from canary basket config."""
        try:
            with open(path, 'r') as f:
                config = json.load(f)

            promotion_criteria = config.get("promotion_criteria", {})
            basket = config.get("basket", {})

            # Parse primary symbols
            for sym_config in basket.get("primary_symbols", []):
                symbol = sym_config["symbol"]
                self.symbol_configs[symbol] = self._parse_symbol_criteria(
                    symbol=symbol,
                    config=sym_config,
                    promotion_criteria=promotion_criteria
                )
                self.criteria[symbol] = self._get_symbol_stage_criteria(
                    symbol, promotion_criteria
                )

            # Parse secondary symbols
            for sym_config in basket.get("secondary_symbols", []):
                symbol = sym_config["symbol"]
                self.symbol_configs[symbol] = self._parse_symbol_criteria(
                    symbol=symbol,
                    config=sym_config,
                    promotion_criteria=promotion_criteria
                )
                self.criteria[symbol] = self._get_symbol_stage_criteria(
                    symbol, promotion_criteria
                )

            logger.info(f"[PROMOTION] Loaded canary basket: {len(self.symbol_configs)} symbols")

        except Exception as e:
            logger.error(f"[PROMOTION] Failed to load canary basket: {e}")
            self._use_default_criteria()

    def _parse_symbol_criteria(
        self,
        symbol: str,
        config: Dict[str, Any],
        promotion_criteria: Dict[str, Any]
    ) -> SymbolPromotionCriteria:
        """Parse symbol-specific criteria from config."""
        crit = promotion_criteria

        return SymbolPromotionCriteria(
            symbol=symbol,
            priority=config.get("priority", 99),
            timeframes=config.get("timeframes", ["1h"]),
            allocation_weight=config.get("allocation_weight", 0.0),
            rationale=config.get("rationale", ""),
            shadow_criteria=StageCriteria(
                min_days=crit.get("shadow_mode", {}).get("min_days", 7),
                min_trades=crit.get("shadow_mode", {}).get("min_trades", 100),
                min_outperformance_rate=55.0,
                min_pnl_difference_pct=2.0,
                min_veto_accuracy=0.0,
                max_drawdown_pct=crit.get("shadow_mode", {}).get("max_drawdown_pct", 5.0),
                min_sharpe_ratio=0.0,
                min_regimes_tested=2,
                required_regimes=["VOL_NORMAL", "TREND_RANGE"],
            ),
            veto_only_criteria=StageCriteria(
                min_days=crit.get("veto_only", {}).get("min_days", 14),
                min_trades=crit.get("veto_only", {}).get("min_trades", 200),
                min_outperformance_rate=55.0,
                min_pnl_difference_pct=2.0,
                min_veto_accuracy=60.0,
                max_drawdown_pct=crit.get("veto_only", {}).get("max_drawdown_pct", 5.0),
                min_sharpe_ratio=1.0,
                min_regimes_tested=3,
                required_regimes=["VOL_NORMAL", "VOL_HIGH", "TREND_BULL_STRONG"],
            ),
            size_capped_criteria=StageCriteria(
                min_days=crit.get("size_capped", {}).get("min_days", 30),
                min_trades=crit.get("size_capped", {}).get("min_trades", 500),
                min_outperformance_rate=55.0,
                min_pnl_difference_pct=2.0,
                min_veto_accuracy=60.0,
                max_drawdown_pct=crit.get("size_capped", {}).get("max_drawdown_pct", 8.0),
                min_sharpe_ratio=1.5,
                min_regimes_tested=4,
                required_regimes=["VOL_NORMAL", "VOL_HIGH", "TREND_BULL_STRONG", "TREND_BEAR_STRONG"],
            ),
            primary_criteria=StageCriteria(
                min_days=crit.get("primary", {}).get("min_days", 60),
                min_trades=crit.get("primary", {}).get("min_trades", 1000),
                min_outperformance_rate=55.0,
                min_pnl_difference_pct=2.0,
                min_veto_accuracy=60.0,
                max_drawdown_pct=crit.get("primary", {}).get("max_drawdown_pct", 10.0),
                min_sharpe_ratio=1.5,
                min_regimes_tested=6,
                required_regimes=[],
            ),
        )

    def _get_symbol_stage_criteria(
        self,
        symbol: str,
        promotion_criteria: Dict[str, Any]
    ) -> Dict[PromotionStage, StageCriteria]:
        """Get stage criteria for a symbol."""
        return {
            PromotionStage.SHADOW: self.DEFAULT_CRITERIA[PromotionStage.SHADOW],
            PromotionStage.VETO_ONLY: self.DEFAULT_CRITERIA[PromotionStage.VETO_ONLY],
            PromotionStage.SIZE_CAPPED: self.DEFAULT_CRITERIA[PromotionStage.SIZE_CAPPED],
            PromotionStage.PRIMARY: self.DEFAULT_CRITERIA[PromotionStage.PRIMARY],
        }

    def _use_default_criteria(self) -> None:
        """Use default criteria for all symbols."""
        self.criteria["DEFAULT"] = self.DEFAULT_CRITERIA
        logger.info("[PROMOTION] Using default promotion criteria")

    def _load_regime_manifest(self, path: str) -> None:
        """Load regime manifest for regime coverage validation."""
        try:
            with open(path, 'r') as f:
                self.regime_manifest = json.load(f)
            logger.info(f"[PROMOTION] Loaded regime manifest from {path}")
        except Exception as e:
            logger.error(f"[PROMOTION] Failed to load regime manifest: {e}")
            self.regime_manifest = {}

    def _get_state_key(self, symbol: str, timeframe: Timeframe) -> str:
        """Generate unique state key."""
        return f"{symbol}_{timeframe.value}"

    def get_or_create_state(
        self,
        symbol: str,
        timeframe: Timeframe,
        initial_stage: PromotionStage = PromotionStage.SHADOW
    ) -> PromotionState:
        """Get or create promotion state for a symbol/timeframe."""
        key = self._get_state_key(symbol, timeframe)

        if key not in self._states:
            self._states[key] = PromotionState(
                symbol=symbol,
                timeframe=timeframe,
                current_stage=initial_stage,
                stage_entered_at=datetime.now(timezone.utc),
                total_days_tracked=0,
                total_trades=0,
                cumulative_pnl=0.0,
                cumulative_sharpe=0.0,
                max_drawdown=0.0,
            )
            logger.info(f"[PROMOTION] Created state for {symbol}/{timeframe.value} at {initial_stage.value}")

        return self._states[key]

    def update_state(
        self,
        symbol: str,
        timeframe: Timeframe,
        metrics: ShadowMetrics,
        regimes_detected: Optional[List[str]] = None
    ) -> None:
        """
        Update promotion state with new metrics.

        Args:
            symbol: Symbol to update
            timeframe: Timeframe
            metrics: ShadowMetrics from shadow engine
            regimes_detected: List of regimes detected during this period
        """
        state = self.get_or_create_state(symbol, timeframe)
        update_date = metrics.end_time.astimezone(timezone.utc).date().isoformat()

        if state.last_update_date == update_date:
            logger.debug(
                f"[PROMOTION] Skipping duplicate update for {symbol}/{timeframe.value} on {update_date}"
            )
            return

        # Update trade counts
        state.total_trades += metrics.hrm_shadow_trades

        # Update cumulative PnL
        state.cumulative_pnl += metrics.pnl_difference

        # Update Sharpe (simple average)
        if metrics.hrm_shadow_sharpe > 0:
            state.cumulative_sharpe = (
                (state.cumulative_sharpe * (state.total_days_tracked) + metrics.hrm_shadow_sharpe)
                / (state.total_days_tracked + 1)
            )

        # Update max drawdown
        if metrics.hrm_shadow_max_drawdown > state.max_drawdown:
            state.max_drawdown = metrics.hrm_shadow_max_drawdown

        # Update veto accuracy history
        if metrics.veto_accuracy > 0:
            state.veto_accuracy_history.append(metrics.veto_accuracy)

        state.outperformance_history.append(metrics.hrm_outperformance)

        # Update regime coverage
        if regimes_detected:
            for regime in regimes_detected:
                if regime not in state.regime_coverage:
                    state.regime_coverage.append(regime)

        # Update days tracked
        state.total_days_tracked += 1
        state.last_update_date = update_date

        logger.debug(
            f"[PROMOTION] Updated state for {symbol}/{timeframe.value}: "
            f"trades={state.total_trades}, pnl={state.cumulative_pnl:.2f}"
        )

    def evaluate_promotion(
        self,
        symbol: str,
        timeframe: Timeframe,
        metrics: ShadowMetrics,
        regimes_detected: Optional[List[str]] = None
    ) -> PromotionEvaluation:
        """
        Evaluate promotion readiness for a symbol.

        Args:
            symbol: Symbol to evaluate
            timeframe: Timeframe
            metrics: Current shadow metrics
            regimes_detected: List of regimes detected

        Returns:
            PromotionEvaluation with promotion/demotion recommendation
        """
        state = self.get_or_create_state(symbol, timeframe)
        current_stage = state.current_stage
        criteria = self._get_criteria(symbol, current_stage)

        now = datetime.now(timezone.utc)
        days_in_stage = (now - state.stage_entered_at).days

        # Calculate current metrics
        if state.outperformance_history:
            outperformance_rate = (
                sum(1 for outcome in state.outperformance_history if outcome) /
                len(state.outperformance_history) * 100.0
            )
        else:
            outperformance_rate = 100.0 if metrics.hrm_outperformance else 0.0
        pnl_difference_pct = (
            (metrics.pnl_difference / abs(metrics.baseline_net_pnl) * 100)
            if metrics.baseline_net_pnl != 0 else 0.0
        )

        # Evaluate promotion criteria
        reasons = []
        blocked_reasons = []

        # Check minimum days
        if days_in_stage < criteria.min_days:
            blocked_reasons.append(
                f"Need {criteria.min_days - days_in_stage} more days in {current_stage.value}"
            )
        else:
            reasons.append(f"✓ Minimum days met ({days_in_stage} >= {criteria.min_days})")

        # Check minimum trades
        if state.total_trades < criteria.min_trades:
            blocked_reasons.append(
                f"Need {criteria.min_trades - state.total_trades} more trades"
            )
        else:
            reasons.append(f"✓ Minimum trades met ({state.total_trades} >= {criteria.min_trades})")

        # Check outperformance rate
        if outperformance_rate < criteria.min_outperformance_rate:
            blocked_reasons.append(
                f"Outperformance rate {outperformance_rate:.1f}% < {criteria.min_outperformance_rate}%"
            )
        else:
            reasons.append(f"✓ Outperformance rate met ({outperformance_rate:.1f}%)")

        # Check PnL difference
        if pnl_difference_pct < criteria.min_pnl_difference_pct:
            blocked_reasons.append(
                f"PnL difference {pnl_difference_pct:.2f}% < {criteria.min_pnl_difference_pct}%"
            )
        else:
            reasons.append(f"✓ PnL difference met ({pnl_difference_pct:.2f}%)")

        # Check veto accuracy (for veto_only and above)
        if current_stage != PromotionStage.SHADOW:
            avg_veto_accuracy = (
                sum(state.veto_accuracy_history) / len(state.veto_accuracy_history)
                if state.veto_accuracy_history else 0.0
            )
            if avg_veto_accuracy < criteria.min_veto_accuracy:
                blocked_reasons.append(
                    f"Veto accuracy {avg_veto_accuracy:.1f}% < {criteria.min_veto_accuracy}%"
                )
            else:
                reasons.append(f"✓ Veto accuracy met ({avg_veto_accuracy:.1f}%)")

        # Check drawdown
        if state.max_drawdown > criteria.max_drawdown_pct:
            blocked_reasons.append(
                f"Max drawdown {state.max_drawdown:.2f}% > {criteria.max_drawdown_pct}%"
            )
        else:
            reasons.append(f"✓ Drawdown within limits ({state.max_drawdown:.2f}%)")

        # Check Sharpe ratio
        if current_stage != PromotionStage.SHADOW:
            if state.cumulative_sharpe < criteria.min_sharpe_ratio:
                blocked_reasons.append(
                    f"Sharpe ratio {state.cumulative_sharpe:.2f} < {criteria.min_sharpe_ratio}"
                )
            else:
                reasons.append(f"✓ Sharpe ratio met ({state.cumulative_sharpe:.2f})")

        # Check regime coverage
        regimes_tested = regimes_detected or state.regime_coverage
        if len(regimes_tested) < criteria.min_regimes_tested:
            blocked_reasons.append(
                f"Need {criteria.min_regimes_tested - len(regimes_tested)} more regimes tested"
            )
        else:
            reasons.append(f"✓ Regime coverage met ({len(regimes_tested)} regimes)")

        # Check required regimes
        if criteria.required_regimes:
            missing_regimes = [
                r for r in criteria.required_regimes
                if r not in regimes_tested
            ]
            if missing_regimes:
                blocked_reasons.append(
                    f"Missing required regimes: {', '.join(missing_regimes)}"
                )
            else:
                reasons.append(f"✓ All required regimes tested")

        # Determine promotion readiness
        promotion_ready = len(blocked_reasons) == 0
        target_stage = None

        if promotion_ready:
            next_stage = PromotionStage.next_stage(current_stage)
            if next_stage:
                target_stage = next_stage
                reasons.append(f"→ Ready for promotion to {next_stage.value}")

        # Check for demotion (regression)
        demotion_required = self._check_demotion(state, metrics)
        if demotion_required:
            prev_stage = PromotionStage.prev_stage(current_stage)
            if prev_stage:
                target_stage = prev_stage
                blocked_reasons.append(f"Demotion required to {prev_stage.value}")
            else:
                # Cannot demote from SHADOW, just mark as not ready
                blocked_reasons.append("Demotion triggered but already at SHADOW stage")

        evaluation = PromotionEvaluation(
            symbol=symbol,
            timeframe=timeframe.value,
            current_stage=current_stage,
            evaluation_date=now.isoformat(),
            days_in_stage=days_in_stage,
            total_trades=state.total_trades,
            outperformance_rate=outperformance_rate,
            pnl_difference_pct=pnl_difference_pct,
            veto_accuracy=(
                sum(state.veto_accuracy_history) / len(state.veto_accuracy_history)
                if state.veto_accuracy_history else 0.0
            ),
            current_drawdown_pct=state.max_drawdown,
            current_sharpe_ratio=state.cumulative_sharpe,
            regimes_tested=regimes_tested,
            promotion_ready=promotion_ready and not demotion_required,
            demotion_required=demotion_required,
            target_stage=target_stage,
            reasons=reasons,
            blocked_reasons=blocked_reasons,
        )

        self._evaluations.append(evaluation)

        logger.info(
            f"[PROMOTION] Evaluated {symbol}/{timeframe.value}: "
            f"{'PROMOTION READY' if evaluation.promotion_ready else 'NOT READY'} - "
            f"{' | '.join(blocked_reasons[:2]) if blocked_reasons else 'All criteria met'}"
        )

        return evaluation

    def _get_criteria(self, symbol: str, stage: PromotionStage) -> StageCriteria:
        """Get criteria for a symbol/stage combination."""
        if symbol in self.criteria:
            return self.criteria[symbol].get(stage, self.DEFAULT_CRITERIA[stage])
        return self.DEFAULT_CRITERIA.get(stage, self.DEFAULT_CRITERIA[PromotionStage.SHADOW])

    def _check_demotion(self, state: PromotionState, metrics: ShadowMetrics) -> bool:
        """Check if demotion is required due to regression."""
        current_stage = state.current_stage

        # Hard demotion triggers
        if state.max_drawdown > 15.0:  # Absolute max drawdown
            logger.warning(f"[PROMOTION] Demotion trigger: max drawdown {state.max_drawdown:.2f}%")
            return True

        if metrics.baseline_net_pnl != 0:
            pnl_diff_pct = (metrics.pnl_difference / abs(metrics.baseline_net_pnl)) * 100
            if pnl_diff_pct < -5.0:  # Underperforming by >5%
                logger.warning(f"[PROMOTION] Demotion trigger: underperforming by {pnl_diff_pct:.2f}%")
                return True

        # Veto accuracy collapse (for veto_only and above)
        if current_stage != PromotionStage.SHADOW and state.veto_accuracy_history:
            recent_veto_accuracy = state.veto_accuracy_history[-1]
            if recent_veto_accuracy < 40.0:  # Below 40% veto accuracy
                logger.warning(f"[PROMOTION] Demotion trigger: veto accuracy {recent_veto_accuracy:.1f}%")
                return True

        return False

    def promote_symbol(
        self,
        symbol: str,
        timeframe: Timeframe,
        new_stage: PromotionStage,
        reason: str = ""
    ) -> bool:
        """
        Promote a symbol to a new stage.

        Args:
            symbol: Symbol to promote
            timeframe: Timeframe
            new_stage: Target promotion stage
            reason: Reason for promotion

        Returns:
            True if promotion was successful
        """
        state = self.get_or_create_state(symbol, timeframe)
        old_stage = state.current_stage

        # Validate promotion is to next stage
        expected_next = PromotionStage.next_stage(old_stage)
        if expected_next != new_stage:
            logger.error(
                f"[PROMOTION] Invalid promotion: {old_stage.value} -> {new_stage.value} "
                f"(expected {expected_next.value if expected_next else 'none'})"
            )
            return False

        # Update state
        state.current_stage = new_stage
        state.stage_entered_at = datetime.now(timezone.utc)
        state.promotion_history.append({
            "from_stage": old_stage.value,
            "to_stage": new_stage.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        })

        logger.info(
            f"[PROMOTION] Promoted {symbol}/{timeframe.value}: "
            f"{old_stage.value} -> {new_stage.value} ({reason})"
        )

        return True

    def demote_symbol(
        self,
        symbol: str,
        timeframe: Timeframe,
        reason: str = ""
    ) -> bool:
        """
        Demote a symbol to previous stage.

        Args:
            symbol: Symbol to demote
            timeframe: Timeframe
            reason: Reason for demotion

        Returns:
            True if demotion was successful
        """
        state = self.get_or_create_state(symbol, timeframe)
        old_stage = state.current_stage

        prev_stage = PromotionStage.prev_stage(old_stage)
        if not prev_stage:
            logger.error(f"[PROMOTION] Cannot demote from {old_stage.value}")
            return False

        state.current_stage = prev_stage
        state.stage_entered_at = datetime.now(timezone.utc)
        state.promotion_history.append({
            "from_stage": old_stage.value,
            "to_stage": prev_stage.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": f"DEMOTION: {reason}",
            "type": "demotion",
        })

        logger.warning(
            f"[PROMOTION] Demoted {symbol}/{timeframe.value}: "
            f"{old_stage.value} -> {prev_stage.value} ({reason})"
        )

        return True

    def get_promotion_state(self, symbol: str, timeframe: Timeframe) -> Optional[PromotionState]:
        """Get current promotion state for a symbol."""
        key = self._get_state_key(symbol, timeframe)
        return self._states.get(key)

    def get_all_states(self) -> Dict[str, PromotionState]:
        """Get all promotion states."""
        return self._states.copy()

    def get_promotion_ready_symbols(self) -> List[PromotionEvaluation]:
        """Get all symbols ready for promotion."""
        latest: Dict[Tuple[str, str], PromotionEvaluation] = {}
        for evaluation in self._evaluations:
            latest[(evaluation.symbol, evaluation.timeframe)] = evaluation
        return [evaluation for evaluation in latest.values() if evaluation.promotion_ready]

    def get_demotion_required_symbols(self) -> List[PromotionEvaluation]:
        """Get all symbols requiring demotion."""
        latest: Dict[Tuple[str, str], PromotionEvaluation] = {}
        for evaluation in self._evaluations:
            latest[(evaluation.symbol, evaluation.timeframe)] = evaluation
        return [evaluation for evaluation in latest.values() if evaluation.demotion_required]

    def save_daily_report(self, date: Optional[datetime] = None) -> str:
        """
        Save daily promotion report.

        Args:
            date: Date to save report for (default: today)

        Returns:
            Path to saved report
        """
        if date is None:
            date = datetime.now(timezone.utc)

        date_str = date.strftime("%Y-%m-%d")
        report_path = self.output_dir / f"promotion_report_{date_str}.json"

        report = {
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_symbols_tracked": len(self._states),
            "evaluations_today": len([
                e for e in self._evaluations
                if e.evaluation_date.startswith(date_str)
            ]),
            "promotion_ready": [e.to_dict() for e in self.get_promotion_ready_symbols()],
            "demotion_required": [e.to_dict() for e in self.get_demotion_required_symbols()],
            "all_states": {k: v.to_dict() for k, v in self._states.items()},
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"[PROMOTION] Daily report saved: {report_path}")
        return str(report_path)

    def get_shadow_mode_for_stage(self, stage: PromotionStage) -> ShadowMode:
        """Convert promotion stage to shadow mode."""
        mapping = {
            PromotionStage.SHADOW: ShadowMode.SHADOW,
            PromotionStage.VETO_ONLY: ShadowMode.VETO_ONLY,
            PromotionStage.SIZE_CAPPED: ShadowMode.SIZE_CAPPED,
            PromotionStage.PRIMARY: ShadowMode.PRIMARY,
        }
        return mapping.get(stage, ShadowMode.SHADOW)


def create_promotion_ladder(
    canary_basket_path: str = "/Users/jim/work/curly-succotash/coordination/runtime/canary_basket.json",
    regime_manifest_path: str = "/Users/jim/work/curly-succotash/coordination/runtime/regime_manifest.json",
    output_dir: str = "/Users/jim/work/curly-succotash/logs/promotion"
) -> HRMPromotionLadder:
    """
    Factory function to create promotion ladder with default paths.

    Returns:
        Configured HRMPromotionLadder instance
    """
    return HRMPromotionLadder(
        canary_basket_path=canary_basket_path,
        regime_manifest_path=regime_manifest_path,
        output_dir=output_dir
    )
