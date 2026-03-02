"""
12 State-of-the-Art Trading Strategies
Each strategy maintains independent state and produces discrete signals.
All strategies are paper-only - no real market orders are placed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from .models import Candle, Signal, SignalType, Timeframe, Position
from .indicators import (
    calculate_sma, calculate_ema, calculate_rsi, calculate_macd,
    calculate_bollinger_bands, calculate_atr, calculate_adx,
    calculate_stochastic, calculate_donchian_channel, calculate_keltner_channel,
    calculate_supertrend, calculate_obv, calculate_ema_ribbon,
    calculate_volatility, detect_regime
)


@dataclass
class StrategyConfig:
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    max_positions: int = 1
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Each strategy maintains its own state and produces independent signals.
    """
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or StrategyConfig()
        self.equity = self.config.initial_capital
        self.position: Optional[Position] = None
        self.signals: List[Signal] = []
        self.trades: List[Dict] = []
        self._candle_buffer: List[Candle] = []
        self._min_candles = 200
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @abstractmethod
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """Generate a trading signal based on current market data."""
        pass
    
    def process_candle(self, candle: Candle) -> Optional[Signal]:
        """Process incoming candle and generate signal if conditions are met."""
        self._candle_buffer.append(candle)
        
        if len(self._candle_buffer) > 1000:
            self._candle_buffer = self._candle_buffer[-500:]
        
        if len(self._candle_buffer) < self._min_candles:
            return None
        
        self._check_stops(candle)
        
        signal = self.generate_signal(self._candle_buffer)
        
        if signal:
            self.signals.append(signal)
            self._execute_paper_signal(signal, candle)
        
        return signal
    
    def _check_stops(self, candle: Candle):
        """Check and execute stop-loss or take-profit."""
        if not self.position:
            return
        
        self.position.update_pnl(candle.close)
        
        if self.position.stop_loss and candle.low <= self.position.stop_loss:
            self._close_position(candle, self.position.stop_loss, "Stop-loss hit")
        elif self.position.take_profit and candle.high >= self.position.take_profit:
            self._close_position(candle, self.position.take_profit, "Take-profit hit")
    
    def _close_position(self, candle: Candle, exit_price: float, reason: str):
        """Close current position and record trade."""
        if not self.position:
            return
        
        if self.position.side == SignalType.LONG:
            pnl = (exit_price - self.position.entry_price) * self.position.size
        else:
            pnl = (self.position.entry_price - exit_price) * self.position.size
        
        self.equity += pnl
        
        self.trades.append({
            "entry_time": self.position.entry_time,
            "exit_time": candle.timestamp,
            "symbol": self.position.symbol,
            "side": self.position.side.value,
            "entry_price": self.position.entry_price,
            "exit_price": exit_price,
            "size": self.position.size,
            "pnl": pnl,
            "reason": reason,
        })
        
        self.position = None
    
    def _execute_paper_signal(self, signal: Signal, candle: Candle):
        """Execute paper trade based on signal."""
        if signal.signal_type == SignalType.LONG and not self.position:
            size = (self.equity * self.config.position_size_pct / 100) / signal.entry_price
            self.position = Position(
                symbol=signal.symbol,
                strategy_name=self.name,
                side=SignalType.LONG,
                entry_price=signal.entry_price,
                entry_time=signal.timestamp,
                size=size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
        elif signal.signal_type == SignalType.SHORT and not self.position:
            size = (self.equity * self.config.position_size_pct / 100) / signal.entry_price
            self.position = Position(
                symbol=signal.symbol,
                strategy_name=self.name,
                side=SignalType.SHORT,
                entry_price=signal.entry_price,
                entry_time=signal.timestamp,
                size=size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
        elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT, SignalType.FLAT]:
            if self.position:
                self._close_position(candle, signal.entry_price, signal.reason)
    
    def calculate_paper_size(self, price: float) -> float:
        """Calculate position size based on configuration."""
        return (self.equity * self.config.position_size_pct / 100) / price
    
    def get_state(self) -> Dict[str, Any]:
        """Get current strategy state."""
        return {
            "name": self.name,
            "description": self.description,
            "equity": self.equity,
            "position": self.position.to_dict() if self.position else None,
            "num_trades": len(self.trades),
            "num_signals": len(self.signals),
            "return_pct": ((self.equity - self.config.initial_capital) / self.config.initial_capital) * 100,
        }
    
    def reset(self):
        """Reset strategy state for new backtest."""
        self.equity = self.config.initial_capital
        self.position = None
        self.signals = []
        self.trades = []
        self._candle_buffer = []


class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy with Regime Filter.
    Uses 21/55 SMA crossover with trend regime confirmation.
    """
    
    @property
    def name(self) -> str:
        return "MA_Crossover"
    
    @property
    def description(self) -> str:
        return "21/55 SMA crossover with bull/bear regime filter"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        sma_fast = calculate_sma(candles, 21)
        sma_slow = calculate_sma(candles, 55)
        regime = detect_regime(candles)
        
        if len(sma_fast) < 2 or len(sma_slow) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        fast_cross_above = sma_fast[-2] <= sma_slow[-2] and sma_fast[-1] > sma_slow[-1]
        fast_cross_below = sma_fast[-2] >= sma_slow[-2] and sma_fast[-1] < sma_slow[-1]
        
        if fast_cross_above and regime["trend"] == "BULL" and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * (1 - self.config.stop_loss_pct / 100),
                take_profit=price * (1 + self.config.take_profit_pct / 100),
                confidence=0.7 + regime["strength"] * 0.3,
                paper_size=self.calculate_paper_size(price),
                reason=f"MA crossover bullish in {regime['regime']}",
            )
        
        if fast_cross_below and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.8,
                paper_size=0,
                reason="MA crossover bearish - exit",
            )
        
        return None


class RSIMeanReversionStrategy(BaseStrategy):
    """
    RSI Mean Reversion Strategy with Low Volatility Filter.
    Buys oversold, sells overbought in range-bound markets.
    """
    
    @property
    def name(self) -> str:
        return "RSI_Mean_Reversion"
    
    @property
    def description(self) -> str:
        return "RSI oversold/overbought reversal with volatility filter"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        rsi = calculate_rsi(candles, 14)
        regime = detect_regime(candles)
        
        if len(rsi) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        is_low_vol = regime["volatility_regime"] == "LOW_VOL"
        
        if rsi[-1] < 30 and is_low_vol and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * 0.97,
                take_profit=price * 1.05,
                confidence=0.6 + (30 - rsi[-1]) / 30 * 0.3,
                paper_size=self.calculate_paper_size(price),
                reason=f"RSI oversold ({rsi[-1]:.1f}) in low volatility",
            )
        
        if rsi[-1] > 70 and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.75,
                paper_size=0,
                reason=f"RSI overbought ({rsi[-1]:.1f}) - exit",
            )
        
        return None


class BollingerBreakoutStrategy(BaseStrategy):
    """
    Bollinger Bands Breakout Strategy.
    Trades breakouts from Bollinger Band squeezes.
    """
    
    @property
    def name(self) -> str:
        return "Bollinger_Breakout"
    
    @property
    def description(self) -> str:
        return "Bollinger Band breakout with squeeze detection"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        middle, upper, lower = calculate_bollinger_bands(candles, 20, 2.0)
        
        if len(middle) < 10:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        band_width = (upper[-1] - lower[-1]) / middle[-1]
        avg_band_width = sum((upper[i] - lower[i]) / middle[i] for i in range(-10, 0)) / 10
        is_squeeze = band_width < avg_band_width * 0.8
        
        if price > upper[-1] and is_squeeze and not self.position:
            atr = calculate_atr(candles)
            stop = price - 2 * atr[-1] if atr else price * 0.98
            
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=stop,
                take_profit=price * 1.06,
                confidence=0.65,
                paper_size=self.calculate_paper_size(price),
                reason="Bollinger upper breakout from squeeze",
            )
        
        if price < lower[-1] and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason="Price broke below lower band - exit",
            )
        
        return None


class MACDMomentumStrategy(BaseStrategy):
    """
    MACD Momentum Strategy with Histogram Divergence.
    Uses MACD crossovers and histogram momentum.
    """
    
    @property
    def name(self) -> str:
        return "MACD_Momentum"
    
    @property
    def description(self) -> str:
        return "MACD line crossover with histogram momentum confirmation"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        macd_line, signal_line, histogram = calculate_macd(candles)
        
        if len(histogram) < 3:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        macd_cross_above = (len(macd_line) >= 2 and len(signal_line) >= 2 and
                          macd_line[-2] <= signal_line[-2] and macd_line[-1] > signal_line[-1])
        histogram_rising = histogram[-1] > histogram[-2] > histogram[-3]
        
        if macd_cross_above and histogram[-1] > 0 and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * 0.975,
                take_profit=price * 1.05,
                confidence=0.7 if histogram_rising else 0.55,
                paper_size=self.calculate_paper_size(price),
                reason="MACD bullish crossover with positive histogram",
            )
        
        macd_cross_below = (len(macd_line) >= 2 and len(signal_line) >= 2 and
                          macd_line[-2] >= signal_line[-2] and macd_line[-1] < signal_line[-1])
        
        if macd_cross_below and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.75,
                paper_size=0,
                reason="MACD bearish crossover - exit",
            )
        
        return None


class SupertrendStrategy(BaseStrategy):
    """
    Supertrend Strategy for Trend Following.
    Uses ATR-based dynamic support/resistance.
    """
    
    @property
    def name(self) -> str:
        return "Supertrend"
    
    @property
    def description(self) -> str:
        return "ATR-based Supertrend with dynamic trend detection"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        supertrend, directions = calculate_supertrend(candles, 10, 3.0)
        
        if len(directions) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        trend_change_bullish = directions[-2] == -1 and directions[-1] == 1
        trend_change_bearish = directions[-2] == 1 and directions[-1] == -1
        
        if trend_change_bullish and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=supertrend[-1],
                take_profit=price * 1.06,
                confidence=0.72,
                paper_size=self.calculate_paper_size(price),
                reason="Supertrend flipped bullish",
            )
        
        if trend_change_bearish and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.78,
                paper_size=0,
                reason="Supertrend flipped bearish - exit",
            )
        
        return None


class ADXTrendFilterStrategy(BaseStrategy):
    """
    ADX Strong Trend Strategy.
    Only trades when ADX confirms strong trend.
    """
    
    @property
    def name(self) -> str:
        return "ADX_Trend_Filter"
    
    @property
    def description(self) -> str:
        return "ADX > 25 strong trend filter with DI crossover"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        plus_di, minus_di, adx = calculate_adx(candles, 14)
        
        if not adx or len(adx) < 2 or len(plus_di) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        strong_trend = adx[-1] > 25
        di_cross_bullish = plus_di[-2] <= minus_di[-2] and plus_di[-1] > minus_di[-1]
        di_cross_bearish = plus_di[-2] >= minus_di[-2] and plus_di[-1] < minus_di[-1]
        
        if strong_trend and di_cross_bullish and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * 0.975,
                take_profit=price * 1.055,
                confidence=0.6 + (adx[-1] - 25) / 50,
                paper_size=self.calculate_paper_size(price),
                reason=f"ADX={adx[-1]:.1f} strong trend, +DI cross above -DI",
            )
        
        if (di_cross_bearish or adx[-1] < 20) and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason="DI bearish cross or weak ADX - exit",
            )
        
        return None


class VolatilityRegimeSwitchStrategy(BaseStrategy):
    """
    Volatility Regime Switching Strategy.
    Adapts between mean-reversion and breakout based on volatility.
    """
    
    @property
    def name(self) -> str:
        return "Volatility_Regime_Switch"
    
    @property
    def description(self) -> str:
        return "Adapts strategy based on high/low volatility regime"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        volatility = calculate_volatility(candles, 20)
        rsi = calculate_rsi(candles, 14)
        middle, upper, lower = calculate_bollinger_bands(candles, 20, 2.0)
        
        if not volatility or not rsi or not middle:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        avg_vol = sum(volatility[-20:]) / min(20, len(volatility))
        is_high_vol = volatility[-1] > avg_vol * 1.5
        
        if is_high_vol:
            if price > upper[-1] and not self.position:
                return Signal(
                    timestamp=current_candle.timestamp,
                    symbol=current_candle.symbol,
                    timeframe=current_candle.timeframe,
                    strategy_name=self.name,
                    signal_type=SignalType.LONG,
                    entry_price=price,
                    stop_loss=middle[-1],
                    take_profit=price * 1.08,
                    confidence=0.65,
                    paper_size=self.calculate_paper_size(price),
                    reason="High volatility breakout above upper BB",
                )
        else:
            if rsi[-1] < 35 and not self.position:
                return Signal(
                    timestamp=current_candle.timestamp,
                    symbol=current_candle.symbol,
                    timeframe=current_candle.timeframe,
                    strategy_name=self.name,
                    signal_type=SignalType.LONG,
                    entry_price=price,
                    stop_loss=price * 0.97,
                    take_profit=middle[-1],
                    confidence=0.6,
                    paper_size=self.calculate_paper_size(price),
                    reason="Low volatility mean reversion from oversold",
                )
        
        if self.position and ((is_high_vol and price < middle[-1]) or (not is_high_vol and rsi[-1] > 65)):
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason="Regime-based exit condition met",
            )
        
        return None


class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout Strategy.
    Classic turtle-trading style breakout system.
    """
    
    @property
    def name(self) -> str:
        return "Donchian_Breakout"
    
    @property
    def description(self) -> str:
        return "20-period Donchian channel breakout (turtle trading)"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        upper, lower, middle = calculate_donchian_channel(candles, 20)
        
        if len(upper) < 2:
            return None
        
        current_candle = candles[-1]
        prev_candle = candles[-2]
        price = current_candle.close
        
        breakout_up = prev_candle.close <= upper[-2] and current_candle.close > upper[-1]
        breakout_down = prev_candle.close >= lower[-2] and current_candle.close < lower[-1]
        
        if breakout_up and not self.position:
            atr = calculate_atr(candles)
            stop = price - 2 * atr[-1] if atr else lower[-1]
            
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=stop,
                take_profit=price * 1.06,
                confidence=0.68,
                paper_size=self.calculate_paper_size(price),
                reason="Donchian 20-period high breakout",
            )
        
        if (breakout_down or current_candle.close < middle[-1]) and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.72,
                paper_size=0,
                reason="Price below Donchian middle - exit",
            )
        
        return None


