import { type FC, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { X } from 'lucide-react';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { cn } from '../lib/utils';

const TopMoversWidget = lazy(() => import('./widgets/TopMoversWidget').then(m => ({ default: m.TopMoversWidget })));
const RecentSignalsWidget = lazy(() => import('./widgets/RecentSignalsWidget').then(m => ({ default: m.RecentSignalsWidget })));
const MarketRegimeWidget = lazy(() => import('./widgets/MarketRegimeWidget').then(m => ({ default: m.MarketRegimeWidget })));
const StrategyAlertsWidget = lazy(() => import('./widgets/StrategyAlertsWidget').then(m => ({ default: m.StrategyAlertsWidget })));
const MacroPulseWidget = lazy(() => import('./widgets/MacroPulseWidget').then(m => ({ default: m.MacroPulseWidget })));

const STORAGE_KEY = 'alphacent_bottom_widgets';

interface WidgetDef {
  id: string;
  title: string;
  component: FC;
}

const ALL_WIDGETS: WidgetDef[] = [
  { id: 'top-movers', title: 'Top Movers', component: TopMoversWidget },
  { id: 'recent-signals', title: 'Recent Signals', component: RecentSignalsWidget },
  { id: 'market-regime', title: 'Market Regime', component: MarketRegimeWidget },
  { id: 'strategy-alerts', title: 'Strategy Alerts', component: StrategyAlertsWidget },
  { id: 'macro-pulse', title: 'Macro Pulse', component: MacroPulseWidget },
];

function loadVisibility(): Record<string, boolean> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  // Default: all visible
  return Object.fromEntries(ALL_WIDGETS.map(w => [w.id, true]));
}

export const BottomWidgetZone: FC = () => {
  const isBelowBreakpoint = useMediaQuery('(max-width: 1023px)');
  const [visibility, setVisibility] = useState<Record<string, boolean>>(loadVisibility);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(visibility));
    } catch { /* ignore */ }
  }, [visibility]);

  const closeWidget = useCallback((id: string) => {
    setVisibility(prev => ({ ...prev, [id]: false }));
  }, []);

  const visibleWidgets = ALL_WIDGETS.filter(w => visibility[w.id] !== false);

  if (visibleWidgets.length === 0) return null;

  return (
    <div
      className={cn(
        'border-t border-[var(--color-dark-border)] bg-[#0a0e17]',
        isBelowBreakpoint ? 'flex flex-col gap-0' : 'flex gap-0'
      )}
      style={{ maxHeight: '200px' }}
    >
      {visibleWidgets.map(widget => {
        const WidgetComponent = widget.component;
        return (
          <div
            key={widget.id}
            className={cn(
              'flex flex-col min-w-0 border-r border-[var(--color-dark-border)] last:border-r-0',
              isBelowBreakpoint ? 'w-full border-r-0 border-b last:border-b-0' : 'flex-1'
            )}
          >
            {/* Widget title bar */}
            <div className="flex items-center justify-between px-2 py-1 min-h-[24px] bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]">
              <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide truncate">
                {widget.title}
              </span>
              <button
                onClick={() => closeWidget(widget.id)}
                className="p-0.5 rounded text-gray-600 hover:text-gray-300 transition-colors shrink-0"
                title={`Close ${widget.title}`}
              >
                <X size={10} />
              </button>
            </div>
            {/* Widget content with internal scroll */}
            <div className="flex-1 overflow-auto min-h-0 p-2">
              <Suspense fallback={<div className="text-[10px] text-gray-600 text-center py-2">Loading...</div>}>
                <WidgetComponent />
              </Suspense>
            </div>
          </div>
        );
      })}
    </div>
  );
};
