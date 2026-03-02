import { Card, CardContent } from '@/components/ui/card';
import type { BullpenSummary } from '@/lib/types';

interface SummaryCardsProps {
  summary: BullpenSummary;
  signalsCount: number;
}

export function SummaryCards({ summary, signalsCount }: SummaryCardsProps) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" data-design-id="summary-cards-grid">
      <Card className="border-slate-800 bg-slate-900/50" data-design-id="summary-card-strategies">
        <CardContent className="p-4" data-design-id="summary-card-strategies-content">
          <div className="flex items-center justify-between" data-design-id="summary-card-strategies-header">
            <span className="text-sm text-slate-400" data-design-id="summary-card-strategies-label">Active Strategies</span>
            <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="summary-card-strategies-icon">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <p className="mt-2 text-3xl font-bold text-white" data-design-id="summary-card-strategies-value">{summary.total_strategies}</p>
          <p className="text-xs text-slate-500" data-design-id="summary-card-strategies-subtitle">12 SOTA algorithms</p>
        </CardContent>
      </Card>

      <Card className="border-slate-800 bg-slate-900/50" data-design-id="summary-card-positions">
        <CardContent className="p-4" data-design-id="summary-card-positions-content">
          <div className="flex items-center justify-between" data-design-id="summary-card-positions-header">
            <span className="text-sm text-slate-400" data-design-id="summary-card-positions-label">Open Positions</span>
            <svg className="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="summary-card-positions-icon">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <p className="mt-2 text-3xl font-bold text-white" data-design-id="summary-card-positions-value">{summary.active_positions}</p>
          <div className="mt-1 flex gap-2 text-xs" data-design-id="summary-card-positions-breakdown">
            <span className="text-emerald-400" data-design-id="summary-card-positions-long">↑ {summary.total_long} Long</span>
            <span className="text-red-400" data-design-id="summary-card-positions-short">↓ {summary.total_short} Short</span>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-800 bg-slate-900/50" data-design-id="summary-card-return">
        <CardContent className="p-4" data-design-id="summary-card-return-content">
          <div className="flex items-center justify-between" data-design-id="summary-card-return-header">
            <span className="text-sm text-slate-400" data-design-id="summary-card-return-label">Avg Return</span>
            <svg className="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="summary-card-return-icon">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className={`mt-2 text-3xl font-bold ${summary.avg_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`} data-design-id="summary-card-return-value">
            {summary.avg_return_pct >= 0 ? '+' : ''}{summary.avg_return_pct.toFixed(2)}%
          </p>
          <p className="text-xs text-slate-500" data-design-id="summary-card-return-subtitle">Across all strategies</p>
        </CardContent>
      </Card>

      <Card className="border-slate-800 bg-slate-900/50" data-design-id="summary-card-signals">
        <CardContent className="p-4" data-design-id="summary-card-signals-content">
          <div className="flex items-center justify-between" data-design-id="summary-card-signals-header">
            <span className="text-sm text-slate-400" data-design-id="summary-card-signals-label">Total Signals</span>
            <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="summary-card-signals-icon">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <p className="mt-2 text-3xl font-bold text-white" data-design-id="summary-card-signals-value">{signalsCount}</p>
          <p className="text-xs text-slate-500" data-design-id="summary-card-signals-subtitle">Paper trade signals</p>
        </CardContent>
      </Card>
    </div>
  );
}