/**
 * SignalStatsWidget — Last signal run summary.
 * Answers: "what happened in the last signal cycle?"
 * Shows: time since last run, total signals, executed vs rejected, top rejection reason.
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { useWidgetActive } from '../BottomWidgetZone';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

interface SignalSnap {
  lastRunAgo: string;       // "14m ago"
  total: number;
  executed: number;
  rejected: number;
  acceptanceRate: number;   // 0-100
  topRejection: string;     // e.g. "Max exposure"
}

function relAge(ts: string): string {
  if (!ts) return '—';
  const ms = Date.now() - new Date(ts.endsWith('Z') ? ts : ts + 'Z').getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

function truncateReason(r: string): string {
  // Shorten common rejection reasons
  const map: Record<string, string> = {
    'Max exposure reached': 'Max exposure',
    'Calculated position size is zero or negative': 'Zero size',
    'Strategy allocation exhausted': 'Alloc full',
    'Position already exists': 'Duplicate',
    'Market closed': 'Mkt closed',
    'Circuit breaker active': 'Circuit brk',
    'Daily loss limit reached': 'Loss limit',
  };
  for (const [k, v] of Object.entries(map)) {
    if (r.toLowerCase().includes(k.toLowerCase())) return v;
  }
  return r.slice(0, 16);
}

export const SignalStatsWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const active = useWidgetActive();
  const [snap, setSnap] = useState<SignalSnap | null>(null);
  const [tick, setTick] = useState(0);

  // Refresh relative time every 30s
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getRecentSignals(tradingMode, 50);
      if (!data) return;

      const { signals, summary } = data;
      const lastTs = signals[0]?.created_at || '';

      const topRejection = summary.rejection_reasons?.[0]?.reason
        ? truncateReason(summary.rejection_reasons[0].reason)
        : summary.rejected > 0 ? 'Unknown' : '—';

      setSnap({
        lastRunAgo: relAge(lastTs),
        total: summary.total,
        executed: summary.accepted,
        rejected: summary.rejected,
        acceptanceRate: summary.acceptance_rate,
        topRejection,
      });
    } catch { /* ignore */ }
  }, [tradingMode, tick]);

  usePolling({ fetchFn: fetch, intervalMs: 20000, enabled: !!tradingMode && active, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const u = wsManager.onSignalGenerated(() => fetch());
    return u;
  }, [tradingMode, fetch]);

  if (!snap) return <div className="text-xs text-gray-600 font-mono py-1">Loading...</div>;

  const rateColor = snap.acceptanceRate >= 30 ? 'text-[#22c55e]'
    : snap.acceptanceRate >= 10 ? 'text-[#eab308]'
    : 'text-[#ef4444]';

  return (
    <div className="flex flex-col gap-1.5 text-xs font-mono h-full">

      {/* Last run time */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-600 uppercase tracking-wide">Last Run</span>
        <span className="text-gray-300 font-semibold">{snap.lastRunAgo}</span>
      </div>

      <div className="h-px bg-gray-800" />

      {/* Signal counts */}
      <div className="grid grid-cols-3 gap-1 text-center">
        <div className="flex flex-col">
          <span className="text-gray-500 text-[10px]">Total</span>
          <span className="font-bold text-gray-200">{snap.total}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-gray-500 text-[10px]">Exec'd</span>
          <span className={cn('font-bold', snap.executed > 0 ? 'text-[#22c55e]' : 'text-gray-500')}>
            {snap.executed}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-gray-500 text-[10px]">Rejected</span>
          <span className={cn('font-bold', snap.rejected > 0 ? 'text-[#ef4444]' : 'text-gray-500')}>
            {snap.rejected}
          </span>
        </div>
      </div>

      {/* Acceptance rate bar */}
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-600">Accept rate</span>
          <span className={cn('font-bold text-[10px]', rateColor)}>
            {snap.acceptanceRate.toFixed(0)}%
          </span>
        </div>
        <div className="h-1 bg-gray-800 rounded overflow-hidden">
          <div
            className={cn('h-full rounded transition-all', rateColor.replace('text-', 'bg-'))}
            style={{ width: `${Math.min(100, snap.acceptanceRate)}%` }}
          />
        </div>
      </div>

      {/* Top rejection reason */}
      {snap.rejected > 0 && (
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-600">Top reject</span>
          <span className="text-[#ef4444]/80 text-[10px] truncate ml-2 text-right">{snap.topRejection}</span>
        </div>
      )}
    </div>
  );
};
