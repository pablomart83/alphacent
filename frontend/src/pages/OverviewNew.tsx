import { type FC, useState, useMemo, useCallback, useEffect, useRef, memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Maximize2, Minimize2, Eye, EyeOff, RefreshCw,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow } from '../components/trading/CompactMetricRow';
import type { CompactMetric } from '../components/trading/CompactMetricRow';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, ChartSkeleton } from '../components/ui/skeleton';
import { PortfolioEquityChart } from '../components/charts/PortfolioEquityChart';
import { MultiTimeframeView } from '../components/charts/MultiTimeframeView';
import { TearSheetGenerator } from '../components/pdf/TearSheetGenerator';
import { ActivityPanel } from '../components/ActivityPanel';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn } from '../lib/utils';
import { classifyError } from '../lib/errors';
import { toast } from 'sonner';
import type { Position, Strategy } from '../types';

// ── Types ──────────────────────────────────────────────────────────────────

interface OverviewNewProps {
  onLogout: () => void;
}

interface DashboardData {
  pnl_periods: Array<{ label: string; pnl_absolute: number; pnl_percent: number }>;
  equity_curve: Array<{ date: string; equity: number; realized?: number; benchmark?: number }>;
  drawdown_data: Array<{ date: string; drawdown_pct: number }>;
  sector_exposure: Array<{ sector: string; allocation_pct: number; pnl: number; pnl_pct: number; position_count: number }>;
  market_regime: { current_regime: string; regime_color: string; regime_description: string };
  health_score: { score: number; drawdown_score: number; concentration_score: number; margin_score: number; diversity_score: number };
  quick_stats: { open_positions: number; active_strategies: number; pending_orders: number; todays_trades: number; win_rate_30d: number; sharpe_30d?: number | null };
  account_balance: number;
  account_equity: number;
  available_cash: number;
  total_unrealized_pnl: number;
  total_invested: number;
}

// ── Asset class helpers ────────────────────────────────────────────────────

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
      // curve[0].date is always "YYYY-MM-DD" (we filter to daily-only before calling this)
      // but guard against any non-ISO string slipping through
      const d = new Date(curve[0].date);
      startDate = isNaN(d.getTime()) ? new Date(now.getFullYear() - 1, 0, 1) : d;
    } else if (days === 'YTD') {
      startDate = new Date(now.getFullYear(), 0, 1);
    } else {
      startDate = new Date(now);
      startDate.setDate(startDate.getDate() - (days as number));
    }

    const startStr = startDate.toISOString().slice(0, 10);
    const startPoint = curve.find(p => /^\d{4}-\d{2}-\d{2}$/.test(p.date) && p.date >= startStr);
    if (!startPoint || startPoint.equity === 0) {
      result[period] = { absolute: null, alpha: null };
      continue;
    }

    const ret = ((lastEquity - startPoint.equity) / startPoint.equity) * 100;
    result[period] = { absolute: Math.round(ret * 100) / 100, alpha: null };
  }

  return result;
}

// ── AutoHeightChart — fills 100% of its flex container ────────────────────

// ── AutoHeightChart — measures available panel space and fills it ──────────

type AutoHeightChartProps = Omit<React.ComponentProps<typeof PortfolioEquityChart>, 'height'>;

const PANEL_HEADER_H = 32; // px — PanelHeader title bar height
const PANEL_PADDING  = 16; // px — p-2 = 8px top + 8px bottom

const AutoHeightChart: FC<AutoHeightChartProps & { containerRef: React.RefObject<HTMLDivElement> }> = ({ containerRef, ...props }) => {
  const [height, setHeight] = useState(480);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const h = el.clientHeight;
      if (h > 80) setHeight(Math.max(200, h - PANEL_HEADER_H - PANEL_PADDING));
    };
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, [containerRef]);

  return <PortfolioEquityChart {...props} height={height} />;
};

// ── Main Component ─────────────────────────────────────────────────────────

