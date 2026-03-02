import type { 
  BullpenView, 
  Signal, 
  Position, 
  Strategy, 
  SimulatorStatus,
  BacktestResult,
  Candle,
  RankingMetric 
} from './types';

const API_BASE = '';

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  
  return response.json();
}

export const api = {
  getStatus: () => 
    fetchApi<SimulatorStatus>('/api/status'),
  
  getStrategies: () => 
    fetchApi<{ count: number; strategies: Strategy[] }>('/api/strategies'),
  
  startSimulator: () => 
    fetchApi<{ status: string; message: string }>('/api/simulator/start', { method: 'POST' }),
  
  stopSimulator: () => 
    fetchApi<{ status: string; message: string }>('/api/simulator/stop', { method: 'POST' }),
  
  getBullpen: (ranking: RankingMetric = 'total_return', symbols?: string, timeframes?: string) => {
    const params = new URLSearchParams({ ranking });
    if (symbols) params.set('symbols', symbols);
    if (timeframes) params.set('timeframes', timeframes);
    return fetchApi<BullpenView>(`/api/bullpen?${params}`);
  },
  
  getSignals: (limit: number = 50) => 
    fetchApi<{ count: number; signals: Signal[]; timestamp: string }>(`/api/signals?limit=${limit}`),
  
  getPositions: () => 
    fetchApi<{ count: number; positions: Position[]; timestamp: string }>('/api/positions'),
  
  runBacktest: (config: {
    symbols: string[];
    timeframes: string[];
    days_back: number;
    initial_capital: number;
  }) => 
    fetchApi<{ 
      status: string; 
      config: any; 
      results_count: number; 
      results: BacktestResult[];
      timestamp: string;
    }>('/api/backtest', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  
  getBacktestResults: () => 
    fetchApi<{ count: number; results: BacktestResult[]; timestamp: string }>('/api/backtest/results'),
  
  getCandles: (symbol: string, timeframe: string = 'ONE_HOUR', limit: number = 100) =>
    fetchApi<{ symbol: string; timeframe: string; count: number; candles: Candle[] }>(
      `/api/candles/${symbol}?timeframe=${timeframe}&limit=${limit}`
    ),
  
  getPrice: (symbol: string) =>
    fetchApi<{ symbol: string; price_usd: number; timestamp: string }>(`/api/price/${symbol}`),
  
  getConsensus: (symbol: string, timeframe?: string) => {
    const params = timeframe ? `?timeframe=${timeframe}` : '';
    return fetchApi<{ symbol: string; consensus: any[]; timestamp: string }>(`/api/consensus/${symbol}${params}`);
  },
  
  getTopStrategies: (n: number = 5, metric: RankingMetric = 'total_return') =>
    fetchApi<{ count: number; metric: string; strategies: any[] }>(`/api/top-strategies?n=${n}&metric=${metric}`),
  
  verifySafety: () =>
    fetchApi<{ safety_verified: boolean; checks: any; message: string }>('/api/safety/verify'),
};

export function createWebSocket(channel: 'signals' | 'bullpen'): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${channel}`);
  return ws;
}