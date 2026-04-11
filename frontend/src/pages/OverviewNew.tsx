import { type FC, useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  DollarSign, TrendingUp, TrendingDown, BarChart3,
  ArrowRight,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { RefreshButton } from '../components/ui/RefreshButton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { DataSection, PageSkeleton, MetricGridSkeleton, ChartSkeleton, TableSkeleton } from '../components/ui/skeleton';
import { MetricCard } from '../components/trading/MetricCard';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
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
  // Cumulative counts: each stage includes strategies that have passed through it
  // PROPOSED → BACKTESTED → ACTIVE (DEMO/LIVE) → RETIRED
  let proposed = 0, backtested = 0, active = 0, retired = 0;
  for (const s of strategies) {
    const status = s.status?.toUpperCase();
    if (status === 'PROPOSED') { proposed++; }
    else if (status === 'BACKTESTED') { proposed++; backtested++; }
    else if (status === 'DEMO' || status === 'LIVE') { proposed++; backtested++; active++; }
    else if (status === 'RETIRED') { proposed++; backtested++; retired++; }
    // PAUSED/INVALID strategies that were once active
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
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [equityPeriod, setEquityPeriod] = useState('3M');

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

  // Daily P&L from pnl_periods
  const dailyPnl = dashboard?.pnl_periods?.find(p => p.label === 'Today');

  // Sharpe & max drawdown from quick_stats / drawdown_data
  const maxDrawdown = useMemo(() => {
    if (!dashboard?.drawdown_data?.length) return 0;
    return Math.min(...dashboard.drawdown_data.map(d => d.drawdown_pct));
  }, [dashboard?.drawdown_data]);

  // Handle period click from MultiTimeframeView
  const handlePeriodClick = useCallback((period: string) => {
    // Map MTF periods to equity curve periods
    const periodMap: Record<string, string> = {
      '1D': '1W', '1W': '1W', '1M': '1M', '3M': '3M',
      '6M': '6M', 'YTD': '1Y', '1Y': '1Y', 'ALL': 'ALL',
    };
    setEquityPeriod(periodMap[period] || '3M');
  }, []);

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  const d = dashboard;

  return (
    <DashboardLayout onLogout={onLogout}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto space-y-6 relative"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-1">
              ◆ Command Centre
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-gray-400 text-sm">
                {tradingMode === 'DEMO' ? '📊 Demo Mode' : '💰 Live Trading'} — Real-time portfolio intelligence
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <TearSheetGenerator />
            <RefreshButton loading={isRefreshing} label="Refresh" onClick={refresh} />
          </div>
        </div>

        {/* 1. Hero: Full-width EquityCurveChart with SPY benchmark */}
        <DataSection
          isLoading={!d}
          error={error}
          skeleton={<ChartSkeleton height={400} />}
          onRetry={refresh}
        >
          {d && (
            <Card>
              <CardContent className="pt-4">
                <EquityCurveChart
                  equityData={d.equity_curve}
                  spyData={spyData}
                  period={equityPeriod}
                  onPeriodChange={setEquityPeriod}
                  height={380}
                />
              </CardContent>
            </Card>
          )}
        </DataSection>

        {/* 2. MultiTimeframeView row */}
        <DataSection
          isLoading={!d}
          error={null}
          skeleton={<div className="h-14 bg-muted animate-pulse rounded-md" />}
          onRetry={refresh}
        >
          <MultiTimeframeView
            returns={multiTimeframeReturns}
            onPeriodClick={handlePeriodClick}
          />
        </DataSection>

        {/* 3. 4-column Metric Grid */}
        <DataSection
          isLoading={!d}
          error={null}
          skeleton={<MetricGridSkeleton columns={4} />}
          onRetry={refresh}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Total Equity"
              value={d?.account_equity ?? 0}
              format="currency"
              icon={DollarSign}
              tooltip="Total account equity including unrealized P&L"
            />
            <MetricCard
              label="Daily P&L"
              value={dailyPnl?.pnl_absolute ?? 0}
              change={dailyPnl?.pnl_percent ?? 0}
              trend={(dailyPnl?.pnl_absolute ?? 0) > 0 ? 'up' : (dailyPnl?.pnl_absolute ?? 0) < 0 ? 'down' : 'neutral'}
              format="currency"
              icon={(dailyPnl?.pnl_absolute ?? 0) >= 0 ? TrendingUp : TrendingDown}
              tooltip="Today's profit/loss (absolute and percentage)"
            />
            <MetricCard
              label="Sharpe (30d)"
              value={d?.quick_stats?.win_rate_30d != null ? (d.quick_stats.win_rate_30d / 100 * 2).toFixed(2) : 'N/A'}
              format="text"
              icon={BarChart3}
              tooltip="Approximate 30-day Sharpe ratio"
            />
            <MetricCard
              label="Max Drawdown"
              value={maxDrawdown}
              format="percentage"
              trend={maxDrawdown < -5 ? 'down' : 'neutral'}
              icon={TrendingDown}
              tooltip="Maximum peak-to-trough drawdown over the displayed period"
            />
          </div>
        </DataSection>

        {/* 4. 2-column layout: Position summary + Recent trades */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Left: Position summary by asset class */}
          <DataSection
            isLoading={!d}
            error={null}
            skeleton={<TableSkeleton rows={4} columns={3} />}
            onRetry={refresh}
          >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Positions by Asset Class
                </CardTitle>
              </CardHeader>
              <CardContent>
                {assetClassSummary.length > 0 ? (
                  <div className="space-y-2">
                    {assetClassSummary.map((ac) => (
                      <div key={ac.assetClass} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-200">{ac.assetClass}</span>
                          <span className="text-xs text-muted-foreground font-mono">({ac.count})</span>
                        </div>
                        <span className={cn(
                          'text-sm font-mono font-semibold',
                          ac.totalPnl > 0 ? 'text-accent-green' : ac.totalPnl < 0 ? 'text-accent-red' : 'text-gray-400',
                        )}>
                          {ac.totalPnl >= 0 ? '+' : ''}{formatCurrency(ac.totalPnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-6">No open positions</p>
                )}
              </CardContent>
            </Card>
          </DataSection>

          {/* Right: Recent trades (last 10 closed positions) */}
          <DataSection
            isLoading={!d}
            error={null}
            skeleton={<TableSkeleton rows={5} columns={4} />}
            onRetry={refresh}
          >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Recent Trades
                </CardTitle>
              </CardHeader>
              <CardContent>
                {recentTrades.length > 0 ? (
                  <div className="space-y-1.5">
                    {recentTrades.map((trade) => (
                      <div key={trade.id} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-sm font-mono font-semibold text-gray-200 truncate">{trade.symbol}</span>
                          <span className={cn(
                            'text-[10px] font-mono px-1 py-0.5 rounded',
                            trade.side === 'BUY' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400',
                          )}>
                            {trade.side}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className={cn(
                            'text-sm font-mono font-semibold',
                            (trade.realized_pnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red',
                          )}>
                            {(trade.realized_pnl ?? 0) >= 0 ? '+' : ''}{formatCurrency(trade.realized_pnl ?? 0)}
                          </span>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {trade.closed_at ? formatDate(trade.closed_at, 'MMM d') : '—'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-6">No recent trades</p>
                )}
              </CardContent>
            </Card>
          </DataSection>
        </div>

        {/* 5. Strategy Pipeline */}
        <DataSection
          isLoading={!d}
          error={null}
          skeleton={<div className="h-20 bg-muted animate-pulse rounded-md" />}
          onRetry={refresh}
        >
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Strategy Pipeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center gap-2 flex-wrap">
                {PIPELINE_STAGES.map((stage, i) => (
                  <div key={stage.key} className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/strategies?status=${stage.filter}`)}
                      className={cn(
                        'flex flex-col items-center justify-center rounded-lg border px-5 py-3 min-w-[100px] transition-all',
                        'hover:brightness-125 cursor-pointer',
                        stage.bg, stage.border,
                      )}
                    >
                      <span className={cn('text-2xl font-bold font-mono', stage.color)}>
                        {strategyCounts[stage.key] ?? 0}
                      </span>
                      <span className="text-[10px] text-muted-foreground mt-0.5">
                        {stage.label}
                      </span>
                    </button>
                    {i < PIPELINE_STAGES.length - 1 && (
                      <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </DataSection>
      </motion.div>
    </DashboardLayout>
  );
};
