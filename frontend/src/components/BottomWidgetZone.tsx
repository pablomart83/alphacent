/**
 * BottomWidgetZone — Persistent trading status bar.
 *
 * Three panels, each answering a distinct trader question:
 *   1. Book Pulse   — "What's moving in my book right now?"
 *   2. System Feed  — "What is the system doing right now?"
 *   3. Risk Pulse   — "Am I about to breach a limit?"
 */
import { type FC, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { cn } from '../lib/utils';

const BookPulseWidget     = lazy(() => import('./widgets/BookPulseWidget').then(m => ({ default: m.BookPulseWidget })));
const SystemFeedWidget    = lazy(() => import('./widgets/SystemFeedWidget').then(m => ({ default: m.SystemFeedWidget })));
const StrategyPulseWidget = lazy(() => import('./widgets/StrategyPulseWidget').then(m => ({ default: m.StrategyPulseWidget })));
const SignalStatsWidget   = lazy(() => import('./widgets/SignalStatsWidget').then(m => ({ default: m.SignalStatsWidget })));
const RiskPulseWidget     = lazy(() => import('./widgets/RiskPulseWidget').then(m => ({ default: m.RiskPulseWidget })));
const MarketPulseWidget   = lazy(() => import('./widgets/MarketPulseWidget').then(m => ({ default: m.MarketPulseWidget })));

const STORAGE_KEY = 'alphacent_bottom_v2';
const COLLAPSED_KEY = 'alphacent_bottom_collapsed';

interface WidgetDef {
  id: string;
  title: string;
  subtitle: string;
  component: FC;
  /** flex-basis hint so Risk Pulse (compact 2×2 grid) gets less width */
  widthClass?: string;
}

const WIDGETS: WidgetDef[] = [
  {
    id: 'book-pulse',
    title: 'Book Pulse',
    subtitle: 'Open positions by move',
    component: BookPulseWidget,
    widthClass: 'flex-[3]',   // ~25% — needs room for 5 columns
  },
  {
    id: 'system-feed',
    title: 'System Feed',
    subtitle: 'Signals · Orders · Lifecycle',
    component: SystemFeedWidget,
    widthClass: 'flex-[3]',   // ~25% — needs room for event rows
  },
  {
    id: 'market-pulse',
    title: 'Market Pulse',
    subtitle: 'Regime by asset class',
    component: MarketPulseWidget,
    widthClass: 'flex-[2]',   // ~17% — 4 compact rows
  },
  {
    id: 'strategy-pulse',
    title: 'Strategy Pulse',
    subtitle: 'Pipeline · Last event',
    component: StrategyPulseWidget,
    widthClass: 'flex-[2]',   // ~17% — 2×2 grid + last event
  },
  {
    id: 'signal-stats',
    title: 'Signal Stats',
    subtitle: 'Last run · Accept rate',
    component: SignalStatsWidget,
    widthClass: 'flex-[2]',   // ~17% — counts + bar
  },
  {
    id: 'risk-pulse',
    title: 'Risk Pulse',
    subtitle: 'Exposure · P&L · Limits',
    component: RiskPulseWidget,
    widthClass: 'flex-[2]',   // ~17% — 2×2 grid
  },
];

function loadVisibility(): Record<string, boolean> {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return JSON.parse(s);
  } catch { /* ignore */ }
  return Object.fromEntries(WIDGETS.map(w => [w.id, true]));
}

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true';
  } catch { return false; }
}

export const BottomWidgetZone: FC = () => {
  const isMobile = useMediaQuery('(max-width: 1023px)');
  const [visibility, setVisibility] = useState<Record<string, boolean>>(loadVisibility);
  const [collapsed, setCollapsed] = useState<boolean>(loadCollapsed);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(visibility)); } catch { /* ignore */ }
  }, [visibility]);

  useEffect(() => {
    try { localStorage.setItem(COLLAPSED_KEY, String(collapsed)); } catch { /* ignore */ }
  }, [collapsed]);

  const closeWidget = useCallback((id: string) => {
    setVisibility(prev => ({ ...prev, [id]: false }));
  }, []);

  const visibleWidgets = WIDGETS.filter(w => visibility[w.id] !== false);
  const hiddenCount = WIDGETS.length - visibleWidgets.length;

  if (visibleWidgets.length === 0) return null;

  return (
    <div className="border-t border-[var(--color-dark-border)] bg-[#080c14] select-none">

      {/* Collapse toggle bar */}
      <div
        className="flex items-center justify-between px-3 py-0.5 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold">
            Trading Console
          </span>
          {hiddenCount > 0 && (
            <button
              className="text-[10px] text-gray-700 hover:text-gray-400 transition-colors"
              onClick={e => { e.stopPropagation(); setVisibility(loadVisibility()); }}
              title="Restore hidden panels"
            >
              +{hiddenCount} hidden
            </button>
          )}
        </div>
        <span className="text-gray-700 hover:text-gray-400 transition-colors">
          {collapsed ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </div>

      {/* Widget panels */}
      {!collapsed && (
        <div
          className={cn(
            isMobile ? 'flex flex-col' : 'flex',
            'border-t border-[var(--color-dark-border)]'
          )}
          style={{ height: '148px' }}
        >
          {visibleWidgets.map((widget) => {
            const WidgetComponent = widget.component;
            return (
              <div
                key={widget.id}
                className={cn(
                  'flex flex-col min-w-0',
                  'border-r border-[var(--color-dark-border)] last:border-r-0',
                  isMobile ? 'w-full border-r-0 border-b last:border-b-0' : widget.widthClass,
                )}
              >
                {/* Content — no separate header, name shown inline */}
                <div className="flex-1 overflow-y-auto min-h-0 px-3 pt-1.5 pb-1.5 relative">
                  {/* Widget name + close — minimal, top of content area */}
                  <div className="flex items-center justify-between mb-1 shrink-0">
                    <span className="text-[9px] font-semibold text-gray-600 uppercase tracking-widest">
                      {widget.title}
                    </span>
                    <button
                      onClick={() => closeWidget(widget.id)}
                      className="p-0.5 rounded text-gray-800 hover:text-gray-500 transition-colors"
                      title={`Hide ${widget.title}`}
                    >
                      <X size={9} />
                    </button>
                  </div>
                  <Suspense fallback={
                    <div className="text-[10px] text-gray-700 font-mono py-1">Loading...</div>
                  }>
                    <WidgetComponent />
                  </Suspense>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