class KeltnerChannelStrategy(BaseStrategy):
    """
    Keltner Channel Strategy.
    EMA + ATR based channel trading.
    """
    
    @property
    def name(self) -> str:
        return "Keltner_Channel"
    
    @property
    def description(self) -> str:
        return "Keltner Channel (EMA + 2x ATR) breakout strategy"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        middle, upper, lower = calculate_keltner_channel(candles, 20, 10, 2.0)
        
        if len(middle) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        if price > upper[-1] and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=middle[-1],
                take_profit=price + (price - middle[-1]),
                confidence=0.64,
                paper_size=self.calculate_paper_size(price),
                reason="Keltner upper channel breakout",
            )
        
        if price < middle[-1] and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason="Price below Keltner middle - exit",
            )
        
        return None


class StochasticOscillatorStrategy(BaseStrategy):
    """
    Stochastic Oscillator Strategy.
    %K/%D crossover with overbought/oversold levels.
    """
    
    @property
    def name(self) -> str:
        return "Stochastic_Oscillator"
    
    @property
    def description(self) -> str:
        return "Stochastic %K/%D crossover with 20/80 levels"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        k_values, d_values = calculate_stochastic(candles, 14, 3)
        
        if len(k_values) < 2 or len(d_values) < 2:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        k_offset = len(k_values) - len(d_values)
        k_curr = k_values[-1]
        k_prev = k_values[-2]
        d_curr = d_values[-1]
        d_prev = d_values[-2]
        
        bullish_cross = k_prev <= d_prev and k_curr > d_curr
        bearish_cross = k_prev >= d_prev and k_curr < d_curr
        
        if bullish_cross and k_curr < 30 and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * 0.975,
                take_profit=price * 1.05,
                confidence=0.62 + (30 - k_curr) / 100,
                paper_size=self.calculate_paper_size(price),
                reason=f"Stochastic bullish cross in oversold (%K={k_curr:.1f})",
            )
        
        if (bearish_cross or k_curr > 80) and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason=f"Stochastic overbought or bearish cross (%K={k_curr:.1f})",
            )
        
        return None


