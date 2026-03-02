import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface HeaderProps {
  isRunning: boolean;
  onStart: () => void;
  onStop: () => void;
  loading: boolean;
}

export function Header({ isRunning, onStart, onStop, loading }: HeaderProps) {
  return (
    <header 
      className="sticky top-0 z-50 border-b border-emerald-900/30 bg-slate-950/95 backdrop-blur-md"
      data-design-id="header-container"
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4" data-design-id="header-inner">
        <div className="flex items-center gap-4" data-design-id="header-logo-section">
          <div className="flex items-center gap-2" data-design-id="header-logo">
            <svg 
              className="h-8 w-8 text-emerald-400"
              viewBox="0 0 24 24" 
              fill="currentColor"
              data-design-id="header-logo-icon"
            >
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            <span className="text-xl font-bold text-white" data-design-id="header-title">
              Coinbase Trading Simulator
            </span>
          </div>
          <Badge 
            variant="outline" 
            className="border-amber-500/50 bg-amber-500/10 text-amber-400"
            data-design-id="header-paper-badge"
          >
            ⚠️ PAPER TRADING ONLY
          </Badge>
        </div>

        <div className="flex items-center gap-4" data-design-id="header-controls">
          <div className="flex items-center gap-2" data-design-id="header-status">
            <span 
              className={`h-2 w-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-500'}`}
              data-design-id="header-status-indicator"
            />
            <span className="text-sm text-slate-400" data-design-id="header-status-text">
              {isRunning ? 'Live' : 'Stopped'}
            </span>
          </div>
          
          <Button
            onClick={isRunning ? onStop : onStart}
            disabled={loading}
            className={isRunning 
              ? 'bg-red-600 hover:bg-red-700' 
              : 'bg-emerald-600 hover:bg-emerald-700'
            }
            data-design-id="header-toggle-button"
          >
            {loading ? 'Loading...' : isRunning ? 'Stop Simulator' : 'Start Simulator'}
          </Button>
        </div>
      </div>
    </header>
  );
}