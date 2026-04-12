import { type FC, useEffect, useState, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, BarChart3, PieChart, Activity, Download, FileText,
  Search, ArrowUpDown, Calendar, Target, Zap
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { RefreshButton } from '../components/ui/RefreshButton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
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
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  Cell, Line
} from 'recharts';
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

export const AnalyticsNew: FC<AnalyticsNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<'1M' | '3M' | '6M' | '1Y' | 'ALL'>('3M');
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
          apiClient.getPerformanceAnalytics(tradingMode, period),
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
          const ts = await apiClient.getTearSheetData(tradingMode, period);
          setTearSheet(ts);
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
      
      // Set tab-specific data (Phase 2 results)
      // Set strategy attribution
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
      
      // Set trade analytics
      if (tradeData) {
        // Build holding period distribution from the raw data
        const holdingPeriods = [
          { range: '< 1 day', count: 0 },
          { range: '1-3 days', count: 0 },
          { range: '3-7 days', count: 0 },
          { range: '1-2 weeks', count: 0 },
          { range: '2+ weeks', count: 0 },
        ];
        // The backend gives us avg_holding_time_hours — we can estimate distribution
        const avgHours = tradeData.avg_holding_time_hours || 0;
        if (avgHours > 0 && tradeData.total_trades > 0) {
          // Rough distribution based on average
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
          pnl_by_hour: [],  // Not available from this endpoint — perfStats has win_rate_by_hour
          pnl_by_day: [],   // Not available from this endpoint — perfStats has win_rate_by_day
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
      
      // Set Alpha Edge data
      if (fundStats) {
        setFundamentalStats(fundStats);
      }
      
      if (mlFilterStats) {
        setMLStats(mlFilterStats);
      }
      
      if (convictionDist) {
        setConvictionDistribution(convictionDist);
      }
      
      if (templatePerf && Array.isArray(templatePerf)) {
        setTemplatePerformance(templatePerf);
      }
      
      if (txCostSavings) {
        setCostSavings(txCostSavings);
      }
      
    } catch (error) {
      const classified = classifyError(error, 'analytics');
      console.error('Failed to fetch analytics data:', error);
      setError(classified.message);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, period, activeTab, rollingWindow, attributionGroupBy]);

  const fetchTradeJournalData = async () => {
    try {
      // Build filters
      const filters: Record<string, string | boolean> = {};
      
      if (journalFilters.strategy_id) filters.strategy_id = journalFilters.strategy_id;
      if (journalFilters.symbol) filters.symbol = journalFilters.symbol;
      if (journalFilters.start_date) filters.start_date = journalFilters.start_date;
      if (journalFilters.end_date) filters.end_date = journalFilters.end_date;
      
      // Fetch trade journal data
      const [journalData, patternsData] = await Promise.all([
        apiClient.getTradeJournal(filters),
        apiClient.getTradeJournalPatterns(filters),
      ]);
      
      if (journalData && journalData.trades) {
        let entries = journalData.trades;
        
        // Apply regime filter
        if (journalFilters.regime) {
          entries = entries.filter((e: TradeJournalEntry) => e.market_regime === journalFilters.regime);
        }
        
        // Apply outcome filter
        if (journalFilters.outcome !== 'all') {
          entries = entries.filter((e: TradeJournalEntry) => {
            if (journalFilters.outcome === 'win') return e.pnl && e.pnl > 0;
            if (journalFilters.outcome === 'loss') return e.pnl && e.pnl < 0;
            return true;
          });
        }
        
        // Sort entries
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
      
      if (patternsData) {
        setTradeJournalPatterns(patternsData);
      }
    } catch (error) {
      console.error('Failed to fetch trade journal data:', error);
      toast.error('Failed to load trade journal data');
    }
  };

  // usePolling replaces manual useEffect + setInterval
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchAnalyticsData,
    intervalMs: 120000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // Re-fetch when period changes
  useEffect(() => {
    if (!tradingModeLoading && tradingMode) {
      fetchAnalyticsData();
    }
  }, [period]);

  // Tab change — re-fetch to get tab-specific Phase 2 data,
  // but Phase 1 will skip the network calls when data is fresh (see fetchAnalyticsData).
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
      
      // Create download link
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
    <div className="flex items-center gap-2">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <Select value={period} onValueChange={(value) => setPeriod(value as typeof period)}>
        <SelectTrigger className="w-[130px]">
          <Calendar className="h-4 w-4 mr-2" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1M">1 Month</SelectItem>
          <SelectItem value="3M">3 Months</SelectItem>
          <SelectItem value="6M">6 Months</SelectItem>
          <SelectItem value="1Y">1 Year</SelectItem>
          <SelectItem value="ALL">All Time</SelectItem>
        </SelectContent>
      </Select>
      <Button variant="outline" size="sm" onClick={handleExportCSV}>
        <Download className="h-4 w-4 mr-2" />
        Export CSV
      </Button>
      <TearSheetGenerator />
      <RefreshButton loading={refreshing} label="Refresh" onClick={handleRefresh} />
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
        <PageTemplate title="◆ Analytics" description="Comprehensive performance analysis and insights">
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  if (error && !performanceMetrics) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Analytics" description="Error loading data">
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

        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-2">
          <TabsList className="w-full overflow-x-auto">
            <TabsTrigger value="performance" className="gap-2">
              <TrendingUp className="h-4 w-4" />
              <span className="hidden sm:inline">Performance</span>
            </TabsTrigger>
            <TabsTrigger value="attribution" className="gap-2">
              <PieChart className="h-4 w-4" />
              <span className="hidden sm:inline">Strategy Attribution</span>
            </TabsTrigger>
            <TabsTrigger value="trades" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              <span className="hidden sm:inline">Trade Analytics</span>
            </TabsTrigger>
            <TabsTrigger value="regime" className="gap-2">
              <Activity className="h-4 w-4" />
              <span className="hidden sm:inline">Regime Analysis</span>
            </TabsTrigger>
            <TabsTrigger value="alpha-edge" className="gap-2">
              <Zap className="h-4 w-4" />
              <span className="hidden sm:inline">Alpha Edge</span>
            </TabsTrigger>
            <TabsTrigger value="trade-journal" className="gap-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Trade Journal</span>
            </TabsTrigger>
            <TabsTrigger value="rolling-statistics" className="gap-2">
              <TrendingUp className="h-4 w-4" />
              <span className="hidden sm:inline">Rolling Statistics</span>
            </TabsTrigger>
            <TabsTrigger value="perf-attribution" className="gap-2">
              <PieChart className="h-4 w-4" />
              <span className="hidden sm:inline">Attribution</span>
            </TabsTrigger>
            <TabsTrigger value="tear-sheet" className="gap-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Tear Sheet</span>
            </TabsTrigger>
            <TabsTrigger value="tca" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              <span className="hidden sm:inline">TCA</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="performance" className="space-y-2">
            {/* Key Metrics — simple 4-col grid, no Card/MetricCard wrappers */}
            <div className="grid grid-cols-4 gap-px bg-[var(--color-dark-border)] border border-[var(--color-dark-border)] rounded">
              {[
                { label: 'Total Return', value: formatPercentage(performanceMetrics?.total_return || 0), color: (performanceMetrics?.total_return ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red' },
                { label: 'Sharpe Ratio', value: (performanceMetrics?.sharpe_ratio ?? 0).toFixed(2), color: 'text-gray-100' },
                { label: 'Max Drawdown', value: formatPercentage(performanceMetrics?.max_drawdown || 0), color: 'text-accent-red' },
                { label: 'Win Rate', value: formatPercentage(performanceMetrics?.win_rate || 0), color: (performanceMetrics?.win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-accent-red' },
              ].map((m, i) => (
                <div key={i} className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[9px] text-gray-500 uppercase tracking-wide">{m.label}</div>
                  <div className={cn('text-sm font-mono font-bold', m.color)}>{m.value}</div>
                </div>
              ))}
            </div>

            {/* CIO Metrics — simple 4-col grid, no Card wrappers */}
            {cioDashboard && (
              <div className="grid grid-cols-4 gap-px bg-[var(--color-dark-border)] border border-[var(--color-dark-border)] rounded">
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[9px] text-gray-500 uppercase tracking-wide">CAGR</div>
                  <div className={cn('text-sm font-mono font-bold', cioDashboard.cagr >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                    {cioDashboard.cagr >= 0 ? '+' : ''}{cioDashboard.cagr.toFixed(1)}%
                  </div>
                </div>
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[9px] text-gray-500 uppercase tracking-wide">Calmar</div>
                  <div className={cn('text-sm font-mono font-bold', cioDashboard.calmar_ratio >= 1 ? 'text-accent-green' : cioDashboard.calmar_ratio >= 0.5 ? 'text-yellow-400' : 'text-accent-red')}>
                    {cioDashboard.calmar_ratio.toFixed(2)}
                  </div>
                </div>
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[9px] text-gray-500 uppercase tracking-wide">Info Ratio</div>
                  <div className={cn('text-sm font-mono font-bold', cioDashboard.information_ratio >= 0.5 ? 'text-accent-green' : cioDashboard.information_ratio >= 0 ? 'text-yellow-400' : 'text-accent-red')}>
                    {cioDashboard.information_ratio.toFixed(2)}
                  </div>
                </div>
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[9px] text-gray-500 uppercase tracking-wide">DD Duration</div>
                  <div className={cn('text-sm font-mono font-bold', cioDashboard.drawdown_duration_days <= 7 ? 'text-accent-green' : cioDashboard.drawdown_duration_days <= 30 ? 'text-yellow-400' : 'text-accent-red')}>
                    {cioDashboard.drawdown_duration_days}d
                  </div>
                </div>
              </div>
            )}

            {/* P&L + Streaks + Execution — 3-col grid with border separators, no Card wrappers */}
            {cioDashboard && (
              <div className="grid grid-cols-3 gap-px bg-[var(--color-dark-border)] border border-[var(--color-dark-border)] rounded">
                {/* P&L Breakdown */}
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">P&L Breakdown</div>
                  <div className="space-y-1 text-[11px] font-mono">
                    <div className="flex justify-between"><span className="text-gray-500">Realized</span><span className={cioDashboard.total_realized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>{formatCurrency(cioDashboard.total_realized_pnl)}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Unrealized</span><span className={cioDashboard.total_unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>{formatCurrency(cioDashboard.total_unrealized_pnl)}</span></div>
                    <div className="flex justify-between border-t border-[var(--color-dark-border)] pt-1"><span className="font-semibold text-gray-300">Total</span><span className={cn('font-semibold', cioDashboard.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioDashboard.total_pnl)}</span></div>
                  </div>
                </div>
                {/* Win/Loss Streaks */}
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">Streaks</div>
                  <div className="space-y-1 text-[11px] font-mono">
                    <div className="flex justify-between"><span className="text-gray-500">Current</span><span className={cioDashboard.current_streak >= 0 ? 'text-accent-green' : 'text-accent-red'}>{cioDashboard.current_streak > 0 ? `+${cioDashboard.current_streak}W` : cioDashboard.current_streak < 0 ? `${cioDashboard.current_streak}L` : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Best</span><span className="text-accent-green">{cioDashboard.longest_win_streak}W</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Worst</span><span className="text-accent-red">{cioDashboard.longest_loss_streak}L</span></div>
                  </div>
                </div>
                {/* Execution Quality */}
                <div className="bg-[var(--color-dark-surface)] px-3 py-2">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">Execution</div>
                  <div className="space-y-1 text-[11px] font-mono">
                    <div className="flex justify-between"><span className="text-gray-500">Entry Slip</span><span>{cioDashboard.avg_entry_slippage_pct.toFixed(3)}%</span></div>
                    <div className="flex justify-between"><span className="text-gray-500">Exit Slip</span><span>{cioDashboard.avg_exit_slippage_pct.toFixed(3)}%</span></div>
                    <div className="flex justify-between border-t border-[var(--color-dark-border)] pt-1"><span className="text-gray-500">Total Cost</span><span className="text-accent-red">{formatCurrency(cioDashboard.total_slippage_cost)}</span></div>
                  </div>
                </div>
              </div>
            )}

            {/* Strategy Lifecycle + Trade Quality + Closure Analysis */}
            {cioDashboard && (
              <PanelHeader title="Strategy Lifecycle & Trade Quality" panelId="analytics-lifecycle">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.045 }} className="space-y-4 p-3">
                
                {/* Pipeline Health */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Strategy Pipeline (30 days)</CardTitle>
                    <CardDescription>Proposal → Activation → Performance → Retirement</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 md:grid-cols-6 gap-4 text-center">
                      <div><p className="text-2xl font-bold font-mono text-blue-400">{cioDashboard.strategies_proposed_30d}</p><p className="text-xs text-muted-foreground">Proposed</p></div>
                      <div><p className="text-2xl font-bold font-mono text-accent-green">{cioDashboard.strategies_activated_30d}</p><p className="text-xs text-muted-foreground">Activated</p></div>
                      <div><p className="text-2xl font-bold font-mono">{cioDashboard.proposal_to_activation_rate?.toFixed(0) || 0}%</p><p className="text-xs text-muted-foreground">Conversion</p></div>
                      <div><p className="text-2xl font-bold font-mono">{cioDashboard.active_strategy_count}</p><p className="text-xs text-muted-foreground">Active Now</p></div>
                      <div><p className="text-2xl font-bold font-mono text-accent-red">{cioDashboard.strategies_retired_30d}</p><p className="text-xs text-muted-foreground">Retired</p></div>
                      <div><p className="text-2xl font-bold font-mono">{cioDashboard.avg_strategy_lifespan_days?.toFixed(0) || 0}d</p><p className="text-xs text-muted-foreground">Avg Lifespan</p></div>
                    </div>
                  </CardContent>
                </Card>

                {/* Active Strategy Health + Retirement Analysis */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Active Strategies</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between"><span className="text-muted-foreground">Profitable</span><span className="text-accent-green">{cioDashboard.active_profitable || 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Unprofitable</span><span className="text-accent-red">{cioDashboard.active_unprofitable || 0}</span></div>
                        <div className="flex justify-between border-t border-border pt-2"><span className="text-muted-foreground">Unrealized P&L</span><span className={cn((cioDashboard.active_total_unrealized || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioDashboard.active_total_unrealized || 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Avg P&L / Strategy</span><span className={cn((cioDashboard.avg_active_strategy_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioDashboard.avg_active_strategy_pnl || 0)}</span></div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Retired Strategies (30d)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between"><span className="text-muted-foreground">Profitable</span><span className="text-accent-green">{cioDashboard.retired_profitable || 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Unprofitable</span><span className="text-accent-red">{cioDashboard.retired_unprofitable || 0}</span></div>
                        <div className="flex justify-between border-t border-border pt-2"><span className="text-muted-foreground">Total P&L</span><span className={cn((cioDashboard.retired_total_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioDashboard.retired_total_pnl || 0)}</span></div>
                        {cioDashboard.retirement_reasons && Object.keys(cioDashboard.retirement_reasons).length > 0 && (
                          <div className="border-t border-border pt-2 space-y-1">
                            <p className="text-xs text-muted-foreground">Retirement Reasons</p>
                            {Object.entries(cioDashboard.retirement_reasons).map(([reason, count]) => (
                              <div key={reason} className="flex justify-between text-xs"><span className="text-muted-foreground capitalize">{reason.replace(/_/g, ' ')}</span><span>{count as number}</span></div>
                            ))}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Trade Quality + Closure Analysis */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Trade Quality</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between"><span className="text-muted-foreground">Closed Trades</span><span>{cioDashboard.total_trades_closed || 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Win / Loss</span><span><span className="text-accent-green">{cioDashboard.winning_trades || 0}</span> / <span className="text-accent-red">{cioDashboard.losing_trades || 0}</span></span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Closed WR</span><span className={cn((cioDashboard.win_rate || 0) >= 50 ? 'text-accent-green' : 'text-yellow-400')}>{(cioDashboard.win_rate || 0).toFixed(1)}%</span></div>
                        <div className="flex justify-between border-t border-border pt-2"><span className="text-muted-foreground">Open Positions</span><span>{cioDashboard.total_open_positions || 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Win / Loss</span><span><span className="text-accent-green">{cioDashboard.open_winning || 0}</span> / <span className="text-accent-red">{cioDashboard.open_losing || 0}</span></span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Open WR</span><span className={cn((cioDashboard.open_win_rate || 0) >= 50 ? 'text-accent-green' : 'text-yellow-400')}>{(cioDashboard.open_win_rate || 0).toFixed(1)}%</span></div>
                        <div className="flex justify-between border-t border-border pt-2"><span className="text-muted-foreground font-semibold">Combined WR</span><span className={cn('font-semibold', (cioDashboard.combined_win_rate || 0) >= 50 ? 'text-accent-green' : 'text-yellow-400')}>{(cioDashboard.combined_win_rate || 0).toFixed(1)}%</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Profit Factor</span><span className={cn((cioDashboard.profit_factor || 0) >= 1.5 ? 'text-accent-green' : (cioDashboard.profit_factor || 0) >= 1 ? 'text-yellow-400' : 'text-accent-red')}>{(cioDashboard.profit_factor || 0).toFixed(2)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Avg Win / Loss</span><span><span className="text-accent-green">{formatCurrency(cioDashboard.avg_win || 0)}</span> / <span className="text-accent-red">{formatCurrency(cioDashboard.avg_loss || 0)}</span></span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Avg Hold Time</span><span>{(cioDashboard.avg_hold_time_hours || 0).toFixed(1)}h</span></div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Position Closures</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm font-mono">
                        {cioDashboard.closure_reasons && Object.keys(cioDashboard.closure_reasons).length > 0 ? (
                          Object.entries(cioDashboard.closure_reasons)
                            .sort(([,a], [,b]) => (b as number) - (a as number))
                            .map(([reason, count]) => (
                              <div key={reason} className="flex justify-between">
                                <span className="text-muted-foreground capitalize">{reason.replace(/_/g, ' ')}</span>
                                <span>{count as number}</span>
                              </div>
                            ))
                        ) : (
                          <p className="text-xs text-muted-foreground">No closed positions in period</p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </motion.div>
              </PanelHeader>
            )}

            {/* Daily P&L Table */}
            {cioDashboard && cioDashboard.daily_pnl_table.length > 0 && (
              <PanelHeader title="Daily P&L" panelId="analytics-daily-pnl">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.048 }} className="p-3">
                <Card>
                  <CardHeader>
                    <CardTitle>Daily P&L</CardTitle>
                    <CardDescription>The most important table at any fund — daily portfolio performance</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                      <table className="w-full text-xs font-mono">
                        <thead className="sticky top-0 bg-card">
                          <tr className="border-b border-border">
                            <th className="text-left p-2 text-muted-foreground">Date</th>
                            <th className="text-right p-2 text-muted-foreground">Start Equity</th>
                            <th className="text-right p-2 text-muted-foreground">End Equity</th>
                            <th className="text-right p-2 text-muted-foreground">Daily P&L</th>
                            <th className="text-right p-2 text-muted-foreground">Daily %</th>
                            <th className="text-right p-2 text-muted-foreground">Cumulative</th>
                            <th className="text-right p-2 text-muted-foreground">Realized</th>
                            <th className="text-right p-2 text-muted-foreground">Unrealized</th>
                            <th className="text-right p-2 text-muted-foreground">Trades</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...cioDashboard.daily_pnl_table].reverse().map((row) => (
                            <tr key={row.date} className="border-b border-border/50 hover:bg-muted/50">
                              <td className="p-2">{row.date}</td>
                              <td className="p-2 text-right">{formatCurrency(row.starting_equity)}</td>
                              <td className="p-2 text-right">{formatCurrency(row.ending_equity)}</td>
                              <td className={cn('p-2 text-right font-semibold', row.daily_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{row.daily_pnl >= 0 ? '+' : ''}{formatCurrency(row.daily_pnl)}</td>
                              <td className={cn('p-2 text-right', row.daily_pnl_pct >= 0 ? 'text-accent-green' : 'text-accent-red')}>{row.daily_pnl_pct >= 0 ? '+' : ''}{row.daily_pnl_pct.toFixed(2)}%</td>
                              <td className={cn('p-2 text-right', row.cumulative_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(row.cumulative_pnl)}</td>
                              <td className="p-2 text-right">{formatCurrency(row.realized_pnl)}</td>
                              <td className="p-2 text-right">{formatCurrency(row.unrealized_pnl)}</td>
                              <td className="p-2 text-right">{row.trades_closed}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
              </PanelHeader>
            )}

            {/* Expectancy + Profit Factor Cards */}
            <PanelHeader title="Expectancy & Profit Factor" panelId="analytics-expectancy">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.05 }} className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Expectancy</CardTitle>
                  <CardDescription>Per-trade expected value — closed trades vs all positions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Closed Trades</p>
                      <div className={cn('text-2xl font-bold font-mono',
                        (perfStats?.expectancy || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                        {formatCurrency(perfStats?.expectancy || 0)}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{perfStats?.total_trades || 0} closed trades</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">All Positions (incl. open)</p>
                      <div className={cn('text-2xl font-bold font-mono',
                        (perfStats?.total_expectancy || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                        {formatCurrency(perfStats?.total_expectancy || 0)}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{perfStats?.total_expectancy_note || ''}</p>
                    </div>
                  </div>
                  <div className="mt-3 text-xs text-muted-foreground font-mono border-t border-border pt-2">
                    Avg Win: {formatCurrency(perfStats?.avg_win || 0)} · Avg Loss: {formatCurrency(perfStats?.avg_loss || 0)} · WR: {perfStats?.win_rate?.toFixed(1) || 0}%
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Profit Factor</CardTitle>
                  <CardDescription>Gross Profits / Gross Losses — target &gt;1.5</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className={cn('text-3xl font-bold font-mono',
                    (perfStats?.profit_factor || 0) >= 1.5 ? 'text-accent-green' :
                    (perfStats?.profit_factor || 0) >= 1.0 ? 'text-yellow-400' : 'text-accent-red')}>
                    {(perfStats?.profit_factor || 0).toFixed(2)}
                    {(perfStats?.profit_factor || 0) >= 1.5 && <span className="text-sm ml-2">✓</span>}
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground font-mono">
                    Gross Profit: {formatCurrency(perfStats?.gross_profit || 0)} · Gross Loss: {formatCurrency(perfStats?.gross_loss || 0)}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Equity Curve with Benchmark */}
            <PanelHeader title="Equity Curve" panelId="analytics-equity-curve">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Equity Curve</CardTitle>
                  <CardDescription>Cumulative P&L over time</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={perfStats?.equity_curve || performanceMetrics?.equity_curve || []}>
                      <defs>
                        <linearGradient id="colorPortfolio" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="date" stroke="#9ca3af" style={{ fontSize: '11px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '11px' }} tickFormatter={(v) => `$${v}`} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }}
                        formatter={(value: any) => [formatCurrency(value), undefined]} />
                      <Legend />
                      <Area type="monotone" dataKey="portfolio" stroke="#10b981" fillOpacity={1} fill="url(#colorPortfolio)" name="Portfolio" />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Monthly Returns Heatmap */}
            {perfStats?.monthly_returns && perfStats.monthly_returns.length > 0 && (
              <PanelHeader title="Monthly Returns Heatmap" panelId="analytics-monthly-returns">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.15 }} className="p-3">
                <Card>
                  <CardHeader>
                    <CardTitle>Monthly Returns Heatmap</CardTitle>
                    <CardDescription>P&L by month — green positive, red negative</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {(() => {
                      const years = [...new Set(perfStats.monthly_returns.map(r => r.year))].sort();
                      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                      return (
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs font-mono">
                            <thead>
                              <tr>
                                <th className="text-left p-2 text-muted-foreground">Year</th>
                                {months.map(m => <th key={m} className="p-2 text-center text-muted-foreground">{m}</th>)}
                                <th className="p-2 text-center text-muted-foreground font-bold">Total</th>
                              </tr>
                            </thead>
                            <tbody>
                              {years.map(year => {
                                const yearData = perfStats.monthly_returns.filter(r => r.year === year);
                                const yearTotal = yearData.reduce((sum, r) => sum + r.return_pct, 0);
                                return (
                                  <tr key={year}>
                                    <td className="p-2 font-semibold text-gray-300">{year}</td>
                                    {months.map((_, idx) => {
                                      const monthData = yearData.find(r => r.month === idx + 1);
                                      const val = monthData?.return_pct || 0;
                                      const intensity = Math.min(Math.abs(val) / 10, 1);  // 10% = max intensity
                                      const bg = val > 0
                                        ? `rgba(16, 185, 129, ${0.15 + intensity * 0.6})`
                                        : val < 0
                                        ? `rgba(239, 68, 68, ${0.15 + intensity * 0.6})`
                                        : 'transparent';
                                      return (
                                        <td key={idx} className="p-2 text-center rounded" style={{ backgroundColor: bg }}>
                                          {monthData ? `${val >= 0 ? '+' : ''}${val.toFixed(1)}%` : '—'}
                                        </td>
                                      );
                                    })}
                                    <td className={cn('p-2 text-center font-bold',
                                      yearTotal >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                                      {yearTotal >= 0 ? '+' : ''}{yearTotal.toFixed(1)}%
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()}
                  </CardContent>
                </Card>
              </motion.div>
              </PanelHeader>
            )}

            {/* Win Rate by Day of Week + Win Rate by Hour */}
            <PanelHeader title="Win Rate Analysis" panelId="analytics-win-rate">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Win Rate by Day of Week</CardTitle>
                  <CardDescription>Which days produce the best entries</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={Object.entries(perfStats?.win_rate_by_day || {}).map(([day, rate]) => ({ day: day.slice(0, 3), rate }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="day" stroke="#9ca3af" style={{ fontSize: '11px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '11px' }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }}
                        formatter={(value: any) => [`${value.toFixed(1)}%`, 'Win Rate']} />
                      <Bar dataKey="rate" name="Win Rate %">
                        {Object.entries(perfStats?.win_rate_by_day || {}).map(([, rate], i) => (
                          <Cell key={i} fill={rate >= 50 ? '#10b981' : '#ef4444'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Win Rate by Hour of Day</CardTitle>
                  <CardDescription>Optimal trading windows</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={Object.entries(perfStats?.win_rate_by_hour || {}).map(([hour, rate]) => ({ hour: `${hour}:00`, rate }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="hour" stroke="#9ca3af" style={{ fontSize: '10px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '11px' }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }}
                        formatter={(value: any) => [`${value.toFixed(1)}%`, 'Win Rate']} />
                      <Bar dataKey="rate" name="Win Rate %">
                        {Object.entries(perfStats?.win_rate_by_hour || {}).map(([, rate], i) => (
                          <Cell key={i} fill={rate >= 50 ? '#10b981' : '#ef4444'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Winners vs Losers Analysis */}
            {perfStats?.winners_vs_losers?.winners && (
              <PanelHeader title="Winners vs Losers" panelId="analytics-winners-losers">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.25 }} className="p-3">
                <Card>
                  <CardHeader>
                    <CardTitle>Winners vs Losers Analysis</CardTitle>
                    <CardDescription>Side-by-side comparison of winning and losing trades</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 mb-3">
                          <div className="w-3 h-3 rounded-full bg-accent-green" />
                          <span className="font-semibold text-accent-green">Winners ({perfStats.winners_vs_losers.winners.count})</span>
                        </div>
                        <div className="space-y-2 text-sm font-mono">
                          <div className="flex justify-between"><span className="text-muted-foreground">Avg Hold Time</span><span>{perfStats.winners_vs_losers.winners.avg_hold_hours?.toFixed(1)}h</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Avg Size</span><span>{formatCurrency(perfStats.winners_vs_losers.winners.avg_size || 0)}</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Common Strategy</span><span className="truncate max-w-[150px]">{perfStats.winners_vs_losers.winners.common_strategy}</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Common Sector</span><span>{perfStats.winners_vs_losers.winners.common_sector}</span></div>
                        </div>
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 mb-3">
                          <div className="w-3 h-3 rounded-full bg-accent-red" />
                          <span className="font-semibold text-accent-red">Losers ({perfStats.winners_vs_losers.losers.count})</span>
                        </div>
                        <div className="space-y-2 text-sm font-mono">
                          <div className="flex justify-between"><span className="text-muted-foreground">Avg Hold Time</span><span>{perfStats.winners_vs_losers.losers.avg_hold_hours?.toFixed(1)}h</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Avg Size</span><span>{formatCurrency(perfStats.winners_vs_losers.losers.avg_size || 0)}</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Common Strategy</span><span className="truncate max-w-[150px]">{perfStats.winners_vs_losers.losers.common_strategy}</span></div>
                          <div className="flex justify-between"><span className="text-muted-foreground">Common Sector</span><span>{perfStats.winners_vs_losers.losers.common_sector}</span></div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
              </PanelHeader>
            )}

            {/* Drawdown + Returns Distribution */}
            <PanelHeader title="Drawdown & Returns Distribution" panelId="analytics-drawdown-returns">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }} className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Drawdown Chart</CardTitle>
                  <CardDescription>Portfolio drawdown over time</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={performanceMetrics?.drawdown_curve || []}>
                      <defs>
                        <linearGradient id="colorDrawdown" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="date" stroke="#9ca3af" style={{ fontSize: '10px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '11px' }} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }} />
                      <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fillOpacity={1} fill="url(#colorDrawdown)" name="Drawdown %" />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Returns Distribution</CardTitle>
                  <CardDescription>Histogram of trade returns</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={performanceMetrics?.returns_distribution || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="range" stroke="#9ca3af" style={{ fontSize: '10px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '11px' }} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }} />
                      <Bar dataKey="count" fill="#3b82f6" name="Trades" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>

          <TabsContent value="attribution" className="space-y-2">
            <PanelHeader title="Strategy Contribution" panelId="analytics-strategy-contribution">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Strategy Contribution to Returns</CardTitle>
                    <CardDescription>
                      Performance attribution by strategy • {filteredStrategies.length} of {strategyAttribution.length} strategies
                    </CardDescription>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input placeholder="Search strategy..." value={strategySearch}
                        onChange={(e) => setStrategySearch(e.target.value)} className="pl-9 w-full sm:w-[200px]" />
                    </div>
                    <Select value={templateFilter} onValueChange={setTemplateFilter}>
                      <SelectTrigger className="w-full sm:w-[140px]">
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
                      <SelectTrigger className="w-full sm:w-[140px]">
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
                      <SelectTrigger className="w-full sm:w-[140px]">
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
              </CardHeader>
              <CardContent>
                {filteredStrategies.length > 0 ? (
                  <div className="max-h-[600px] overflow-y-auto">
                    <DataTable columns={strategyColumns} data={filteredStrategies} pageSize={20} showPagination={true} />
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    {strategySearch || templateFilter !== 'all' || regimeFilter !== 'all'
                      ? 'No strategies match your filters' : 'No strategy data available'}
                  </div>
                )}
              </CardContent>
            </Card>
            </PanelHeader>

            <PanelHeader title="Performance by Strategy" panelId="analytics-perf-by-strategy">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Performance by Strategy</CardTitle>
                  <CardDescription>Top 10 strategies by contribution</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={filteredStrategies.slice(0, 10)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis type="number" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <YAxis dataKey="strategy_name" type="category" stroke="#9ca3af" style={{ fontSize: '11px' }} width={120} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Bar dataKey="contribution_percent" fill="#10b981" name="Contribution %" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>

          <TabsContent value="trades" className="space-y-2">
            <PanelHeader title="Trade Metrics" panelId="analytics-trade-metrics">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }} className="grid grid-cols-2 md:grid-cols-3 gap-4 p-3">
              <MetricCard label="Total Trades" value={Number(tradeAnalytics?.trade_statistics?.total_trades) || 0}
                format="number" icon={BarChart3} tooltip="Total number of trades executed" />
              <MetricCard label="Winning Trades" value={Number(tradeAnalytics?.trade_statistics?.winning_trades) || 0}
                format="number" icon={TrendingUp} tooltip="Number of profitable trades" />
              <MetricCard label="Losing Trades" value={Number(tradeAnalytics?.trade_statistics?.losing_trades) || 0}
                format="number" icon={Activity} tooltip="Number of losing trades" />
            </motion.div>
            </PanelHeader>

            <PanelHeader title="Trade Distribution" panelId="analytics-trade-distribution">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Win/Loss Distribution</CardTitle>
                  <CardDescription>Trade outcomes by count and value</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={tradeAnalytics?.win_loss_distribution || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="type" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Legend />
                      <Bar dataKey="count" fill="#3b82f6" name="Count" />
                      <Bar dataKey="value" fill="#10b981" name="Value" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Holding Periods</CardTitle>
                  <CardDescription>Distribution of trade durations</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={tradeAnalytics?.holding_periods || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="range" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Bar dataKey="count" fill="#8b5cf6" name="Trades" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            <PanelHeader title="P&L by Day of Week" panelId="analytics-pnl-by-day">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>P&L by Day of Week</CardTitle>
                  <CardDescription>Average profit/loss by trading day</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={tradeAnalytics?.pnl_by_day || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="day" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <YAxis stroke="#9ca3af" style={{ fontSize: '12px' }} />
                      <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Bar dataKey="pnl" fill="#f59e0b" name="P&L" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            <PanelHeader title="Trade Statistics" panelId="analytics-trade-stats">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Trade Statistics</CardTitle>
                  <CardDescription>Key trading metrics and performance indicators</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Avg Holding Period</p>
                      <p className="text-lg font-bold font-mono">
                        {(tradeAnalytics?.trade_statistics?.avg_holding_period || 0).toFixed(1)} days
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Best Trade</p>
                      <p className="text-lg font-bold font-mono text-accent-green">
                        {formatCurrency(tradeAnalytics?.trade_statistics.best_trade || 0)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Worst Trade</p>
                      <p className="text-lg font-bold font-mono text-accent-red">
                        {formatCurrency(tradeAnalytics?.trade_statistics.worst_trade || 0)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>

          <TabsContent value="regime" className="space-y-2">
            {/* Current Regimes by Asset Class */}
            {regimeAnalysis?.current_regimes && Object.keys(regimeAnalysis.current_regimes).length > 0 && (
              <PanelHeader title="Current Market Regimes" panelId="analytics-current-regimes">
              <Card>
                <CardHeader>
                  <CardTitle>Current Market Regimes</CardTitle>
                  <CardDescription>Per-asset-class regime detection using representative benchmarks</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {Object.entries(regimeAnalysis.current_regimes).map(([assetClass, data]) => (
                      <div key={assetClass} className="p-4 bg-muted rounded-lg space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold capitalize">{assetClass}</span>
                          <Badge variant="outline" className="text-xs">{(data as any).confidence ? `${((data as any).confidence * 100).toFixed(0)}%` : ''}</Badge>
                        </div>
                        <p className="text-lg font-bold font-mono">{((data as any).regime || 'unknown').replace(/_/g, ' ')}</p>
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          <p>20d: <span className={((data as any).change_20d || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{((data as any).change_20d || 0).toFixed(1)}%</span></p>
                          <p>50d: <span className={((data as any).change_50d || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{((data as any).change_50d || 0).toFixed(1)}%</span></p>
                          <p>ATR: {((data as any).atr_ratio || 0).toFixed(2)}%</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
              </PanelHeader>
            )}

            {/* Market Context (FRED Macro Data) */}
            {regimeAnalysis?.market_context && regimeAnalysis.market_context.vix && (
              <PanelHeader title="Macro Market Context" panelId="analytics-macro-context">
              <Card>
                <CardHeader>
                  <CardTitle>Macro Market Context</CardTitle>
                  <CardDescription>FRED economic data driving regime and risk decisions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
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
                      <div key={idx} className="p-3 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground">{item.label}</p>
                        <p className={cn('text-sm font-bold font-mono', item.color || '')}>{item.value || 'N/A'}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
              </PanelHeader>
            )}

            {/* Crypto Cycle + Forex Carry */}
            <PanelHeader title="Crypto Cycle & Forex Carry" panelId="analytics-crypto-forex">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
              {regimeAnalysis?.crypto_cycle && regimeAnalysis.crypto_cycle.phase && (
                <Card>
                  <CardHeader>
                    <CardTitle>Bitcoin Halving Cycle</CardTitle>
                    <CardDescription>Position in the 4-year halving cycle</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Phase</span>
                        <Badge variant="outline" className="font-mono">{regimeAnalysis.crypto_cycle.phase?.replace(/_/g, ' ')}</Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Months Since Halving</span>
                        <span className="font-mono text-sm">{regimeAnalysis.crypto_cycle.months_since_halving}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Cycle Score</span>
                        <span className="font-mono text-sm">{regimeAnalysis.crypto_cycle.cycle_score}/100</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Recommendation</span>
                        <Badge className={cn('text-xs',
                          regimeAnalysis.crypto_cycle.recommendation === 'accumulate' ? 'bg-green-500/20 text-green-400' :
                          regimeAnalysis.crypto_cycle.recommendation === 'hold' ? 'bg-blue-500/20 text-blue-400' :
                          regimeAnalysis.crypto_cycle.recommendation === 'reduce' ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-red-500/20 text-red-400'
                        )}>{regimeAnalysis.crypto_cycle.recommendation}</Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {regimeAnalysis?.carry_rates && regimeAnalysis.carry_rates.carry && Object.keys(regimeAnalysis.carry_rates.carry).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Forex Carry Rates</CardTitle>
                    <CardDescription>Interest rate differentials from FRED central bank data</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {Object.entries(regimeAnalysis.carry_rates.carry).map(([pair, diff]) => (
                        <div key={pair} className="flex items-center justify-between p-2 bg-muted rounded">
                          <span className="font-mono text-sm">{pair}</span>
                          <span className={cn('font-mono text-sm font-bold',
                            (diff as number) > 0 ? 'text-accent-green' : (diff as number) < 0 ? 'text-accent-red' : ''
                          )}>{(diff as number) > 0 ? '+' : ''}{(diff as number).toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
            </PanelHeader>

            <PanelHeader title="Performance by Market Regime" panelId="analytics-perf-by-regime">
            <Card>
              <CardHeader>
                <CardTitle>Performance by Market Regime</CardTitle>
                <CardDescription>Strategy performance across different market conditions</CardDescription>
              </CardHeader>
              <CardContent>
                {regimeAnalysis?.performance_by_regime && regimeAnalysis.performance_by_regime.length > 0 ? (
                  <DataTable columns={regimeColumns} data={regimeAnalysis.performance_by_regime} pageSize={10} showPagination={false} />
                ) : (
                  <div className="text-center py-12 text-muted-foreground">No regime data available</div>
                )}
              </CardContent>
            </Card>
            </PanelHeader>

            <PanelHeader title="Regime Transition Timeline" panelId="analytics-regime-transitions">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Regime Transition Timeline</CardTitle>
                  <CardDescription>Market regime changes over time</CardDescription>
                </CardHeader>
                <CardContent>
                  {regimeAnalysis?.regime_transitions && regimeAnalysis.regime_transitions.length > 0 ? (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {regimeAnalysis.regime_transitions.map((transition, idx) => (
                        <div key={idx} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground font-mono">
                              {formatTimestamp(transition.date, { includeTime: false })}
                            </span>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">{transition.from_regime}</Badge>
                              <span className="text-muted-foreground">→</span>
                              <Badge variant="outline" className="text-xs">{transition.to_regime}</Badge>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">No regime transitions recorded</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            <PanelHeader title="Strategy Performance by Regime" panelId="analytics-strategy-regime-perf">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Strategy Performance by Regime</CardTitle>
                  <CardDescription>Heatmap showing strategy effectiveness in different market conditions</CardDescription>
                </CardHeader>
                <CardContent>
                  {regimeAnalysis?.strategy_regime_performance && regimeAnalysis.strategy_regime_performance.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left p-2 font-mono text-xs text-muted-foreground">Strategy</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Trending Up</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Trending Down</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Ranging</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Volatile</th>
                          </tr>
                        </thead>
                        <tbody>
                          {regimeAnalysis.strategy_regime_performance.map((row, idx) => (
                            <tr key={idx} className="border-b border-border/50">
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
                    <div className="text-center py-12 text-muted-foreground">No strategy regime data available</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>

          <TabsContent value="alpha-edge" className="space-y-2">
            <PanelHeader title="Filter Statistics" panelId="analytics-filter-stats">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }} className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
              
              {/* Fundamental Filter Statistics */}
              <Card>
                <CardHeader>
                  <CardTitle>Fundamental Filter Statistics</CardTitle>
                  <CardDescription>Stock screening based on fundamental criteria</CardDescription>
                </CardHeader>
                <CardContent>
                  {fundamentalStats ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Symbols Filtered</p>
                          <p className="text-2xl font-bold font-mono">{fundamentalStats.symbols_filtered || 0}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Symbols Passed</p>
                          <p className="text-2xl font-bold font-mono text-accent-green">
                            {fundamentalStats.symbols_passed || 0}
                          </p>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Pass Rate</p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted rounded-full h-2">
                            <div className="bg-accent-green h-2 rounded-full" 
                              style={{ width: `${fundamentalStats.pass_rate || 0}%` }} />
                          </div>
                          <span className="text-sm font-mono font-semibold">
                            {formatPercentage(fundamentalStats.pass_rate || 0)}
                          </span>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">Most Common Failure Reasons</p>
                        <div className="space-y-1">
                          {fundamentalStats.failure_reasons && Object.entries(fundamentalStats.failure_reasons)
                            .sort(([, a], [, b]) => (b as number) - (a as number))
                            .slice(0, 3)
                            .map(([reason, count]) => (
                              <div key={reason} className="flex justify-between text-xs">
                                <span className="text-muted-foreground capitalize">
                                  {reason.replace(/_/g, ' ')}
                                </span>
                                <span className="font-mono">{String(count)}</span>
                              </div>
                            ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">No data available</div>
                  )}
                </CardContent>
              </Card>

              {/* ML Filter Statistics */}
              <Card>
                <CardHeader>
                  <CardTitle>ML Filter Statistics</CardTitle>
                  <CardDescription>Machine learning signal filtering performance</CardDescription>
                </CardHeader>
                <CardContent>
                  {mlStats ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Signals Filtered</p>
                          <p className="text-2xl font-bold font-mono">{mlStats.signals_filtered || 0}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Signals Passed</p>
                          <p className="text-2xl font-bold font-mono text-accent-green">
                            {mlStats.signals_passed || 0}
                          </p>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Average Confidence</p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted rounded-full h-2">
                            <div className="bg-blue-500 h-2 rounded-full" 
                              style={{ width: `${(mlStats.avg_confidence || 0) * 100}%` }} />
                          </div>
                          <span className="text-sm font-mono font-semibold">
                            {formatPercentage((mlStats.avg_confidence || 0) * 100)}
                          </span>
                        </div>
                      </div>
                      {mlStats.model_accuracy && (
                        <div>
                          <p className="text-xs text-muted-foreground mb-2">Model Accuracy Metrics</p>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Accuracy</span>
                              <span className="font-mono">{formatPercentage((mlStats.model_accuracy || 0) * 100)}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Precision</span>
                              <span className="font-mono">{formatPercentage((mlStats.model_precision || 0) * 100)}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Recall</span>
                              <span className="font-mono">{formatPercentage((mlStats.model_recall || 0) * 100)}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">F1 Score</span>
                              <span className="font-mono">{formatPercentage((mlStats.model_f1_score || 0) * 100)}</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">No data available</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Conviction Score Distribution */}
            <PanelHeader title="Conviction Score Distribution" panelId="analytics-conviction-dist">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Conviction Score Distribution</CardTitle>
                  <CardDescription>Distribution of signal conviction scores and their performance</CardDescription>
                </CardHeader>
                <CardContent>
                  {convictionDistribution ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Average</p>
                          <p className="text-lg font-bold font-mono">{convictionDistribution.avg_score?.toFixed(1) || 0}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Median</p>
                          <p className="text-lg font-bold font-mono">{convictionDistribution.median_score?.toFixed(1) || 0}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Min</p>
                          <p className="text-lg font-bold font-mono">{convictionDistribution.min_score?.toFixed(1) || 0}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Max</p>
                          <p className="text-lg font-bold font-mono">{convictionDistribution.max_score?.toFixed(1) || 0}</p>
                        </div>
                      </div>
                      <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={convictionDistribution.score_ranges || []}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis dataKey="range" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                          <YAxis stroke="#9ca3af" style={{ fontSize: '12px' }} />
                          <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                          <Legend />
                          <Bar dataKey="count" fill="#8b5cf6" name="Count" />
                          <Bar dataKey="avg_return" fill="#10b981" name="Avg Return %" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">No data available</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Strategy Template Performance */}
            <PanelHeader title="Template Performance" panelId="analytics-template-perf">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Strategy Template Performance Comparison</CardTitle>
                  <CardDescription>Performance metrics by strategy template type</CardDescription>
                </CardHeader>
                <CardContent>
                  {templatePerformance && templatePerformance.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left p-2 font-mono text-xs text-muted-foreground">Template</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Trades</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Win Rate</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Return</th>
                            <th className="text-right p-2 font-mono text-xs text-muted-foreground">Sharpe</th>
                          </tr>
                        </thead>
                        <tbody>
                          {templatePerformance.map((template, idx) => (
                            <tr key={idx} className="border-b border-border/50">
                              <td className="p-2 font-mono text-xs">
                                <Badge variant="outline">{template.template}</Badge>
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
                    <div className="text-center py-12 text-muted-foreground">No template data available</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Transaction Cost Savings */}
            <PanelHeader title="Transaction Cost Savings" panelId="analytics-tx-cost-savings">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Transaction Cost Savings</CardTitle>
                  <CardDescription>Cost reduction from reduced trading frequency</CardDescription>
                </CardHeader>
                <CardContent>
                  {costSavings ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Before</p>
                          <p className="text-xl font-bold font-mono text-accent-red">
                            {formatCurrency(costSavings.before_costs || 0)}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {costSavings.trades_before || 0} trades
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">After</p>
                          <p className="text-xl font-bold font-mono text-accent-green">
                            {formatCurrency(costSavings.after_costs || 0)}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {costSavings.trades_after || 0} trades
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Total Savings</p>
                          <p className="text-xl font-bold font-mono text-blue-500">
                            {formatCurrency(costSavings.total_savings || 0)}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {formatPercentage(((costSavings.total_savings || 0) / (costSavings.before_costs || 1)) * 100)} reduction
                          </p>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">Cost as % of Returns</p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted rounded-full h-3">
                            <div className="bg-blue-500 h-3 rounded-full" 
                              style={{ width: `${Math.min(100, costSavings.cost_as_percent_of_returns || 0)}%` }} />
                          </div>
                          <span className="text-sm font-mono font-semibold">
                            {formatPercentage(costSavings.cost_as_percent_of_returns || 0)}
                          </span>
                        </div>
                      </div>
                      <div className="pt-4 border-t border-border">
                        <ResponsiveContainer width="100%" height={200}>
                          <BarChart data={[
                            { period: 'Before', costs: costSavings.before_costs || 0 },
                            { period: 'After', costs: costSavings.after_costs || 0 }
                          ]}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="period" stroke="#9ca3af" style={{ fontSize: '12px' }} />
                            <YAxis stroke="#9ca3af" style={{ fontSize: '12px' }} />
                            <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                            <Bar dataKey="costs" fill="#3b82f6" name="Transaction Costs" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">No cost data available</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>

          <TabsContent value="trade-journal" className="space-y-2">
            {/* Trade Journal Table with Filters */}
            <PanelHeader title="Trade Journal" panelId="analytics-trade-journal">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Trade Journal</CardTitle>
                    <CardDescription>
                      Detailed trade history with filters • {tradeJournalEntries.length} trades
                    </CardDescription>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={handleExportCSV}>
                      <Download className="h-4 w-4 mr-2" />
                      Export CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleGenerateMonthlyReport}>
                      <FileText className="h-4 w-4 mr-2" />
                      Monthly Report
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Filters */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                  <Input
                    placeholder="Strategy ID..."
                    value={journalFilters.strategy_id}
                    onChange={(e) => setJournalFilters({ ...journalFilters, strategy_id: e.target.value })}
                  />
                  <Input
                    placeholder="Symbol..."
                    value={journalFilters.symbol}
                    onChange={(e) => setJournalFilters({ ...journalFilters, symbol: e.target.value })}
                  />
                  <Select
                    value={journalFilters.regime || 'all'}
                    onValueChange={(value) => setJournalFilters({ ...journalFilters, regime: value === 'all' ? '' : value })}
                  >
                    <SelectTrigger>
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
                    <SelectTrigger>
                      <SelectValue placeholder="All Outcomes" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Outcomes</SelectItem>
                      <SelectItem value="win">Winners</SelectItem>
                      <SelectItem value="loss">Losers</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                  <Input
                    type="date"
                    placeholder="Start Date"
                    value={journalFilters.start_date}
                    onChange={(e) => setJournalFilters({ ...journalFilters, start_date: e.target.value })}
                  />
                  <Input
                    type="date"
                    placeholder="End Date"
                    value={journalFilters.end_date}
                    onChange={(e) => setJournalFilters({ ...journalFilters, end_date: e.target.value })}
                  />
                </div>

                {/* Trade Table */}
                {tradeJournalEntries.length > 0 ? (
                  <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-card border-b border-border">
                        <tr>
                          <th className="text-left p-2 font-mono text-xs text-muted-foreground cursor-pointer"
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
                          <th className="text-left p-2 font-mono text-xs text-muted-foreground cursor-pointer"
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
                          <th className="text-left p-2 font-mono text-xs text-muted-foreground">Strategy</th>
                          <th className="text-right p-2 font-mono text-xs text-muted-foreground">Entry</th>
                          <th className="text-right p-2 font-mono text-xs text-muted-foreground">Exit</th>
                          <th className="text-right p-2 font-mono text-xs text-muted-foreground cursor-pointer"
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
                          <th className="text-right p-2 font-mono text-xs text-muted-foreground cursor-pointer"
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
                          <th className="text-left p-2 font-mono text-xs text-muted-foreground">Regime</th>
                          <th className="text-left p-2 font-mono text-xs text-muted-foreground">Exit Reason</th>
                          <th className="text-right p-2 font-mono text-xs text-muted-foreground">Conviction</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tradeJournalEntries.map((trade) => (
                          <tr key={trade.id} className="border-b border-border/50 hover:bg-muted/50">
                            <td className="p-2 font-mono text-xs">
                              {formatTimestamp(trade.entry_time, { includeTime: false })}
                            </td>
                            <td className="p-2 font-mono text-xs font-semibold">{trade.symbol}</td>
                            <td className="p-2 font-mono text-xs text-muted-foreground truncate max-w-[150px]" title={trade.strategy_name || trade.strategy_id}>
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
                            <td className="p-2 text-xs text-muted-foreground">
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
                  <div className="text-center py-12 text-muted-foreground">
                    No trades match your filters
                  </div>
                )}
              </CardContent>
            </Card>
            </PanelHeader>

            {/* MAE/MFE Visualization */}
            <PanelHeader title="MAE vs MFE Analysis" panelId="analytics-mae-mfe">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>MAE vs MFE Analysis</CardTitle>
                  <CardDescription>Maximum Adverse Excursion vs Maximum Favorable Excursion</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={350}>
                    <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="max_adverse_excursion" 
                      type="number"
                      stroke="#9ca3af" 
                      style={{ fontSize: '12px' }}
                      label={{ value: 'MAE (%)', position: 'insideBottom', offset: -5 }}
                    />
                    <YAxis 
                      dataKey="max_favorable_excursion"
                      type="number"
                      stroke="#9ca3af" 
                      style={{ fontSize: '12px' }}
                      label={{ value: 'MFE (%)', angle: -90, position: 'insideLeft' }}
                    />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                      formatter={(value: any) => `${value?.toFixed(2)}%`}
                    />
                    <Legend />
                    {/* Scatter plot using Line with scatter type */}
                    <Line
                      data={tradeJournalEntries.filter(t => t.max_adverse_excursion && t.max_favorable_excursion)}
                      type="monotone"
                      dataKey="max_favorable_excursion"
                      stroke="none"
                      dot={(props: any) => {
                        const { cx, cy, payload } = props;
                        const isWin = payload.pnl && payload.pnl > 0;
                        return (
                          <circle
                            cx={cx}
                            cy={cy}
                            r={4}
                            fill={isWin ? '#10b981' : '#ef4444'}
                            fillOpacity={0.6}
                          />
                        );
                      }}
                      name="Trades"
                    />
                  </ResponsiveContainer>
                  <div className="flex items-center justify-center gap-6 mt-4">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-accent-green" />
                      <span className="text-xs text-muted-foreground">Winners</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-accent-red" />
                      <span className="text-xs text-muted-foreground">Losers</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Pattern Recognition Insights */}
            <PanelHeader title="Pattern Recognition" panelId="analytics-pattern-recognition">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }} className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-3">
              
              {/* Best Performing Patterns */}
              <Card>
                <CardHeader>
                  <CardTitle>Best Performing Patterns</CardTitle>
                  <CardDescription>Top patterns with high win rates</CardDescription>
                </CardHeader>
                <CardContent>
                  {tradeJournalPatterns?.best_patterns && tradeJournalPatterns.best_patterns.length > 0 ? (
                    <div className="space-y-3">
                      {tradeJournalPatterns.best_patterns.map((pattern, idx) => (
                        <div key={idx} className="p-3 bg-muted rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <Badge variant="outline" className="text-xs">
                              {pattern.pattern_type}
                            </Badge>
                            <span className="text-sm font-mono font-semibold text-accent-green">
                              {formatPercentage(pattern.win_rate ?? 0)}
                            </span>
                          </div>
                          <p className="text-sm font-mono">{pattern.pattern}</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {pattern.total_trades} trades • Avg P&L: {formatCurrency(pattern.avg_pnl ?? 0)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No patterns identified yet
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Worst Performing Patterns */}
              <Card>
                <CardHeader>
                  <CardTitle>Worst Performing Patterns</CardTitle>
                  <CardDescription>Patterns to avoid or improve</CardDescription>
                </CardHeader>
                <CardContent>
                  {tradeJournalPatterns?.worst_patterns && tradeJournalPatterns.worst_patterns.length > 0 ? (
                    <div className="space-y-3">
                      {tradeJournalPatterns.worst_patterns.map((pattern, idx) => (
                        <div key={idx} className="p-3 bg-muted rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <Badge variant="outline" className="text-xs">
                              {pattern.pattern_type}
                            </Badge>
                            <span className="text-sm font-mono font-semibold text-accent-red">
                              {formatPercentage(pattern.win_rate ?? 0)}
                            </span>
                          </div>
                          <p className="text-sm font-mono">{pattern.pattern}</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {pattern.total_trades} trades • Avg P&L: {formatCurrency(pattern.avg_pnl ?? 0)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No patterns identified yet
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>

            {/* Actionable Recommendations */}
            <PanelHeader title="Actionable Recommendations" panelId="analytics-recommendations">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }} className="p-3">
              <Card>
                <CardHeader>
                  <CardTitle>Actionable Recommendations</CardTitle>
                  <CardDescription>Data-driven insights to improve trading performance</CardDescription>
                </CardHeader>
                <CardContent>
                  {tradeJournalPatterns?.recommendations && tradeJournalPatterns.recommendations.length > 0 ? (
                    <div className="space-y-3">
                      {tradeJournalPatterns.recommendations.map((rec, idx) => (
                        <div key={idx} className="p-4 bg-muted rounded-lg border-l-4 border-blue-500">
                          <div className="flex items-start gap-3">
                            <div className="mt-1">
                              {rec.type === 'increase_allocation' && <TrendingUp className="h-5 w-5 text-accent-green" />}
                              {rec.type === 'reduce_allocation' && <Activity className="h-5 w-5 text-accent-red" />}
                              {rec.type === 'favor_regime' && <Zap className="h-5 w-5 text-blue-500" />}
                              {rec.type === 'avoid_regime' && <Activity className="h-5 w-5 text-yellow-500" />}
                              {rec.type === 'optimize_hold_period' && <Target className="h-5 w-5 text-purple-500" />}
                            </div>
                            <div className="flex-1">
                              <p className="text-sm font-semibold mb-1 capitalize">
                                {rec.type.replace(/_/g, ' ')}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                <span className="font-mono">{rec.target}</span> - {rec.reason}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No recommendations available yet. More trade data needed.
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            </PanelHeader>
          </TabsContent>
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

          {/* ── Performance Attribution Tab ── */}
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

          {/* ── Tear Sheet Tab ── */}
          <TabsContent value="tear-sheet" className="space-y-2">
            <TearSheetTab
              data={tearSheet}
              loading={tearSheetLoading}
              error={tearSheetError}
              onRetry={() => handleTabChange('tear-sheet')}
            />
          </TabsContent>

          {/* ── TCA Tab ── */}
          <TabsContent value="tca" className="space-y-2">
            <TCATab
              data={tcaData}
              loading={tcaLoading}
              error={tcaError}
              period={period}
              onRetry={() => handleTabChange('tca')}
            />
          </TabsContent>
        </Tabs>
      </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