export const OverviewNew: FC<OverviewNewProps> = memo(({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const navigate = useNavigate();

  // State
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [spyData, setSpyData] = useState<Array<{ date: string; close: number }> | undefined>(undefined);
  // Equity curve fetched separately from analytics endpoint (same as PerformanceTab)
  const [equityCurveData, setEquityCurveData] = useState<Array<{ date: string; equity: number; realized?: number }>>([]);
  const [_recentTrades, setRecentTrades] = useState<Position[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [equityPeriod, setEquityPeriod] = useState('3M');
  const [equityInterval, setEquityInterval] = useState<'1d' | '4h' | '1h'>('1d');
  const [showBenchmark, setShowBenchmark] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  // Ref for the center panel container — used by AutoHeightChart to measure available height
  const centerPanelRef = useRef<HTMLDivElement>(null);

  // Fetch all data
  const fetchAll = useCallback(async (intervalOverride?: '1d' | '4h' | '1h') => {
    if (!tradingMode) return;
    const iv = intervalOverride ?? equityInterval;
    try {
      setError(null);
      const [dashData, closedPos, strats] = await Promise.all([
        apiClient.getDashboardSummary(tradingMode, iv),
        apiClient.getClosedPositions(tradingMode, 10),
        apiClient.getStrategies(tradingMode, true),
      ]);

      setDashboard(dashData);
      setRecentTrades(closedPos.slice(0, 10));
      setStrategies(strats);
      setLastFetchedAt(new Date());
      setLoading(false);

      // Fetch equity curve from analytics endpoint (same as PerformanceTab — handles
      // intraday intervals correctly with Unix timestamps)
      try {
        const perfData = await apiClient.getPerformanceAnalytics(tradingMode, '3M', iv);
        if (perfData?.equity_curve?.length) {
          setEquityCurveData(
            (perfData.equity_curve as Array<{ timestamp: string; equity: number; drawdown?: number; realized?: number }>).map(p => ({
              date: p.timestamp,
              equity: p.equity,
              realized: p.realized ?? undefined,
            }))
          );
        } else {
          // Fallback to dashboard equity curve
          setEquityCurveData(dashData?.equity_curve ?? []);
        }
      } catch {
        setEquityCurveData(dashData?.equity_curve ?? []);
      }

      // Fetch SPY benchmark (non-blocking)
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
  }, [tradingMode, equityPeriod, equityInterval]);

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
    () => calcReturnsFromEquityCurve(
      // Use the analytics equity curve (same source as the chart), filtered to daily points only.
      // This guarantees the left-panel returns match exactly what the chart shows.
      equityCurveData.filter((d: any) => String(d.date).length === 10)
    ),
    [equityCurveData],
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
    const sharpe = d.quick_stats?.sharpe_30d != null
      ? d.quick_stats.sharpe_30d.toFixed(2)
      : d.quick_stats?.win_rate_30d != null
      ? (d.quick_stats.win_rate_30d / 100 * 2).toFixed(2)
      : 'N/A';
    return [
      {
        label: 'Equity',
        value: d.account_equity ?? 0,
        trend: 'neutral' as const,
      },
      {
        label: 'Daily P&L',
        value: pnl,
        trend: pnl > 0 ? 'up' as const : pnl < 0 ? 'down' as const : 'neutral' as const,
      },
      {
        label: 'Daily %',
        value: `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`,
        trend: pnlPct > 0 ? 'up' as const : pnlPct < 0 ? 'down' as const : 'neutral' as const,
      },
      {
        label: 'Unrealized',
        value: d.total_unrealized_pnl ?? 0,
        trend: (d.total_unrealized_pnl ?? 0) > 0 ? 'up' as const : (d.total_unrealized_pnl ?? 0) < 0 ? 'down' as const : 'neutral' as const,
      },
      {
        label: 'Win Rate',
        value: `${(d.quick_stats?.win_rate_30d ?? 0).toFixed(1)}%`,
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
      {
        label: 'Cash',
        value: d.available_cash ?? 0,
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

  // ── Header actions ─────────────────────────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <TearSheetGenerator />
      <button
        onClick={refresh}
        className={cn('p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors')}
        title="Refresh"
      >
        <RefreshCw size={14} className={cn(isRefreshing && 'animate-spin')} />
      </button>
    </div>
  );

  const modeLabel = tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading';

  // ── Center panel toolbar actions ───────────────────────────────────────
  const centerToolbar = (
    <div className="flex items-center gap-2">
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
    <div className="flex flex-col h-full">
      <PanelHeader title="Metrics" panelId="overview-metrics" onRefresh={refresh}>
        <div className="flex flex-col gap-1.5 p-1.5">
          {/* Compact Metric Row */}
          <CompactMetricRow metrics={compactMetrics} className="flex-wrap h-auto min-h-0 max-h-none" />

          {/* Multi-Timeframe View */}
          <div>
            <div className="text-xs font-medium text-gray-500 tracking-wide mb-1.5">
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
            <div className="text-xs font-medium text-gray-500 tracking-wide mb-1.5">
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
    <div ref={centerPanelRef} className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Equity Curve" panelId="overview-equity" actions={centerToolbar}>
        <div className="p-2">
          {d && equityCurveData.length ? (
            <AutoHeightChart
              containerRef={centerPanelRef}
              equityData={equityCurveData.map((p: any) => ({
                date: typeof p.date === 'string' ? p.date : (p.timestamp ?? ''),
                equity: p.portfolio ?? p.equity ?? p.value ?? 0,
                realized: p.realized,
              }))}
              dailyEquity={(dashboard?.equity_curve ?? [])
                .filter((d: any) => /^\d{4}-\d{2}-\d{2}$/.test(String(d.date)))
                .map((d: any) => ({ date: d.date, equity: d.equity, realized: d.realized }))}
              spyData={showBenchmark ? spyData : undefined}
              period={equityPeriod}
              onPeriodChange={setEquityPeriod}
              interval={equityInterval}
              onIntervalChange={(iv) => { setEquityInterval(iv); fetchAll(iv); }}
            />
          ) : (
            <ChartSkeleton height={480} />
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Right Panel Content ────────────────────────────────────────────────
  const rightPanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Activity" panelId="overview-activity" onRefresh={refresh}>
        <div className="flex flex-col h-full min-h-0 overflow-hidden">
          <ActivityPanel initialStrategies={strategies} />
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
          compact={true}
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
        compact={true}
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
});
