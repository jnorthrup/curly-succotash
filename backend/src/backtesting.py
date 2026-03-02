"""
Backtesting Engine
Run historical backtests with full performance metrics.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict

from .models import Candle, Signal, Timeframe, PerformanceMetrics
from .strategies import BaseStrategy, create_all_strategies, StrategyConfig, STRATEGY_REGISTRY
from .paper_trading import PaperTradingEngine, PaperTradingConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    symbols: List[str] = field(default_factory=lambda: ["BTC-USD"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    commission_pct: float = 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "timeframes": [tf.value for tf in self.timeframes],
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "initial_capital": self.initial_capital,
            "position_size_pct": self.position_size_pct,
            "commission_pct": self.commission_pct,
        }


@dataclass
class BacktestResult:
    config: BacktestConfig
    strategy_name: str
    symbol: str
    timeframe: Timeframe
    metrics: PerformanceMetrics
    trades: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "metrics": self.metrics.to_dict(),
            "trades": self.trades,
            "signals": self.signals,
            "equity_curve": self.equity_curve,
        }


class MetricsCalculator:
    """Calculate performance metrics from trade history."""
    
    @staticmethod
    def calculate_returns(equity_curve: List[Dict[str, Any]]) -> List[float]:
        """Calculate period returns from equity curve."""
        if len(equity_curve) < 2:
            return []
        
        returns = []
        for i in range(1, len(equity_curve)):
            prev_equity = equity_curve[i-1]["equity"]
            curr_equity = equity_curve[i]["equity"]
            if prev_equity > 0:
                returns.append((curr_equity - prev_equity) / prev_equity)
            else:
                returns.append(0)
        
        return returns
    
    @staticmethod
    def calculate_sharpe_ratio(
        returns: List[float], 
        risk_free_rate: float = 0.0,
        annualization_factor: float = 252
    ) -> float:
        """Calculate annualized Sharpe ratio."""
        if not returns or len(returns) < 2:
            return 0.0
        
        mean_return = sum(returns) / len(returns)
        excess_returns = [r - risk_free_rate / annualization_factor for r in returns]
        
        if len(excess_returns) < 2:
            return 0.0
        
        mean_excess = sum(excess_returns) / len(excess_returns)
        variance = sum((r - mean_excess) ** 2 for r in excess_returns) / (len(excess_returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        
        if std_dev == 0:
            return 0.0
        
        return (mean_excess * annualization_factor) / (std_dev * math.sqrt(annualization_factor))
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: List[Dict[str, Any]]) -> float:
        """Calculate maximum drawdown percentage."""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]["equity"]
        max_dd = 0.0
        
        for point in equity_curve:
            equity = point["equity"]
            peak = max(peak, equity)
            drawdown = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, drawdown)
        
        return max_dd * 100
    
    @staticmethod
    def calculate_cagr(
        initial_capital: float,
        final_capital: float,
        days: int
    ) -> float:
        """Calculate Compound Annual Growth Rate."""
        if initial_capital <= 0 or final_capital <= 0 or days <= 0:
            return 0.0
        
        years = days / 365.25
        if years <= 0:
            return 0.0
        
        return ((final_capital / initial_capital) ** (1 / years) - 1) * 100
    
    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> float:
        """Calculate win rate percentage."""
        if not trades:
            return 0.0
        
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        return (wins / len(trades)) * 100
    
    @staticmethod
    def calculate_profit_factor(trades: List[Dict]) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        if not trades:
            return 0.0
        
        gross_profit = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    @staticmethod
    def calculate_metrics(
        strategy_name: str,
        symbol: str,
        timeframe: Timeframe,
        trades: List[Dict],
        equity_curve: List[Dict[str, Any]],
        initial_capital: float,
        start_date: datetime,
        end_date: datetime
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        
        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        net_pnl = final_equity - initial_capital
        total_return_pct = (net_pnl / initial_capital) * 100 if initial_capital > 0 else 0
        
        days = (end_date - start_date).days if end_date and start_date else 1
        cagr = MetricsCalculator.calculate_cagr(initial_capital, final_equity, max(days, 1))
        
        returns = MetricsCalculator.calculate_returns(equity_curve)
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns)
        
        max_dd = MetricsCalculator.calculate_max_drawdown(equity_curve)
        win_rate = MetricsCalculator.calculate_win_rate(trades)
        profit_factor = MetricsCalculator.calculate_profit_factor(trades)
        
        avg_trade_pnl = sum(t.get("pnl", 0) for t in trades) / len(trades) if trades else 0
        
        return PerformanceMetrics(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            net_pnl=net_pnl,
            total_return_pct=total_return_pct,
            cagr=cagr,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            avg_trade_pnl=avg_trade_pnl,
            num_trades=len(trades),
            profit_factor=profit_factor,
            equity_curve=[{
                "timestamp": e["timestamp"],
                "equity": e["equity"]
            } for e in equity_curve[::max(1, len(equity_curve)//100)]],
        )


class BacktestEngine:
    """
    Backtesting engine for historical strategy evaluation.
    Ensures reproducibility with same historical data.
    """
    
    def __init__(self):
        self.results: Dict[str, BacktestResult] = {}
        self._metrics_calculator = MetricsCalculator()
    
    def run_backtest(
        self,
        candles: List[Candle],
        config: BacktestConfig
    ) -> List[BacktestResult]:
        """
        Run backtest for all strategies on provided candles.
        
        Args:
            candles: Historical candle data (sorted oldest to newest)
            config: Backtest configuration
        
        Returns:
            List of backtest results for each strategy
        """
        if not candles:
            logger.warning("[BACKTEST] No candles provided")
            return []
        
        candles = sorted(candles, key=lambda c: c.timestamp)
        
        start_date = candles[0].timestamp
        end_date = candles[-1].timestamp
        symbol = candles[0].symbol
        timeframe = candles[0].timeframe
        
        logger.info(
            f"[BACKTEST] Starting backtest: {symbol} {timeframe.value} | "
            f"{start_date} to {end_date} | {len(candles)} candles"
        )
        
        results = []
        strategy_config = StrategyConfig(
            initial_capital=config.initial_capital,
            position_size_pct=config.position_size_pct,
        )
        
        strategies = create_all_strategies(strategy_config)
        
        for strategy in strategies:
            result = self._run_single_strategy_backtest(
                strategy=strategy,
                candles=candles,
                config=config,
                start_date=start_date,
                end_date=end_date,
            )
            results.append(result)
            
            self.results[f"{symbol}_{timeframe.value}_{strategy.name}"] = result
        
        results.sort(key=lambda r: r.metrics.total_return_pct, reverse=True)
        
        logger.info(f"[BACKTEST] Completed {len(results)} strategy backtests")
        self._log_summary(results)
        
        return results
    
    def _run_single_strategy_backtest(
        self,
        strategy: BaseStrategy,
        candles: List[Candle],
        config: BacktestConfig,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestResult:
        """Run backtest for a single strategy."""
        
        strategy.reset()
        
        equity_curve = []
        signals = []
        
        for candle in candles:
            signal = strategy.process_candle(candle)
            
            if signal:
                signals.append(signal.to_dict())
            
            equity_curve.append({
                "timestamp": candle.timestamp.isoformat(),
                "equity": strategy.equity,
            })
        
        metrics = self._metrics_calculator.calculate_metrics(
            strategy_name=strategy.name,
            symbol=candles[0].symbol,
            timeframe=candles[0].timeframe,
            trades=strategy.trades,
            equity_curve=equity_curve,
            initial_capital=config.initial_capital,
            start_date=start_date,
            end_date=end_date,
        )
        
        return BacktestResult(
            config=config,
            strategy_name=strategy.name,
            symbol=candles[0].symbol,
            timeframe=candles[0].timeframe,
            metrics=metrics,
            trades=strategy.trades,
            signals=signals,
            equity_curve=equity_curve,
        )
    
    def _log_summary(self, results: List[BacktestResult]):
        """Log backtest summary."""
        logger.info("=" * 60)
        logger.info("BACKTEST RESULTS SUMMARY")
        logger.info("=" * 60)
        
        for i, result in enumerate(results[:5], 1):
            m = result.metrics
            logger.info(
                f"{i}. {m.strategy_name}: "
                f"Return={m.total_return_pct:.2f}% | "
                f"Sharpe={m.sharpe_ratio:.2f} | "
                f"MaxDD={m.max_drawdown:.2f}% | "
                f"WinRate={m.win_rate:.1f}% | "
                f"Trades={m.num_trades}"
            )
        
        logger.info("=" * 60)
    
    def get_result(self, key: str) -> Optional[BacktestResult]:
        """Get a specific backtest result."""
        return self.results.get(key)
    
    def get_all_results(self) -> List[BacktestResult]:
        """Get all backtest results."""
        return list(self.results.values())
    
    def compare_strategies(
        self,
        results: List[BacktestResult],
        metric: str = "total_return_pct"
    ) -> List[Dict[str, Any]]:
        """Compare strategies by a specific metric."""
        comparison = []
        
        for result in results:
            metrics_dict = result.metrics.to_dict()
            comparison.append({
                "strategy_name": result.strategy_name,
                "symbol": result.symbol,
                "timeframe": result.timeframe.value,
                "metric_name": metric,
                "metric_value": metrics_dict.get(metric, 0),
                "total_return_pct": metrics_dict["total_return_pct"],
                "sharpe_ratio": metrics_dict["sharpe_ratio"],
                "max_drawdown": metrics_dict["max_drawdown"],
                "win_rate": metrics_dict["win_rate"],
                "num_trades": metrics_dict["num_trades"],
            })
        
        comparison.sort(key=lambda x: x["metric_value"], reverse=True)
        
        for i, entry in enumerate(comparison, 1):
            entry["rank"] = i
        
        return comparison
    
    def validate_reproducibility(
        self,
        candles: List[Candle],
        config: BacktestConfig,
        runs: int = 3
    ) -> Dict[str, bool]:
        """
        Validate that backtests are reproducible.
        Runs multiple times and compares results.
        """
        results_per_run = []
        
        for run in range(runs):
            results = self.run_backtest(candles, config)
            results_per_run.append({
                r.strategy_name: r.metrics.net_pnl for r in results
            })
        
        reproducible = True
        mismatches = []
        
        for strategy_name in results_per_run[0].keys():
            values = [r.get(strategy_name, 0) for r in results_per_run]
            if not all(abs(v - values[0]) < 0.01 for v in values):
                reproducible = False
                mismatches.append(strategy_name)
        
        return {
            "reproducible": reproducible,
            "runs": runs,
            "mismatches": mismatches,
        }