class EMARibbonStrategy(BaseStrategy):
    """
    EMA Ribbon Strategy.
    Uses multiple EMAs (8, 13, 21, 34, 55) for trend confirmation.
    """
    
    @property
    def name(self) -> str:
        return "EMA_Ribbon"
    
    @property
    def description(self) -> str:
        return "8/13/21/34/55 EMA ribbon alignment for trend trading"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        ribbon = calculate_ema_ribbon(candles, [8, 13, 21, 34, 55])
        
        if any(len(ema) < 2 for ema in ribbon):
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        current_values = [ema[-1] for ema in ribbon]
        prev_values = [ema[-2] for ema in ribbon]
        
        bullish_alignment = all(current_values[i] > current_values[i+1] for i in range(len(current_values)-1))
        bearish_alignment = all(current_values[i] < current_values[i+1] for i in range(len(current_values)-1))
        
        was_bullish = all(prev_values[i] > prev_values[i+1] for i in range(len(prev_values)-1))
        was_bearish = all(prev_values[i] < prev_values[i+1] for i in range(len(prev_values)-1))
        
        if bullish_alignment and not was_bullish and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=current_values[-1],
                take_profit=price * 1.06,
                confidence=0.73,
                paper_size=self.calculate_paper_size(price),
                reason="EMA ribbon fully aligned bullish",
            )
        
        if (bearish_alignment or not bullish_alignment) and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.7,
                paper_size=0,
                reason="EMA ribbon alignment broken - exit",
            )
        
        return None


