/**
 * StrategyPulseWidget — Strategy pipeline counts + last lifecycle event.
 * Answers: "did anything activate or retire since I last looked?"
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { useWidgetActive } from '../BottomWidgetZone';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

interface PipelineSnap {
  proposed: number;
  backtested: number;
  active: number;
  retired: number;
  lastEvent: { kind: 'ACTIVATED' | 'RETIRED' | 'BACKTESTED'; name: string; ageMin: number } | null;
}

const STAGE_CFG = [
  { key: 'proposed',   label: 'Proposed',    color: 'text-[#3b82f6]', bg: 'bg-[#3b82f6]/10' },
  { key: 'backtested', label: 'Backtested',  color: 'text-[#eab308]', bg: 'bg-[#eab308]/10' },
  { key: 'active',     label: 'Active',      color: 'text-[#22c55e]', bg: 'bg-[#22c55e]/10' },
  { key: 'retired',    label: 'Retired',     color: 'text-gray-500',  bg: 'bg-gray-500/10'  },
] as const;

const EVENT_COLOR: Record<string, string> = {
  ACTIVATED: 'text-[#22c55e]',
  RETIRED:   'text-[#f97316]',
  BACKTESTED:'text-[#eab308]',
};

function minsAgo(ts: string): number {
  if (!ts) return 0;
  const ms = Date.now() - new Date(ts.endsWith('Z') ? ts : ts + 'Z').getTime();
  return Math.floor(ms / 60000);
}

export const StrategyPulseWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const active = useWidgetActive();
  const [snap, setSnap] = useState<PipelineSnap | null>(null);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const strategies = await apiClient.getStrategies(tradingMode, true);

      let proposed = 0, backtested = 0, active = 0, retired = 0;
      let lastEvent: PipelineSnap['lastEvent'] = null;
      let lastEventTs = 0;

      for (const s of strategies) {
        const status = s.status?.toUpperCase();
        if (status === 'PROPOSED') proposed++;
        else if (status === 'BACKTESTED') { proposed++; backtested++; }
        else if (status === 'DEMO' || status === 'LIVE' || status === 'PAUSED') { proposed++; backtested++; active++; }
        else if (status === 'RETIRED') { proposed++; backtested++; retired++; }

        // Track most recent lifecycle event
        const activatedTs = (s as any).activated_at ? new Date((s as any).activated_at + (!(s as any).activated_at.endsWith('Z') ? 'Z' : '')).getTime() : 0;
        const retiredTs = s.retired_at ? new Date(s.retired_at.endsWith('Z') ? s.retired_at : s.retired_at + 'Z').getTime() : 0;
        const updatedTs = s.updated_at ? new Date(s.updated_at.endsWith('Z') ? s.updated_at : s.updated_at + 'Z').getTime() : 0;

        if ((status === 'DEMO' || status === 'LIVE') && activatedTs > lastEventTs) {
          lastEventTs = activatedTs;
          lastEvent = { kind: 'ACTIVATED', name: s.name?.split(' ').slice(-2).join(' ') || s.name, ageMin: minsAgo((s as any).activated_at || s.updated_at) };
        }
        if (status === 'RETIRED' && retiredTs > lastEventTs) {
          lastEventTs = retiredTs;
          lastEvent = { kind: 'RETIRED', name: s.name?.split(' ').slice(-2).join(' ') || s.name, ageMin: minsAgo(s.retired_at || s.updated_at) };
        }
        if (status === 'BACKTESTED' && updatedTs > lastEventTs) {
          lastEventTs = updatedTs;
          lastEvent = { kind: 'BACKTESTED', name: s.name?.split(' ').slice(-2).join(' ') || s.name, ageMin: minsAgo(s.updated_at) };
        }
      }

      setSnap({ proposed, backtested, active, retired, lastEvent });
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetch, intervalMs: 30000, enabled: !!tradingMode && active, skipWhenWsConnected: true });
  useEffect(() => {
    if (!tradingMode) return;
    return wsManager.onStrategyUpdate(() => fetch());
  }, [tradingMode, fetch]);

  if (!snap) return <div className="text-xs text-gray-600 font-mono py-1">Loading...</div>;

  return (
    <div className="flex flex-col gap-1.5 text-xs font-mono h-full">
      {/* Pipeline counts */}
      <div className="grid grid-cols-2 gap-1">
        {STAGE_CFG.map(s => (
          <div key={s.key} className={cn('flex items-center justify-between px-1.5 py-0.5 rounded', s.bg)}>
            <span className="text-gray-500 text-[10px]">{s.label}</span>
            <span className={cn('font-bold', s.color)}>{snap[s.key as keyof PipelineSnap] as number}</span>
          </div>
        ))}
      </div>

      {/* Divider */}
      <div className="h-px bg-gray-800" />

      {/* Last lifecycle event */}
      {snap.lastEvent ? (
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] text-gray-600 uppercase tracking-wide">Last Event</span>
          <div className="flex items-center gap-1.5">
            <span className={cn('font-bold text-[10px] px-1 rounded', EVENT_COLOR[snap.lastEvent.kind],
              snap.lastEvent.kind === 'ACTIVATED' ? 'bg-[#22c55e]/10' :
              snap.lastEvent.kind === 'RETIRED' ? 'bg-[#f97316]/10' : 'bg-[#eab308]/10'
            )}>
              {snap.lastEvent.kind}
            </span>
            <span className="text-gray-300 truncate flex-1">{snap.lastEvent.name}</span>
          </div>
          <span className="text-gray-600 text-[10px]">
            {snap.lastEvent.ageMin < 60
              ? `${snap.lastEvent.ageMin}m ago`
              : `${Math.floor(snap.lastEvent.ageMin / 60)}h ago`}
          </span>
        </div>
      ) : (
        <span className="text-gray-700 text-[10px]">No recent events</span>
      )}
    </div>
  );
};
