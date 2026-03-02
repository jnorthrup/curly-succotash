import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { BullpenStrategy } from '@/lib/types';

interface StrategyTableProps {
  strategies: BullpenStrategy[];
}

export function StrategyTable({ strategies }: StrategyTableProps) {
  if (strategies.length === 0) {
    return (
      <Card className="border-slate-800 bg-slate-900/50" data-design-id="strategy-table-empty-card">
        <CardContent className="flex h-64 items-center justify-center text-slate-500" data-design-id="strategy-table-empty-content">
          Start simulator to see strategy rankings
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-slate-800 bg-slate-900/50" data-design-id="strategy-table-card">
      <CardHeader className="pb-3" data-design-id="strategy-table-header">
        <CardTitle className="flex items-center gap-2 text-lg text-white" data-design-id="strategy-table-title">
          <svg className="h-5 w-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="strategy-table-icon">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          Strategy Bullpen Rankings
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0" data-design-id="strategy-table-content">
        <ScrollArea className="h-[400px]" data-design-id="strategy-table-scroll">
          <Table data-design-id="strategy-table">
            <TableHeader data-design-id="strategy-table-thead">
              <TableRow className="border-slate-700 hover:bg-transparent" data-design-id="strategy-table-thead-row">
                <TableHead className="w-12 text-slate-400" data-design-id="strategy-table-th-rank">#</TableHead>
                <TableHead className="text-slate-400" data-design-id="strategy-table-th-strategy">Strategy</TableHead>
                <TableHead className="text-slate-400" data-design-id="strategy-table-th-symbol">Symbol</TableHead>
                <TableHead className="text-slate-400" data-design-id="strategy-table-th-position">Position</TableHead>
                <TableHead className="text-right text-slate-400" data-design-id="strategy-table-th-return">Return</TableHead>
                <TableHead className="text-right text-slate-400" data-design-id="strategy-table-th-pnl">P&L</TableHead>
                <TableHead className="text-right text-slate-400" data-design-id="strategy-table-th-trades">Trades</TableHead>
                <TableHead className="text-right text-slate-400" data-design-id="strategy-table-th-confidence">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-design-id="strategy-table-tbody">
              {strategies.map((strategy, index) => (
                <TableRow 
                  key={`${strategy.strategy_name}-${strategy.symbol}-${index}`}
                  className="border-slate-700/50 hover:bg-slate-800/50"
                  data-design-id={`strategy-table-row-${index}`}
                >
                  <TableCell className="font-mono text-slate-500" data-design-id={`strategy-table-cell-${index}-rank`}>
                    {strategy.rank}
                  </TableCell>
                  <TableCell data-design-id={`strategy-table-cell-${index}-name`}>
                    <div data-design-id={`strategy-table-cell-${index}-name-content`}>
                      <p className="font-medium text-white">{strategy.strategy_name.replace(/_/g, ' ')}</p>
                      <p className="text-xs text-slate-500 line-clamp-1">{strategy.description}</p>
                    </div>
                  </TableCell>
                  <TableCell data-design-id={`strategy-table-cell-${index}-symbol`}>
                    <Badge variant="outline" className="border-slate-600 font-mono text-slate-300">
                      {strategy.symbol}
                    </Badge>
                  </TableCell>
                  <TableCell data-design-id={`strategy-table-cell-${index}-position`}>
                    <Badge 
                      className={
                        strategy.position_state.includes('LONG')
                          ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                          : strategy.position_state.includes('SHORT')
                          ? 'bg-red-500/20 text-red-400 border-red-500/30'
                          : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                      }
                    >
                      {strategy.position_state}
                    </Badge>
                  </TableCell>
                  <TableCell 
                    className={`text-right font-mono ${
                      strategy.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}
                    data-design-id={`strategy-table-cell-${index}-return`}
                  >
                    {strategy.return_pct >= 0 ? '+' : ''}{strategy.return_pct.toFixed(2)}%
                  </TableCell>
                  <TableCell 
                    className={`text-right font-mono ${
                      strategy.hypothetical_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}
                    data-design-id={`strategy-table-cell-${index}-pnl`}
                  >
                    ${strategy.hypothetical_pnl.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-slate-300" data-design-id={`strategy-table-cell-${index}-trades`}>
                    {strategy.num_trades}
                  </TableCell>
                  <TableCell className="text-right" data-design-id={`strategy-table-cell-${index}-confidence`}>
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-700">
                        <div 
                          className="h-full bg-gradient-to-r from-violet-500 to-purple-500 transition-all"
                          style={{ width: `${strategy.confidence * 100}%` }}
                        />
                      </div>
                      <span className="w-10 text-right font-mono text-xs text-slate-400">
                        {(strategy.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}