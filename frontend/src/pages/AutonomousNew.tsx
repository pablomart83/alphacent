import { type FC, useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  PlayCircle, PauseCircle, Settings, RefreshCw, Search,
  AlertCircle, Clock, Trash2,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { DataTable } from '../components/trading/DataTable';
import { TradingCyclePipeline } from '../components/trading/TradingCyclePipeline';
// Card imports removed — using PanelHeader sections instead
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent } from '../components/ui/tabs';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '../lib/utils';
import { utcToLocal } from '../lib/date-utils';
import { classifyError } from '../lib/errors';
import { InteractiveChart } from '../components/charts/InteractiveChart';
import { colors as designColors } from '../lib/design-tokens';
import type { 
  AutonomousStatus, SystemStatus, Strategy, Order, SystemState 
} from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';

interface AutonomousNewProps {
  onLogout: () => void;
}

export const AutonomousNew: FC<AutonomousNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const navigate = useNavigate();
  
  // State
  const [autonomousStatus, setAutonomousStatus] = useState<AutonomousStatus | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [tradingAction, setTradingAction] = useState(false);
  const [_error, setError] = useState<ReturnType<typeof classifyError> | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  
  // Cycle logs state (kept for WebSocket event processing)
  const [_cycleStage, setCycleStage] = useState<string>('Idle');
  const [cycleProgress, setCycleProgress] = useState<number>(0);
  
  // Last cycle data from cycle history
  const [lastCycleData, setLastCycleData] = useState<{
    duration_seconds: number | null;
    proposals_generated: number;
    backtest_passed: number;
    backtested: number;
    activated: number;
    strategies_retired: number;
  } | null>(null);
  
  const [_currentCycleMetrics, setCurrentCycleMetrics] = useState({
    proposed: 0,
    backtested: 0,
    activated: 0,
    retired: 0,
  });
  
  // Filter states
  const [strategySearch, setStrategySearch] = useState('');
  const [strategyStageFilter, setStrategyStageFilter] = useState<string>('all');
  const [orderSearch, setOrderSearch] = useState('');
  const [orderStatusFilter, setOrderStatusFilter] = useState<string>('all');
  const [orderSideFilter, setOrderSideFilter] = useState<string>('all');

  // Cycle research filters — persisted to localStorage
  const [cycleAssetClasses, setCycleAssetClasses] = useState<Set<string>>(() => {
    try { const v = localStorage.getItem('cycle_filter_assets'); return v ? new Set(JSON.parse(v)) : new Set(); } catch { return new Set(); }
  });
  const [cycleIntervals, setCycleIntervals] = useState<Set<string>>(() => {
    try { const v = localStorage.getItem('cycle_filter_intervals'); return v ? new Set(JSON.parse(v)) : new Set(); } catch { return new Set(); }
  });
  const [cycleStrategyTypes, setCycleStrategyTypes] = useState<Set<string>>(() => {
    try { const v = localStorage.getItem('cycle_filter_types'); return v ? new Set(JSON.parse(v)) : new Set(); } catch { return new Set(); }
  });

  useEffect(() => { localStorage.setItem('cycle_filter_assets', JSON.stringify([...cycleAssetClasses])); }, [cycleAssetClasses]);
  useEffect(() => { localStorage.setItem('cycle_filter_intervals', JSON.stringify([...cycleIntervals])); }, [cycleIntervals]);
  useEffect(() => { localStorage.setItem('cycle_filter_types', JSON.stringify([...cycleStrategyTypes])); }, [cycleStrategyTypes]);

  // Signal activity state
  const [signalData, setSignalData] = useState<{
    signals: Array<{
      id: number;
      signal_id: string;
      strategy_id: string;
      symbol: string;
      side: string;
      signal_type: string;
      decision: string;
      rejection_reason: string | null;
      created_at: string;
      metadata: Record<string, any> | null;
    }>;
    summary: {
      total: number;
      accepted: number;
      rejected: number;
      acceptance_rate: number;
      rejection_reasons: Array<{ reason: string; count: number; percentage: number }>;
    };
  } | null>(null);
  const [signalFilter, setSignalFilter] = useState<string>('all');

  // Schedule state
  const [scheduleConfig, setScheduleConfig] = useState<{
    enabled: boolean;
    frequency: string;
    day_of_week: string;
    hour: number;
    minute: number;
  } | null>(null);
  const [nextScheduledRun, setNextScheduledRun] = useState<string | null>(null);
  const [lastScheduledRun, setLastScheduledRun] = useState<string | null>(null);
  const [scheduleUpdating, setScheduleUpdating] = useState(false);
  const [signalRefreshing, setSignalRefreshing] = useState(false);

  // Walk-Forward Analytics state (Task 9.4)
  const [walkForwardData, setWalkForwardData] = useState<any>(null);
  const [walkForwardLoading, setWalkForwardLoading] = useState(false);
  const [walkForwardPeriod, setWalkForwardPeriod] = useState<string>('3M');

  // Active tab state for main panel
  const [autoTab, setAutoTab] = useState<string>('control');

  // Schedule editing state
  const [editFrequency, setEditFrequency] = useState<string>('weekly');
  const [editDay, setEditDay] = useState<string>('saturday');
  const [editHour, setEditHour] = useState<number>(2);
  const [editMinute, setEditMinute] = useState<number>(0);

  // Fetch all data
  const fetchData = useCallback(async () => {
    if (!tradingMode) return;
    
    try {
      setRefreshing(true);
      setError(null);
      const [autoStatus, sysStatus, strategiesData, ordersData, signalResult, scheduleResult, cyclesResult] = await Promise.all([
        apiClient.getAutonomousStatus(),
        apiClient.getSystemStatus(),
        apiClient.getStrategies(tradingMode, false),
        apiClient.getOrders(tradingMode),
        apiClient.getRecentSignals(tradingMode, 100).catch(() => null),
        apiClient.getAutonomousSchedule().catch(() => null),
        apiClient.getAutonomousCycles(1).catch(() => null),
      ]);

      setAutonomousStatus(autoStatus);
      setSystemStatus(sysStatus);
      setStrategies(strategiesData);
      
      // Filter orders to only show autonomous orders (those with strategy_id)
      const autonomousOrders = ordersData
        .filter(order => order.strategy_id)
        .sort((a, b) => utcToLocal(b.created_at).getTime() - utcToLocal(a.created_at).getTime())
        .slice(0, 50); // Last 50 orders
      setOrders(autonomousOrders);

      // Apply signal activity data
      if (signalResult) {
        setSignalData(signalResult);
      }

      // Apply schedule config
      if (scheduleResult) {
        setScheduleConfig(scheduleResult.schedule);
        setNextScheduledRun(scheduleResult.next_run);
        setLastScheduledRun(scheduleResult.last_run);
      }

      // Apply last cycle data from cycle history
      if (cyclesResult) {
        const cycles = Array.isArray(cyclesResult) ? cyclesResult : (cyclesResult.data || []);
        if (cycles.length > 0) {
          const lastCycle = cycles[0];
          setLastCycleData({
            duration_seconds: lastCycle.duration_seconds,
            proposals_generated: lastCycle.proposals_generated ?? 0,
            backtest_passed: lastCycle.backtest_passed ?? 0,
            backtested: lastCycle.backtested ?? 0,
            activated: lastCycle.activated ?? 0,
            strategies_retired: lastCycle.strategies_retired ?? 0,
          });
        }
      }
      
      setLoading(false);
      setLastFetchedAt(new Date());

      // Fetch walk-forward analytics in background (Task 9.4)
      setWalkForwardLoading(true);
      apiClient.getWalkForwardAnalytics(tradingMode, walkForwardPeriod).then((data) => {
        setWalkForwardData(data);
      }).catch(() => setWalkForwardData(null)).finally(() => setWalkForwardLoading(false));
    } catch (err) {
      console.error('Failed to fetch autonomous data:', err);
      setError(classifyError(err, 'autonomous data'));
      toast.error('Failed to load autonomous data');
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  }, [tradingMode]);

  // Polling for data refresh
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchData,
    intervalMs: 60000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // WebSocket subscriptions
  useEffect(() => {
    const unsubscribeAutonomous = wsManager.onAutonomousStatus((status: AutonomousStatus) => {
      setAutonomousStatus(status);
    });

    const unsubscribeSystem = wsManager.onSystemState((status: SystemStatus) => {
      setSystemStatus(status);
    });

    const unsubscribeStrategy = wsManager.onStrategyUpdate((strategy: Strategy) => {
      setStrategies((prev) => {
        const index = prev.findIndex(s => s.id === strategy.id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = strategy;
          return updated;
        }
        return [strategy, ...prev];
      });
      toast.info(`Strategy updated: ${strategy.name}`);
    });

    const unsubscribeOrder = wsManager.onOrderUpdate((order: Order) => {
      if (order.strategy_id) {
        setOrders((prev) => {
          const index = prev.findIndex(o => o.id === order.id);
          if (index >= 0) {
            const updated = [...prev];
            updated[index] = order;
            return updated;
          }
          return [order, ...prev].slice(0, 50);
        });
        toast.info(`Order ${order.status.toLowerCase()}: ${order.symbol}`);
      }
    });

    // Subscribe to signal decision events for real-time updates
    const unsubscribeSignalDecision = wsManager.subscribe('signal_decision', (data: { data?: Record<string, unknown> }) => {
      const entry = data?.data;
      if (entry) {
        setSignalData((prev) => {
          if (!prev) {
            return {
              signals: [entry as any],
              summary: {
                total: 1,
                accepted: entry.decision === 'ACCEPTED' ? 1 : 0,
                rejected: entry.decision === 'REJECTED' ? 1 : 0,
                acceptance_rate: entry.decision === 'ACCEPTED' ? 100 : 0,
                rejection_reasons: [],
              },
            };
          }
          const newSignals = [entry as any, ...prev.signals].slice(0, 100);
          const accepted = newSignals.filter((s) => s.decision === 'ACCEPTED').length;
          const total = newSignals.length;
          return {
            signals: newSignals,
            summary: {
              ...prev.summary,
              total,
              accepted,
              rejected: total - accepted,
              acceptance_rate: total > 0 ? Math.round((accepted / total) * 1000) / 10 : 0,
            },
          };
        });
      }
    });

    // Subscribe to autonomous cycle events for stage tracking
    const unsubscribeCycle = wsManager.onAutonomousCycle((data: { event: string; data: Record<string, unknown> }) => {
      try {
        switch (data.event) {
          case 'cycle_started':
            setCycleStage('Running');
            setCycleProgress(5);
            setCurrentCycleMetrics({ proposed: 0, backtested: 0, activated: 0, retired: 0 });
            break;
          case 'cycle_completed':
            setCycleStage('Completed');
            setCycleProgress(100);
            // Refresh last cycle data from API
            apiClient.getAutonomousCycles(1).then((result) => {
              const cycles = Array.isArray(result) ? result : (result.data || []);
              if (cycles.length > 0) {
                const lastCycle = cycles[0];
                setLastCycleData({
                  duration_seconds: lastCycle.duration_seconds,
                  proposals_generated: lastCycle.proposals_generated ?? 0,
                  backtest_passed: lastCycle.backtest_passed ?? 0,
                  backtested: lastCycle.backtested ?? 0,
                  activated: lastCycle.activated ?? 0,
                  strategies_retired: lastCycle.strategies_retired ?? 0,
                });
              }
            }).catch(() => {});
            break;
          case 'strategies_proposed':
            setCycleStage('Backtesting');
            setCycleProgress(30);
            setCurrentCycleMetrics(prev => ({ ...prev, proposed: (data.data.count as number) || 0 }));
            break;
          case 'backtest_completed':
            setCycleProgress(prev => Math.min(prev + 5, 80));
            setCurrentCycleMetrics(prev => ({ ...prev, backtested: prev.backtested + 1 }));
            break;
          case 'strategy_activated':
            setCycleStage('Activating');
            setCycleProgress(prev => Math.min(prev + 3, 90));
            setCurrentCycleMetrics(prev => ({ ...prev, activated: prev.activated + 1 }));
            break;
          case 'strategy_retired':
            setCurrentCycleMetrics(prev => ({ ...prev, retired: prev.retired + 1 }));
            break;
          case 'error':
            setCycleStage('Error');
            setCycleProgress(0);
            break;
        }
      } catch (error) {
        console.error('Error processing cycle event:', error, data);
      }
    });

    return () => {
      unsubscribeAutonomous();
      unsubscribeSystem();
      unsubscribeStrategy();
      unsubscribeOrder();
      unsubscribeSignalDecision();
      unsubscribeCycle();
    };
  }, []);

  // Control handlers
  const handleStartTrading = async () => {
    if (!window.confirm('Start autonomous trading? This will activate signal generation and order execution.')) return;
    setTradingAction(true);
    try {
      await apiClient.startAutonomousTrading(true);
      await fetchData();
      toast.success('Trading started successfully');
    } catch (err: any) {
      toast.error(`Failed to start trading: ${err.message}`);
    } finally {
      setTradingAction(false);
    }
  };

  const handlePauseTrading = async () => {
    if (!window.confirm('Pause trading? Signal generation will stop but positions are maintained.')) return;
    setTradingAction(true);
    try {
      await apiClient.pauseAutonomousTrading(true);
      await fetchData();
      toast.success('Trading paused');
    } catch (err: any) {
      toast.error(`Failed to pause trading: ${err.message}`);
    } finally {
      setTradingAction(false);
    }
  };

  const handleStopTrading = async () => {
    if (!window.confirm('Stop trading? All autonomous operations will halt.')) return;
    setTradingAction(true);
    try {
      await apiClient.stopAutonomousTrading(true);
      await fetchData();
      toast.success('Trading stopped');
    } catch (err: any) {
      toast.error(`Failed to stop trading: ${err.message}`);
    } finally {
      setTradingAction(false);
    }
  };

  const handleResumeTrading = async () => {
    if (!window.confirm('Resume trading? Signal generation and order execution will restart.')) return;
    setTradingAction(true);
    try {
      await apiClient.resumeAutonomousTrading(true);
      await fetchData();
      toast.success('Trading resumed');
    } catch (err: any) {
      toast.error(`Failed to resume trading: ${err.message}`);
    } finally {
      setTradingAction(false);
    }
  };

  const handleTriggerCycle = async () => {
    const filterSummary: string[] = [];
    if (cycleAssetClasses.size > 0) filterSummary.push(`Assets: ${[...cycleAssetClasses].join(', ')}`);
    if (cycleIntervals.size > 0) filterSummary.push(`Intervals: ${[...cycleIntervals].join(', ')}`);
    if (cycleStrategyTypes.size > 0) filterSummary.push(`Types: ${[...cycleStrategyTypes].join(', ')}`);
    const filterMsg = filterSummary.length > 0 ? `\n\nFilters: ${filterSummary.join(' | ')}` : '\n\nNo filters (all strategies)';
    
    if (!window.confirm(`Trigger an autonomous cycle? This will propose, backtest, and activate new strategies.${filterMsg}`)) return;
    
    // Reset progress
    setCycleStage('Initializing');
    setCycleProgress(5);
    
    setTriggering(true);
    try {
      const filters: Record<string, string[]> = {};
      if (cycleAssetClasses.size > 0) filters.asset_classes = [...cycleAssetClasses];
      if (cycleIntervals.size > 0) filters.intervals = [...cycleIntervals];
      if (cycleStrategyTypes.size > 0) filters.strategy_types = [...cycleStrategyTypes];
      
      const result = await apiClient.triggerAutonomousCycle(false, Object.keys(filters).length > 0 ? filters : undefined);
      if (result.success) {
        toast.success(`Cycle started (ID: ${result.cycle_id})`);
        await fetchData();
      }
    } catch (err: any) {
      toast.error(`Failed to trigger cycle: ${err.message}`);
      setCycleStage('Error');
      setCycleProgress(0);
    } finally {
      setTriggering(false);
    }
  };

  const handleToggleSchedule = async () => {
    if (!scheduleConfig) return;
    setScheduleUpdating(true);
    try {
      const newEnabled = !scheduleConfig.enabled;
      const result = await apiClient.updateAutonomousSchedule({
        ...scheduleConfig,
        enabled: newEnabled,
      });
      setScheduleConfig(result.schedule);
      setNextScheduledRun(result.next_run);
      toast.success(newEnabled ? 'Scheduled runs enabled' : 'Scheduled runs disabled');
    } catch (err: any) {
      toast.error(`Failed to update schedule: ${err.message}`);
    } finally {
      setScheduleUpdating(false);
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleUpdating(true);
    try {
      const result = await apiClient.updateAutonomousSchedule({
        enabled: scheduleConfig?.enabled ?? true,
        frequency: editFrequency,
        day_of_week: editDay,
        hour: editHour,
        minute: editMinute,
      });
      setScheduleConfig(result.schedule);
      setNextScheduledRun(result.next_run);
      toast.success('Schedule updated');
    } catch (err: any) {
      toast.error(`Failed to update schedule: ${err.message}`);
    } finally {
      setScheduleUpdating(false);
    }
  };

  // Sync edit state when scheduleConfig loads
  useEffect(() => {
    if (scheduleConfig) {
      setEditFrequency(scheduleConfig.frequency);
      setEditDay(scheduleConfig.day_of_week);
      setEditHour(scheduleConfig.hour);
      setEditMinute(scheduleConfig.minute);
    }
  }, [scheduleConfig]);

  const handleRefreshSignals = async () => {
    if (!tradingMode) return;
    setSignalRefreshing(true);
    try {
      const signalResult = await apiClient.getRecentSignals(tradingMode, 100);
      setSignalData(signalResult);
      toast.success('Signal activity refreshed');
    } catch (err: any) {
      toast.error(`Failed to refresh signals: ${err.message}`);
    } finally {
      setSignalRefreshing(false);
    }
  };

  // Helper functions
  const getConfidenceLabel = (confidence: number): { label: string; color: string } => {
    if (confidence >= 0.15) return { label: 'Strong', color: 'text-accent-green' };
    if (confidence >= 0.08) return { label: 'Moderate', color: 'text-yellow-400' };
    if (confidence >= 0.03) return { label: 'Mild', color: 'text-orange-400' };
    return { label: 'Weak', color: 'text-gray-400' };
  };

  const getRegimeColor = (regime: string): string => {
    switch (regime.toUpperCase()) {
      case 'TRENDING_UP': return 'text-accent-green';
      case 'TRENDING_DOWN': return 'text-accent-red';
      case 'RANGING': return 'text-blue-400';
      case 'VOLATILE': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getRegimeIcon = (regime: string): string => {
    switch (regime.toUpperCase()) {
      case 'TRENDING_UP': return '↗️';
      case 'TRENDING_DOWN': return '↘️';
      case 'RANGING': return '↔️';
      case 'VOLATILE': return '⚡';
      default: return '📊';
    }
  };

  const getTradingStateColor = (state: SystemState): string => {
    switch (state) {
      case 'ACTIVE': return 'bg-accent-green/20 text-accent-green border-accent-green/30';
      case 'PAUSED': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'STOPPED': return 'bg-accent-red/20 text-accent-red border-accent-red/30';
      case 'EMERGENCY_HALT': return 'bg-red-900/40 text-red-400 border-red-700/50';
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  const getTradingStateLabel = (state: SystemState): string => {
    switch (state) {
      case 'ACTIVE': return '● TRADING ACTIVE';
      case 'PAUSED': return '⏸ TRADING PAUSED';
      case 'STOPPED': return '○ TRADING STOPPED';
      case 'EMERGENCY_HALT': return '⚠ EMERGENCY HALT';
      default: return '? UNKNOWN';
    }
  };

  // Filter strategies
  const filteredStrategies = strategies.filter(strategy => {
    const matchesSearch = strategy.name.toLowerCase().includes(strategySearch.toLowerCase()) ||
                         strategy.symbols.some(s => s.toLowerCase().includes(strategySearch.toLowerCase()));
    const matchesStage = strategyStageFilter === 'all' || strategy.status === strategyStageFilter;
    return matchesSearch && matchesStage;
  });

  // Filter orders
  const filteredOrders = orders.filter(order => {
    const matchesSearch = order.symbol.toLowerCase().includes(orderSearch.toLowerCase());
    const matchesStatus = orderStatusFilter === 'all' || order.status === orderStatusFilter;
    const matchesSide = orderSideFilter === 'all' || order.side === orderSideFilter;
    return matchesSearch && matchesStatus && matchesSide;
  });

  // Calculate lifecycle counts
  const lifecycleCounts = {
    proposed: strategies.filter(s => s.status === 'PROPOSED').length,
    backtested: strategies.filter(s => s.status === 'BACKTESTED').length,
    active: strategies.filter(s => s.status === 'DEMO' || s.status === 'LIVE').length,
    retired: strategies.filter(s => s.status === 'RETIRED').length,
  };

  // Calculate performance metrics
  const activeStrategies = strategies.filter(s => s.status === 'DEMO' || s.status === 'LIVE');
  const avgSharpe = activeStrategies.length > 0
    ? activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.sharpe_ratio || 0), 0) / activeStrategies.length
    : 0;
  const avgReturn = activeStrategies.length > 0
    ? activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.total_return || 0), 0) / activeStrategies.length
    : 0;
  const avgWinRate = activeStrategies.length > 0
    ? activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.win_rate || 0), 0) / activeStrategies.length
    : 0;

  // Calculate activation and retirement rates
  const totalProposed = autonomousStatus?.cycle_stats.proposals_count || 0;
  const totalActivated = autonomousStatus?.cycle_stats.activated_count || 0;
  const totalRetired = autonomousStatus?.cycle_stats.retired_count || 0;
  const activationRate = totalProposed > 0 ? (totalActivated / totalProposed) * 100 : 0;
  const retirementRate = totalActivated > 0 ? (totalRetired / totalActivated) * 100 : 0;

  // Table columns for strategies
  const strategyColumns: ColumnDef<Strategy>[] = [
    {
      accessorKey: 'name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div>
          <div className="font-mono font-semibold text-sm">{row.original.name}</div>
          {row.original.template_name && (
            <div className="text-xs text-muted-foreground mt-0.5">
              Template: {row.original.template_name}
            </div>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'symbols',
      header: 'Symbols',
      cell: ({ row }) => (
        <div className="font-mono text-xs">
          {row.original.symbols.slice(0, 3).join(', ')}
          {row.original.symbols.length > 3 && ` +${row.original.symbols.length - 3}`}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Stage',
      cell: ({ row }) => {
        const statusColors: Record<string, string> = {
          PROPOSED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
          BACKTESTED: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
          DEMO: 'bg-accent-green/20 text-accent-green border-accent-green/30',
          LIVE: 'bg-accent-green/20 text-accent-green border-accent-green/30',
          RETIRED: 'bg-accent-red/20 text-accent-red border-accent-red/30',
        };
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold border whitespace-nowrap',
            statusColors[row.original.status] || statusColors.PROPOSED
          )}>
            {row.original.status}
          </span>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.sharpe_ratio',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">
            {row.original.performance_metrics?.sharpe_ratio?.toFixed(2) || 
             row.original.backtest_results?.sharpe_ratio?.toFixed(2) || 
             '—'}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'performance_metrics.total_return',
      header: () => <div className="text-right">Return</div>,
      cell: ({ row }) => {
        const returnValue = row.original.performance_metrics?.total_return || 
                           row.original.backtest_results?.total_return || 0;
        return (
          <div className="text-right">
            <span className={cn(
              'font-mono text-sm',
              returnValue >= 0 ? 'text-accent-green' : 'text-accent-red'
            )}>
              {formatPercentage(returnValue)}
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: 'created_at',
      header: () => <div className="text-right">Created</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {utcToLocal(row.original.created_at).toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      ),
    },
  ];

  // Table columns for orders
  const orderColumns: ColumnDef<Order>[] = [
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div className="font-mono font-semibold text-sm">{row.original.symbol}</div>
      ),
    },
    {
      accessorKey: 'side',
      header: 'Side',
      cell: ({ row }) => (
        <span className={cn(
          'px-2 py-0.5 rounded text-xs font-mono font-semibold whitespace-nowrap',
          row.original.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'
        )}>
          {row.original.side}
        </span>
      ),
    },
    {
      accessorKey: 'type',
      header: 'Type',
      cell: ({ row }) => (
        <span className="font-mono text-xs">{row.original.type}</span>
      ),
    },
    {
      accessorKey: 'quantity',
      header: () => <div className="text-right">Qty</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{row.original.quantity.toFixed(2)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'price',
      header: () => <div className="text-right">Price</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm whitespace-nowrap">
            {row.original.price ? formatCurrency(row.original.price) : 'Market'}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const statusColors: Record<string, string> = {
          PENDING: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
          FILLED: 'bg-accent-green/20 text-accent-green border-accent-green/30',
          PARTIALLY_FILLED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
          CANCELLED: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
          REJECTED: 'bg-accent-red/20 text-accent-red border-accent-red/30',
        };
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold border whitespace-nowrap',
            statusColors[row.original.status] || statusColors.PENDING
          )}>
            {row.original.status}
          </span>
        );
      },
    },
    {
      accessorKey: 'created_at',
      header: () => <div className="text-right">Time</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {utcToLocal(row.original.created_at).toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      ),
    },
  ];

  // ── Side panel compact metrics ─────────────────────────────────────────
  const cycleStatusLabel = autonomousStatus?.enabled
    ? (cycleProgress > 0 && cycleProgress < 100 ? 'Running' : 'Idle')
    : 'Disabled';
  const cycleStatusTrend = autonomousStatus?.enabled ? 'up' as const : 'neutral' as const;

  const wfPassRate = useMemo(() => {
    if (!lastCycleData || lastCycleData.backtested === 0) return '—';
    return `${((lastCycleData.backtest_passed / lastCycleData.backtested) * 100).toFixed(0)}%`;
  }, [lastCycleData]);

  const proposalsThisWeek = lastCycleData?.proposals_generated ?? 0;

  const sideMetrics: CompactMetric[] = useMemo(() => [
    { label: 'Cycle', value: cycleStatusLabel, trend: cycleStatusTrend },
    { label: 'Pass Rate', value: wfPassRate, trend: wfPassRate !== '—' && parseInt(wfPassRate) >= 50 ? 'up' as const : 'down' as const },
    { label: 'Proposals', value: proposalsThisWeek },
    { label: 'Active', value: lifecycleCounts.active, trend: 'up' as const },
  ], [cycleStatusLabel, cycleStatusTrend, wfPassRate, proposalsThisWeek, lifecycleCounts.active]);

  // ── Loading state ──────────────────────────────────────────────────────
  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="🤖 Autonomous" description="Autonomous trading system" compact={true}>
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  // ── Header actions ─────────────────────────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <button
        onClick={fetchData}
        disabled={refreshing}
        className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
        title="Refresh"
      >
        <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
      </button>
    </div>
  );

  const autoTabButtons = [
    { value: 'control', label: 'Control' },
    { value: 'lifecycle', label: `Lifecycle (${filteredStrategies.length})` },
    { value: 'activity', label: `Activity (${filteredOrders.length})` },
    { value: 'signals', label: 'Signals' },
    { value: 'performance', label: 'Performance' },
    { value: 'walkforward', label: 'Walk-Forward' },
    { value: 'conviction', label: 'Conviction' },
  ];

  const mainPanel = (
    <div className="flex flex-col h-full">
      <RefreshIndicator visible={pollingRefreshing || refreshing} />
      {/* Single 32px header row: inline tabs + actions */}
      <div className="flex items-center px-3 min-h-[32px] max-h-[32px] shrink-0 bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]">
        <div className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide flex-1 min-w-0">
          {autoTabButtons.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setAutoTab(tab.value)}
              className={cn(
                'px-2.5 py-1 text-xs font-medium rounded whitespace-nowrap transition-colors shrink-0',
                autoTab === tab.value
                  ? 'bg-gray-700/60 text-gray-100'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/40'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          <button
            onClick={fetchData}
            className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} className={cn(refreshing && 'animate-spin')} />
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-auto px-2 pb-2">
      <Tabs value={autoTab} onValueChange={setAutoTab} className="flex flex-col h-full">
        {/* Hidden TabsList — we use custom buttons above */}
        <div className="flex-1 min-h-0 overflow-auto">

            {/* Tab 1: Control & Status */}
            <TabsContent value="control" className="space-y-3 p-2">
              {/* Status Badges — inline */}
              <div className="flex items-center gap-2 flex-wrap">
                {systemStatus && (
                  <div className={cn(
                    'px-3 py-1 rounded text-xs font-mono border',
                    getTradingStateColor(systemStatus.state)
                  )}>
                    {getTradingStateLabel(systemStatus.state)}
                  </div>
                )}
                {autonomousStatus && (
                  <div className={cn(
                    'px-3 py-1 rounded text-xs font-mono border',
                    autonomousStatus.enabled
                      ? 'bg-[#22c55e]/20 text-[#22c55e] border-[#22c55e]/30'
                      : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                  )}>
                    {autonomousStatus.enabled ? '● AUTO ENABLED' : '○ AUTO DISABLED'}
                  </div>
                )}
              </div>

              {/* Research Filters — flat inline row */}
              <div className="flex flex-wrap items-center gap-3 py-2 border-b border-[var(--color-dark-border)]">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 tracking-wide">Assets:</span>
                  <div className="flex flex-wrap gap-1">
                    {['stock', 'etf', 'crypto', 'forex', 'index', 'commodity'].map(ac => (
                      <button key={ac} onClick={() => {
                        const next = new Set(cycleAssetClasses);
                        next.has(ac) ? next.delete(ac) : next.add(ac);
                        setCycleAssetClasses(next);
                      }} className={cn(
                        'px-2 py-0.5 rounded text-[11px] font-medium border transition-colors',
                        cycleAssetClasses.has(ac)
                          ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                          : 'border-gray-700 text-gray-500 hover:border-blue-500/50'
                      )}>{ac.charAt(0).toUpperCase() + ac.slice(1)}</button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 tracking-wide">TF:</span>
                  <div className="flex gap-1">
                    {[{ key: '1d', label: 'Daily' }, { key: '1h', label: '1H' }, { key: '4h', label: '4H' }].map(({ key, label }) => (
                      <button key={key} onClick={() => {
                        const next = new Set(cycleIntervals);
                        next.has(key) ? next.delete(key) : next.add(key);
                        setCycleIntervals(next);
                      }} className={cn(
                        'px-2 py-0.5 rounded text-[11px] font-medium border transition-colors',
                        cycleIntervals.has(key)
                          ? 'bg-[#22c55e]/20 border-[#22c55e] text-[#22c55e]'
                          : 'border-gray-700 text-gray-500 hover:border-[#22c55e]/50'
                      )}>{label}</button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 tracking-wide">Type:</span>
                  <div className="flex gap-1">
                    {[{ key: 'dsl', label: 'DSL' }, { key: 'alpha_edge', label: 'AE' }].map(({ key, label }) => (
                      <button key={key} onClick={() => {
                        const next = new Set(cycleStrategyTypes);
                        next.has(key) ? next.delete(key) : next.add(key);
                        setCycleStrategyTypes(next);
                      }} className={cn(
                        'px-2 py-0.5 rounded text-[11px] font-medium border transition-colors',
                        cycleStrategyTypes.has(key)
                          ? 'bg-yellow-500/20 border-yellow-500 text-yellow-400'
                          : 'border-gray-700 text-gray-500 hover:border-yellow-500/50'
                      )}>{label}</button>
                    ))}
                  </div>
                </div>
                {(cycleAssetClasses.size > 0 || cycleIntervals.size > 0 || cycleStrategyTypes.size > 0) && (
                  <button onClick={() => { setCycleAssetClasses(new Set()); setCycleIntervals(new Set()); setCycleStrategyTypes(new Set()); }}
                    className="text-[10px] text-[#ef4444] hover:underline">Clear</button>
                )}
                <Button
                  onClick={handleTriggerCycle}
                  disabled={triggering || !autonomousStatus?.enabled}
                  size="sm"
                  className="gap-1.5 ml-auto bg-[#22c55e] hover:bg-[#22c55e]/80 text-black font-semibold h-7 text-[11px]"
                >
                  <RefreshCw className={cn('h-3 w-3', triggering && 'animate-spin')} />
                  {triggering ? 'Running...' : 'Run Cycle'}
                </Button>
              </div>

              {/* Trading Cycle Pipeline */}
              <TradingCyclePipeline cycleRunning={triggering || (cycleProgress > 0 && cycleProgress < 100)} />

              {/* Controls + Schedule — 2-column grid, flat sections */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* Left Column - Controls */}
                <div className="space-y-3">
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Controls</div>

                    {/* Trading State Warning */}
                    {systemStatus && systemStatus.state !== 'ACTIVE' && lifecycleCounts.active > 0 && (
                      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-2">
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-3.5 w-3.5 text-yellow-400 shrink-0" />
                          <span className="text-[10px] text-yellow-400">{lifecycleCounts.active} strategies ready but trading is {systemStatus.state}.</span>
                        </div>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-1.5">
                        {(!systemStatus || systemStatus.state === 'STOPPED') && (
                          <Button onClick={handleStartTrading} disabled={tradingAction} variant="outline" size="sm"
                            className="justify-start gap-1.5 h-7 text-[11px] border-[#22c55e]/30 text-[#22c55e] hover:bg-[#22c55e]/10">
                            <PlayCircle className="h-3 w-3" />
                            {tradingAction ? 'Starting...' : 'Start'}
                          </Button>
                        )}
                        {systemStatus?.state === 'ACTIVE' && (
                          <>
                            <Button onClick={handlePauseTrading} disabled={tradingAction} variant="outline" size="sm"
                              className="justify-start gap-1.5 h-7 text-[11px] border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10">
                              <PauseCircle className="h-3 w-3" />
                              Pause
                            </Button>
                            <Button onClick={handleStopTrading} disabled={tradingAction} variant="outline" size="sm"
                              className="justify-start gap-1.5 h-7 text-[11px] border-[#ef4444]/30 text-[#ef4444] hover:bg-[#ef4444]/10">
                              <AlertCircle className="h-3 w-3" />
                              Stop
                            </Button>
                          </>
                        )}
                        {systemStatus?.state === 'PAUSED' && (
                          <>
                            <Button onClick={handleResumeTrading} disabled={tradingAction} variant="outline" size="sm"
                              className="justify-start gap-1.5 h-7 text-[11px] border-[#22c55e]/30 text-[#22c55e] hover:bg-[#22c55e]/10">
                              <PlayCircle className="h-3 w-3" />
                              Resume
                            </Button>
                            <Button onClick={handleStopTrading} disabled={tradingAction} variant="outline" size="sm"
                              className="justify-start gap-1.5 h-7 text-[11px] border-[#ef4444]/30 text-[#ef4444] hover:bg-[#ef4444]/10">
                              <AlertCircle className="h-3 w-3" />
                              Stop
                            </Button>
                          </>
                        )}
                        <Button onClick={() => navigate('/settings')} variant="outline" size="sm" className="justify-start gap-1.5 h-7 text-[11px]">
                          <Settings className="h-3 w-3" />
                          Settings
                        </Button>
                        <Button
                          onClick={async () => {
                            try {
                              const result = await apiClient.clearBlacklists();
                              toast.success(result.message || 'Blacklists cleared');
                            } catch (err: any) {
                              toast.error(`Failed: ${err.message}`);
                            }
                          }}
                          variant="outline" size="sm"
                          className="justify-start gap-1.5 h-7 text-[11px] text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10"
                        >
                          <Trash2 className="h-3 w-3" />
                          Clear Caches
                        </Button>
                    </div>

                    {autonomousStatus && !autonomousStatus.enabled && (
                      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-2">
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-3.5 w-3.5 text-yellow-400 shrink-0" />
                          <span className="text-[10px] text-yellow-400">Auto-Management Disabled — enable in settings.</span>
                        </div>
                      </div>
                    )}
                </div>

                {/* Right Column - Schedule */}
                <div className="space-y-3">
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Scheduled Execution</div>
                    {scheduleConfig ? (
                      <>
                        {/* Enable/Disable toggle */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">
                            {scheduleConfig.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                          <button
                            onClick={handleToggleSchedule}
                            disabled={scheduleUpdating}
                            className={cn(
                              'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none',
                              scheduleConfig.enabled ? 'bg-accent-green' : 'bg-gray-600'
                            )}
                          >
                            <span className={cn(
                              'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform',
                              scheduleConfig.enabled ? 'translate-x-5' : 'translate-x-0.5'
                            )} />
                          </button>
                        </div>

                        {/* Frequency */}
                        <div className="space-y-1">
                          <label className="text-[11px] text-muted-foreground">Frequency</label>
                          <div className="flex gap-1">
                            {['daily', 'weekly'].map((freq) => (
                              <button key={freq} onClick={() => {
                                setEditFrequency(freq);
                                if (freq === 'daily' && editHour === 2) setEditHour(22);
                                if (freq === 'weekly' && editHour === 22) setEditHour(2);
                              }} className={cn(
                                'px-2 py-0.5 text-xs rounded-md border transition-colors',
                                editFrequency === freq
                                  ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                                  : 'border-border text-muted-foreground hover:border-blue-500/50'
                              )}>
                                {freq.charAt(0).toUpperCase() + freq.slice(1)}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Day of week (weekly only) */}
                        {editFrequency === 'weekly' && (
                          <div className="space-y-1">
                            <label className="text-[11px] text-muted-foreground">Day</label>
                            <select value={editDay} onChange={(e) => setEditDay(e.target.value)}
                              className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs">
                              {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map((day) => (
                                <option key={day} value={day}>{day.charAt(0).toUpperCase() + day.slice(1)}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {/* Time picker */}
                        <div className="space-y-1">
                          <label className="text-[11px] text-muted-foreground">Time (UTC)</label>
                          <div className="flex gap-1 items-center">
                            <select value={editHour} onChange={(e) => setEditHour(parseInt(e.target.value))}
                              className="bg-background border border-border rounded-md px-1.5 py-0.5 text-xs w-14">
                              {Array.from({ length: 24 }, (_, i) => (
                                <option key={i} value={i}>{i.toString().padStart(2, '0')}</option>
                              ))}
                            </select>
                            <span className="text-muted-foreground text-xs">:</span>
                            <select value={editMinute} onChange={(e) => setEditMinute(parseInt(e.target.value))}
                              className="bg-background border border-border rounded-md px-1.5 py-0.5 text-xs w-14">
                              {[0, 15, 30, 45].map((m) => (
                                <option key={m} value={m}>{m.toString().padStart(2, '0')}</option>
                              ))}
                            </select>
                            <span className="text-[11px] text-muted-foreground">UTC</span>
                          </div>
                        </div>

                        {/* Save button */}
                        {(editFrequency !== scheduleConfig.frequency ||
                          editDay !== scheduleConfig.day_of_week ||
                          editHour !== scheduleConfig.hour ||
                          editMinute !== scheduleConfig.minute) && (
                          <button onClick={handleSaveSchedule} disabled={scheduleUpdating}
                            className="w-full px-2 py-1 text-xs rounded-md bg-blue-500 hover:bg-blue-600 text-white transition-colors disabled:opacity-50">
                            {scheduleUpdating ? 'Saving...' : 'Save Schedule'}
                          </button>
                        )}

                        {/* Next run */}
                        {nextScheduledRun && scheduleConfig.enabled && (
                          <div className="bg-muted/50 rounded-lg p-2 flex items-center gap-2">
                            <Clock className="h-3 w-3 text-blue-400 flex-shrink-0" />
                            <div>
                              <div className="text-[11px] text-muted-foreground">Next Run</div>
                              <div className="text-xs font-mono text-blue-400">
                                {new Date(nextScheduledRun).toLocaleString('en-US', {
                                  weekday: 'short', month: 'short', day: 'numeric',
                                  hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
                                })}
                              </div>
                            </div>
                          </div>
                        )}
                        {lastScheduledRun && (
                          <div className="text-[11px] text-muted-foreground">
                            Last run: {formatTimestamp(lastScheduledRun)}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-xs text-muted-foreground">Loading schedule...</div>
                    )}
                </div>
              </div>

              {/* Demo Mode Warning */}
              {tradingMode === 'DEMO' && (
                <div className="bg-yellow-500/5 border border-yellow-500/30 rounded-lg p-3 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-yellow-400">Demo Mode Active</p>
                    <p className="text-[10px] text-yellow-400/80">All trades are simulated.</p>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Tab 2: Strategy Lifecycle */}
            <TabsContent value="lifecycle" className="space-y-3 p-2">
              {/* Lifecycle stage buttons — compact inline row */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { key: 'PROPOSED', label: 'Proposed', count: lifecycleCounts.proposed, color: 'blue' },
                  { key: 'BACKTESTED', label: 'Backtested', count: lifecycleCounts.backtested, color: 'purple' },
                  { key: 'DEMO', label: 'Active', count: lifecycleCounts.active, color: 'green' },
                  { key: 'RETIRED', label: 'Retired', count: lifecycleCounts.retired, color: 'red' },
                ].map(s => (
                  <button key={s.key}
                    onClick={() => setStrategyStageFilter(strategyStageFilter === s.key ? 'all' : s.key)}
                    className={cn(
                      'flex items-center justify-between rounded-md border px-3 py-2 transition-all cursor-pointer',
                      `bg-${s.color}-500/10 border-${s.color}-500/30`,
                      strategyStageFilter === s.key && `ring-1 ring-${s.color}-500`,
                    )}
                    style={{
                      backgroundColor: `color-mix(in srgb, ${s.color === 'green' ? '#22c55e' : s.color === 'red' ? '#ef4444' : s.color === 'blue' ? '#3b82f6' : '#8b5cf6'} 10%, transparent)`,
                      borderColor: `color-mix(in srgb, ${s.color === 'green' ? '#22c55e' : s.color === 'red' ? '#ef4444' : s.color === 'blue' ? '#3b82f6' : '#8b5cf6'} 30%, transparent)`,
                    }}
                  >
                    <span className="text-[11px] text-gray-400">{s.label}</span>
                    <span className="text-lg font-mono font-bold text-gray-200">{s.count}</span>
                  </button>
                ))}
              </div>

              {/* Filters + table — flat, no PanelHeader wrapper */}
              <div className="flex items-center gap-2 py-1">
                <span className="text-[11px] text-gray-500">{filteredStrategies.length} of {strategies.length}</span>
                <div className="relative ml-auto">
                  <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-gray-500" />
                  <Input placeholder="Search..." value={strategySearch}
                    onChange={(e) => setStrategySearch(e.target.value)}
                    className="pl-7 h-7 text-[11px] w-[150px]" />
                </div>
                <Select value={strategyStageFilter} onValueChange={setStrategyStageFilter}>
                  <SelectTrigger className="w-[110px] h-7 text-[11px]">
                    <SelectValue placeholder="Stage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Stages</SelectItem>
                    <SelectItem value="PROPOSED">Proposed</SelectItem>
                    <SelectItem value="BACKTESTED">Backtested</SelectItem>
                    <SelectItem value="DEMO">Demo</SelectItem>
                    <SelectItem value="RETIRED">Retired</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {filteredStrategies.length > 0 ? (
                <DataTable columns={strategyColumns} data={filteredStrategies} pageSize={20} showPagination={true} className="[&_table]:table-dense [&_td]:py-1 [&_th]:py-1" />
              ) : (
                <div className="text-center py-6 text-gray-500 text-[11px]">
                  {strategySearch || strategyStageFilter !== 'all' ? 'No strategies match filters' : 'No strategies found'}
                </div>
              )}
            </TabsContent>

            {/* Tab 3: Recent Activity */}
            <TabsContent value="activity" className="space-y-2 p-2">
              {/* Filters — flat inline row */}
              <div className="flex items-center gap-2 py-1">
                <span className="text-[11px] text-gray-500">Last 50 orders · {filteredOrders.length} of {orders.length}</span>
                <div className="relative ml-auto">
                  <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-gray-500" />
                  <Input placeholder="Search symbol..." value={orderSearch}
                    onChange={(e) => setOrderSearch(e.target.value)}
                    className="pl-7 h-7 text-[11px] w-[150px]" />
                </div>
                <Select value={orderStatusFilter} onValueChange={setOrderStatusFilter}>
                  <SelectTrigger className="w-[100px] h-7 text-[11px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="PENDING">Pending</SelectItem>
                    <SelectItem value="FILLED">Filled</SelectItem>
                    <SelectItem value="CANCELLED">Cancelled</SelectItem>
                    <SelectItem value="REJECTED">Rejected</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={orderSideFilter} onValueChange={setOrderSideFilter}>
                  <SelectTrigger className="w-[90px] h-7 text-[11px]">
                    <SelectValue placeholder="Side" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="BUY">Buy</SelectItem>
                    <SelectItem value="SELL">Sell</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {filteredOrders.length > 0 ? (
                <DataTable columns={orderColumns} data={filteredOrders} pageSize={20} showPagination={true} className="[&_table]:table-dense [&_td]:py-1 [&_th]:py-1" />
              ) : (
                <div className="text-center py-6 text-gray-500 text-[11px]">
                  {orderSearch || orderStatusFilter !== 'all' || orderSideFilter !== 'all'
                    ? 'No orders match filters' : 'No autonomous orders found'}
                </div>
              )}
            </TabsContent>

            {/* Tab 4: Signal Activity */}
            <TabsContent value="signals" className="space-y-3 p-2">
              {/* Signal metrics — inline dense grid */}
              <div className="flex items-center gap-2">
                <div className="grid grid-cols-4 gap-2 flex-1">
                  {[
                    { label: 'Generated', value: String(signalData?.summary.total ?? 0), color: 'text-gray-200' },
                    { label: 'Accepted', value: String(signalData?.summary.accepted ?? 0), color: 'text-[#22c55e]' },
                    { label: 'Rejected', value: String(signalData?.summary.rejected ?? 0), color: 'text-[#ef4444]' },
                    { label: 'Accept Rate', value: `${signalData?.summary.acceptance_rate ?? 0}%`, color: 'text-blue-400' },
                  ].map((m, i) => (
                    <div key={i} className="rounded-md p-2 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)]">
                      <div className="text-xs text-gray-500 tracking-wide">{m.label}</div>
                      <div className={cn('text-sm font-mono font-bold mt-0.5', m.color)}>{m.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={handleRefreshSignals} disabled={signalRefreshing}
                  className="p-1.5 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors shrink-0" title="Refresh signals">
                  <RefreshCw className={cn('h-3.5 w-3.5', signalRefreshing && 'animate-spin')} />
                </button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                {/* Rejection Reasons — flat section */}
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Rejection Reasons</div>
                  {signalData?.summary.rejection_reasons && signalData.summary.rejection_reasons.length > 0 ? (
                    <div className="space-y-1.5">
                      {signalData.summary.rejection_reasons.map((r) => (
                        <div key={r.reason}>
                          <div className="flex justify-between text-[10px] mb-0.5">
                            <span className="text-gray-300 truncate">{r.reason}</span>
                            <span className="text-gray-500 ml-2 shrink-0">{r.count} ({r.percentage.toFixed(0)}%)</span>
                          </div>
                          <div className="w-full bg-gray-800 rounded-full h-1">
                            <div className="bg-[#ef4444]/70 h-1 rounded-full" style={{ width: `${Math.min(r.percentage, 100)}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-[10px]">No rejections recorded.</p>
                  )}
                </div>

                {/* Recent Signals Table — flat */}
                <div className="lg:col-span-2">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Recent Signals</div>
                    <Select value={signalFilter} onValueChange={setSignalFilter}>
                      <SelectTrigger className="w-[90px] h-6 text-[10px]">
                        <SelectValue placeholder="Filter" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="ACCEPTED">Accepted</SelectItem>
                        <SelectItem value="REJECTED">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="max-h-[350px] overflow-y-auto">
                    <table className="w-full text-[11px] font-mono">
                      <thead className="sticky top-0 bg-[var(--color-dark-bg)]">
                        <tr className="border-b border-[var(--color-dark-border)] text-gray-500 text-[10px]">
                          <th className="text-left py-1 pr-2">Time</th>
                          <th className="text-left py-1 pr-2">Symbol</th>
                          <th className="text-left py-1 pr-2">Side</th>
                          <th className="text-left py-1 pr-2">Decision</th>
                          <th className="text-left py-1">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(signalData?.signals ?? [])
                          .filter(s => signalFilter === 'all' || s.decision === signalFilter)
                          .slice(0, 50)
                          .map((s) => (
                          <tr key={s.id} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/30">
                            <td className="py-1 pr-2 text-[11px] text-gray-500 whitespace-nowrap">
                              {utcToLocal(s.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            </td>
                            <td className="py-1 pr-2 font-semibold text-gray-200">{s.symbol}</td>
                            <td className="py-1 pr-2">
                              <span className={cn('px-1 py-0.5 rounded text-[10px]',
                                s.side === 'BUY' ? 'bg-[#22c55e]/20 text-[#22c55e]' : 'bg-[#ef4444]/20 text-[#ef4444]')}>
                                {s.side}
                              </span>
                            </td>
                            <td className="py-1 pr-2">
                              <span className={cn('px-1 py-0.5 rounded text-[10px] font-semibold',
                                s.decision === 'ACCEPTED' ? 'bg-[#22c55e]/20 text-[#22c55e]' : 'bg-[#ef4444]/20 text-[#ef4444]')}>
                                {s.decision}
                              </span>
                            </td>
                            <td className="py-1 text-[11px] text-gray-500 truncate max-w-[150px]" title={s.rejection_reason || ''}>
                              {s.rejection_reason || '—'}
                            </td>
                          </tr>
                        ))}
                        {(!signalData?.signals || signalData.signals.length === 0) && (
                          <tr><td colSpan={5} className="py-6 text-center text-gray-500 text-[10px]">No signal decisions recorded.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </TabsContent>

            {/* Tab 5: Performance */}
            <TabsContent value="performance" className="space-y-3 p-2">
              {/* Performance + Lifecycle metrics — single dense grid */}
              <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
                {[
                  { label: 'Avg Sharpe', value: avgSharpe.toFixed(2), color: avgSharpe >= 1 ? 'text-[#22c55e]' : 'text-gray-200' },
                  { label: 'Avg Return', value: `${avgReturn >= 0 ? '+' : ''}${(avgReturn * 100).toFixed(2)}%`, color: avgReturn >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]' },
                  { label: 'Avg Win Rate', value: `${(avgWinRate * 100).toFixed(1)}%`, color: avgWinRate >= 0.5 ? 'text-[#22c55e]' : 'text-[#ef4444]' },
                  { label: 'Active', value: String(lifecycleCounts.active), color: 'text-[#22c55e]' },
                  { label: 'Proposed', value: String(totalProposed), color: 'text-gray-200' },
                  { label: 'Activated', value: String(totalActivated), color: 'text-[#22c55e]' },
                  { label: 'Act. Rate', value: `${activationRate.toFixed(1)}%`, color: 'text-blue-400' },
                  { label: 'Ret. Rate', value: `${retirementRate.toFixed(1)}%`, color: 'text-[#ef4444]' },
                ].map((m, i) => (
                  <div key={i} className="rounded-md p-2 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)]">
                    <div className="text-xs text-gray-500 tracking-wide">{m.label}</div>
                    <div className={cn('text-sm font-mono font-bold mt-0.5', m.color)}>{m.value}</div>
                  </div>
                ))}
              </div>

              {/* Template Performance — inline bars, no nested panel */}
              {autonomousStatus && autonomousStatus.template_stats.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Template Success Rates</div>
                  <div className="space-y-1">
                    {autonomousStatus.template_stats.map((template) => (
                      <div key={template.name} className="flex items-center gap-2 py-1 border-b border-[var(--color-dark-border)]/30 last:border-0">
                        <span className="text-[12px] font-mono text-gray-300 truncate w-[180px] shrink-0">{template.name}</span>
                        <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                          <div className={cn('h-full',
                            template.success_rate >= 0.6 ? 'bg-[#22c55e]' :
                            template.success_rate >= 0.4 ? 'bg-yellow-400' : 'bg-[#ef4444]'
                          )} style={{ width: `${template.success_rate * 100}%` }} />
                        </div>
                        <span className="text-[11px] font-mono text-gray-400 w-[40px] text-right shrink-0">{(template.success_rate * 100).toFixed(0)}%</span>
                        <span className="text-[10px] text-gray-600 w-[30px] text-right shrink-0">{template.usage_count}×</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Thresholds — compact inline grid, no nested panel */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Activation Thresholds</div>
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { label: 'Min Sharpe', value: '1.5' },
                      { label: 'Max DD', value: '15%' },
                      { label: 'Min WR', value: '50%' },
                      { label: 'Min Trades', value: '20' },
                    ].map((t, i) => (
                      <div key={i} className="flex items-center justify-between py-1 px-2 rounded bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)]">
                        <span className="text-[11px] text-gray-500">{t.label}</span>
                        <span className="text-[12px] font-mono font-semibold text-gray-200">{t.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Retirement Triggers</div>
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { label: 'Max Sharpe', value: '0.5' },
                      { label: 'Max DD', value: '15%' },
                      { label: 'Min WR', value: '40%' },
                      { label: 'Min Trades', value: '30' },
                    ].map((t, i) => (
                      <div key={i} className="flex items-center justify-between py-1 px-2 rounded bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)]">
                        <span className="text-[11px] text-gray-500">{t.label}</span>
                        <span className="text-[12px] font-mono font-semibold text-gray-200">{t.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </TabsContent>

            {/* Tab 6: Walk-Forward Analytics */}
            <TabsContent value="walkforward" className="space-y-3 p-2">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* Cycle History Table */}
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Cycle History</div>
                  {walkForwardLoading ? (
                    <div className="flex items-center justify-center h-24 text-[11px] text-gray-500">Loading...</div>
                  ) : walkForwardData?.cycles && walkForwardData.cycles.length > 0 ? (
                    <div className="overflow-x-auto max-h-[300px]">
                      <table className="w-full text-[10px] font-mono">
                        <thead className="sticky top-0 bg-[var(--color-dark-bg)]">
                          <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                            <th className="py-1 px-2 text-left">Cycle</th>
                            <th className="py-1 px-2 text-right">Proposals</th>
                            <th className="py-1 px-2 text-right">BTs</th>
                            <th className="py-1 px-2 text-right">Pass Rate</th>
                            <th className="py-1 px-2 text-right">Avg Sharpe</th>
                          </tr>
                        </thead>
                        <tbody>
                          {walkForwardData.cycles.slice(0, 20).map((c: any, idx: number) => (
                            <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/30">
                              <td className="py-1 px-2 text-gray-500">{c.date || c.cycle_id || `#${idx + 1}`}</td>
                              <td className="py-1 px-2 text-right text-gray-300">{c.proposals ?? '—'}</td>
                              <td className="py-1 px-2 text-right text-gray-300">{c.backtests ?? '—'}</td>
                              <td className={cn('py-1 px-2 text-right', (c.pass_rate ?? 0) >= 50 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
                                {c.pass_rate != null ? `${c.pass_rate.toFixed(1)}%` : '—'}
                              </td>
                              <td className="py-1 px-2 text-right text-gray-300">{c.avg_sharpe != null ? c.avg_sharpe.toFixed(2) : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-6 text-[11px] text-gray-500">No walk-forward data</div>
                  )}
                </div>

                {/* Pass Rate Trend Chart */}
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Pass Rate Trend</div>
                  {walkForwardData?.pass_rate_history && walkForwardData.pass_rate_history.length > 0 ? (
                    <InteractiveChart
                      data={walkForwardData.pass_rate_history}
                      dataKeys={[{ key: 'pass_rate', color: designColors.green, type: 'line' }]}
                      xAxisKey="date"
                      height={200}
                      periods={['1M', '3M', '6M', '1Y', 'ALL']}
                      defaultPeriod={walkForwardPeriod}
                      onPeriodChange={(p) => {
                        setWalkForwardPeriod(p);
                        if (tradingMode) {
                          apiClient.getWalkForwardAnalytics(tradingMode, p).then(setWalkForwardData).catch(() => {});
                        }
                      }}
                      tooltipFormatter={(v: number) => [`${v.toFixed(1)}%`, 'Pass Rate']}
                    />
                  ) : (
                    <div className="text-center py-6 text-[11px] text-gray-500">No pass rate history</div>
                  )}
                </div>
              </div>

              {/* Similarity Rejections — flat table */}
              {walkForwardData?.similarity_rejections && walkForwardData.similarity_rejections.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Similarity Rejections</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[10px] font-mono">
                      <thead>
                        <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                          <th className="py-1 px-2 text-left">Rejected Strategy</th>
                          <th className="py-1 px-2 text-left">Existing Strategy</th>
                          <th className="py-1 px-2 text-right">Similarity %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {walkForwardData.similarity_rejections.map((r: any, idx: number) => (
                          <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/30">
                            <td className="py-1 px-2 text-gray-200 truncate max-w-[180px]">{r.rejected_name || '—'}</td>
                            <td className="py-1 px-2 text-gray-300 truncate max-w-[180px]">{r.existing_name || '—'}</td>
                            <td className="py-1 px-2 text-right text-[#ef4444]">{r.similarity != null ? `${(r.similarity * 100).toFixed(1)}%` : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Tab 7: Conviction Score */}
            <TabsContent value="conviction" className="space-y-3 p-2">
              <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1">Conviction Score Decomposition</div>
                  {(() => {
                    const activeWithConviction = strategies.filter(
                      (s) => (s.status === 'DEMO' || s.status === 'LIVE') && s.metadata?.conviction_score
                    );
                    if (activeWithConviction.length === 0) {
                      return <div className="flex items-center justify-center h-24 text-xs text-muted-foreground">No conviction score data</div>;
                    }
                    const factors = ['signal_strength', 'fundamental_quality', 'regime_fit', 'carry_bias', 'halving_cycle'];
                    const factorColors: Record<string, string> = {
                      signal_strength: '#3b82f6',
                      fundamental_quality: '#22c55e',
                      regime_fit: '#f59e0b',
                      carry_bias: '#8b5cf6',
                      halving_cycle: '#ec4899',
                    };
                    return (
                      <div className="space-y-2">
                        {activeWithConviction.slice(0, 15).map((s) => {
                          const total = s.metadata?.conviction_score || 0;
                          const confidence = s.metadata?.confidence_factors || s.reasoning?.confidence_factors || {};
                          return (
                            <div key={s.id} className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono text-gray-300 truncate max-w-[180px]">{s.name}</span>
                                <span className="text-[10px] font-mono font-semibold">{typeof total === 'number' ? total.toFixed(2) : total}</span>
                              </div>
                              <div className="flex h-3 rounded overflow-hidden bg-dark-border/30">
                                {factors.map((f) => {
                                  const val = Number(confidence[f] || 0);
                                  const pct = total > 0 ? (val / total) * 100 : 0;
                                  if (pct <= 0) return null;
                                  return (
                                    <div key={f} className="h-full"
                                      style={{ width: `${pct}%`, backgroundColor: factorColors[f] || '#6b7280' }}
                                      title={`${f.replace(/_/g, ' ')}: ${val.toFixed(2)} (${pct.toFixed(0)}%)`} />
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
                        <div className="flex flex-wrap gap-2 mt-3 text-[11px] text-muted-foreground">
                          {factors.map((f) => (
                            <span key={f} className="flex items-center gap-1">
                              <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: factorColors[f] }} />
                              {f.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
            </TabsContent>
        </div>
      </Tabs>
      </div>
    </div>
  );

  // ── Side Panel (35%) — Cycle Intelligence ──────────────────────────────
  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Cycle Intelligence" panelId="autonomous-side" onRefresh={fetchData}>
        <div className="flex flex-col gap-2 p-2">
          {/* Compact Metric Row */}
          <CompactMetricRow metrics={sideMetrics} className="flex-wrap h-auto min-h-0 max-h-none" />

          {/* Cycle Progress Indicator */}
          <div>
            <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
              Cycle Progress
            </div>
            <div className="bg-muted rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-300 font-mono">
                  {cycleProgress > 0 && cycleProgress < 100 ? 'Running' : cycleProgress === 100 ? 'Complete' : 'Idle'}
                </span>
                <span className="text-xs font-mono font-semibold text-gray-200">{cycleProgress}%</span>
              </div>
              <div className="w-full bg-dark-bg rounded-full h-2 overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-500',
                    cycleProgress === 100 ? 'bg-accent-green' :
                    cycleProgress > 0 ? 'bg-blue-500' : 'bg-gray-600'
                  )}
                  style={{ width: `${cycleProgress}%` }}
                />
              </div>
              {lastCycleData && (
                <div className="grid grid-cols-2 gap-2 mt-3">
                  <div>
                    <div className="text-[11px] text-muted-foreground">Duration</div>
                    <div className="text-xs font-mono font-semibold">
                      {lastCycleData.duration_seconds != null
                        ? lastCycleData.duration_seconds < 60
                          ? `${lastCycleData.duration_seconds.toFixed(0)}s`
                          : `${Math.floor(lastCycleData.duration_seconds / 60)}m ${Math.floor(lastCycleData.duration_seconds % 60)}s`
                        : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-muted-foreground">Proposals</div>
                    <div className="text-xs font-mono font-semibold text-blue-400">{lastCycleData.proposals_generated}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-muted-foreground">BT Pass Rate</div>
                    <div className="text-xs font-mono font-semibold text-purple-400">
                      {lastCycleData.backtested > 0
                        ? `${((lastCycleData.backtest_passed / lastCycleData.backtested) * 100).toFixed(0)}%`
                        : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-muted-foreground">Net Activations</div>
                    <div className={cn('text-xs font-mono font-semibold',
                      (lastCycleData.activated - lastCycleData.strategies_retired) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                      {lastCycleData.activated - lastCycleData.strategies_retired >= 0 ? '+' : ''}{lastCycleData.activated - lastCycleData.strategies_retired}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* WF Pass Rate Sparkline */}
          <div>
            <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
              WF Pass Rate Trend
            </div>
            {walkForwardData?.pass_rate_history && walkForwardData.pass_rate_history.length > 0 ? (
              <div className="bg-muted rounded-lg p-2">
                <InteractiveChart
                  data={walkForwardData.pass_rate_history.slice(-20)}
                  dataKeys={[{ key: 'pass_rate', color: designColors.green, type: 'line' }]}
                  xAxisKey="date"
                  height={100}
                  tooltipFormatter={(v: number) => [`${v.toFixed(1)}%`, 'Pass Rate']}
                />
              </div>
            ) : (
              <div className="bg-muted rounded-lg p-3 text-center text-[11px] text-muted-foreground">
                No pass rate history
              </div>
            )}
          </div>

          {/* System Status Summary */}
          {autonomousStatus && (
            <div>
              <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
                Market Regime
              </div>
              <div className="bg-muted rounded-lg p-3">
                <div className={cn(
                  'text-sm font-mono font-semibold flex items-center gap-2',
                  getRegimeColor(autonomousStatus.market_regime)
                )}>
                  {getRegimeIcon(autonomousStatus.market_regime)} {autonomousStatus.market_regime}
                </div>
                <div className="text-[11px] text-muted-foreground mt-1">
                  Confidence: <span className={getConfidenceLabel(autonomousStatus.market_confidence).color}>
                    {getConfidenceLabel(autonomousStatus.market_confidence).label}
                  </span> ({(autonomousStatus.market_confidence * 100).toFixed(0)}%)
                </div>
              </div>
            </div>
          )}

          {/* Recent Similarity Rejections */}
          <div>
            <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
              Recent Similarity Rejections
            </div>
            {walkForwardData?.similarity_rejections && walkForwardData.similarity_rejections.length > 0 ? (
              <div className="space-y-1.5">
                {walkForwardData.similarity_rejections.slice(0, 5).map((r: any, idx: number) => (
                  <div key={idx} className="bg-muted rounded-lg p-2 flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="text-[10px] font-mono text-gray-300 truncate">{r.rejected_name || '—'}</div>
                      <div className="text-[11px] text-muted-foreground truncate">vs {r.existing_name || '—'}</div>
                    </div>
                    <span className="text-[10px] font-mono font-semibold text-accent-red shrink-0 ml-2">
                      {r.similarity != null ? `${(r.similarity * 100).toFixed(0)}%` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-muted rounded-lg p-3 text-center text-[11px] text-muted-foreground">
                No similarity rejections
              </div>
            )}
          </div>

          {/* Cumulative Stats */}
          {autonomousStatus && (
            <div>
              <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
                Cumulative Stats
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-muted rounded-lg p-2 text-center">
                  <div className="text-[11px] text-muted-foreground">Last Cycle</div>
                  <div className="text-[10px] font-mono font-semibold text-gray-200">
                    {autonomousStatus.last_cycle_time ? formatTimestamp(autonomousStatus.last_cycle_time) : '—'}
                  </div>
                </div>
                <div className="bg-muted rounded-lg p-2 text-center">
                  <div className="text-[11px] text-muted-foreground">Activated</div>
                  <div className="text-lg font-mono font-semibold text-accent-green">
                    {autonomousStatus.cycle_stats.activated_count}
                  </div>
                </div>
                <div className="bg-muted rounded-lg p-2 text-center">
                  <div className="text-[11px] text-muted-foreground">Retired</div>
                  <div className="text-lg font-mono font-semibold text-accent-red">
                    {autonomousStatus.cycle_stats.retired_count}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Final Render — 2-panel layout ──────────────────────────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="🤖 Autonomous"
        description="Monitor and control the autonomous trading system"
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
            layoutId="autonomous-panels"
            direction="horizontal"
            panels={[
              {
                id: 'autonomous-main',
                defaultSize: 65,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'autonomous-side',
                defaultSize: 35,
                minSize: 250,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
