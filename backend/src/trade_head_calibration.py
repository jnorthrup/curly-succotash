"""Placeholder module for trade-head calibration logic.

This module provides an interface for computing a cost-aware training objective
for trade-head outputs.  The real implementation is future work (MT10).

Currently the `TradeHeadCalibrator` simply returns zero cost, satisfying the
backlog requirement to have a loadable interface and allow downstream code to
check for calibration existence.
"""

from __future__ import annotations

from typing import Any, Dict


class TradeHeadCalibrator:
    """Minimal calibrator used during model training and evaluation.

    Computes a cost-aware objective that reflects trading reality (e.g., fee penalty,
    missed profit).
    """

    def __init__(self, fee_rate: float = 0.001) -> None:
        """
        Initialize the calibrator.
        
        Args:
            fee_rate: Base fee/slippage rate applied per trade side. 
                      Default is 0.1% (0.001).
        """
        self.fee_rate = fee_rate
        self.loaded = False

    def compute_cost(self, prediction: Dict[str, Any], actual: Optional[Dict[str, Any]] = None) -> float:
        """Compute a cost for a trade-head prediction.

        Parameters
        ----------
        prediction:
            dictionary representing a model prediction. Expected keys:
            - 'direction': 1 for long, -1 for short, 0 for neutral
            - 'confidence': 0.0 to 1.0 (optional)
        actual:
            dictionary representing the ground truth. Expected keys:
            - 'return': actual percentage return over the target horizon
            If not provided, falls back to a placeholder sum-of-absolute-values.

        Returns
        -------
        float
            cost value; lower is better (a perfect trade has negative cost or zero).
        """
        self.loaded = True

        if actual is None:
            # Fallback for old code calling this without actuals
            cost = 0.0
            for v in prediction.values():
                if isinstance(v, (int, float)):
                    cost += abs(v)
            return cost

        # Extract prediction values
        direction = prediction.get("direction", 0)
        
        # We only consider hard directional bets for simple cost
        if direction not in (-1, 0, 1):
            # Penalize invalid directions heavily
            return 100.0
            
        # Extract ground truth
        actual_return = actual.get("return", 0.0)

        if direction == 0:
            # Neutral position: missed opportunity cost if there was a big move
            # but no fee penalty. We penalize missing out on > fee_rate moves.
            abs_return = abs(actual_return)
            if abs_return > self.fee_rate * 2:
                return abs_return - (self.fee_rate * 2)
            return 0.0

        # Active position cost:
        # PnL = (direction * actual_return) - (2 * fee_rate)
        # Cost is negative PnL (we want to minimize cost -> maximize PnL)
        pnl = (direction * actual_return) - (2 * self.fee_rate)
        
        return -pnl

    def compute_tp_sl(
        self,
        volatility: float,
        regime: str,
        base_tp_mult: float = 2.0,
        base_sl_mult: float = 1.0
    ) -> tuple[float, float]:
        """Calculate realistic TP/SL levels based on volatility and regime.
        
        Args:
            volatility: Current market volatility (e.g., rolling std of returns).
            regime: Current market regime (e.g., 'VOL_HIGH', 'TREND_BULL_STRONG').
            base_tp_mult: Multiple of volatility for take-profit.
            base_sl_mult: Multiple of volatility for stop-loss.
            
        Returns:
            Tuple of (take_profit_pct, stop_loss_pct)
        """
        # Adjust multiples based on regime
        tp_mult = base_tp_mult
        sl_mult = base_sl_mult
        
        if "VOL_HIGH" in regime:
            # Wider stops in high volatility
            tp_mult *= 1.5
            sl_mult *= 1.5
        elif "VOL_LOW" in regime:
            # Tighter stops in low volatility
            tp_mult *= 0.8
            sl_mult *= 0.8
            
        if "TREND" in regime:
            # In trending markets, let profits run a bit more
            tp_mult *= 1.2
            
        tp_pct = volatility * tp_mult
        sl_pct = volatility * sl_mult
        
        # Ensure minimum bounds (e.g., must cover fees)
        tp_pct = max(tp_pct, self.fee_rate * 5)
        sl_pct = max(sl_pct, self.fee_rate * 3)
        
        return tp_pct, sl_pct


# convenience helper for downstream consumers

def is_calibration_loaded(obj: Any) -> bool:
    """Check whether an object has a loaded trade-head calibration.

    Used by ring-agent code to surface the `trade_head_calibration_loaded`
    boolean flag in API responses.

    The input may be an object with a ``loaded`` attribute (used by the
    calibrator class) or a raw dictionary containing a
    ``trade_head_calibration_loaded`` key (used in payloads).
    """
    # dict payloads are the most common path in the ring-agent integrations
    if isinstance(obj, dict):
        return bool(obj.get("trade_head_calibration_loaded"))
    return getattr(obj, "loaded", False) is True
