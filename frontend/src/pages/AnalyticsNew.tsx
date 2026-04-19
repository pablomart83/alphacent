import { type FC, useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, Activity, Download, FileText,
  Search, ArrowUpDown, Target, Zap, RefreshCw
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { DataTable } from '../components/trading/DataTable';
import { SectionLabel } from '../components/ui/SectionLabel';
import { PerformanceTab } from './analytics/PerformanceTab';
import { MetricGrid } from '../components/ui/MetricGrid';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent } from '../components/ui/tabs';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/Badge';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '../lib/utils';
import { classifyError } from '../lib/errors';
import type { TradeJournalPattern } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { SVGBarChart } from '../components/charts/SVGBarChart';
import { TvChart } from '../components/charts/TvChart';
import { usePolling } from '../hooks/usePolling';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import type { RollingStatsData, AttributionData, TearSheetData, TCAData } from '../types/analytics';
import { RollingStatisticsTab, PerformanceAttributionTab, TearSheetTab, TCATab } from './analytics';
import { TearSheetGenerator } from '../components/pdf/TearSheetGenerator';

interface AnalyticsNewProps {
  onLogout: () => void;
}

interface PerformanceMetrics {
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  equity_curve: Array<{ date: string; value: number; benchmark?: number }>;
  drawdown_curve: Array<{ date: string; drawdown: number }>;
  returns_distribution: Array<{ range: string; count: number }>;
}

interface StrategyAttribution {
  strategy_id: string;
  strategy_name: string;
  template?: string;
  regime?: string;
  total_return: number;
  contribution_percent: number;
  sharpe_ratio: number;
  trades: number;
  win_rate: number;
}

interface TradeAnalytics {
  win_loss_distribution: Array<{ type: string; count: number; value: number }>;
  holding_periods: Array<{ range: string; count: number }>;
  pnl_by_hour: Array<{ hour: number; pnl: number }>;
  pnl_by_day: Array<{ day: string; pnl: number }>;
  trade_statistics: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    avg_holding_period: number;
    best_trade: number;
    worst_trade: number;
  };
}

interface RegimeAnalysis {
  performance_by_regime: Array<{
    regime: string;
    return: number;
    sharpe: number;
    trades: number;
    win_rate: number;
  }>;
  regime_transitions: Array<{
    date: string;
    from_regime: string;
    to_regime: string;
  }>;
  strategy_regime_performance: Array<{
    strategy: string;
    trending_up: number;
    trending_down: number;
    ranging: number;
    volatile: number;
  }>;
  current_regimes: Record<string, {
    regime: string;
    confidence: number;
    data_quality: string;
    change_20d: number;
    change_50d: number;
    atr_ratio: number;
    symbols: string[];
  }>;
  market_context: Record<string, any>;
  crypto_cycle: Record<string, any>;
  carry_rates: Record<string, any>;
}

interface TradeJournalEntry {
  id: number;
  trade_id: string;
  strategy_id: string;
  strategy_name?: string;
  symbol: string;
  entry_time: string;
  entry_price: number;
  entry_size: number;
  entry_reason: string;
  exit_time?: string;
  exit_price?: number;
  exit_reason?: string;
  pnl?: number;
  pnl_percent?: number;
  hold_time_hours?: number;
  max_adverse_excursion?: number;
  max_favorable_excursion?: number;
  market_regime?: string;
  sector?: string;
  conviction_score?: number;
  ml_confidence?: number;
}

interface TradeJournalPatterns {
  best_patterns: Array<TradeJournalPattern>;
  worst_patterns: Array<TradeJournalPattern>;
  recommendations: Array<any>;
}

/** Small inline scatter plot with ResizeObserver — used for MAE vs MFE */
const MaeMfeScatter: FC<{
  scatterData: Array<{ max_adverse_excursion?: number; max_favorable_excursion?: number; pnl?: number }>;
}> = ({ scatterData }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [svgW, setSvgW] = useState(500);
  const svgH = 350;
  const m = { top: 20, right: 20, bottom: 40, left: 50 };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const w = Math.round(e.contentRect.width);
        if (w > 0) setSvgW(w);
      }
    });
    ro.observe(el);
    setSvgW(el.clientWidth || 500);
    return () => ro.disconnect();
  }, []);

  const maxMAE = Math.max(...scatterData.map(t => Math.abs(t.max_adverse_excursion || 0)), 1);
  const maxMFE = Math.max(...scatterData.map(t => Math.abs(t.max_favorable_excursion || 0)), 1);
  const cW = svgW - m.left - m.right;
  const cH = svgH - m.top - m.bottom;

  return (
    <div ref={ref} className="relative w-full" style={{ height: svgH }}>
      <svg width={svgW} height={svgH}>
        <line x1={m.left} y1={m.top} x2={m.left} y2={svgH - m.bottom} stroke="#374151" />
        <line x1={m.left} y1={svgH - m.bottom} x2={svgW - m.right} y2={svgH - m.bottom} stroke="#374151" />
        <text x={svgW / 2} y={svgH - 5} textAnchor="middle" fill="#9ca3af" fontSize={11} fontFamily="'JetBrains Mono', monospace">MAE (%)</text>
        <text x={12} y={svgH / 2} textAnchor="middle" fill="#9ca3af" fontSize={11} fontFamily="'JetBrains Mono', monospace" transform={`rotate(-90, 12, ${svgH / 2})`}>MFE (%)</text>
        {scatterData.map((t, i) => {
          const x = m.left + (Math.abs(t.max_adverse_excursion || 0) / maxMAE) * cW;
          const y = m.top + cH - (Math.abs(t.max_favorable_excursion || 0) / maxMFE) * cH;
          const isWin = t.pnl && t.pnl > 0;
          return <circle key={i} cx={x} cy={y} r={4} fill={isWin ? '#10b981' : '#ef4444'} fillOpacity={0.6} />;
        })}
      </svg>
    </div>
  );
};

