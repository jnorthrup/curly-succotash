import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { api } from '@/lib/api';
import type { BacktestResult } from '@/lib/types';

const SYMBOLS = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'AVAX-USD'];
const TIMEFRAMES = ['ONE_HOUR', 'FOUR_HOUR', 'ONE_DAY'];
const DAYS_OPTIONS = [7, 14, 30, 60, 90];

export function BacktestPanel() {
  const [symbol, setSymbol] = useState('BTC-USD');
  const [timeframe, setTimeframe] = useState('ONE_HOUR');
  const [daysBack, setDaysBack] = useState(30);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.runBacktest({
        symbols: [symbol],
        timeframes: [timeframe],
        days_back: daysBack,
        initial_capital: 10000,
      });
      
      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run backtest');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-slate-800 bg-slate-900/50" data-design-id="backtest-panel-card">
      <CardHeader className="pb-3" data-design-id="backtest-panel-header">
        <CardTitle className="flex items-center gap-2 text-lg text-white" data-design-id="backtest-panel-title">
          <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="backtest-panel-icon">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Historical Backtest
        </CardTitle>
      </CardHeader>
      <CardContent data-design-id="backtest-panel-content">
        <div className="mb-4 flex flex-wrap gap-3" data-design-id="backtest-panel-controls">
          <Select value={symbol} onValueChange={setSymbol}>
            <SelectTrigger className="w-32 border-slate-700 bg-slate-800" data-design-id="backtest-panel-symbol-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800" data-design-id="backtest-panel-symbol-content">
              {SYMBOLS.map((s) => (
                <SelectItem key={s} value={s} className="text-white hover:bg-slate-700">
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={timeframe} onValueChange={setTimeframe}>
            <SelectTrigger className="w-32 border-slate-700 bg-slate-800" data-design-id="backtest-panel-timeframe-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800" data-design-id="backtest-panel-timeframe-content">
              {TIMEFRAMES.map((tf) => (
                <SelectItem key={tf} value={tf} className="text-white hover:bg-slate-700">
                  {tf.replace(/_/g, ' ')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={String(daysBack)} onValueChange={(v) => setDaysBack(Number(v))}>
            <SelectTrigger className="w-28 border-slate-700 bg-slate-800" data-design-id="backtest-panel-days-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800" data-design-id="backtest-panel-days-content">
              {DAYS_OPTIONS.map((d) => (
                <SelectItem key={d} value={String(d)} className="text-white hover:bg-slate-700">
                  {d} days
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button 
            onClick={runBacktest} 
            disabled={loading}
            className="bg-cyan-600 hover:bg-cyan-700"
            data-design-id="backtest-panel-run-button"
          >
            {loading ? (
              <>
                <svg className="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Running...
              </>
            ) : (
              'Run Backtest'
            )}
          </Button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400" data-design-id="backtest-panel-error">
            {error}
          </div>
        )}

        {results.length > 0 && (
          <ScrollArea className="h-[300px]" data-design-id="backtest-panel-results-scroll">
            <div className="space-y-2" data-design-id="backtest-panel-results">
              {results.map((result, index) => (
                <div 
                  key={`${result.strategy_name}-${index}`}
                  className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3"
                  data-design-id={`backtest-result-${index}`}
                >
                  <div className="flex items-center justify-between" data-design-id={`backtest-result-${index}-header`}>
                    <div className="flex items-center gap-2" data-design-id={`backtest-result-${index}-info`}>
                      <span className="font-mono text-xs text-slate-500">#{index + 1}</span>
                      <span className="font-medium text-white">{result.strategy_name.replace(/_/g, ' ')}</span>
                    </div>
                    <Badge 
                      className={
                        result.metrics.total_return_pct >= 0
                          ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                          : 'bg-red-500/20 text-red-400 border-red-500/30'
                      }
                      data-design-id={`backtest-result-${index}-return-badge`}
                    >
                      {result.metrics.total_return_pct >= 0 ? '+' : ''}{result.metrics.total_return_pct.toFixed(2)}%
                    </Badge>
                  </div>
                  
                  <div className="mt-2 grid grid-cols-4 gap-4 text-xs" data-design-id={`backtest-result-${index}-metrics`}>
                    <div data-design-id={`backtest-result-${index}-pnl`}>
                      <span className="text-slate-500">P&L</span>
                      <p className={`font-mono ${result.metrics.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        ${result.metrics.net_pnl.toFixed(2)}
                      </p>
                    </div>
                    <div data-design-id={`backtest-result-${index}-sharpe`}>
                      <span className="text-slate-500">Sharpe</span>
                      <p className="font-mono text-white">{result.metrics.sharpe_ratio.toFixed(2)}</p>
                    </div>
                    <div data-design-id={`backtest-result-${index}-winrate`}>
                      <span className="text-slate-500">Win Rate</span>
                      <p className="font-mono text-white">{result.metrics.win_rate.toFixed(1)}%</p>
                    </div>
                    <div data-design-id={`backtest-result-${index}-trades`}>
                      <span className="text-slate-500">Trades</span>
                      <p className="font-mono text-white">{result.metrics.num_trades}</p>
                    </div>
                  </div>
                  
                  <div className="mt-2 grid grid-cols-2 gap-4 text-xs" data-design-id={`backtest-result-${index}-extra`}>
                    <div data-design-id={`backtest-result-${index}-drawdown`}>
                      <span className="text-slate-500">Max Drawdown</span>
                      <p className="font-mono text-red-400">-{result.metrics.max_drawdown.toFixed(2)}%</p>
                    </div>
                    <div data-design-id={`backtest-result-${index}-pf`}>
                      <span className="text-slate-500">Profit Factor</span>
                      <p className="font-mono text-white">
                        {result.metrics.profit_factor === Infinity ? '∞' : result.metrics.profit_factor.toFixed(2)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {results.length === 0 && !loading && !error && (
          <div className="flex h-32 items-center justify-center text-slate-500" data-design-id="backtest-panel-empty">
            Select parameters and run backtest
          </div>
        )}
      </CardContent>
    </Card>
  );
}