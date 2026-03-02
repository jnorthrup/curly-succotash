import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Signal } from '@/lib/types';

interface SignalFeedProps {
  signals: Signal[];
}

export function SignalFeed({ signals }: SignalFeedProps) {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <Card className="border-slate-800 bg-slate-900/50" data-design-id="signal-feed-card">
      <CardHeader className="pb-3" data-design-id="signal-feed-header">
        <CardTitle className="flex items-center gap-2 text-lg text-white" data-design-id="signal-feed-title">
          <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" data-design-id="signal-feed-icon">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Live Signal Feed
          <Badge variant="outline" className="ml-auto border-amber-500/30 text-amber-400" data-design-id="signal-feed-count-badge">
            {signals.length} signals
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0" data-design-id="signal-feed-content">
        <ScrollArea className="h-[300px]" data-design-id="signal-feed-scroll">
          {signals.length === 0 ? (
            <div className="flex h-full items-center justify-center p-6 text-slate-500" data-design-id="signal-feed-empty">
              Waiting for signals...
            </div>
          ) : (
            <div className="space-y-2 p-4" data-design-id="signal-feed-list">
              {signals.slice().reverse().map((signal, index) => (
                <div 
                  key={`${signal.timestamp}-${signal.strategy_name}-${index}`}
                  className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 transition-all hover:bg-slate-800/50"
                  data-design-id={`signal-item-${index}`}
                >
                  <div className="flex items-start justify-between gap-2" data-design-id={`signal-item-${index}-header`}>
                    <div className="flex items-center gap-2" data-design-id={`signal-item-${index}-info`}>
                      <Badge 
                        className={
                          signal.signal_type === 'LONG'
                            ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                            : signal.signal_type === 'SHORT'
                            ? 'bg-red-500/20 text-red-400 border-red-500/30'
                            : signal.signal_type.includes('CLOSE')
                            ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                            : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                        }
                        data-design-id={`signal-item-${index}-type-badge`}
                      >
                        {signal.signal_type === 'LONG' ? '↑' : signal.signal_type === 'SHORT' ? '↓' : '○'} {signal.signal_type}
                      </Badge>
                      <span className="font-mono text-sm font-medium text-white" data-design-id={`signal-item-${index}-symbol`}>
                        {signal.symbol}
                      </span>
                    </div>
                    <span className="text-xs text-slate-500" data-design-id={`signal-item-${index}-time`}>
                      {formatTime(signal.timestamp)}
                    </span>
                  </div>
                  
                  <div className="mt-2 flex items-center gap-4 text-xs" data-design-id={`signal-item-${index}-details`}>
                    <span className="text-slate-400" data-design-id={`signal-item-${index}-strategy`}>
                      {signal.strategy_name.replace(/_/g, ' ')}
                    </span>
                    <span className="font-mono text-white" data-design-id={`signal-item-${index}-price`}>
                      @ ${signal.entry_price.toLocaleString()}
                    </span>
                    <span className="text-purple-400" data-design-id={`signal-item-${index}-confidence`}>
                      {(signal.confidence * 100).toFixed(0)}% conf
                    </span>
                  </div>
                  
                  {(signal.stop_loss || signal.take_profit) && (
                    <div className="mt-2 flex gap-4 text-xs" data-design-id={`signal-item-${index}-levels`}>
                      {signal.stop_loss && (
                        <span className="text-red-400" data-design-id={`signal-item-${index}-sl`}>
                          SL: ${signal.stop_loss.toLocaleString()}
                        </span>
                      )}
                      {signal.take_profit && (
                        <span className="text-emerald-400" data-design-id={`signal-item-${index}-tp`}>
                          TP: ${signal.take_profit.toLocaleString()}
                        </span>
                      )}
                    </div>
                  )}
                  
                  <p className="mt-2 text-xs text-slate-500 line-clamp-1" data-design-id={`signal-item-${index}-reason`}>
                    {signal.reason}
                  </p>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}