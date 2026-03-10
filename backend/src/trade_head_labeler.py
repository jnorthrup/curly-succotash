"""
Trade-Head Labeler - Realistic Target Generation for TP/SL

Generates training labels for the trade-head by simulating 
Take-Profit (TP) and Stop-Loss (SL) conditions on future market data.
Satisfies the requirement for TP/SL realism in trade-head targets.
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
from .models import Candle

logger = logging.getLogger(__name__)


class TradeHeadLabeler:
    """Generates realistic trading labels based on future price action."""

    def __init__(self, fee_rate: float = 0.001):
        """
        Initialize the labeler.
        
        Args:
            fee_rate: Base fee/slippage rate used to offset targets.
        """
        self.fee_rate = fee_rate

    def generate_label(
        self,
        current_candle: Candle,
        future_candles: List[Candle],
        tp_pct: float,
        sl_pct: float
    ) -> int:
        """
        Determine the optimal trade action based on future price action.
        
        Args:
            current_candle: The candle at the time of prediction.
            future_candles: Sequence of future candles to evaluate.
            tp_pct: Take-profit percentage (e.g., 0.02 for 2%).
            sl_pct: Stop-loss percentage (e.g., 0.01 for 1%).
            
        Returns:
            int: 1 for Long, -1 for Short, 0 for Neutral.
        """
        if not future_candles:
            return 0
            
        entry_price = current_candle.close
        
        # Calculate absolute price levels
        long_tp = entry_price * (1 + tp_pct)
        long_sl = entry_price * (1 - sl_pct)
        
        short_tp = entry_price * (1 - tp_pct)
        short_sl = entry_price * (1 + sl_pct)
        
        # Track which side hits first
        long_success = False
        short_success = False
        
        # Simulate Long
        for candle in future_candles:
            if candle.low <= long_sl:
                # Stop loss hit first
                break
            if candle.high >= long_tp:
                # Take profit hit!
                long_success = True
                break
                
        # Simulate Short
        for candle in future_candles:
            if candle.high >= short_sl:
                # Stop loss hit first
                break
            if candle.low <= short_tp:
                # Take profit hit!
                short_success = True
                break
                
        if long_success and not short_success:
            return 1
        if short_success and not long_success:
            return -1
            
        # If both hit (volatile) or neither hit (range-bound), return neutral
        return 0

    def generate_batch_labels(
        self,
        candles: List[Candle],
        lookahead_window: int,
        tp_pct: float,
        sl_pct: float
    ) -> List[int]:
        """Generate labels for a whole sequence of candles."""
        labels = []
        for i in range(len(candles)):
            if i + lookahead_window >= len(candles):
                labels.append(0) # Not enough lookahead
                continue
                
            current = candles[i]
            future = candles[i+1 : i+1+lookahead_window]
            labels.append(self.generate_label(current, future, tp_pct, sl_pct))
            
        return labels
