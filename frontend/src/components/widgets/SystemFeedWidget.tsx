/**
 * SystemFeedWidget — Unified chronological feed of system events.
 * Shows: timestamp (relative), event type badge, symbol/strategy, outcome.
 * Merges signals + orders + strategy lifecycle into one scannable stream.
 * Answers: "what is the system doing right now?"
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { useWidgetActive } from '../BottomWidgetZone';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

type EventKind = 'ORDER' | 'SIGNAL' | 'REJECTED' | 'ACTIVATED' | 'RETIRED';

interface FeedEvent {
  kind: EventKind;
  symbol: string;
  detail: string;   // e.g. "BUY · 95%" or "Max exposure" or "Sharpe 1.2"
  ageMs: number;
  ts: number;       // epoch ms for sorting
}

const KIND_STYLE: Record<EventKind, { label: string; color: string }> = {
  ORDER:     { label: 'ORDER',    color: 'text-[#22c55e] bg-[#22c55e]/10' },
  SIGNAL:    { label: 'SIGNAL',   color: 'text-[#3b82f6] bg-[#3b82f6]/10' },
  REJECTED:  { label: 'REJECT',   color: 'text-[#ef4444] bg-[#ef4444]/10' },
  ACTIVATED: { label: 'ACTIVE',   color: 'text-[#a855f7] bg-[#a855f7]/10' },
  RETIRED:   { label: 'RETIRED',  color: 'text-[#f97316] bg-[#f97316]/10' },
};

function relativeTime(ageMs: number): string {
  const s = Math.floor(ageMs / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h`;
}

function parseTs(ts: string | undefined): number {
  if (!ts) return 0;
  return new Date(ts.endsWith('Z') ? ts : ts + 'Z').getTime();
}

export const SystemFeedWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const active = useWidgetActive();
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [now, setNow] = useState(Date.now());

  // Tick every 30s to refresh relative timestamps
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const collected: FeedEvent[] = [];

      // 1. Recent orders (executed = ORDER, failed = REJECTED) — last 6h only
      try {
        const orders = await apiClient.getOrders(tradingMode, 20);
        const cutoff6h = Date.now() - 6 * 3600 * 1000;
        for (const o of orders) {
          const ts = parseTs(o.created_at || o.updated_at);
          if (ts < cutoff6h) continue; // skip stale orders
          const isFilled = (o.status || '').toLowerCase() === 'filled';
          const isFailed = ['failed', 'cancelled', 'rejected'].includes((o.status || '').toLowerCase());
          if (!isFilled && !isFailed) continue;
          collected.push({
            kind: isFilled ? 'ORDER' : 'REJECTED',
            symbol: o.symbol || '?',
            detail: `${o.side || 'BUY'} · $${((o as any).amount ?? o.quantity ?? 0).toFixed(0)}`,
            ageMs: 0,
            ts,
          });
        }
      } catch { /* ignore */ }

      // 2. Recent signals (from signals endpoint)
      try {
        const sigData = await apiClient.getRecentSignals(tradingMode, 10);
        const sigs = sigData?.signals || [];
        for (const s of sigs) {
          const ts = parseTs(s.created_at);
          const conviction = s.metadata?.conviction_score ?? s.metadata?.signal_strength ?? 0;
          const hasOrder = s.metadata?.order_placed === true;
          const rejReason = s.metadata?.rejection_reason || '';
          collected.push({
            kind: hasOrder ? 'SIGNAL' : rejReason ? 'REJECTED' : 'SIGNAL',
            symbol: s.symbol || '?',
            detail: `${(s.side || 'LONG').replace('ENTER_', '')} · ${(conviction * 100).toFixed(0)}%${rejReason ? ` · ${rejReason.slice(0, 20)}` : ''}`,
            ageMs: 0,
            ts,
          });
        }
      } catch { /* ignore */ }

      // 3. Strategy lifecycle events (activated / retired)
      try {
        const strategies = await apiClient.getStrategies(tradingMode, true);
        const cutoff = Date.now() - 24 * 3600 * 1000; // last 24h
        for (const s of strategies) {
          if (s.status === 'DEMO' || s.status === 'LIVE') {
            const ts = parseTs((s as any).activated_at || s.created_at);
            if (ts > cutoff) {
              const sharpe = s.performance_metrics?.sharpe_ratio ?? s.backtest_results?.sharpe_ratio ?? 0;
              collected.push({
                kind: 'ACTIVATED',
                symbol: s.name?.split(' ').slice(-1)[0] || s.name || '?',
                detail: `Sharpe ${sharpe.toFixed(2)}`,
                ageMs: 0,
                ts,
              });
            }
          }
          if (s.status === 'RETIRED') {
            const ts = parseTs(s.retired_at || s.updated_at);
            if (ts > cutoff) {
              collected.push({
                kind: 'RETIRED',
                symbol: s.name?.split(' ').slice(-1)[0] || s.name || '?',
                detail: (s as any).retirement_reason?.slice(0, 24) || 'Performance',
                ageMs: 0,
                ts,
              });
            }
          }
        }
      } catch { /* ignore */ }

      // Sort newest first, dedupe, cap at 10
      const sorted = collected
        .filter(e => e.ts > 0)
        .sort((a, b) => b.ts - a.ts)
        .slice(0, 10)
        .map(e => ({ ...e, ageMs: Date.now() - e.ts }));

      setEvents(sorted);
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetch, intervalMs: 20000, enabled: !!tradingMode && active, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const u1 = wsManager.onSignalGenerated(() => fetch());
    const u2 = wsManager.onStrategyUpdate(() => fetch());
    const u3 = wsManager.on('order_filled', () => fetch());
    return () => { u1(); u2(); u3(); };
  }, [tradingMode, fetch]);

  if (events.length === 0) {
    return <div className="text-xs text-gray-600 font-mono py-1">No recent activity</div>;
  }

  return (
    <div className="space-y-0.5 text-xs font-mono">
      {events.map((e, i) => {
        const style = KIND_STYLE[e.kind];
        const age = relativeTime(now - e.ts);
        return (
          <div key={i} className="flex items-center gap-1.5 py-0.5">
            {/* Age */}
            <span className="text-gray-600 w-6 shrink-0 text-right">{age}</span>
            {/* Kind badge */}
            <span className={cn('px-1 rounded text-[10px] font-bold shrink-0', style.color)}>
              {style.label}
            </span>
            {/* Symbol */}
            <span className="text-gray-200 w-12 truncate shrink-0">{e.symbol}</span>
            {/* Detail */}
            <span className="text-gray-500 truncate flex-1">{e.detail}</span>
          </div>
        );
      })}
    </div>
  );
};
