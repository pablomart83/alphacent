import { type FC, useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Maximize2, Minimize2, Eye, EyeOff,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow } from '../components/trading/CompactMetricRow';
import type { CompactMetric } from '../components/trading/CompactMetricRow';
import { RefreshButton } from '../components/ui/RefreshButton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, ChartSkeleton } from '../components/ui/skeleton';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { PeriodSelector } from '../components/charts/PeriodSelector';
import { MultiTimeframeView } from '../components/charts/MultiTimeframeView';
import { TearSheetGenerator } from '../components/pdf/TearSheetGenerator';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency } from '../lib/utils';
import { formatDate } from '../lib/date-utils';
import { classifyError } from '../lib/errors';
import { toast } from 'sonner';
import type { Position, Strategy } from '../types';

// ── Types ──────────────────────────────────────────────────────────────────

interface OverviewNewProps {
  onLogout: () => void;
}

interface DashboardData {
  pnl_periods: Array<{ label: string; pnl_absolute: number; pnl_percent: number }>;
  equity_curve: Array<{ date: string; equity: number; benchmark?: number }>;
  drawdown_data: Array<{ date: string; drawdown_pct: number }>;
  sector_exposure: Array<{ sector: string; allocation_pct: number; pnl: number; pnl_pct: number; position_count: number }>;
  market_regime: { current_regime: string; regime_color: string; regime_description: string };
  health_score: { score: number; drawdown_score: number; concentration_score: number; margin_score: number; diversity_score: number };
  quick_stats: { open_positions: number; active_strategies: number; pending_orders: number; todays_trades: number; win_rate_30d: number };
  account_balance: number;
  account_equity: number;
  available_cash: number;
  total_unrealized_pnl: number;
  total_invested: number;
}

// ── Asset class helpers ────────────────────────────────────────────────────

const ASSET_CLASS_MAP: Record<string, string> = {
  Technology: 'Stocks', Healthcare: 'Stocks', 'Consumer Cyclical': 'Stocks',
  'Consumer Defensive': 'Stocks', Financial: 'Stocks', Industrials: 'Stocks',
  Energy: 'Stocks', Utilities: 'Stocks', 'Real Estate': 'Stocks',
  'Basic Materials': 'Stocks', 'Communication Services': 'Stocks',
  ETF: 'ETFs', Forex: 'Forex', Crypto: 'Crypto',
  Indices: 'Indices', Commodities: 'Commodities',
};

function classifyAssetClass(sector: string): string {
  return ASSET_CLASS_MAP[sector] || 'Stocks';
}

// ── Strategy pipeline stages ───────────────────────────────────────────────

