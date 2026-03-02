"""
Technical Analysis Indicators
Pure Python implementations of SOTA trading indicators.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import math
from .models import Candle


@dataclass
class IndicatorResult:
    """Container for indicator values with metadata."""
    name: str
    values: List[float]
    period: int


def calculate_sma(candles: List[Candle], period: int) -> List[float]:
    """Simple Moving Average."""
    if len(candles) < period:
        return []
    
    closes = [c.close for c in candles]
    sma = []
    
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        sma.append(sum(window) / period)
    
    return sma


def calculate_ema(candles: List[Candle], period: int) -> List[float]:
    """Exponential Moving Average."""
    if len(candles) < period:
        return []
    
    closes = [c.close for c in candles]
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    
    for i in range(period, len(closes)):
        ema.append(closes[i] * k + ema[-1] * (1 - k))
    
    return ema


def calculate_ema_from_values(values: List[float], period: int) -> List[float]:
    """EMA calculated from raw values instead of candles."""
    if len(values) < period:
        return []
    
    k = 2 / (period + 1)
    ema = [sum(values[:period]) / period]
    
    for i in range(period, len(values)):
        ema.append(values[i] * k + ema[-1] * (1 - k))
    
    return ema


def calculate_rsi(candles: List[Candle], period: int = 14) -> List[float]:
    """Relative Strength Index."""
    if len(candles) < period + 1:
        return []
    
    closes = [c.close for c in candles]
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    if len(gains) < period:
        return []
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi = []
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    
    return rsi


def calculate_macd(
    candles: List[Candle],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[List[float], List[float], List[float]]:
    """MACD (Moving Average Convergence Divergence)."""
    ema_fast = calculate_ema(candles, fast)
    ema_slow = calculate_ema(candles, slow)
    
    offset = slow - fast
    macd_line = []
    
    for i in range(len(ema_slow)):
        if i + offset < len(ema_fast):
            macd_line.append(ema_fast[i + offset] - ema_slow[i])
    
    if len(macd_line) < signal:
        return [], [], []
    
    signal_line = calculate_ema_from_values(macd_line, signal)
    
    histogram = []
    signal_offset = signal - 1
    for i in range(len(signal_line)):
        if i + signal_offset < len(macd_line):
            histogram.append(macd_line[i + signal_offset] - signal_line[i])
    
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    candles: List[Candle],
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """Bollinger Bands (middle, upper, lower)."""
    if len(candles) < period:
        return [], [], []
    
    closes = [c.close for c in candles]
    middle = []
    upper = []
    lower = []
    
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = math.sqrt(variance)
        
        middle.append(sma)
        upper.append(sma + std_dev * std)
        lower.append(sma - std_dev * std)
    
    return middle, upper, lower


def calculate_atr(candles: List[Candle], period: int = 14) -> List[float]:
    """Average True Range."""
    if len(candles) < period + 1:
        return []
    
    tr = []
    for i in range(1, len(candles)):
        high_low = candles[i].high - candles[i].low
        high_close = abs(candles[i].high - candles[i - 1].close)
        low_close = abs(candles[i].low - candles[i - 1].close)
        tr.append(max(high_low, high_close, low_close))
    
    if len(tr) < period:
        return []
    
    atr = [sum(tr[:period]) / period]
    
    for i in range(period, len(tr)):
        atr.append((atr[-1] * (period - 1) + tr[i]) / period)
    
    return atr


def calculate_adx(candles: List[Candle], period: int = 14) -> Tuple[List[float], List[float], List[float]]:
    """Average Directional Index with +DI and -DI."""
    if len(candles) < period + 1:
        return [], [], []
    
    plus_dm = []
    minus_dm = []
    tr = []
    
    for i in range(1, len(candles)):
        high_diff = candles[i].high - candles[i - 1].high
        low_diff = candles[i - 1].low - candles[i].low
        
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)
        
        high_low = candles[i].high - candles[i].low
        high_close = abs(candles[i].high - candles[i - 1].close)
        low_close = abs(candles[i].low - candles[i - 1].close)
        tr.append(max(high_low, high_close, low_close))
    
    if len(tr) < period:
        return [], [], []
    
    smoothed_plus_dm = [sum(plus_dm[:period])]
    smoothed_minus_dm = [sum(minus_dm[:period])]
    smoothed_tr = [sum(tr[:period])]
    
    for i in range(period, len(tr)):
        smoothed_plus_dm.append(smoothed_plus_dm[-1] - smoothed_plus_dm[-1] / period + plus_dm[i])
        smoothed_minus_dm.append(smoothed_minus_dm[-1] - smoothed_minus_dm[-1] / period + minus_dm[i])
        smoothed_tr.append(smoothed_tr[-1] - smoothed_tr[-1] / period + tr[i])
    
    plus_di = []
    minus_di = []
    dx = []
    
    for i in range(len(smoothed_tr)):
        if smoothed_tr[i] == 0:
            plus_di.append(0)
            minus_di.append(0)
        else:
            plus_di.append(100 * smoothed_plus_dm[i] / smoothed_tr[i])
            minus_di.append(100 * smoothed_minus_dm[i] / smoothed_tr[i])
        
        di_sum = plus_di[-1] + minus_di[-1]
        if di_sum == 0:
            dx.append(0)
        else:
            dx.append(100 * abs(plus_di[-1] - minus_di[-1]) / di_sum)
    
    if len(dx) < period:
        return plus_di, minus_di, []
    
    adx = [sum(dx[:period]) / period]
    for i in range(period, len(dx)):
        adx.append((adx[-1] * (period - 1) + dx[i]) / period)
    
    return plus_di, minus_di, adx


def calculate_stochastic(
    candles: List[Candle],
    k_period: int = 14,
    d_period: int = 3
) -> Tuple[List[float], List[float]]:
    """Stochastic Oscillator (%K and %D)."""
    if len(candles) < k_period:
        return [], []
    
    k_values = []
    
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1:i + 1]
        highest_high = max(c.high for c in window)
        lowest_low = min(c.low for c in window)
        
        if highest_high == lowest_low:
            k_values.append(50.0)
        else:
            k = 100 * (candles[i].close - lowest_low) / (highest_high - lowest_low)
            k_values.append(k)
    
    if len(k_values) < d_period:
        return k_values, []
    
    d_values = []
    for i in range(d_period - 1, len(k_values)):
        d = sum(k_values[i - d_period + 1:i + 1]) / d_period
        d_values.append(d)
    
    return k_values, d_values


def calculate_donchian_channel(
    candles: List[Candle],
    period: int = 20
) -> Tuple[List[float], List[float], List[float]]:
    """Donchian Channel (upper, lower, middle)."""
    if len(candles) < period:
        return [], [], []
    
    upper = []
    lower = []
    middle = []
    
    for i in range(period - 1, len(candles)):
        window = candles[i - period + 1:i + 1]
        high = max(c.high for c in window)
        low = min(c.low for c in window)
        
        upper.append(high)
        lower.append(low)
        middle.append((high + low) / 2)
    
    return upper, lower, middle


def calculate_keltner_channel(
    candles: List[Candle],
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """Keltner Channel (middle, upper, lower)."""
    ema = calculate_ema(candles, ema_period)
    atr = calculate_atr(candles, atr_period)
    
    if not ema or not atr:
        return [], [], []
    
    offset = max(0, len(ema) - len(atr))
    
    middle = []
    upper = []
    lower = []
    
    for i in range(len(atr)):
        ema_idx = i + offset
        if ema_idx < len(ema):
            mid = ema[ema_idx]
            middle.append(mid)
            upper.append(mid + multiplier * atr[i])
            lower.append(mid - multiplier * atr[i])
    
    return middle, upper, lower


def calculate_supertrend(
    candles: List[Candle],
    period: int = 10,
    multiplier: float = 3.0
) -> Tuple[List[float], List[int]]:
    """
    Supertrend indicator.
    Returns (supertrend_values, directions) where direction is 1 for uptrend, -1 for downtrend.
    """
    atr = calculate_atr(candles, period)
    
    if not atr:
        return [], []
    
    offset = len(candles) - len(atr) - 1
    
    supertrend = []
    directions = []
    
    upper_band = []
    lower_band = []
    
    for i in range(len(atr)):
        candle_idx = i + offset + 1
        if candle_idx >= len(candles):
            break
            
        hl2 = (candles[candle_idx].high + candles[candle_idx].low) / 2
        basic_upper = hl2 + multiplier * atr[i]
        basic_lower = hl2 - multiplier * atr[i]
        
        if i == 0:
            upper_band.append(basic_upper)
            lower_band.append(basic_lower)
            supertrend.append(basic_lower)
            directions.append(1)
        else:
            prev_close = candles[candle_idx - 1].close
            
            final_upper = basic_upper if basic_upper < upper_band[-1] or prev_close > upper_band[-1] else upper_band[-1]
            final_lower = basic_lower if basic_lower > lower_band[-1] or prev_close < lower_band[-1] else lower_band[-1]
            
            upper_band.append(final_upper)
            lower_band.append(final_lower)
            
            if directions[-1] == 1:
                if candles[candle_idx].close < final_lower:
                    directions.append(-1)
                    supertrend.append(final_upper)
                else:
                    directions.append(1)
                    supertrend.append(final_lower)
            else:
                if candles[candle_idx].close > final_upper:
                    directions.append(1)
                    supertrend.append(final_lower)
                else:
                    directions.append(-1)
                    supertrend.append(final_upper)
    
    return supertrend, directions


def calculate_obv(candles: List[Candle]) -> List[float]:
    """On-Balance Volume."""
    if len(candles) < 2:
        return []
    
    obv = [0.0]
    
    for i in range(1, len(candles)):
        if candles[i].close > candles[i - 1].close:
            obv.append(obv[-1] + candles[i].volume)
        elif candles[i].close < candles[i - 1].close:
            obv.append(obv[-1] - candles[i].volume)
        else:
            obv.append(obv[-1])
    
    return obv


def calculate_ema_ribbon(
    candles: List[Candle],
    periods: List[int] = None
) -> List[List[float]]:
    """EMA Ribbon with multiple periods."""
    if periods is None:
        periods = [8, 13, 21, 34, 55]
    
    return [calculate_ema(candles, p) for p in periods]


def calculate_volatility(candles: List[Candle], period: int = 20) -> List[float]:
    """Historical volatility (standard deviation of returns)."""
    if len(candles) < period + 1:
        return []
    
    returns = []
    for i in range(1, len(candles)):
        if candles[i - 1].close > 0:
            returns.append((candles[i].close - candles[i - 1].close) / candles[i - 1].close)
        else:
            returns.append(0)
    
    volatility = []
    for i in range(period - 1, len(returns)):
        window = returns[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((r - mean) ** 2 for r in window) / period
        volatility.append(math.sqrt(variance))
    
    return volatility


def detect_regime(candles: List[Candle]) -> dict:
    """
    Detect market regime based on multiple indicators.
    Returns regime classification and strength.
    """
    if len(candles) < 200:
        return {"regime": "UNKNOWN", "strength": 0.0, "volatility": "UNKNOWN"}
    
    close = candles[-1].close
    sma50 = calculate_sma(candles, 50)
    sma200 = calculate_sma(candles, 200)
    atr = calculate_atr(candles)
    volatility = calculate_volatility(candles)
    
    trend = "BULL" if sma50 and sma200 and sma50[-1] > sma200[-1] else "BEAR"
    
    vol_regime = "HIGH_VOL" if volatility and volatility[-1] > 0.02 else "LOW_VOL"
    
    strength = 0.0
    if sma50 and sma200:
        strength = abs(sma50[-1] - sma200[-1]) / close
    
    return {
        "regime": f"{trend}_{vol_regime}",
        "trend": trend,
        "volatility_regime": vol_regime,
        "strength": strength,
        "current_volatility": volatility[-1] if volatility else 0.0,
    }