export const AnalyticsNew: FC<AnalyticsNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<'1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL'>('3M');
  const [equityInterval, setEquityInterval] = useState<'1d' | '4h' | '1h'>('1d');
  const [performanceMetrics, setPerformanceMetrics] = useState<PerformanceMetrics | null>(null);
  const [strategyAttribution, setStrategyAttribution] = useState<StrategyAttribution[]>([]);
  const [tradeAnalytics, setTradeAnalytics] = useState<TradeAnalytics | null>(null);
  const [regimeAnalysis, setRegimeAnalysis] = useState<RegimeAnalysis | null>(null);
  const [strategySearch, setStrategySearch] = useState('');
  const [templateFilter, setTemplateFilter] = useState<string>('all');
  const [regimeFilter, setRegimeFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('contribution');
  
  // Alpha Edge state
  const [fundamentalStats, setFundamentalStats] = useState<any>(null);
  const [mlStats, setMLStats] = useState<any>(null);
  const [convictionDistribution, setConvictionDistribution] = useState<any>(null);
  const [templatePerformance, setTemplatePerformance] = useState<any[]>([]);
  const [costSavings, setCostSavings] = useState<any>(null);

  // Trade Journal state
  const [tradeJournalEntries, setTradeJournalEntries] = useState<TradeJournalEntry[]>([]);
  const [tradeJournalPatterns, setTradeJournalPatterns] = useState<TradeJournalPatterns | null>(null);

  // Rolling Statistics state
  const [rollingStats, setRollingStats] = useState<RollingStatsData | null>(null);
  const [rollingStatsLoading, setRollingStatsLoading] = useState(false);
  const [rollingStatsError, setRollingStatsError] = useState<string | null>(null);
  const [rollingWindow, setRollingWindow] = useState<number>(30);

  // Performance Attribution state
  const [perfAttribution, setPerfAttribution] = useState<AttributionData | null>(null);
  const [perfAttributionLoading, setPerfAttributionLoading] = useState(false);
  const [perfAttributionError, setPerfAttributionError] = useState<string | null>(null);
  const [attributionGroupBy, setAttributionGroupBy] = useState<'sector' | 'asset_class'>('sector');

  // Tear Sheet state
  const [tearSheet, setTearSheet] = useState<TearSheetData | null>(null);
  const [tearSheetLoading, setTearSheetLoading] = useState(false);
  const [tearSheetError, setTearSheetError] = useState<string | null>(null);

  // Stress tests state (Sprint 7.2)
  const [stressTests, setStressTests] = useState<any | null>(null);
  const [stressTestsLoading, setStressTestsLoading] = useState(false);
  const [stressTestsError, setStressTestsError] = useState<string | null>(null);

  // R-Multiples state (Sprint 7.1)
  const [rMultiples, setRMultiples] = useState<any | null>(null);

  // TCA state
  const [tcaData, setTcaData] = useState<TCAData | null>(null);
  const [tcaLoading, setTcaLoading] = useState(false);
  const [tcaError, setTcaError] = useState<string | null>(null);
  const [journalFilters, setJournalFilters] = useState({
    strategy_id: '',
    symbol: '',
    start_date: '',
    end_date: '',
    regime: '',
    outcome: 'all' as 'all' | 'win' | 'loss',
  });
  const [journalSortBy, setJournalSortBy] = useState<string>('entry_time');
  const [journalSortOrder, setJournalSortOrder] = useState<'asc' | 'desc'>('desc');
  const [activeTab, setActiveTab] = useState<string>('performance');
  const [refreshing, setRefreshing] = useState(false);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Performance Stats state (11.10.15)
  const [perfStats, setPerfStats] = useState<{
    monthly_returns: Array<{ year: number; month: number; return_pct: number; month_name: string }>;
    win_rate_by_day: Record<string, number>;
    win_rate_by_hour: Record<string, number>;
    winners_vs_losers: Record<string, any>;
    expectancy: number;
    profit_factor: number;
    equity_curve: Array<{ date: string; portfolio: number; benchmark: number }>;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    gross_profit: number;
    gross_loss: number;
    total_expectancy: number;
    total_expectancy_note: string;
  } | null>(null);

  // CIO Dashboard state (institutional-grade metrics)
  const [cioDashboard, setCIODashboard] = useState<{
    calmar_ratio: number;
    cagr: number;
    information_ratio: number;
    total_realized_pnl: number;
    total_unrealized_pnl: number;
    total_pnl: number;
    daily_pnl_table: Array<{
      date: string; starting_equity: number; ending_equity: number;
      daily_pnl: number; daily_pnl_pct: number; cumulative_pnl: number;
      cumulative_pnl_pct: number; realized_pnl: number; unrealized_pnl: number;
      trades_closed: number;
    }>;
    current_drawdown_pct: number;
    max_drawdown_pct: number;
    drawdown_duration_days: number;
    last_equity_high_date: string | null;
    current_streak: number;
    longest_win_streak: number;
    longest_loss_streak: number;
    avg_entry_slippage_pct: number;
    avg_exit_slippage_pct: number;
    total_slippage_cost: number;
    strategies_proposed_30d: number;
    strategies_activated_30d: number;
    strategies_retired_30d: number;
    avg_strategy_lifespan_days: number;
    active_strategy_count: number;
    // Pipeline health
    proposal_to_activation_rate: number;
    // Retirement analysis
    retired_profitable: number;
    retired_unprofitable: number;
    retired_total_pnl: number;
    retirement_reasons: Record<string, number>;
    // Active strategy health
    active_profitable: number;
    active_unprofitable: number;
    active_total_unrealized: number;
    avg_active_strategy_pnl: number;
    // Trade quality
    total_trades_closed: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    profit_factor: number;
    avg_hold_time_hours: number;
    // Open position stats
    total_open_positions: number;
    open_winning: number;
    open_losing: number;
    open_win_rate: number;
    combined_win_rate: number;
    // Closure analysis
    closure_reasons: Record<string, number>;
  } | null>(null);

  const fetchAnalyticsData = useCallback(async (tabOverride?: string) => {
    if (!tradingMode) return;
    const currentTab = tabOverride || activeTab;
    
    try {
      if (!performanceMetrics) setLoading(true);  // Only show skeleton on first load
      setError(null);
      
      // Phase 1: Core metrics — skip if data was fetched recently (within 60s)
      // Tab switches should NOT re-fetch these heavy endpoints
      const now = new Date();
      const dataIsFresh = lastFetchedAt && (now.getTime() - lastFetchedAt.getTime()) < 60000
        && performanceMetrics && cioDashboard;
      
      if (!dataIsFresh) {
        const [perfAnalytics, perfStatsData, cioDashboardData, regimeDataPhase1] = await Promise.all([
          apiClient.getPerformanceAnalytics(tradingMode, period, equityInterval),
          apiClient.getPerformanceStats(tradingMode, period).catch(() => null),
          apiClient.getCIODashboard(tradingMode, period).catch(() => null),
          apiClient.getComprehensiveRegimeAnalysis().catch(() => null),
        ]);
        
        // Set core data and show the page immediately
        if (perfAnalytics) {
          setPerformanceMetrics({
            total_return: perfAnalytics.total_return || 0,
            sharpe_ratio: perfAnalytics.sharpe_ratio || 0,
            max_drawdown: perfAnalytics.max_drawdown || 0,
            win_rate: perfAnalytics.win_rate || 0,
            total_trades: perfAnalytics.total_trades || 0,
            avg_win: 0,
            avg_loss: 0,
            profit_factor: perfAnalytics.profit_factor || 0,
            equity_curve: (perfAnalytics.equity_curve || []).map((point: { timestamp: string; equity: number }) => ({
              date: point.timestamp,
              value: point.equity,
            })),
            drawdown_curve: (perfAnalytics.equity_curve || []).map((point: { timestamp: string; drawdown: number }) => ({
              date: point.timestamp,
              drawdown: point.drawdown
            })),
            returns_distribution: Object.entries(perfAnalytics.returns_distribution || {}).map(([range, count]) => ({
              range,
              count: count as number
            })),
          });
        }
        if (perfStatsData) setPerfStats(perfStatsData);
        if (cioDashboardData) setCIODashboard(cioDashboardData);
        
        if (regimeDataPhase1 && typeof regimeDataPhase1 === 'object') {
          setRegimeAnalysis({
            performance_by_regime: (regimeDataPhase1.performance_by_regime || []).map((item: any) => ({
              regime: item.regime || 'Unknown',
              return: item.total_return || 0,
              sharpe: item.sharpe || 0,
              trades: item.trades || 0,
              win_rate: item.win_rate || 0,
            })),
            regime_transitions: regimeDataPhase1.regime_transitions || [],
            strategy_regime_performance: regimeDataPhase1.strategy_regime_performance || [],
            current_regimes: regimeDataPhase1.current_regimes || {},
            market_context: regimeDataPhase1.market_context || {},
            crypto_cycle: regimeDataPhase1.crypto_cycle || {},
            carry_rates: regimeDataPhase1.carry_rates || {},
          });
        }
        
        setLastFetchedAt(new Date());
      }
      
      // Page is now visible with core metrics
      setLoading(false);
      
      // Phase 2: Tab-specific data — fetch in background, don't block the page
      let attribution: any[] = [];
      let tradeData: any = null;
      let fundStats: any = null;
      let mlFilterStats: any = null;
      let convictionDist: any = null;
      let templatePerf: any[] = [];
      let txCostSavings: any = null;
      
      if (currentTab === 'performance' || currentTab === 'attribution') {
        attribution = await apiClient.getStrategyAttribution(tradingMode, period).catch(() => []);
      }
      if (currentTab === 'performance' || currentTab === 'trades') {
        tradeData = await apiClient.getTradeAnalytics(tradingMode, period).catch(() => null);
      }
      if (currentTab === 'regime') {
        // Regime data is fetched in Phase 1 — no additional fetch needed
      }
      if (currentTab === 'alpha-edge') {
        [fundStats, mlFilterStats, convictionDist, templatePerf, txCostSavings] = await Promise.all([
          apiClient.getFundamentalFilterStats(tradingMode, period).catch(() => null),
          apiClient.getMLFilterStats(tradingMode, period).catch(() => null),
          apiClient.getConvictionDistribution(tradingMode, period).catch(() => null),
          apiClient.getTemplatePerformance(tradingMode, period).catch(() => []),
          apiClient.getTransactionCostSavings(tradingMode, period).catch(() => null),
        ]);
      }

      // New analytics tabs — fetch independently
      if (currentTab === 'rolling-statistics') {
        setRollingStatsLoading(true);
        setRollingStatsError(null);
        try {
          const rs = await apiClient.getRollingStatistics(tradingMode, period, rollingWindow);
          setRollingStats(rs);
        } catch (e: any) {
          setRollingStatsError(e?.message || 'Failed to load rolling statistics');
        } finally {
          setRollingStatsLoading(false);
        }
      }
      if (currentTab === 'perf-attribution') {
        setPerfAttributionLoading(true);
        setPerfAttributionError(null);
        try {
          const pa = await apiClient.getPerformanceAttribution(tradingMode, period, attributionGroupBy);
          setPerfAttribution(pa);
        } catch (e: any) {
          setPerfAttributionError(e?.message || 'Failed to load performance attribution');
        } finally {
          setPerfAttributionLoading(false);
        }
      }
      if (currentTab === 'tear-sheet') {
        setTearSheetLoading(true);
        setTearSheetError(null);
        try {
          const [ts, rm] = await Promise.all([
            apiClient.getTearSheetData(tradingMode, period),
            apiClient.get(`/analytics/r-multiples?mode=${tradingMode}`).catch(() => null),
          ]);
          setTearSheet(ts);
          if (rm) setRMultiples(rm);
        } catch (e: any) {
          setTearSheetError(e?.message || 'Failed to load tear sheet data');
        } finally {
          setTearSheetLoading(false);
        }
      }
      if (currentTab === 'tca') {
        setTcaLoading(true);
        setTcaError(null);
        try {
          const tca = await apiClient.getTCAData(tradingMode, period);
          setTcaData(tca);
        } catch (e: any) {
          setTcaError(e?.message || 'Failed to load TCA data');
        } finally {
          setTcaLoading(false);
        }
      }

      if (currentTab === 'stress-tests') {
        setStressTestsLoading(true);
        setStressTestsError(null);
        try {
          const data = await apiClient.get('/analytics/stress-tests');
          setStressTests(data);
        } catch (e: any) {
          setStressTestsError(e?.message || 'Failed to load stress tests');
        } finally {
          setStressTestsLoading(false);
        }
      }
      
      // Set tab-specific data (Phase 2 results)
      if (attribution && Array.isArray(attribution)) {
        setStrategyAttribution(attribution.map((item: any) => ({
          strategy_id: item.strategy_id || '',
          strategy_name: item.strategy_name || 'Unknown',
          template: undefined,
          regime: undefined,
          total_return: item.total_return || 0,
          contribution_percent: item.contribution_percent || 0,
          sharpe_ratio: item.sharpe_ratio || 0,
          trades: item.total_trades || 0,
          win_rate: item.win_rate || 0,
        })));
      }
      
      if (tradeData) {
        const holdingPeriods = [
          { range: '< 1 day', count: 0 },
          { range: '1-3 days', count: 0 },
          { range: '3-7 days', count: 0 },
          { range: '1-2 weeks', count: 0 },
          { range: '2+ weeks', count: 0 },
        ];
        const avgHours = tradeData.avg_holding_time_hours || 0;
        if (avgHours > 0 && tradeData.total_trades > 0) {
          if (avgHours < 24) holdingPeriods[0].count = tradeData.total_trades;
          else if (avgHours < 72) holdingPeriods[1].count = tradeData.total_trades;
          else if (avgHours < 168) holdingPeriods[2].count = tradeData.total_trades;
          else if (avgHours < 336) holdingPeriods[3].count = tradeData.total_trades;
          else holdingPeriods[4].count = tradeData.total_trades;
        }

        setTradeAnalytics({
          win_loss_distribution: Object.entries(tradeData.win_loss_distribution || {}).map(([type, count]) => ({
            type: type.replace(/_/g, ' '),
            count: count as number,
            value: 0
          })),
          holding_periods: holdingPeriods,
          pnl_by_hour: Object.entries(tradeData.pnl_by_hour || {}).map(([hour, pnl]) => ({
            hour: parseInt(hour),
            pnl: pnl as number,
          })).sort((a, b) => a.hour - b.hour),
          pnl_by_day: Object.entries(tradeData.pnl_by_day || {}).map(([day, pnl]) => ({
            day,
            pnl: pnl as number,
          })),
          trade_statistics: {
            total_trades: tradeData.total_trades || 0,
            winning_trades: tradeData.winning_trades || 0,
            losing_trades: tradeData.losing_trades || 0,
            avg_holding_period: tradeData.avg_holding_time_hours ? tradeData.avg_holding_time_hours / 24 : 0,
            best_trade: tradeData.largest_win || 0,
            worst_trade: tradeData.largest_loss || 0,
          },
        });
      }
      
      if (fundStats) setFundamentalStats(fundStats);
      if (mlFilterStats) setMLStats(mlFilterStats);
      if (convictionDist) setConvictionDistribution(convictionDist);
      if (templatePerf && Array.isArray(templatePerf)) setTemplatePerformance(templatePerf);
      if (txCostSavings) setCostSavings(txCostSavings);
      
    } catch (error) {
      const classified = classifyError(error, 'analytics');
      console.error('Failed to fetch analytics data:', error);
      setError(classified.message);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, period, equityInterval, activeTab, rollingWindow, attributionGroupBy]);

  const fetchTradeJournalData = async () => {
    try {
      const filters: Record<string, string | boolean> = {};
      if (journalFilters.strategy_id) filters.strategy_id = journalFilters.strategy_id;
      if (journalFilters.symbol) filters.symbol = journalFilters.symbol;
      if (journalFilters.start_date) filters.start_date = journalFilters.start_date;
      if (journalFilters.end_date) filters.end_date = journalFilters.end_date;
      
      const [journalData, patternsData] = await Promise.all([
        apiClient.getTradeJournal(filters),
        apiClient.getTradeJournalPatterns(filters),
      ]);
      
      if (journalData && journalData.trades) {
        let entries = journalData.trades;
        if (journalFilters.regime) {
          entries = entries.filter((e: TradeJournalEntry) => e.market_regime === journalFilters.regime);
        }
        if (journalFilters.outcome !== 'all') {
          entries = entries.filter((e: TradeJournalEntry) => {
            if (journalFilters.outcome === 'win') return e.pnl && e.pnl > 0;
            if (journalFilters.outcome === 'loss') return e.pnl && e.pnl < 0;
            return true;
          });
        }
        entries.sort((a: TradeJournalEntry, b: TradeJournalEntry) => {
          const aVal = a[journalSortBy as keyof TradeJournalEntry];
          const bVal = b[journalSortBy as keyof TradeJournalEntry];
          if (aVal === undefined || aVal === null) return 1;
          if (bVal === undefined || bVal === null) return -1;
          if (journalSortOrder === 'asc') {
            return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
          } else {
            return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
          }
        });
        setTradeJournalEntries(entries);
      }
      if (patternsData) setTradeJournalPatterns(patternsData);
    } catch (error) {
      console.error('Failed to fetch trade journal data:', error);
      toast.error('Failed to load trade journal data');
    }
  };

  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchAnalyticsData,
    intervalMs: 120000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  useEffect(() => {
    if (!tradingModeLoading && tradingMode) {
      fetchAnalyticsData();
    }
  }, [period]);

  const handleTabChange = useCallback((tab: string) => {
    setActiveTab(tab);
    fetchAnalyticsData(tab);
  }, [fetchAnalyticsData]);

  useEffect(() => {
    if (!tradingModeLoading && tradingMode) {
      fetchTradeJournalData();
    }
  }, [journalFilters, journalSortBy, journalSortOrder]);

  const handleExportCSV = async () => {
    try {
      const blob = await apiClient.exportTradeJournal({
        start_date: journalFilters.start_date,
        end_date: journalFilters.end_date,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trade_journal_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success('Trade journal exported to CSV');
    } catch (error) {
      console.error('Failed to export CSV:', error);
      toast.error('Failed to export CSV');
    }
  };

  const handleGenerateMonthlyReport = () => {
    toast.success('Generating monthly report...');
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchAnalyticsData();
    if (activeTab === 'trade-journal') {
      await fetchTradeJournalData();
    }
    setRefreshing(false);
  };

  const filteredStrategies = strategyAttribution.filter(strategy => {
    if (!strategy || !strategy.strategy_name) return false;
    const matchesSearch = strategy.strategy_name.toLowerCase().includes(strategySearch.toLowerCase());
    const matchesTemplate = templateFilter === 'all' || strategy.template === templateFilter;
    const matchesRegime = regimeFilter === 'all' || strategy.regime === regimeFilter;
    return matchesSearch && matchesTemplate && matchesRegime;
  }).sort((a, b) => {
    switch (sortBy) {
      case 'contribution': return (b.contribution_percent || 0) - (a.contribution_percent || 0);
      case 'return': return (b.total_return || 0) - (a.total_return || 0);
      case 'sharpe': return (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0);
      case 'name': return (a.strategy_name || '').localeCompare(b.strategy_name || '');
      default: return 0;
    }
  });

  // ── CompactMetricRow metrics for the top of the page ──
  const compactMetrics: CompactMetric[] = useMemo(() => [
    {
      label: 'Total Return',
      value: `${(performanceMetrics?.total_return ?? 0) >= 0 ? '+' : ''}${(performanceMetrics?.total_return ?? 0).toFixed(2)}%`,
      trend: (performanceMetrics?.total_return ?? 0) >= 0 ? 'up' as const : 'down' as const,
    },
    {
      label: 'Sharpe',
      value: (performanceMetrics?.sharpe_ratio ?? 0).toFixed(2),
      trend: (performanceMetrics?.sharpe_ratio ?? 0) >= 1 ? 'up' as const : (performanceMetrics?.sharpe_ratio ?? 0) >= 0 ? 'neutral' as const : 'down' as const,
    },
    {
      label: 'Max DD',
      value: `${(performanceMetrics?.max_drawdown ?? 0).toFixed(2)}%`,
      trend: 'down' as const,
    },
    {
      label: 'Win Rate',
      value: `${(performanceMetrics?.win_rate ?? 0).toFixed(1)}%`,
      trend: (performanceMetrics?.win_rate ?? 0) >= 50 ? 'up' as const : 'down' as const,
    },
    {
      label: 'Profit Factor',
      value: (performanceMetrics?.profit_factor ?? 0).toFixed(2),
      trend: (performanceMetrics?.profit_factor ?? 0) >= 1.5 ? 'up' as const : (performanceMetrics?.profit_factor ?? 0) >= 1 ? 'neutral' as const : 'down' as const,
    },
    {
      label: 'Trades',
      value: String(performanceMetrics?.total_trades ?? 0),
      trend: 'neutral' as const,
    },
  ], [performanceMetrics]);

  // ── Header actions for PageTemplate ──
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <Select value={period} onValueChange={(value) => setPeriod(value as typeof period)}>
        <SelectTrigger className="w-[100px] h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1W">1 Week</SelectItem>
          <SelectItem value="1M">1 Month</SelectItem>
          <SelectItem value="3M">3 Months</SelectItem>
          <SelectItem value="6M">6 Months</SelectItem>
          <SelectItem value="1Y">1 Year</SelectItem>
          <SelectItem value="ALL">All Time</SelectItem>
        </SelectContent>
      </Select>
      <button onClick={handleExportCSV} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Export CSV">
        <Download className="h-3.5 w-3.5" />
      </button>
      <TearSheetGenerator />
      <button onClick={handleRefresh} disabled={refreshing} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Refresh">
        <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
      </button>
    </div>
  );

  const strategyColumns: ColumnDef<StrategyAttribution>[] = [
    {
      accessorKey: 'strategy_name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div>
          <div className="font-mono font-semibold text-sm">{row.original.strategy_name}</div>
          {row.original.template && (
            <Badge variant="outline" className="mt-1 text-xs">{row.original.template}</Badge>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'total_return',
      header: () => <div className="text-right">Return</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className={cn('font-mono font-semibold text-sm',
            (row.original.total_return || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
            {formatPercentage(row.original.total_return || 0)}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'contribution_percent',
      header: () => <div className="text-right">Contribution</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatPercentage(row.original.contribution_percent || 0)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'sharpe_ratio',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{(row.original.sharpe_ratio || 0).toFixed(2)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'trades',
      header: () => <div className="text-right">Trades</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{row.original.trades || 0}</span>
        </div>
      ),
    },
    {
      accessorKey: 'win_rate',
      header: () => <div className="text-right">Win Rate</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatPercentage(row.original.win_rate || 0)}</span>
        </div>
      ),
    },
  ];

  const regimeColumns: ColumnDef<RegimeAnalysis['performance_by_regime'][number]>[] = [
    {
      accessorKey: 'regime',
      header: 'Market Regime',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <div className={cn('w-2 h-2 rounded-full',
            row.original.regime === 'TRENDING_UP' && 'bg-accent-green',
            row.original.regime === 'TRENDING_DOWN' && 'bg-accent-red',
            row.original.regime === 'RANGING' && 'bg-blue-500',
            row.original.regime === 'VOLATILE' && 'bg-yellow-500')} />
          <span className="font-mono text-sm">{row.original.regime}</span>
        </div>
      ),
    },
    {
      accessorKey: 'return',
      header: () => <div className="text-right">Return</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className={cn('font-mono font-semibold text-sm',
            (row.original.return || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
            {formatPercentage(row.original.return || 0)}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'sharpe',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{(row.original.sharpe || 0).toFixed(2)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'trades',
      header: () => <div className="text-right">Trades</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{row.original.trades || 0}</span>
        </div>
      ),
    },
    {
      accessorKey: 'win_rate',
      header: () => <div className="text-right">Win Rate</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatPercentage(row.original.win_rate || 0)}</span>
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Analytics" compact={true}>
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  if (error && !performanceMetrics) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Analytics" compact={true}>
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <Activity className="h-8 w-8 text-accent-red" />
            <div className="text-gray-400 font-mono">Failed to load analytics</div>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={() => fetchAnalyticsData()}>Retry</Button>
          </div>
        </PageTemplate>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Analytics"
        description={tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading'}
        actions={headerActions}
        compact={true}
      >
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}
          className="p-2 max-w-[1800px] mx-auto relative">
          <RefreshIndicator visible={pollingRefreshing && !loading} />

          {/* CompactMetricRow: total return, Sharpe, max DD, win rate, profit factor, trades */}
          <CompactMetricRow metrics={compactMetrics} className="mb-2" />

        {/* Standardized tab buttons — matches Strategies/Portfolio/Autonomous/Risk/Orders */}
        <div className="flex items-center px-1 min-h-[32px] max-h-[32px] shrink-0 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)] rounded-lg mb-2">
          <div className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide flex-1 min-w-0">
            {[
              { value: 'performance', label: 'Performance' },
              { value: 'attribution', label: 'Strategy Attribution' },
              { value: 'trades', label: 'Trade Analytics' },
              { value: 'regime', label: 'Regime Analysis' },
              { value: 'alpha-edge', label: 'Alpha Edge' },
              { value: 'trade-journal', label: 'Trade Journal' },
              { value: 'rolling-statistics', label: 'Rolling Statistics' },
              { value: 'perf-attribution', label: 'Attribution' },
              { value: 'tear-sheet', label: 'Tear Sheet' },
              { value: 'tca', label: 'TCA' },
              { value: 'stress-tests', label: 'Stress Tests' },
            ].map((tab) => (
              <button
                key={tab.value}
                onClick={() => handleTabChange(tab.value)}
                className={cn(
                  'px-3 py-1 text-[13px] font-medium rounded whitespace-nowrap transition-colors shrink-0',
                  activeTab === tab.value
                    ? 'bg-gray-700/60 text-gray-100'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/40'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-2">
          {/* Hidden TabsList — we use custom buttons above */}

          {/* ═══════════════════════════════════════════════════════════════
              PERFORMANCE TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="performance">
            <PerformanceTab
              performanceMetrics={performanceMetrics}
              cioDashboard={cioDashboard}
              perfStats={perfStats}
              regimeAnalysis={regimeAnalysis}
              period={period}
              setPeriod={setPeriod}
              equityInterval={equityInterval}
              setEquityInterval={setEquityInterval}
            />
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              ATTRIBUTION TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="attribution" className="space-y-3">
            <SectionLabel>Strategy Contribution</SectionLabel>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2">
              <div className="text-xs text-gray-500">
                Performance attribution by strategy • {filteredStrategies.length} of {strategyAttribution.length} strategies
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                  <Input placeholder="Search strategy..." value={strategySearch}
                    onChange={(e) => setStrategySearch(e.target.value)} className="pl-9 w-full sm:w-[200px] h-7 text-xs" />
                </div>
                <Select value={templateFilter} onValueChange={setTemplateFilter}>
                  <SelectTrigger className="w-full sm:w-[140px] h-7 text-xs">
                    <SelectValue placeholder="Template" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Templates</SelectItem>
                    <SelectItem value="RSI">RSI</SelectItem>
                    <SelectItem value="MACD">MACD</SelectItem>
                    <SelectItem value="Bollinger">Bollinger</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                  <SelectTrigger className="w-full sm:w-[140px] h-7 text-xs">
                    <SelectValue placeholder="Regime" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Regimes</SelectItem>
                    <SelectItem value="TRENDING_UP">Trending Up</SelectItem>
                    <SelectItem value="TRENDING_DOWN">Trending Down</SelectItem>
                    <SelectItem value="RANGING">Ranging</SelectItem>
                    <SelectItem value="VOLATILE">Volatile</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="w-full sm:w-[140px] h-7 text-xs">
                    <ArrowUpDown className="h-4 w-4 mr-2" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="contribution">Contribution</SelectItem>
                    <SelectItem value="return">Return</SelectItem>
                    <SelectItem value="sharpe">Sharpe</SelectItem>
                    <SelectItem value="name">Name</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {filteredStrategies.length > 0 ? (
              <div className="max-h-[600px] overflow-y-auto">
                <DataTable columns={strategyColumns} data={filteredStrategies} pageSize={20} showPagination={true} />
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500 text-xs">
                {strategySearch || templateFilter !== 'all' || regimeFilter !== 'all'
                  ? 'No strategies match your filters' : 'No strategy data available'}
              </div>
            )}

            <SectionLabel>Performance by Strategy</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}>
              <SVGBarChart
                data={filteredStrategies.slice(0, 10).map((s) => ({
                  label: s.strategy_name,
                  value: s.contribution_percent,
                }))}
                height={300}
                color="#10b981"
                horizontal
                formatValue={(v) => `${v.toFixed(2)}%`}
              />
            </motion.div>
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              TRADES TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="trades" className="space-y-3">
            <SectionLabel>Trade Metrics</SectionLabel>
            <MetricGrid items={[
              { label: 'Total Trades', value: tradeAnalytics?.trade_statistics?.total_trades || 0 },
              { label: 'Winning Trades', value: tradeAnalytics?.trade_statistics?.winning_trades || 0, color: 'text-[#22c55e]' },
              { label: 'Losing Trades', value: tradeAnalytics?.trade_statistics?.losing_trades || 0, color: 'text-[#ef4444]' },
            ]} cols={3} />

            <SectionLabel>Trade Distribution</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs text-gray-500 tracking-wide mb-2">Win/Loss Distribution</div>
                <SVGBarChart
                  data={(tradeAnalytics?.win_loss_distribution || []).map((d) => ({
                    label: d.type,
                    value: d.count,
                  }))}
                  height={250}
                  color="#3b82f6"
                  formatValue={(v) => String(Math.round(v))}
                />
              </div>

              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs text-gray-500 tracking-wide mb-2">Holding Periods</div>
                <SVGBarChart
                  data={(tradeAnalytics?.holding_periods || []).map((d) => ({
                    label: d.range,
                    value: d.count,
                  }))}
                  height={250}
                  color="#8b5cf6"
                  formatValue={(v) => String(Math.round(v))}
                />
              </div>
            </motion.div>

            <SectionLabel>P&L by Day of Week</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}>
              <SVGBarChart
                data={(tradeAnalytics?.pnl_by_day || []).map((d) => ({
                  label: d.day,
                  value: d.pnl,
                  color: d.pnl >= 0 ? '#10b981' : '#ef4444',
                }))}
                height={250}
                color="#f59e0b"
                formatValue={(v) => `$${v.toFixed(0)}`}
              />
            </motion.div>

            <SectionLabel>Trade Statistics</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}>
              <MetricGrid items={[
                { label: 'Avg Holding Period', value: `${(tradeAnalytics?.trade_statistics?.avg_holding_period || 0).toFixed(1)} days` },
                { label: 'Best Trade', value: formatCurrency(tradeAnalytics?.trade_statistics.best_trade || 0), color: 'text-[#22c55e]' },
                { label: 'Worst Trade', value: formatCurrency(tradeAnalytics?.trade_statistics.worst_trade || 0), color: 'text-[#ef4444]' },
              ]} cols={3} />
            </motion.div>
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              REGIME TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="regime" className="space-y-3">
            {/* Current Regimes by Asset Class */}
            {regimeAnalysis?.current_regimes && Object.keys(regimeAnalysis.current_regimes).length > 0 && (
              <>
                <SectionLabel>Current Market Regimes</SectionLabel>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(regimeAnalysis.current_regimes).map(([assetClass, data]) => (
                    <div key={assetClass} className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold capitalize">{assetClass}</span>
                        <Badge variant="outline" className="text-xs">{(data as any).confidence ? `${((data as any).confidence * 100).toFixed(0)}%` : ''}</Badge>
                      </div>
                      <p className="text-[13px] font-bold font-mono">{((data as any).regime || 'unknown').replace(/_/g, ' ')}</p>
                      <div className="text-xs text-gray-500 space-y-0.5">
                        <p>20d: <span className={((data as any).change_20d || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{((data as any).change_20d || 0).toFixed(1)}%</span></p>
                        <p>50d: <span className={((data as any).change_50d || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{((data as any).change_50d || 0).toFixed(1)}%</span></p>
                        <p>ATR: {((data as any).atr_ratio || 0).toFixed(2)}%</p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Macro Market Context */}
            {regimeAnalysis?.market_context && regimeAnalysis.market_context.vix && (
              <>
                <SectionLabel>Macro Market Context</SectionLabel>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
                  {[
                    { label: 'VIX', value: regimeAnalysis.market_context.vix?.toFixed(1), color: regimeAnalysis.market_context.vix > 25 ? 'text-accent-red' : regimeAnalysis.market_context.vix < 15 ? 'text-accent-green' : '' },
                    { label: 'Fed Funds', value: `${regimeAnalysis.market_context.fed_funds_rate?.toFixed(2)}%` },
                    { label: '10Y Treasury', value: `${regimeAnalysis.market_context.treasury_10y?.toFixed(2)}%` },
                    { label: 'Yield Curve', value: `${regimeAnalysis.market_context.yield_curve_slope?.toFixed(2)}%`, color: regimeAnalysis.market_context.yield_curve_slope < 0 ? 'text-accent-red' : 'text-accent-green' },
                    { label: 'Inflation', value: `${regimeAnalysis.market_context.inflation_rate?.toFixed(1)}%` },
                    { label: 'ISM PMI', value: regimeAnalysis.market_context.ism_pmi?.toFixed(1), color: regimeAnalysis.market_context.ism_pmi < 50 ? 'text-accent-red' : 'text-accent-green' },
                    { label: 'HY Spread', value: `${regimeAnalysis.market_context.hy_spread?.toFixed(2)}%` },
                    { label: 'Risk Regime', value: regimeAnalysis.market_context.risk_regime?.replace(/_/g, ' ') },
                    { label: 'Unemployment', value: `${regimeAnalysis.market_context.unemployment_rate?.toFixed(1)}%` },
                    { label: 'Fed Stance', value: regimeAnalysis.market_context.fed_stance },
                    { label: 'USD Index', value: regimeAnalysis.market_context.trade_weighted_dollar?.toFixed(1) },
                    { label: 'Macro Regime', value: regimeAnalysis.market_context.macro_regime?.replace(/_/g, ' ') },
                  ].map((item, idx) => (
                    <div key={idx} className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-2">
                      <p className="text-xs text-gray-500">{item.label}</p>
                      <p className={cn('text-[13px] font-bold font-mono', item.color || '')}>{item.value || 'N/A'}</p>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Crypto Cycle & Forex Carry */}
            <SectionLabel>Crypto Cycle & Forex Carry</SectionLabel>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {regimeAnalysis?.crypto_cycle && regimeAnalysis.crypto_cycle.phase && (
                <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                  <div className="text-xs text-gray-500 tracking-wide mb-2">Bitcoin Halving Cycle</div>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span>Phase</span>
                      <Badge variant="outline" className="font-mono text-xs">{regimeAnalysis.crypto_cycle.phase?.replace(/_/g, ' ')}</Badge>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span>Months Since Halving</span>
                      <span className="font-mono">{regimeAnalysis.crypto_cycle.months_since_halving}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span>Cycle Score</span>
                      <span className="font-mono">{regimeAnalysis.crypto_cycle.cycle_score}/100</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span>Recommendation</span>
                      <Badge className={cn('text-xs',
                        regimeAnalysis.crypto_cycle.recommendation === 'accumulate' ? 'bg-green-500/20 text-green-400' :
                        regimeAnalysis.crypto_cycle.recommendation === 'hold' ? 'bg-blue-500/20 text-blue-400' :
                        regimeAnalysis.crypto_cycle.recommendation === 'reduce' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-red-500/20 text-red-400'
                      )}>{regimeAnalysis.crypto_cycle.recommendation}</Badge>
                    </div>
                  </div>
                </div>
              )}

              {regimeAnalysis?.carry_rates && regimeAnalysis.carry_rates.carry && Object.keys(regimeAnalysis.carry_rates.carry).length > 0 && (
                <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                  <div className="text-xs text-gray-500 tracking-wide mb-2">Forex Carry Rates</div>
                  <div className="space-y-2">
                    {Object.entries(regimeAnalysis.carry_rates.carry).map(([pair, diff]) => (
                      <div key={pair} className="flex items-center justify-between p-1.5 bg-[var(--color-dark-surface)] rounded text-xs">
                        <span className="font-mono">{pair}</span>
                        <span className={cn('font-mono font-bold',
                          (diff as number) > 0 ? 'text-accent-green' : (diff as number) < 0 ? 'text-accent-red' : ''
                        )}>{(diff as number) > 0 ? '+' : ''}{(diff as number).toFixed(2)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Performance by Market Regime */}
            <SectionLabel>Performance by Market Regime</SectionLabel>
            {regimeAnalysis?.performance_by_regime && regimeAnalysis.performance_by_regime.length > 0 ? (
              <DataTable columns={regimeColumns} data={regimeAnalysis.performance_by_regime} pageSize={10} showPagination={false} />
            ) : (
              <div className="text-center py-12 text-gray-500 text-xs">No regime data available</div>
            )}

            {/* Regime Transition Timeline */}
            <SectionLabel>Regime Transition Timeline</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}>
              {regimeAnalysis?.regime_transitions && regimeAnalysis.regime_transitions.length > 0 ? (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {regimeAnalysis.regime_transitions.map((transition, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)] rounded-md">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-gray-500 font-mono">
                          {formatTimestamp(transition.date, { includeTime: false })}
                        </span>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">{transition.from_regime}</Badge>
                          <span className="text-gray-500">→</span>
                          <Badge variant="outline" className="text-xs">{transition.to_regime}</Badge>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 text-xs">No regime transitions recorded</div>
              )}
            </motion.div>

            {/* Strategy Performance by Regime */}
            <SectionLabel>Strategy Performance by Regime</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}>
              {regimeAnalysis?.strategy_regime_performance && regimeAnalysis.strategy_regime_performance.length > 0 ? (
                <div className="overflow-x-auto rounded-md border border-[var(--color-dark-border)]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)]">
                        <th className="text-left p-2 font-mono text-xs text-gray-500">Strategy</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Trending Up</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Trending Down</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Ranging</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Volatile</th>
                      </tr>
                    </thead>
                    <tbody>
                      {regimeAnalysis.strategy_regime_performance.map((row, idx) => (
                        <tr key={idx} className="border-b border-[var(--color-dark-border)]/50">
                          <td className="p-2 font-mono text-xs">{row.strategy}</td>
                          <td className={cn('p-2 font-mono text-xs text-right',
                            row.trending_up >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                            {formatPercentage(row.trending_up)}
                          </td>
                          <td className={cn('p-2 font-mono text-xs text-right',
                            row.trending_down >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                            {formatPercentage(row.trending_down)}
                          </td>
                          <td className={cn('p-2 font-mono text-xs text-right',
                            row.ranging >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                            {formatPercentage(row.ranging)}
                          </td>
                          <td className={cn('p-2 font-mono text-xs text-right',
                            row.volatile >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                            {formatPercentage(row.volatile)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 text-xs">No strategy regime data available</div>
              )}
            </motion.div>
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              ALPHA EDGE TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="alpha-edge" className="space-y-3">
            <SectionLabel>Filter Statistics</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }} className="grid grid-cols-1 md:grid-cols-2 gap-3">
              
              {/* Fundamental Filter Statistics */}
              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Fundamental Filter Statistics</div>
                {fundamentalStats ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Symbols Filtered</p>
                        <p className="text-[13px] font-bold font-mono">{fundamentalStats.symbols_filtered || 0}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Symbols Passed</p>
                        <p className="text-[13px] font-bold font-mono text-accent-green">
                          {fundamentalStats.symbols_passed || 0}
                        </p>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Pass Rate</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-[var(--color-dark-surface)] rounded-full h-2">
                          <div className="bg-accent-green h-2 rounded-full" 
                            style={{ width: `${fundamentalStats.pass_rate || 0}%` }} />
                        </div>
                        <span className="text-xs font-mono font-semibold">
                          {formatPercentage(fundamentalStats.pass_rate || 0)}
                        </span>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-2">Most Common Failure Reasons</p>
                      <div className="space-y-1">
                        {fundamentalStats.failure_reasons && Object.entries(fundamentalStats.failure_reasons)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 3)
                          .map(([reason, count]) => (
                            <div key={reason} className="flex justify-between text-xs">
                              <span className="text-gray-500 capitalize">
                                {reason.replace(/_/g, ' ')}
                              </span>
                              <span className="font-mono">{String(count)}</span>
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500 text-xs">No data available</div>
                )}
              </div>

              {/* ML Filter Statistics */}
              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">ML Filter Statistics</div>
                {mlStats ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Signals Filtered</p>
                        <p className="text-[13px] font-bold font-mono">{mlStats.signals_filtered || 0}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Signals Passed</p>
                        <p className="text-[13px] font-bold font-mono text-accent-green">
                          {mlStats.signals_passed || 0}
                        </p>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Average Confidence</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-[var(--color-dark-surface)] rounded-full h-2">
                          <div className="bg-blue-500 h-2 rounded-full" 
                            style={{ width: `${(mlStats.avg_confidence || 0) * 100}%` }} />
                        </div>
                        <span className="text-xs font-mono font-semibold">
                          {formatPercentage((mlStats.avg_confidence || 0) * 100)}
                        </span>
                      </div>
                    </div>
                    {mlStats.model_accuracy && (
                      <div>
                        <p className="text-xs text-gray-500 mb-2">Model Accuracy Metrics</p>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">Accuracy</span>
                            <span className="font-mono">{formatPercentage((mlStats.model_accuracy || 0) * 100)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">Precision</span>
                            <span className="font-mono">{formatPercentage((mlStats.model_precision || 0) * 100)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">Recall</span>
                            <span className="font-mono">{formatPercentage((mlStats.model_recall || 0) * 100)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">F1 Score</span>
                            <span className="font-mono">{formatPercentage((mlStats.model_f1_score || 0) * 100)}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500 text-xs">No data available</div>
                )}
              </div>
            </motion.div>

            {/* Conviction Score Distribution */}
            <SectionLabel>Conviction Score Distribution</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}>
              {convictionDistribution ? (
                <div className="space-y-3">
                  <MetricGrid items={[
                    { label: 'Average', value: convictionDistribution.avg_score?.toFixed(1) || '0' },
                    { label: 'Median', value: convictionDistribution.median_score?.toFixed(1) || '0' },
                    { label: 'Min', value: convictionDistribution.min_score?.toFixed(1) || '0' },
                    { label: 'Max', value: convictionDistribution.max_score?.toFixed(1) || '0' },
                  ]} cols={4} />
                  <SVGBarChart
                    data={(convictionDistribution.score_ranges || []).map((d: any) => ({
                      label: d.range,
                      value: d.count,
                    }))}
                    height={250}
                    color="#8b5cf6"
                    formatValue={(v) => String(Math.round(v))}
                  />
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 text-xs">No data available</div>
              )}
            </motion.div>

            {/* Template Performance */}
            <SectionLabel>Template Performance</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}>
              {templatePerformance && templatePerformance.length > 0 ? (
                <div className="overflow-x-auto rounded-md border border-[var(--color-dark-border)]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)]">
                        <th className="text-left p-2 font-mono text-xs text-gray-500">Template</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Trades</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Win Rate</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Return</th>
                        <th className="text-right p-2 font-mono text-xs text-gray-500">Sharpe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {templatePerformance.map((template, idx) => (
                        <tr key={idx} className="border-b border-[var(--color-dark-border)]/50">
                          <td className="p-2 font-mono text-xs">
                            <Badge variant="outline" className="text-xs">{template.template}</Badge>
                          </td>
                          <td className="p-2 font-mono text-xs text-right">{template.trades || 0}</td>
                          <td className="p-2 font-mono text-xs text-right">
                            {formatPercentage(template.win_rate || 0)}
                          </td>
                          <td className={cn('p-2 font-mono text-xs text-right font-semibold',
                            (template.total_return || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                            {formatPercentage(template.total_return || 0)}
                          </td>
                          <td className="p-2 font-mono text-xs text-right">
                            {(template.sharpe_ratio || 0).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 text-xs">No template data available</div>
              )}
            </motion.div>

            {/* Transaction Cost Savings */}
            <SectionLabel>Transaction Cost Savings</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}>
              {costSavings ? (
                <div className="space-y-3">
                  <MetricGrid items={[
                    { label: 'Before', value: formatCurrency(costSavings.before_costs || 0), color: 'text-[#ef4444]', sub: `${costSavings.trades_before || 0} trades` },
                    { label: 'After', value: formatCurrency(costSavings.after_costs || 0), color: 'text-[#22c55e]', sub: `${costSavings.trades_after || 0} trades` },
                    { label: 'Total Savings', value: formatCurrency(costSavings.total_savings || 0), color: 'text-blue-400', sub: `${formatPercentage(((costSavings.total_savings || 0) / (costSavings.before_costs || 1)) * 100)} reduction` },
                  ]} cols={3} />
                  <div>
                    <p className="text-xs text-gray-500 mb-2">Cost as % of Returns</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-[var(--color-dark-surface)] rounded-full h-3">
                        <div className="bg-blue-500 h-3 rounded-full" 
                          style={{ width: `${Math.min(100, costSavings.cost_as_percent_of_returns || 0)}%` }} />
                      </div>
                      <span className="text-xs font-mono font-semibold">
                        {formatPercentage(costSavings.cost_as_percent_of_returns || 0)}
                      </span>
                    </div>
                  </div>
                  <div className="pt-3 border-t border-[var(--color-dark-border)]">
                    <SVGBarChart
                      data={[
                        { label: 'Before', value: costSavings.before_costs || 0 },
                        { label: 'After', value: costSavings.after_costs || 0 },
                      ]}
                      height={200}
                      color="#3b82f6"
                      formatValue={(v) => `$${v.toFixed(0)}`}
                    />
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 text-xs">No cost data available</div>
              )}
            </motion.div>
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              TRADE JOURNAL TAB
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="trade-journal" className="space-y-3">
            <SectionLabel actions={
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleExportCSV} className="h-6 text-xs">
                  <Download className="h-3 w-3 mr-1" />
                  Export CSV
                </Button>
                <Button variant="outline" size="sm" onClick={handleGenerateMonthlyReport} className="h-6 text-xs">
                  <FileText className="h-3 w-3 mr-1" />
                  Monthly Report
                </Button>
              </div>
            }>Trade Journal</SectionLabel>
            <div className="text-xs text-gray-500 mb-2">
              Detailed trade history with filters • {tradeJournalEntries.length} trades
            </div>

            {/* Filters */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 mb-2">
              <Input
                placeholder="Strategy ID..."
                value={journalFilters.strategy_id}
                onChange={(e) => setJournalFilters({ ...journalFilters, strategy_id: e.target.value })}
                className="h-7 text-xs"
              />
              <Input
                placeholder="Symbol..."
                value={journalFilters.symbol}
                onChange={(e) => setJournalFilters({ ...journalFilters, symbol: e.target.value })}
                className="h-7 text-xs"
              />
              <Select
                value={journalFilters.regime || 'all'}
                onValueChange={(value) => setJournalFilters({ ...journalFilters, regime: value === 'all' ? '' : value })}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="All Regimes" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Regimes</SelectItem>
                  <SelectItem value="TRENDING_UP">Trending Up</SelectItem>
                  <SelectItem value="TRENDING_DOWN">Trending Down</SelectItem>
                  <SelectItem value="RANGING">Ranging</SelectItem>
                  <SelectItem value="VOLATILE">Volatile</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={journalFilters.outcome}
                onValueChange={(value) => setJournalFilters({ ...journalFilters, outcome: value as 'all' | 'win' | 'loss' })}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="All Outcomes" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Outcomes</SelectItem>
                  <SelectItem value="win">Winners</SelectItem>
                  <SelectItem value="loss">Losers</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-2">
              <Input
                type="date"
                placeholder="Start Date"
                value={journalFilters.start_date}
                onChange={(e) => setJournalFilters({ ...journalFilters, start_date: e.target.value })}
                className="h-7 text-xs"
              />
              <Input
                type="date"
                placeholder="End Date"
                value={journalFilters.end_date}
                onChange={(e) => setJournalFilters({ ...journalFilters, end_date: e.target.value })}
                className="h-7 text-xs"
              />
            </div>

            {/* Trade Table */}
            {tradeJournalEntries.length > 0 ? (
              <div className="overflow-x-auto max-h-[600px] overflow-y-auto rounded-md border border-[var(--color-dark-border)]">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-[var(--color-dark-surface)] border-b border-[var(--color-dark-border)]">
                    <tr>
                      <th className="text-left p-2 font-mono text-xs text-gray-500 cursor-pointer"
                        onClick={() => {
                          if (journalSortBy === 'entry_time') {
                            setJournalSortOrder(journalSortOrder === 'asc' ? 'desc' : 'asc');
                          } else {
                            setJournalSortBy('entry_time');
                            setJournalSortOrder('desc');
                          }
                        }}>
                        Date {journalSortBy === 'entry_time' && (journalSortOrder === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="text-left p-2 font-mono text-xs text-gray-500 cursor-pointer"
                        onClick={() => {
                          if (journalSortBy === 'symbol') {
                            setJournalSortOrder(journalSortOrder === 'asc' ? 'desc' : 'asc');
                          } else {
                            setJournalSortBy('symbol');
                            setJournalSortOrder('asc');
                          }
                        }}>
                        Symbol {journalSortBy === 'symbol' && (journalSortOrder === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="text-left p-2 font-mono text-xs text-gray-500">Strategy</th>
                      <th className="text-right p-2 font-mono text-xs text-gray-500">Entry</th>
                      <th className="text-right p-2 font-mono text-xs text-gray-500">Exit</th>
                      <th className="text-right p-2 font-mono text-xs text-gray-500 cursor-pointer"
                        onClick={() => {
                          if (journalSortBy === 'pnl') {
                            setJournalSortOrder(journalSortOrder === 'asc' ? 'desc' : 'asc');
                          } else {
                            setJournalSortBy('pnl');
                            setJournalSortOrder('desc');
                          }
                        }}>
                        P&L {journalSortBy === 'pnl' && (journalSortOrder === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="text-right p-2 font-mono text-xs text-gray-500 cursor-pointer"
                        onClick={() => {
                          if (journalSortBy === 'hold_time_hours') {
                            setJournalSortOrder(journalSortOrder === 'asc' ? 'desc' : 'asc');
                          } else {
                            setJournalSortBy('hold_time_hours');
                            setJournalSortOrder('desc');
                          }
                        }}>
                        Hold Time {journalSortBy === 'hold_time_hours' && (journalSortOrder === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="text-left p-2 font-mono text-xs text-gray-500">Regime</th>
                      <th className="text-left p-2 font-mono text-xs text-gray-500">Exit Reason</th>
                      <th className="text-right p-2 font-mono text-xs text-gray-500">Conviction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradeJournalEntries.map((trade) => (
                      <tr key={trade.id} className="border-b border-[var(--color-dark-border)]/50 hover:bg-[var(--color-dark-surface)]">
                        <td className="p-2 font-mono text-xs">
                          {formatTimestamp(trade.entry_time, { includeTime: false })}
                        </td>
                        <td className="p-2 font-mono text-xs font-semibold">{trade.symbol}</td>
                        <td className="p-2 font-mono text-xs text-gray-500 truncate max-w-[150px]" title={trade.strategy_name || trade.strategy_id}>
                          {trade.strategy_name || trade.strategy_id}
                        </td>
                        <td className="p-2 font-mono text-xs text-right">
                          {formatCurrency(trade.entry_price)}
                        </td>
                        <td className="p-2 font-mono text-xs text-right">
                          {trade.exit_price ? formatCurrency(trade.exit_price) : '-'}
                        </td>
                        <td className={cn('p-2 font-mono text-xs text-right font-semibold',
                          (trade.pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                          {trade.pnl ? formatCurrency(trade.pnl) : '-'}
                          {trade.pnl_percent && (
                            <span className="text-xs ml-1">
                              ({formatPercentage(trade.pnl_percent)})
                            </span>
                          )}
                        </td>
                        <td className="p-2 font-mono text-xs text-right">
                          {trade.hold_time_hours ? `${(trade.hold_time_hours / 24).toFixed(1)}d` : '-'}
                        </td>
                        <td className="p-2 text-xs">
                          {trade.market_regime && (
                            <Badge variant="outline" className="text-xs">
                              {trade.market_regime}
                            </Badge>
                          )}
                        </td>
                        <td className="p-2 text-xs text-gray-500">
                          {trade.exit_reason || '-'}
                        </td>
                        <td className="p-2 font-mono text-xs text-right">
                          {trade.conviction_score ? trade.conviction_score.toFixed(0) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500 text-xs">
                No trades match your filters
              </div>
            )}

            {/* MAE vs MFE Analysis */}
            <SectionLabel>MAE vs MFE Analysis</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}>
              {(() => {
                const scatterData = tradeJournalEntries.filter(t => t.max_adverse_excursion && t.max_favorable_excursion);
                if (scatterData.length === 0) {
                  return <div className="text-center py-12 text-gray-500 text-xs font-mono">No MAE/MFE data available</div>;
                }
                return <MaeMfeScatter scatterData={scatterData} />;
              })()}
              <div className="flex items-center justify-center gap-6 mt-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-accent-green" />
                  <span className="text-xs text-gray-500">Winners</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-accent-red" />
                  <span className="text-xs text-gray-500">Losers</span>
                </div>
              </div>
            </motion.div>

            {/* Pattern Recognition */}
            <SectionLabel>Pattern Recognition</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              
              {/* Best Performing Patterns */}
              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs text-gray-500 tracking-wide mb-2">Best Performing Patterns</div>
                {tradeJournalPatterns?.best_patterns && tradeJournalPatterns.best_patterns.length > 0 ? (
                  <div className="space-y-2">
                    {tradeJournalPatterns.best_patterns.map((pattern, idx) => (
                      <div key={idx} className="p-2 bg-[var(--color-dark-surface)] rounded">
                        <div className="flex items-center justify-between mb-1">
                          <Badge variant="outline" className="text-xs">
                            {pattern.pattern_type}
                          </Badge>
                          <span className="text-xs font-mono font-semibold text-accent-green">
                            {formatPercentage(pattern.win_rate ?? 0)}
                          </span>
                        </div>
                        <p className="text-xs font-mono">{pattern.pattern}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {pattern.total_trades} trades • Avg P&L: {formatCurrency(pattern.avg_pnl ?? 0)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500 text-xs">
                    No patterns identified yet
                  </div>
                )}
              </div>

              {/* Worst Performing Patterns */}
              <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
                <div className="text-xs text-gray-500 tracking-wide mb-2">Worst Performing Patterns</div>
                {tradeJournalPatterns?.worst_patterns && tradeJournalPatterns.worst_patterns.length > 0 ? (
                  <div className="space-y-2">
                    {tradeJournalPatterns.worst_patterns.map((pattern, idx) => (
                      <div key={idx} className="p-2 bg-[var(--color-dark-surface)] rounded">
                        <div className="flex items-center justify-between mb-1">
                          <Badge variant="outline" className="text-xs">
                            {pattern.pattern_type}
                          </Badge>
                          <span className="text-xs font-mono font-semibold text-accent-red">
                            {formatPercentage(pattern.win_rate ?? 0)}
                          </span>
                        </div>
                        <p className="text-xs font-mono">{pattern.pattern}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {pattern.total_trades} trades • Avg P&L: {formatCurrency(pattern.avg_pnl ?? 0)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500 text-xs">
                    No patterns identified yet
                  </div>
                )}
              </div>
            </motion.div>

            {/* Actionable Recommendations */}
            <SectionLabel>Actionable Recommendations</SectionLabel>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}>
              {tradeJournalPatterns?.recommendations && tradeJournalPatterns.recommendations.length > 0 ? (
                <div className="space-y-2">
                  {tradeJournalPatterns.recommendations.map((rec, idx) => (
                    <div key={idx} className="p-3 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)] rounded-md border-l-4 border-l-blue-500">
                      <div className="flex items-start gap-3">
                        <div className="mt-1">
                          {rec.type === 'increase_allocation' && <TrendingUp className="h-4 w-4 text-accent-green" />}
                          {rec.type === 'reduce_allocation' && <Activity className="h-4 w-4 text-accent-red" />}
                          {rec.type === 'favor_regime' && <Zap className="h-4 w-4 text-blue-500" />}
                          {rec.type === 'avoid_regime' && <Activity className="h-4 w-4 text-yellow-500" />}
                          {rec.type === 'optimize_hold_period' && <Target className="h-4 w-4 text-purple-500" />}
                        </div>
                        <div className="flex-1">
                          <p className="text-xs font-semibold mb-1 capitalize">
                            {rec.type.replace(/_/g, ' ')}
                          </p>
                          <p className="text-xs text-gray-500">
                            <span className="font-mono">{rec.target}</span> - {rec.reason}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500 text-xs">
                  No recommendations available yet. More trade data needed.
                </div>
              )}
            </motion.div>
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              SUB-TAB COMPONENTS (separate files — rendered as-is)
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="rolling-statistics" className="space-y-2">
            <RollingStatisticsTab
              data={rollingStats}
              loading={rollingStatsLoading}
              error={rollingStatsError}
              window={rollingWindow}
              onWindowChange={(w) => { setRollingWindow(w); }}
              period={period}
              onRetry={() => handleTabChange('rolling-statistics')}
            />
          </TabsContent>

          <TabsContent value="perf-attribution" className="space-y-2">
            <PerformanceAttributionTab
              data={perfAttribution}
              loading={perfAttributionLoading}
              error={perfAttributionError}
              groupBy={attributionGroupBy}
              onGroupByChange={(g) => { setAttributionGroupBy(g); }}
              period={period}
              onRetry={() => handleTabChange('perf-attribution')}
            />
          </TabsContent>

          <TabsContent value="tear-sheet" className="space-y-2">
            <TearSheetTab
              data={tearSheet}
              loading={tearSheetLoading}
              error={tearSheetError}
              rMultiples={rMultiples}
              onRetry={() => handleTabChange('tear-sheet')}
            />
          </TabsContent>

          <TabsContent value="tca" className="space-y-2">
            <TCATab
              data={tcaData}
              loading={tcaLoading}
              error={tcaError}
              period={period}
              onRetry={() => handleTabChange('tca')}
            />
          </TabsContent>

          {/* ═══════════════════════════════════════════════════════════════
              STRESS TESTS TAB (Sprint 7.2)
              ═══════════════════════════════════════════════════════════════ */}
          <TabsContent value="stress-tests" className="space-y-3">
            {stressTestsLoading ? (
              <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">Loading stress tests...</div>
            ) : stressTestsError ? (
              <div className="text-sm text-accent-red p-4">{stressTestsError}</div>
            ) : stressTests?.message && !stressTests?.scenarios?.length ? (
              <div className="text-sm text-muted-foreground p-4">{stressTests.message}</div>
            ) : stressTests?.scenarios?.length ? (
              <div className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Simulated portfolio performance during major market crashes (β=0.70 vs SPY).
                  SPY data from historical cache.
                </p>
                {stressTests.scenarios.map((scenario: any) => (
                  <div key={scenario.name} className="border border-border rounded-md p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-semibold">{scenario.name}</span>
                      <div className="flex items-center gap-4 text-xs font-mono">
                        <span className="text-muted-foreground">{scenario.start_date} → {scenario.end_date}</span>
                        <span className={scenario.spy_return_pct >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                          SPY: {scenario.spy_return_pct >= 0 ? '+' : ''}{scenario.spy_return_pct.toFixed(1)}%
                        </span>
                        <span className={scenario.portfolio_simulated_return_pct >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                          Portfolio: {scenario.portfolio_simulated_return_pct >= 0 ? '+' : ''}{scenario.portfolio_simulated_return_pct.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                    {scenario.spy_curve?.length > 1 && (
                      <TvChart
                        height={180}
                        series={[
                          {
                            id: `spy_${scenario.name}`,
                            type: 'line',
                            data: scenario.spy_curve.map((p: any) => ({ time: p.date, value: p.value })),
                            color: '#9ca3af',
                            lineWidth: 1,
                            dashed: true,
                          },
                          {
                            id: `port_${scenario.name}`,
                            type: 'area',
                            data: scenario.portfolio_curve.map((p: any) => ({ time: p.date, value: p.value })),
                            lineColor: '#3b82f6',
                            topColor: 'rgba(59,130,246,0.15)',
                            bottomColor: 'transparent',
                            lineWidth: 2,
                          },
                        ]}
                        showTimeScale
                        autoResize
                      />
                    )}
                    <div className="flex items-center gap-4 mt-1 text-[10px] font-mono text-muted-foreground">
                      <span className="flex items-center gap-1"><span className="w-4 h-px bg-gray-400 inline-block" style={{ borderTop: '1px dashed #9ca3af' }} /> SPY</span>
                      <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-blue-500 inline-block rounded" /> Portfolio (simulated)</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground p-4">Click the Stress Tests tab to load data.</div>
            )}
          </TabsContent>
        </Tabs>
      </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
