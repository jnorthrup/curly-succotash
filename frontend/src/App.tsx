import { useEffect, useState, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Header } from '@/components/Header';
import { SummaryCards } from '@/components/SummaryCards';
import { ConsensusDisplay } from '@/components/ConsensusDisplay';
import { StrategyTable } from '@/components/StrategyTable';
import { SignalFeed } from '@/components/SignalFeed';
import { BacktestPanel } from '@/components/BacktestPanel';
import { api } from '@/lib/api';
import type { BullpenView, Signal, SimulatorStatus } from '@/lib/types';

function App() {
  const [status, setStatus] = useState<SimulatorStatus | null>(null);
  const [bullpen, setBullpen] = useState<BullpenView | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, bullpenRes, signalsRes] = await Promise.all([
        api.getStatus(),
        api.getBullpen('total_return'),
        api.getSignals(50),
      ]);
      
      setStatus(statusRes);
      setBullpen(bullpenRes);
      setSignals(signalsRes.signals);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleStart = async () => {
    setLoading(true);
    try {
      await api.startSimulator();
      await new Promise(r => setTimeout(r, 2000));
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await api.stopSimulator();
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop');
    } finally {
      setLoading(false);
    }
  };

  const defaultSummary = {
    total_strategies: 12,
    active_positions: 0,
    avg_return_pct: 0,
    total_long: 0,
    total_short: 0,
    total_flat: 12,
    best_performer: null,
    worst_performer: null,
  };

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-slate-950 text-white" data-design-id="app-container">
        <div 
          className="fixed inset-0 -z-10 bg-gradient-to-br from-slate-950 via-slate-900 to-emerald-950/20"
          data-design-id="app-background"
        />
        <div 
          className="fixed inset-0 -z-10 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxwYXRoIGQ9Ik0zNiAxOGMzLjMxNCAwIDYgMi42ODYgNiA2cy0yLjY4NiA2LTYgNi02LTIuNjg2LTYtNiAyLjY4Ni02IDYtNiIgc3Ryb2tlPSJyZ2JhKDE2LDE4NSwxMjksMC4wNSkiIHN0cm9rZS13aWR0aD0iMiIvPjwvZz48L3N2Zz4=')] opacity-30"
          data-design-id="app-pattern"
        />

        <Header 
          isRunning={status?.running ?? false}
          onStart={handleStart}
          onStop={handleStop}
          loading={loading}
        />

        <main className="mx-auto max-w-7xl px-4 py-6" data-design-id="main-content">
          {error && (
            <div 
              className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400"
              data-design-id="error-banner"
            >
              <p className="font-medium" data-design-id="error-title">Error</p>
              <p className="text-sm" data-design-id="error-message">{error}</p>
            </div>
          )}

          <div className="mb-6" data-design-id="summary-section">
            <SummaryCards 
              summary={bullpen?.summary ?? defaultSummary}
              signalsCount={signals.length}
            />
          </div>

          <Tabs defaultValue="bullpen" className="space-y-6" data-design-id="main-tabs">
            <TabsList className="bg-slate-900/50 border border-slate-800" data-design-id="tabs-list">
              <TabsTrigger 
                value="bullpen" 
                className="data-[state=active]:bg-emerald-600/20 data-[state=active]:text-emerald-400"
                data-design-id="tab-bullpen"
              >
                Bullpen
              </TabsTrigger>
              <TabsTrigger 
                value="signals" 
                className="data-[state=active]:bg-amber-600/20 data-[state=active]:text-amber-400"
                data-design-id="tab-signals"
              >
                Signals
              </TabsTrigger>
              <TabsTrigger 
                value="backtest" 
                className="data-[state=active]:bg-cyan-600/20 data-[state=active]:text-cyan-400"
                data-design-id="tab-backtest"
              >
                Backtest
              </TabsTrigger>
            </TabsList>

            <TabsContent value="bullpen" className="space-y-6" data-design-id="bullpen-tab-content">
              <div className="grid gap-6 lg:grid-cols-3" data-design-id="bullpen-grid">
                <div className="lg:col-span-2" data-design-id="strategy-table-wrapper">
                  <StrategyTable strategies={bullpen?.strategies ?? []} />
                </div>
                <div data-design-id="consensus-wrapper">
                  <ConsensusDisplay consensus={bullpen?.consensus_signals ?? []} />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="signals" data-design-id="signals-tab-content">
              <SignalFeed signals={signals} />
            </TabsContent>

            <TabsContent value="backtest" data-design-id="backtest-tab-content">
              <BacktestPanel />
            </TabsContent>
          </Tabs>

          <footer className="mt-12 border-t border-slate-800 pt-6 text-center text-sm text-slate-500" data-design-id="footer">
            <p data-design-id="footer-safety">
              ⚠️ This is a paper trading simulator. No real trades are placed.
            </p>
            <p className="mt-1" data-design-id="footer-data">
              Market data provided by Coinbase Advanced API (read-only)
            </p>
          </footer>
        </main>
      </div>
    </TooltipProvider>
  );
}

export default App
