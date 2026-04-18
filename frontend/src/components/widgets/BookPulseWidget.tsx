/**
 * BookPulseWidget — Live open positions sorted by today's move.
 * Shows: symbol, L/S, unrealized P&L $, unrealized P&L %, time in trade.
 * Replaces the old "Top Movers" widget which only showed your own positions
 * ranked by total unrealized P&L (not today's move, not actionable).
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

interface BookRow {
  symbol: string;
  side: 'L' | 'S';
  pnlPct: number;
  pnlUsd: number;
  daysOpen: number;
}

function daysAgo(dateStr: string): number {
  if (!dateStr) return 0;
  const ms = Date.now() - new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z').getTime();
  return Math.floor(ms / 86400000);
}

export const BookPulseWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [rows, setRows] = useState<BookRow[]>([]);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const positions = await apiClient.getPositions(tradingMode);
      const mapped: BookRow[] = positions
        .filter(p => !p.closed_at)
        .map(p => ({
          symbol: p.symbol || '?',
          side: (p.side === 'SELL') ? 'S' as const : 'L' as const,
          pnlPct: p.unrealized_pnl_percent ?? 0,
          pnlUsd: p.unrealized_pnl ?? 0,
          daysOpen: daysAgo(p.opened_at || ''),
        }))
        .sort((a, b) => Math.abs(b.pnlPct) - Math.abs(a.pnlPct))
        .slice(0, 8);
      setRows(mapped);
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetch, intervalMs: 15000, enabled: !!tradingMode, skipWhenWsConnected: true });
  useEffect(() => {
    if (!tradingMode) return;
    return wsManager.onPositionUpdate(() => fetch());
  }, [tradingMode, fetch]);

  if (rows.length === 0) {
    return <div className="text-xs text-gray-600 font-mono py-1">No open positions</div>;
  }

  return (
    <div className="space-y-0.5 text-xs font-mono">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-1.5 py-0.5">
          {/* Side badge */}
          <span className={cn(
            'w-4 text-center font-bold shrink-0 rounded-sm text-[10px]',
            r.side === 'L' ? 'text-[#22c55e]' : 'text-[#ef4444]'
          )}>
            {r.side}
          </span>
          {/* Symbol */}
          <span className="text-gray-200 w-14 truncate shrink-0">{r.symbol}</span>
          {/* P&L % */}
          <span className={cn(
            'font-semibold w-14 text-right shrink-0',
            r.pnlPct >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'
          )}>
            {r.pnlPct >= 0 ? '+' : ''}{r.pnlPct.toFixed(2)}%
          </span>
          {/* P&L $ */}
          <span className={cn(
            'w-16 text-right shrink-0',
            r.pnlUsd >= 0 ? 'text-[#22c55e]/70' : 'text-[#ef4444]/70'
          )}>
            {r.pnlUsd >= 0 ? '+' : ''}${Math.abs(r.pnlUsd).toFixed(0)}
          </span>
          {/* Days open */}
          <span className="text-gray-600 text-right flex-1 shrink-0">
            {r.daysOpen === 0 ? 'today' : `${r.daysOpen}d`}
          </span>
        </div>
      ))}
    </div>
  );
};
