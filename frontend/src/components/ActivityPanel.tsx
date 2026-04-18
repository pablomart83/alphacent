/**
 * ActivityPanel — Tabbed activity feed for the Overview right panel.
 *
 * Tabs:
 *   Trades    — last 20 closed trades, sortable by P&L or date
 *   Opened    — recently opened positions (last 20)
 *   Closed    — recently closed positions with P&L detail (last 20)
 *   Top P&L   — best 10 + worst 10 closed trades
 *   Strategies — recent lifecycle events (activated / backtested / retired)
 */
import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency } from '../lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import type { Strategy } from '../types';

// ── Types ──────────────────────────────────────────────────────────────────

interface ClosedTrade {
  id: string;
  symbol: string;
  side: string;
  realizedPnl: number;
  realizedPnlPct: number;
  closedAt: string;
  openedAt: string;
  entryPrice: number;
  exitPrice: number;
  strategyName?: string;
}

interface OpenedPosition {
  id: string;
  symbol: string;
  side: string;
  entryPrice: number;
  currentPrice: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  openedAt: string;
  strategyName?: string;
}

interface StrategyEvent {
  id: string;
  name: string;
  status: string;
  eventTs: string;
  sharpe?: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function relDate(ts: string): string {
  if (!ts) return '—';
  const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  const diffMs = Date.now() - d.getTime();
  const diffM = Math.floor(diffMs / 60000);
  if (diffM < 60) return `${diffM}m ago`;
  const diffH = Math.floor(diffM / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function holdingTime(openedAt: string, closedAt: string): string {
  if (!openedAt || !closedAt) return '—';
  const ms = new Date(closedAt.endsWith('Z') ? closedAt : closedAt + 'Z').getTime()
           - new Date(openedAt.endsWith('Z') ? openedAt : openedAt + 'Z').getTime();
  const h = Math.floor(ms / 3600000);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const pnlColor = (v: number) => v >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]';
const sideColor = (s: string) => s === 'BUY' ? 'text-[#22c55e] bg-[#22c55e]/10' : 'text-[#ef4444] bg-[#ef4444]/10';

const STATUS_CFG: Record<string, { label: string; color: string; bg: string }> = {
  DEMO:       { label: 'ACTIVATED', color: 'text-[#22c55e]', bg: 'bg-[#22c55e]/10' },
  LIVE:       { label: 'ACTIVATED', color: 'text-[#22c55e]', bg: 'bg-[#22c55e]/10' },
  BACKTESTED: { label: 'BACKTESTED', color: 'text-[#eab308]', bg: 'bg-[#eab308]/10' },
  RETIRED:    { label: 'RETIRED',   color: 'text-[#f97316]', bg: 'bg-[#f97316]/10' },
  PROPOSED:   { label: 'PROPOSED',  color: 'text-[#3b82f6]', bg: 'bg-[#3b82f6]/10' },
};

// ── Sub-components ─────────────────────────────────────────────────────────

const EmptyState: FC<{ msg: string }> = ({ msg }) => (
  <div className="flex items-center justify-center h-16 text-xs text-gray-600 font-mono">{msg}</div>
);

const SortBtn: FC<{ active: boolean; label: string; onClick: () => void }> = ({ active, label, onClick }) => (
  <button
    onClick={onClick}
    className={cn(
      'text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors',
      active ? 'bg-gray-700 text-gray-200' : 'text-gray-600 hover:text-gray-400'
    )}
  >
    {label}
  </button>
);

// ── Main component ─────────────────────────────────────────────────────────

interface ActivityPanelProps {
  /** Pass strategies from parent if already fetched */
  initialStrategies?: Strategy[];
}

export const ActivityPanel: FC<ActivityPanelProps> = ({ initialStrategies }) => {
  const { tradingMode } = useTradingMode();

  const [trades, setTrades]         = useState<ClosedTrade[]>([]);
  const [opened, setOpened]         = useState<OpenedPosition[]>([]);
  const [stratEvents, setStratEvents] = useState<StrategyEvent[]>([]);
  const [tradeSort, setTradeSort]   = useState<'date' | 'pnl'>('date');
  const [activeTab, setActiveTab]   = useState('trades');

  // ── Fetch ────────────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const [closedRaw, openRaw, stratsRaw] = await Promise.all([
        apiClient.getClosedPositions(tradingMode, 20),
        apiClient.getPositions(tradingMode),
        initialStrategies ? Promise.resolve(initialStrategies) : apiClient.getStrategies(tradingMode, true),
      ]);

      // Closed trades
      const mapped: ClosedTrade[] = (closedRaw as any[]).map(p => ({
        id: p.id,
        symbol: p.symbol || '?',
        side: p.side || 'BUY',
        realizedPnl: p.realized_pnl ?? 0,
        realizedPnlPct: p.realized_pnl_percent ?? 0,
        closedAt: p.closed_at || '',
        openedAt: p.opened_at || '',
        entryPrice: p.entry_price ?? 0,
        exitPrice: p.exit_price ?? p.current_price ?? 0,
        strategyName: p.strategy_name,
      }));
      setTrades(mapped);

      // Open positions sorted by opened_at desc
      const openMapped: OpenedPosition[] = openRaw
        .filter(p => !p.closed_at)
        .sort((a, b) => {
          const ta = new Date((a.opened_at || '').endsWith('Z') ? a.opened_at : a.opened_at + 'Z').getTime();
          const tb = new Date((b.opened_at || '').endsWith('Z') ? b.opened_at : b.opened_at + 'Z').getTime();
          return tb - ta;
        })
        .slice(0, 20)
        .map(p => ({
          id: p.id,
          symbol: p.symbol || '?',
          side: p.side || 'BUY',
          entryPrice: p.entry_price ?? 0,
          currentPrice: p.current_price ?? 0,
          unrealizedPnl: p.unrealized_pnl ?? 0,
          unrealizedPnlPct: p.unrealized_pnl_percent ?? 0,
          openedAt: p.opened_at || '',
          strategyName: p.strategy_name,
        }));
      setOpened(openMapped);

      // Strategy events — last 20 lifecycle changes
      const events: StrategyEvent[] = (stratsRaw as Strategy[])
        .map(s => {
          const ts = s.status === 'RETIRED' ? (s.retired_at || s.updated_at)
                   : s.status === 'BACKTESTED' ? s.updated_at
                   : ((s as any).activated_at || s.updated_at);
          return {
            id: s.id,
            name: s.name,
            status: s.status?.toUpperCase() || 'UNKNOWN',
            eventTs: ts || '',
            sharpe: s.performance_metrics?.sharpe_ratio ?? s.backtest_results?.sharpe_ratio,
          };
        })
        .filter(e => e.eventTs)
        .sort((a, b) => new Date(b.eventTs.endsWith('Z') ? b.eventTs : b.eventTs + 'Z').getTime()
                      - new Date(a.eventTs.endsWith('Z') ? a.eventTs : a.eventTs + 'Z').getTime())
        .slice(0, 20);
      setStratEvents(events);
    } catch { /* ignore */ }
  }, [tradingMode, initialStrategies]);

  usePolling({ fetchFn: fetchAll, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const u1 = wsManager.onPositionUpdate(() => fetchAll());
    const u2 = wsManager.onStrategyUpdate(() => fetchAll());
    return () => { u1(); u2(); };
  }, [tradingMode, fetchAll]);

  // ── Derived ──────────────────────────────────────────────────────────────

  const sortedTrades = [...trades].sort((a, b) =>
    tradeSort === 'pnl'
      ? b.realizedPnl - a.realizedPnl
      : new Date(b.closedAt.endsWith('Z') ? b.closedAt : b.closedAt + 'Z').getTime()
      - new Date(a.closedAt.endsWith('Z') ? a.closedAt : a.closedAt + 'Z').getTime()
  );

  const winners = [...trades].sort((a, b) => b.realizedPnl - a.realizedPnl).slice(0, 10);
  const losers  = [...trades].sort((a, b) => a.realizedPnl - b.realizedPnl).slice(0, 10);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
      <TabsList className="shrink-0 flex gap-0 bg-transparent border-b border-gray-800 rounded-none px-1 h-7">
        {[
          { value: 'trades',     label: 'Trades' },
          { value: 'opened',     label: 'Opened' },
          { value: 'closed',     label: 'Closed' },
          { value: 'toppnl',     label: 'Top P&L' },
          { value: 'strategies', label: 'Strategies' },
        ].map(t => (
          <TabsTrigger
            key={t.value}
            value={t.value}
            className="text-[10px] px-2 py-0.5 h-6 rounded-none data-[state=active]:bg-transparent data-[state=active]:text-gray-100 data-[state=active]:border-b data-[state=active]:border-blue-500 text-gray-500 hover:text-gray-300 transition-colors"
          >
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>

      {/* ── Trades tab ── */}
      <TabsContent value="trades" className="flex-1 overflow-y-auto min-h-0 mt-0 px-1.5 py-1">
        <div className="flex items-center gap-1 mb-1.5">
          <span className="text-[10px] text-gray-600 mr-1">Sort:</span>
          <SortBtn active={tradeSort === 'date'} label="Date" onClick={() => setTradeSort('date')} />
          <SortBtn active={tradeSort === 'pnl'}  label="P&L"  onClick={() => setTradeSort('pnl')} />
        </div>
        {sortedTrades.length === 0 ? <EmptyState msg="No closed trades" /> : (
          <div className="space-y-0.5">
            {sortedTrades.map(t => (
              <div key={t.id} className="flex items-center gap-1.5 py-1 border-b border-gray-800/50 last:border-0 text-xs font-mono">
                <span className={cn('px-1 rounded text-[10px] font-bold shrink-0', sideColor(t.side))}>{t.side[0]}</span>
                <span className="text-gray-200 w-14 truncate shrink-0">{t.symbol}</span>
                <span className={cn('font-semibold w-16 text-right shrink-0', pnlColor(t.realizedPnl))}>
                  {t.realizedPnl >= 0 ? '+' : ''}{formatCurrency(t.realizedPnl)}
                </span>
                <span className={cn('w-12 text-right shrink-0 text-[10px]', pnlColor(t.realizedPnlPct))}>
                  {t.realizedPnlPct >= 0 ? '+' : ''}{t.realizedPnlPct.toFixed(1)}%
                </span>
                <span className="text-gray-600 text-right flex-1 text-[10px]">{relDate(t.closedAt)}</span>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      {/* ── Opened tab ── */}
      <TabsContent value="opened" className="flex-1 overflow-y-auto min-h-0 mt-0 px-1.5 py-1">
        {opened.length === 0 ? <EmptyState msg="No open positions" /> : (
          <div className="space-y-0.5">
            {opened.map(p => (
              <div key={p.id} className="flex items-center gap-1.5 py-1 border-b border-gray-800/50 last:border-0 text-xs font-mono">
                <span className={cn('px-1 rounded text-[10px] font-bold shrink-0', sideColor(p.side))}>{p.side[0]}</span>
                <span className="text-gray-200 w-14 truncate shrink-0">{p.symbol}</span>
                <span className="text-gray-500 w-16 text-right shrink-0">${p.entryPrice.toFixed(2)}</span>
                <span className={cn('font-semibold w-14 text-right shrink-0', pnlColor(p.unrealizedPnl))}>
                  {p.unrealizedPnl >= 0 ? '+' : ''}{formatCurrency(p.unrealizedPnl)}
                </span>
                <span className="text-gray-600 text-right flex-1 text-[10px]">{relDate(p.openedAt)}</span>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      {/* ── Closed tab ── */}
      <TabsContent value="closed" className="flex-1 overflow-y-auto min-h-0 mt-0 px-1.5 py-1">
        {trades.length === 0 ? <EmptyState msg="No closed trades" /> : (
          <div className="space-y-0.5">
            {[...trades]
              .sort((a, b) => new Date(b.closedAt.endsWith('Z') ? b.closedAt : b.closedAt + 'Z').getTime()
                            - new Date(a.closedAt.endsWith('Z') ? a.closedAt : a.closedAt + 'Z').getTime())
              .map(t => (
              <div key={t.id} className="flex items-center gap-1.5 py-1 border-b border-gray-800/50 last:border-0 text-xs font-mono">
                <span className={cn('px-1 rounded text-[10px] font-bold shrink-0', sideColor(t.side))}>{t.side[0]}</span>
                <span className="text-gray-200 w-14 truncate shrink-0">{t.symbol}</span>
                <span className="text-gray-500 text-[10px] shrink-0">${t.entryPrice.toFixed(2)}→${t.exitPrice.toFixed(2)}</span>
                <span className={cn('font-semibold shrink-0 ml-auto', pnlColor(t.realizedPnl))}>
                  {t.realizedPnl >= 0 ? '+' : ''}{formatCurrency(t.realizedPnl)}
                </span>
                <span className="text-gray-600 text-[10px] shrink-0 w-10 text-right">{holdingTime(t.openedAt, t.closedAt)}</span>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      {/* ── Top P&L tab ── */}
      <TabsContent value="toppnl" className="flex-1 overflow-y-auto min-h-0 mt-0 px-1.5 py-1">
        {trades.length === 0 ? <EmptyState msg="No closed trades" /> : (
          <div className="space-y-2">
            <div>
              <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">▲ Best</div>
              {winners.filter(t => t.realizedPnl > 0).map(t => (
                <div key={t.id} className="flex items-center gap-1.5 py-0.5 text-xs font-mono">
                  <span className="text-gray-200 w-14 truncate shrink-0">{t.symbol}</span>
                  <span className="text-[#22c55e] font-semibold w-16 text-right shrink-0">+{formatCurrency(t.realizedPnl)}</span>
                  <span className="text-[#22c55e]/70 text-[10px] shrink-0">+{t.realizedPnlPct.toFixed(1)}%</span>
                  <span className="text-gray-600 text-[10px] flex-1 text-right">{relDate(t.closedAt)}</span>
                </div>
              ))}
            </div>
            <div className="h-px bg-gray-800" />
            <div>
              <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">▼ Worst</div>
              {losers.filter(t => t.realizedPnl < 0).map(t => (
                <div key={t.id} className="flex items-center gap-1.5 py-0.5 text-xs font-mono">
                  <span className="text-gray-200 w-14 truncate shrink-0">{t.symbol}</span>
                  <span className="text-[#ef4444] font-semibold w-16 text-right shrink-0">{formatCurrency(t.realizedPnl)}</span>
                  <span className="text-[#ef4444]/70 text-[10px] shrink-0">{t.realizedPnlPct.toFixed(1)}%</span>
                  <span className="text-gray-600 text-[10px] flex-1 text-right">{relDate(t.closedAt)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </TabsContent>

      {/* ── Strategies tab ── */}
      <TabsContent value="strategies" className="flex-1 overflow-y-auto min-h-0 mt-0 px-1.5 py-1">
        {stratEvents.length === 0 ? <EmptyState msg="No strategy events" /> : (
          <div className="space-y-0.5">
            {stratEvents.map(e => {
              const cfg = STATUS_CFG[e.status] || { label: e.status, color: 'text-gray-400', bg: 'bg-gray-500/10' };
              return (
                <div key={e.id} className="flex items-center gap-1.5 py-1 border-b border-gray-800/50 last:border-0 text-xs font-mono">
                  <span className={cn('px-1 rounded text-[10px] font-bold shrink-0', cfg.color, cfg.bg)}>
                    {cfg.label.slice(0, 4)}
                  </span>
                  <span className="text-gray-200 truncate flex-1 min-w-0">{e.name}</span>
                  {e.sharpe != null && (
                    <span className="text-gray-500 text-[10px] shrink-0">S:{e.sharpe.toFixed(2)}</span>
                  )}
                  <span className="text-gray-600 text-[10px] shrink-0 w-12 text-right">{relDate(e.eventTs)}</span>
                </div>
              );
            })}
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
};