const PIPELINE_STAGES = [
  { key: 'proposed', label: 'Proposed', filter: 'PROPOSED', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  { key: 'backtested', label: 'Backtested', filter: 'BACKTESTED', color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20' },
  { key: 'active', label: 'Active', filter: 'ACTIVE', color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' },
  { key: 'retired', label: 'Retired', filter: 'RETIRED', color: 'text-gray-400', bg: 'bg-gray-500/10', border: 'border-gray-500/20' },
] as const;

function countStrategiesByStage(strategies: Strategy[]): Record<string, number> {
  let proposed = 0, backtested = 0, active = 0, retired = 0;
  for (const s of strategies) {
    const status = s.status?.toUpperCase();
    if (status === 'PROPOSED') { proposed++; }
    else if (status === 'BACKTESTED') { proposed++; backtested++; }
    else if (status === 'DEMO' || status === 'LIVE') { proposed++; backtested++; active++; }
    else if (status === 'RETIRED') { proposed++; backtested++; retired++; }
    else if (status === 'PAUSED') { proposed++; backtested++; active++; }
  }
  return { proposed, backtested, active, retired };
}

// ── Multi-timeframe return calculation ─────────────────────────────────────

function calcReturnsFromEquityCurve(
  curve: Array<{ date: string; equity: number }>,
): Record<string, { absolute: number | null; alpha: number | null }> {
  if (!curve || curve.length < 2) return {};
  const now = new Date();
  const lastEquity = curve[curve.length - 1].equity;

  const periodDays: Record<string, number | 'YTD' | 'ALL'> = {
    '1D': 1, '1W': 7, '1M': 30, '3M': 90, '6M': 180, 'YTD': 'YTD', '1Y': 365, 'ALL': 'ALL',
  };

  const result: Record<string, { absolute: number | null; alpha: number | null }> = {};

  for (const [period, days] of Object.entries(periodDays)) {
    let startDate: Date;
    if (days === 'ALL') {
      startDate = new Date(curve[0].date);
    } else if (days === 'YTD') {
      startDate = new Date(now.getFullYear(), 0, 1);
    } else {
      startDate = new Date(now);
      startDate.setDate(startDate.getDate() - (days as number));
    }

    const startStr = startDate.toISOString().slice(0, 10);
    const startPoint = curve.find(p => p.date >= startStr);
    if (!startPoint || startPoint.equity === 0) {
      result[period] = { absolute: null, alpha: null };
      continue;
    }

    const ret = ((lastEquity - startPoint.equity) / startPoint.equity) * 100;
    result[period] = { absolute: Math.round(ret * 100) / 100, alpha: null };
  }

  return result;
}

// ── Position summary by asset class ────────────────────────────────────────

interface AssetClassSummary {
  assetClass: string;
  count: number;
  totalPnl: number;
}

function buildAssetClassSummary(
  sectorExposure: DashboardData['sector_exposure'],
): AssetClassSummary[] {
  const map = new Map<string, AssetClassSummary>();
  for (const s of sectorExposure) {
    const ac = classifyAssetClass(s.sector);
    const existing = map.get(ac);
    if (existing) {
      existing.count += s.position_count;
      existing.totalPnl += s.pnl;
    } else {
      map.set(ac, { assetClass: ac, count: s.position_count, totalPnl: s.pnl });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count);
}

// ── Main Component ─────────────────────────────────────────────────────────

export const OverviewNew: FC<OverviewNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const navigate = useNavigate();

  // State
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [spyData, setSpyData] = useState<Array<{ date: string; close: number }> | undefined>(undefined);
  const [recentTrades, setRecentTrades] = useState<Position[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [equityPeriod, setEquityPeriod] = useState('3M');
  const [showBenchmark, setShowBenchmark] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Fetch all data
  const fetchAll = useCallback(async () => {
    if (!tradingMode) return;
    try {
      setError(null);
      const [dashData, closedPos, strats] = await Promise.all([
        apiClient.getDashboardSummary(tradingMode),
        apiClient.getClosedPositions(tradingMode, 10),
        apiClient.getStrategies(tradingMode, true),
      ]);

      setDashboard(dashData);
      setRecentTrades(closedPos.slice(0, 10));
      setStrategies(strats);
      setLastFetchedAt(new Date());
      setLoading(false);

      // Fetch SPY benchmark (non-blocking — endpoint may not exist yet)
      try {
        const spy = await apiClient.getSpyBenchmark(equityPeriod);
        setSpyData(spy && spy.length > 0 ? spy : undefined);
      } catch {
        setSpyData(undefined);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard:', err);
      const classified = classifyError(err, 'dashboard data');
      toast.error(classified.title, { description: classified.message });
      setError(classified.message);
      setLoading(false);
    }
  }, [tradingMode, equityPeriod]);

  const { refresh, isRefreshing } = usePolling({
    fetchFn: fetchAll,
    intervalMs: 30000,
    enabled: !!tradingMode && !tradingModeLoading,
    skipWhenWsConnected: true,
  });

  // WebSocket live updates
  useEffect(() => {
    const unsub1 = wsManager.onPositionUpdate(() => { if (tradingMode) refresh(); });
    const unsub2 = wsManager.onOrderUpdate(() => { if (tradingMode) refresh(); });
    return () => { unsub1(); unsub2(); };
  }, [tradingMode, refresh]);

  // Derived data
  const multiTimeframeReturns = useMemo(
    () => calcReturnsFromEquityCurve(dashboard?.equity_curve ?? []),
    [dashboard?.equity_curve],
  );

  const assetClassSummary = useMemo(
    () => buildAssetClassSummary(dashboard?.sector_exposure ?? []),
    [dashboard?.sector_exposure],
  );

  const strategyCounts = useMemo(
    () => countStrategiesByStage(strategies),
    [strategies],
  );

  const dailyPnl = dashboard?.pnl_periods?.find(p => p.label === 'Today');

  const maxDrawdown = useMemo(() => {
    if (!dashboard?.drawdown_data?.length) return 0;
    return Math.min(...dashboard.drawdown_data.map(d => d.drawdown_pct));
  }, [dashboard?.drawdown_data]);

  const handlePeriodClick = useCallback((period: string) => {
    const periodMap: Record<string, string> = {
      '1D': '1W', '1W': '1W', '1M': '1M', '3M': '3M',
      '6M': '6M', 'YTD': '1Y', '1Y': '1Y', 'ALL': 'ALL',
    };
    setEquityPeriod(periodMap[period] || '3M');
  }, []);

  // Build compact metrics for left panel
  const compactMetrics: CompactMetric[] = useMemo(() => {
    const d = dashboard;
    if (!d) return [];
    const pnl = dailyPnl?.pnl_absolute ?? 0;
    const pnlPct = dailyPnl?.pnl_percent ?? 0;
    const sharpe = d.quick_stats?.win_rate_30d != null
      ? (d.quick_stats.win_rate_30d / 100 * 2).toFixed(2)
      : 'N/A';
    return [
      {
        label: 'Equity',
        value: formatCurrency(d.account_equity ?? 0),
        trend: 'neutral' as const,
      },
      {
        label: 'Daily P&L',
        value: `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)`,
        trend: pnl > 0 ? 'up' as const : pnl < 0 ? 'down' as const : 'neutral' as const,
      },
      {
        label: 'Sharpe',
        value: sharpe,
      },
      {
        label: 'Max DD',
        value: `${maxDrawdown.toFixed(2)}%`,
        trend: maxDrawdown < -5 ? 'down' as const : 'neutral' as const,
      },
    ];
  }, [dashboard, dailyPnl, maxDrawdown]);

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  const d = dashboard;

  // Effective SPY data — hide if benchmark toggle is off
  const effectiveSpyData = showBenchmark ? spyData : undefined;

  // ── Header actions ─────────────────────────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-2">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <TearSheetGenerator />
      <RefreshButton loading={isRefreshing} label="Refresh" onClick={refresh} />
    </div>
  );

  const modeLabel = tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading';

  // ── Center panel toolbar actions ───────────────────────────────────────
  const centerToolbar = (
    <div className="flex items-center gap-2">
      <PeriodSelector
        activePeriod={equityPeriod}
        onPeriodChange={setEquityPeriod}
      />
      <button
        onClick={() => setShowBenchmark(!showBenchmark)}
        className={cn(
          'p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors',
          showBenchmark && 'text-blue-400 hover:text-blue-300',
        )}
        title={showBenchmark ? 'Hide benchmark' : 'Show benchmark'}
      >
        {showBenchmark ? <Eye size={14} /> : <EyeOff size={14} />}
      </button>
      <button
        onClick={() => setIsFullscreen(!isFullscreen)}
        className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
        title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
      >
        {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
    </div>
  );

  // ── Left Panel Content ─────────────────────────────────────────────────
  const leftPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Metrics" panelId="overview-metrics" onRefresh={refresh}>
        <div className="flex flex-col gap-3 p-3 overflow-auto">
          {/* Compact Metric Row */}
          <CompactMetricRow metrics={compactMetrics} className="flex-wrap h-auto min-h-0 max-h-none" />

          {/* Multi-Timeframe View */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Performance
            </div>
            <MultiTimeframeView
              returns={multiTimeframeReturns}
              onPeriodClick={handlePeriodClick}
              compact
            />
          </div>

          {/* Strategy Pipeline */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Strategy Pipeline
            </div>
            <div className="flex flex-col gap-1.5">
              {PIPELINE_STAGES.map((stage) => (
                <button
                  key={stage.key}
                  type="button"
                  onClick={() => navigate(`/strategies?status=${stage.filter}`)}
                  className={cn(
                    'flex items-center justify-between rounded-md border px-3 py-1.5 transition-all',
                    'hover:brightness-125 cursor-pointer',
                    stage.bg, stage.border,
                  )}
                >
                  <span className="text-xs text-gray-300">{stage.label}</span>
                  <span className={cn('text-sm font-bold font-mono', stage.color)}>
                    {strategyCounts[stage.key] ?? 0}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Center Panel Content ───────────────────────────────────────────────
  const centerPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Equity Curve" panelId="overview-equity" actions={centerToolbar}>
        <div className="flex-1 p-3 overflow-auto min-h-0">
          {d ? (
            <EquityCurveChart
              equityData={d.equity_curve}
              spyData={effectiveSpyData}
              period={equityPeriod}
              onPeriodChange={setEquityPeriod}
              height={Math.max(400, 500)}
            />
          ) : (
            <ChartSkeleton height={400} />
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Right Panel Content ────────────────────────────────────────────────
  const rightPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Activity" panelId="overview-activity" onRefresh={refresh}>
        <div className="flex flex-col gap-3 p-3 overflow-auto">
          {/* Recent Trades */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Recent Trades
            </div>
            {recentTrades.length > 0 ? (
              <div className="space-y-1">
                {recentTrades.map((trade) => (
                  <div key={trade.id} className="flex items-center justify-between py-1 border-b border-border/30 last:border-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-mono font-semibold text-gray-200 truncate">{trade.symbol}</span>
                      <span className={cn(
                        'text-[9px] font-mono px-1 py-0.5 rounded',
                        trade.side === 'BUY' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400',
                      )}>
                        {trade.side}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={cn(
                        'text-xs font-mono font-semibold',
                        (trade.realized_pnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red',
                      )}>
                        {(trade.realized_pnl ?? 0) >= 0 ? '+' : ''}{formatCurrency(trade.realized_pnl ?? 0)}
                      </span>
                      <span className="text-[9px] text-muted-foreground font-mono">
                        {trade.closed_at ? formatDate(trade.closed_at, 'MMM d') : '—'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-4">No recent trades</p>
            )}
          </div>

          {/* Position Summary by Asset Class */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Positions by Asset Class
            </div>
            {assetClassSummary.length > 0 ? (
              <div className="space-y-1">
                {assetClassSummary.map((ac) => (
                  <div key={ac.assetClass} className="flex items-center justify-between py-1 border-b border-border/30 last:border-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-gray-200">{ac.assetClass}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">({ac.count})</span>
                    </div>
                    <span className={cn(
                      'text-xs font-mono font-semibold',
                      ac.totalPnl > 0 ? 'text-accent-green' : ac.totalPnl < 0 ? 'text-accent-red' : 'text-gray-400',
                    )}>
                      {ac.totalPnl >= 0 ? '+' : ''}{formatCurrency(ac.totalPnl)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-4">No open positions</p>
            )}
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Fullscreen mode — center panel only ────────────────────────────────
  if (isFullscreen) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate
          title="◆ Command Centre"
          description={modeLabel}
          actions={headerActions}
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            {centerPanel}
          </motion.div>
        </PageTemplate>
      </DashboardLayout>
    );
  }

  // ── Normal 3-panel layout ──────────────────────────────────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Command Centre"
        description={modeLabel}
        actions={headerActions}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <ResizablePanelLayout
            layoutId="overview-panels"
            direction="horizontal"
            panels={[
              {
                id: 'overview-left',
                defaultSize: 25,
                minSize: 200,
                content: leftPanel,
              },
              {
                id: 'overview-center',
                defaultSize: 50,
                minSize: 400,
                content: centerPanel,
              },
              {
                id: 'overview-right',
                defaultSize: 25,
                minSize: 200,
                content: rightPanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