class VolumePriceConfirmationStrategy(BaseStrategy):
    """
    Volume-Price Confirmation Strategy.
    Uses OBV divergence and volume spikes for confirmation.
    """
    
    @property
    def name(self) -> str:
        return "Volume_Price_Confirmation"
    
    @property
    def description(self) -> str:
        return "OBV trend + volume spike confirmation for entries"
    
    def generate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        obv = calculate_obv(candles)
        
        if len(obv) < 20:
            return None
        
        current_candle = candles[-1]
        price = current_candle.close
        
        obv_sma = sum(obv[-20:]) / 20
        obv_rising = obv[-1] > obv_sma and obv[-1] > obv[-2] > obv[-3]
        
        volumes = [c.volume for c in candles[-20:]]
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
        volume_spike = current_candle.volume > avg_volume * 1.5
        
        price_rising = current_candle.close > candles[-2].close > candles[-3].close
        
        if obv_rising and volume_spike and price_rising and not self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.LONG,
                entry_price=price,
                stop_loss=price * 0.97,
                take_profit=price * 1.055,
                confidence=0.68,
                paper_size=self.calculate_paper_size(price),
                reason="Volume spike with OBV confirmation and rising price",
            )
        
        obv_falling = obv[-1] < obv_sma and obv[-1] < obv[-2]
        
        if obv_falling and self.position:
            return Signal(
                timestamp=current_candle.timestamp,
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                strategy_name=self.name,
                signal_type=SignalType.CLOSE_LONG,
                entry_price=price,
                stop_loss=None,
                take_profit=None,
                confidence=0.65,
                paper_size=0,
                reason="OBV declining below average - exit",
            )
        
        return None


STRATEGY_REGISTRY: Dict[str, type] = {
    "MA_Crossover": MACrossoverStrategy,
    "RSI_Mean_Reversion": RSIMeanReversionStrategy,
    "Bollinger_Breakout": BollingerBreakoutStrategy,
    "MACD_Momentum": MACDMomentumStrategy,
    "Supertrend": SupertrendStrategy,
    "ADX_Trend_Filter": ADXTrendFilterStrategy,
    "Volatility_Regime_Switch": VolatilityRegimeSwitchStrategy,
    "Donchian_Breakout": DonchianBreakoutStrategy,
    "Keltner_Channel": KeltnerChannelStrategy,
    "Stochastic_Oscillator": StochasticOscillatorStrategy,
    "EMA_Ribbon": EMARibbonStrategy,
    "Volume_Price_Confirmation": VolumePriceConfirmationStrategy,
}


def create_all_strategies(config: StrategyConfig = None) -> List[BaseStrategy]:
    """Create instances of all 12 strategies."""
    return [cls(config) for cls in STRATEGY_REGISTRY.values()]