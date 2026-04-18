/**
 * RiskPulseWidget — The 4 numbers a risk manager checks constantly.
 * Portfolio exposure %, daily P&L, position count vs limit, largest position.
 * Answers: "am I about to breach a limit?"
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

interface RiskSnapshot {
  exposurePct: number;       // current margin used / equity
  exposureLimit: number;     // configured max (e.g. 0.95)
  dailyPnlUsd: number;
  dailyPnlPct: number;
  positionCount: number;
  equity: number;
  largestSymbol: string;
  largestPct: number;        // largest single position as % of equity
}

function trafficLight(val: number, warn: number, danger: number): string {
  if (val >= danger) return 'text-[#ef4444]';
  if (val >= warn) return 'text-[#eab308]';
  return 'text-[#22c55e]';
}

export const RiskPulseWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [snap, setSnap] = useState<RiskSnapshot | null>(null);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const [account, positions, riskLimits] = await Promise.all([
        apiClient.getAccountInfo(tradingMode),
        apiClient.getPositions(tradingMode),
        apiClient.getRiskLimits(tradingMode).catch(() => null),
      ]);

      const equity = account.equity || account.balance || 0;
      const marginUsed = (account as any).margin_used ?? 0;
      const exposurePct = equity > 0 ? (marginUsed / equity) * 100 : 0;
      const exposureLimit = ((riskLimits as any)?.max_portfolio_exposure ?? 95);

      const openPositions = positions.filter(p => !p.closed_at);
      const positionCount = openPositions.length;

      // Largest single position by value
      let largestSymbol = '—';
      let largestPct = 0;
      if (equity > 0 && openPositions.length > 0) {
        const largest = openPositions.reduce((best, p) => {
          const val = Math.abs((p as any).current_value ?? (p.quantity ?? 0) * (p.current_price ?? 0));
          const bestVal = Math.abs((best as any).current_value ?? (best.quantity ?? 0) * (best.current_price ?? 0));
          return val > bestVal ? p : best;
        });
        const largestVal = Math.abs((largest as any).current_value ?? (largest.quantity ?? 0) * (largest.current_price ?? 0));
        largestSymbol = largest.symbol || '?';
        largestPct = (largestVal / equity) * 100;
      }

      // Daily P&L from account
      const dailyPnlUsd = (account as any).daily_pnl ?? (account as any).unrealized_pnl ?? 0;
      const dailyPnlPct = equity > 0 ? (dailyPnlUsd / equity) * 100 : 0;

      setSnap({ exposurePct, exposureLimit, dailyPnlUsd, dailyPnlPct, positionCount, equity, largestSymbol, largestPct });
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetch, intervalMs: 15000, enabled: !!tradingMode, skipWhenWsConnected: true });
  useEffect(() => {
    if (!tradingMode) return;
    return wsManager.onPositionUpdate(() => fetch());
  }, [tradingMode, fetch]);

  if (!snap) {
    return <div className="text-xs text-gray-600 font-mono py-1">Loading...</div>;
  }

  const exposureWarn = snap.exposureLimit * 0.9;
  const exposureDanger = snap.exposureLimit * 0.98;

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">

      {/* Exposure */}
      <div className="flex flex-col">
        <span className="text-gray-500 text-[10px] uppercase tracking-wide">Exposure</span>
        <div className="flex items-baseline gap-1">
          <span className={cn('font-bold text-sm', trafficLight(snap.exposurePct, exposureWarn, exposureDanger))}>
            {snap.exposurePct.toFixed(1)}%
          </span>
          <span className="text-gray-600 text-[10px]">/ {snap.exposureLimit.toFixed(0)}%</span>
        </div>
        {/* Mini bar */}
        <div className="h-0.5 bg-gray-800 rounded mt-0.5 w-full">
          <div
            className={cn('h-full rounded transition-all', snap.exposurePct >= exposureDanger ? 'bg-[#ef4444]' : snap.exposurePct >= exposureWarn ? 'bg-[#eab308]' : 'bg-[#22c55e]')}
            style={{ width: `${Math.min(100, (snap.exposurePct / snap.exposureLimit) * 100)}%` }}
          />
        </div>
      </div>

      {/* Daily P&L */}
      <div className="flex flex-col">
        <span className="text-gray-500 text-[10px] uppercase tracking-wide">Daily P&L</span>
        <span className={cn('font-bold text-sm', snap.dailyPnlUsd >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
          {snap.dailyPnlUsd >= 0 ? '+' : ''}${Math.abs(snap.dailyPnlUsd).toLocaleString('en', { maximumFractionDigits: 0 })}
        </span>
        <span className={cn('text-[10px]', snap.dailyPnlPct >= 0 ? 'text-[#22c55e]/70' : 'text-[#ef4444]/70')}>
          {snap.dailyPnlPct >= 0 ? '+' : ''}{snap.dailyPnlPct.toFixed(2)}%
        </span>
      </div>

      {/* Positions */}
      <div className="flex flex-col">
        <span className="text-gray-500 text-[10px] uppercase tracking-wide">Positions</span>
        <span className="font-bold text-sm text-gray-200">{snap.positionCount}</span>
        <span className="text-gray-600 text-[10px]">
          ${snap.equity > 0 ? (snap.positionCount > 0 ? (snap.equity / snap.positionCount).toFixed(0) : '0') : '—'} avg
        </span>
      </div>

      {/* Largest position */}
      <div className="flex flex-col">
        <span className="text-gray-500 text-[10px] uppercase tracking-wide">Largest</span>
        <span className={cn('font-bold text-sm', trafficLight(snap.largestPct, 5, 10))}>
          {snap.largestPct.toFixed(1)}%
        </span>
        <span className="text-gray-600 text-[10px] truncate">{snap.largestSymbol}</span>
      </div>

    </div>
  );
};
