export type SignalType = 'LONG' | 'SHORT' | 'FLAT' | 'CLOSE_LONG' | 'CLOSE_SHORT';

export type Timeframe = 
  | 'ONE_MINUTE' 
  | 'FIVE_MINUTE' 
  | 'FIFTEEN_MINUTE' 
  | 'THIRTY_MINUTE' 
  | 'ONE_HOUR' 
  | 'TWO_HOUR' 
  | 'SIX_HOUR' 
  | 'ONE_DAY';

export type RankingMetric = 
  | 'total_return' 
  | 'sharpe_ratio' 
  | 'win_rate' 
  | 'confidence' 
  | 'recent_performance';

export interface Signal {
  timestamp: string;
  symbol: string;
  timeframe: Timeframe;
  strategy_name: string;
  signal_type: SignalType;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  confidence: number;
  paper_size: number;
  reason: string;
}

export interface Position {
  symbol: string;
  strategy_name: string;
  side: SignalType;
  entry_price: number;
  entry_time: string;
  size: number;
  stop_loss: number | null;
  take_profit: number | null;
  current_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  timeframe: string;
}

export interface Strategy {
  name: string;
  description: string;
}

export interface BullpenStrategy {
  strategy_name: string;
  description: string;
  symbol: string;
  timeframe: string;
  position_state: string;
  latest_signal: Signal | null;
  hypothetical_pnl: number;
  return_pct: number;
  sharpe_ratio: number;
  win_rate: number;
  num_trades: number;
  confidence: number;
  rank: number;
}

export interface ConsensusSignal {
  symbol: string;
  timeframe: string;
  timestamp: string;
  long_count: number;
  short_count: number;
  flat_count: number;
  consensus: SignalType;
  consensus_strength: number;
}

export interface BullpenSummary {
  total_strategies: number;
  active_positions: number;
  avg_return_pct: number;
  total_long: number;
  total_short: number;
  total_flat: number;
  best_performer: {
    name: string;
    symbol: string;
    return_pct: number;
  } | null;
  worst_performer: {
    name: string;
    symbol: string;
    return_pct: number;
  } | null;
}

export interface BullpenView {
  timestamp: string;
  ranking_metric: RankingMetric;
  filter: {
    symbols: string[] | null;
    timeframes: string[] | null;
  };
  summary: BullpenSummary;
  consensus_signals: ConsensusSignal[];
  strategies: BullpenStrategy[];
  total_strategies: number;
}

export interface PerformanceMetrics {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  net_pnl: number;
  total_return_pct: number;
  cagr: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  avg_trade_pnl: number;
  num_trades: number;
  profit_factor: number;
  equity_curve: { timestamp: string; equity: number }[];
}

export interface BacktestResult {
  config: {
    symbols: string[];
    timeframes: string[];
    start_date: string | null;
    end_date: string | null;
    initial_capital: number;
    position_size_pct: number;
    commission_pct: number;
  };
  strategy_name: string;
  symbol: string;
  timeframe: string;
  metrics: PerformanceMetrics;
  trades: any[];
  signals: Signal[];
  equity_curve: { timestamp: string; equity: number }[];
}

export interface SimulatorStatus {
  mode: string;
  running: boolean;
  started_at: string | null;
  candles_processed: number;
  signals_generated: number;
  last_error: string | null;
  config: {
    symbols: string[];
    timeframes: string[];
    initial_capital: number;
    position_size_pct: number;
    commission_pct: number;
    poll_interval_seconds: number;
  };
  safety_verified: boolean;
  strategies_count: number;
  strategy_names: string[];
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  symbol: string;
  timeframe: string;
}