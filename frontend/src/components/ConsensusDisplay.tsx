import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ConsensusSignal } from '@/lib/types';

interface ConsensusDisplayProps {
  consensus: ConsensusSignal[];
}

export function ConsensusDisplay({ consensus }: ConsensusDisplayProps) {
  if (consensus.length === 0) {
    return (
      <Card className="border-slate-800 bg-slate-900/50" data-design-id="consensus-empty-card">
        <CardContent className="flex h-32 items-center justify-center text-slate-500" data-design-id="consensus-empty-content">
          Start simulator to see consensus signals
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-slate-800 bg-slate-900/50" data-design-id="consensus-card">
      <CardHeader className="pb-3" data-design-id="consensus-header">
        <CardTitle className="flex items-center gap-2 text-lg text-white" data-design-id="consensus-title">
          <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="consensus-icon">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Consensus Signals
        </CardTitle>
      </CardHeader>
      <CardContent data-design-id="consensus-content">
        <div className="space-y-4" data-design-id="consensus-list">
          {consensus.map((cs, index) => {
            const total = cs.long_count + cs.short_count + cs.flat_count;
            const longPct = (cs.long_count / total) * 100;
            const shortPct = (cs.short_count / total) * 100;
            
            return (
              <div 
                key={`${cs.symbol}-${cs.timeframe}-${index}`} 
                className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4"
                data-design-id={`consensus-item-${index}`}
              >
                <div className="mb-3 flex items-center justify-between" data-design-id={`consensus-item-${index}-header`}>
                  <div className="flex items-center gap-2" data-design-id={`consensus-item-${index}-symbol`}>
                    <span className="font-mono text-lg font-semibold text-white">{cs.symbol}</span>
                    <Badge variant="outline" className="border-slate-600 text-slate-400" data-design-id={`consensus-item-${index}-timeframe`}>
                      {cs.timeframe}
                    </Badge>
                  </div>
                  <Badge 
                    className={
                      cs.consensus === 'LONG' 
                        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' 
                        : cs.consensus === 'SHORT'
                        ? 'bg-red-500/20 text-red-400 border-red-500/30'
                        : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                    }
                    data-design-id={`consensus-item-${index}-badge`}
                  >
                    {cs.consensus} ({(cs.consensus_strength * 100).toFixed(0)}%)
                  </Badge>
                </div>
                
                <div className="space-y-2" data-design-id={`consensus-item-${index}-bars`}>
                  <div className="flex items-center gap-2" data-design-id={`consensus-item-${index}-long-bar`}>
                    <span className="w-12 text-xs text-emerald-400">Long</span>
                    <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-700">
                      <div 
                        className="absolute h-full bg-emerald-500 transition-all duration-300"
                        style={{ width: `${longPct}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-xs text-slate-400">{cs.long_count}</span>
                  </div>
                  
                  <div className="flex items-center gap-2" data-design-id={`consensus-item-${index}-short-bar`}>
                    <span className="w-12 text-xs text-red-400">Short</span>
                    <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-700">
                      <div 
                        className="absolute h-full bg-red-500 transition-all duration-300"
                        style={{ width: `${shortPct}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-xs text-slate-400">{cs.short_count}</span>
                  </div>
                  
                  <div className="flex items-center gap-2" data-design-id={`consensus-item-${index}-flat-bar`}>
                    <span className="w-12 text-xs text-slate-400">Flat</span>
                    <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-700">
                      <div 
                        className="absolute h-full bg-slate-500 transition-all duration-300"
                        style={{ width: `${100 - longPct - shortPct}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-xs text-slate-400">{cs.flat_count}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}