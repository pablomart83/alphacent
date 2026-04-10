import { type FC, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Activity, PlayCircle, PauseCircle, Settings, RefreshCw, Search,
  AlertCircle, TrendingUp, BarChart3, Zap, Clock, Calendar, Trash2,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { TradingCyclePipeline } from '../components/trading/TradingCyclePipeline';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
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
    const filterSummary = [];
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

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8">
          <PageSkeleton />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout onLogout={onLogout}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto relative"
      >
        <RefreshIndicator visible={pollingRefreshing || refreshing} />

        {/* Header */}
        <div className="mb-6 lg:mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-2">
              🤖 Autonomous Trading
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-gray-400 text-sm">
                Monitor and control the autonomous trading system
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            disabled={refreshing}
            className="gap-2"
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="control" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
            <TabsTrigger value="control">Control & Status</TabsTrigger>
            <TabsTrigger value="lifecycle">
              Strategy Lifecycle ({filteredStrategies.length})
            </TabsTrigger>
            <TabsTrigger value="activity">
              Recent Activity ({filteredOrders.length})
            </TabsTrigger>
            <TabsTrigger value="signals">Signal Activity</TabsTrigger>
            <TabsTrigger value="performance">Performance</TabsTrigger>
          </TabsList>

          {/* Tab 1: Control & Status */}
          <TabsContent value="control" className="space-y-6">
            {/* Top Row - Status Badges */}
            <div className="flex items-center justify-between">
              <div className="flex gap-3">
                {systemStatus && (
                  <div className={cn(
                    'px-4 py-2 rounded-lg text-sm font-mono border',
                    getTradingStateColor(systemStatus.state)
                  )}>
                    {getTradingStateLabel(systemStatus.state)}
                  </div>
                )}
                {autonomousStatus && (
                  <div className={cn(
                    'px-4 py-2 rounded-lg text-sm font-mono border',
                    autonomousStatus.enabled
                      ? 'bg-accent-green/20 text-accent-green border-accent-green/30'
                      : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                  )}>
                    {autonomousStatus.enabled ? '● AUTO-MANAGEMENT ENABLED' : '○ AUTO-MANAGEMENT DISABLED'}
                  </div>
                )}
              </div>
            </div>

            {/* Compact Metric Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-3">
                <Zap className="h-4 w-4 text-accent-green flex-shrink-0" />
                <div>
                  <div className="text-xs text-muted-foreground">Active Strategies</div>
                  <div className="text-lg font-mono font-bold">{systemStatus?.active_strategies ?? '—'}</div>
                </div>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-3">
                <TrendingUp className="h-4 w-4 text-blue-400 flex-shrink-0" />
                <div>
                  <div className="text-xs text-muted-foreground">Open Positions</div>
                  <div className="text-lg font-mono font-bold">{systemStatus?.open_positions ?? '—'}</div>
                </div>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-3">
                <Clock className="h-4 w-4 text-yellow-400 flex-shrink-0" />
                <div>
                  <div className="text-xs text-muted-foreground">Last Signal</div>
                  <div className="text-sm font-mono">{systemStatus?.last_signal_generated ? formatTimestamp(systemStatus.last_signal_generated) : 'Never'}</div>
                </div>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-3">
                <Activity className="h-4 w-4 flex-shrink-0" />
                <div>
                  <div className="text-xs text-muted-foreground">Market Regime</div>
                  <div className={cn('text-sm font-mono font-semibold', autonomousStatus ? getRegimeColor(autonomousStatus.market_regime) : '')}>
                    {autonomousStatus ? `${getRegimeIcon(autonomousStatus.market_regime)} ${autonomousStatus.market_regime}` : '—'}
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Controls Bar — Research Filters + Trigger Cycle, always visible */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.05 }}>
              <Card>
                <CardContent className="pt-4 pb-4">
                  <div className="flex flex-col lg:flex-row lg:items-end gap-4">
                    {/* Research Filters — compact inline */}
                    <div className="flex-1 space-y-2">
                      <div className="text-sm font-semibold flex items-center gap-2">
                        <Search className="h-4 w-4" />
                        Research Filters
                        {(cycleAssetClasses.size > 0 || cycleIntervals.size > 0 || cycleStrategyTypes.size > 0) && (
                          <span className="text-xs text-accent-blue font-normal">(filtered)</span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-muted-foreground whitespace-nowrap">Assets:</span>
                          <div className="flex flex-wrap gap-1">
                            {['stock', 'etf', 'crypto', 'forex', 'index', 'commodity'].map(ac => (
                              <button key={ac} onClick={() => {
                                const next = new Set(cycleAssetClasses);
                                next.has(ac) ? next.delete(ac) : next.add(ac);
                                setCycleAssetClasses(next);
                              }} className={cn(
                                'px-2 py-0.5 rounded text-xs font-medium border transition-colors',
                                cycleAssetClasses.has(ac)
                                  ? 'bg-accent-blue/20 border-accent-blue text-accent-blue'
                                  : 'border-border text-muted-foreground hover:border-accent-blue/50'
                              )}>{ac.charAt(0).toUpperCase() + ac.slice(1)}</button>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-muted-foreground whitespace-nowrap">TF:</span>
                          <div className="flex gap-1">
                            {[{ key: '1d', label: 'Daily' }, { key: '1h', label: '1H' }, { key: '4h', label: '4H' }].map(({ key, label }) => (
                              <button key={key} onClick={() => {
                                const next = new Set(cycleIntervals);
                                next.has(key) ? next.delete(key) : next.add(key);
                                setCycleIntervals(next);
                              }} className={cn(
                                'px-2 py-0.5 rounded text-xs font-medium border transition-colors',
                                cycleIntervals.has(key)
                                  ? 'bg-accent-green/20 border-accent-green text-accent-green'
                                  : 'border-border text-muted-foreground hover:border-accent-green/50'
                              )}>{label}</button>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-muted-foreground whitespace-nowrap">Type:</span>
                          <div className="flex gap-1">
                            {[{ key: 'dsl', label: 'DSL' }, { key: 'alpha_edge', label: 'AE' }].map(({ key, label }) => (
                              <button key={key} onClick={() => {
                                const next = new Set(cycleStrategyTypes);
                                next.has(key) ? next.delete(key) : next.add(key);
                                setCycleStrategyTypes(next);
                              }} className={cn(
                                'px-2 py-0.5 rounded text-xs font-medium border transition-colors',
                                cycleStrategyTypes.has(key)
                                  ? 'bg-accent-yellow/20 border-accent-yellow text-accent-yellow'
                                  : 'border-border text-muted-foreground hover:border-accent-yellow/50'
                              )}>{label}</button>
                            ))}
                          </div>
                        </div>
                        {(cycleAssetClasses.size > 0 || cycleIntervals.size > 0 || cycleStrategyTypes.size > 0) && (
                          <button onClick={() => { setCycleAssetClasses(new Set()); setCycleIntervals(new Set()); setCycleStrategyTypes(new Set()); }}
                            className="text-xs text-accent-red hover:underline whitespace-nowrap">Clear</button>
                        )}
                      </div>
                    </div>
                    {/* Trigger Cycle Button — prominent */}
                    <div className="flex gap-2 lg:flex-shrink-0">
                      <Button
                        onClick={handleTriggerCycle}
                        disabled={triggering || !autonomousStatus?.enabled}
                        size="lg"
                        className="gap-2 bg-accent-green hover:bg-accent-green/80 text-black font-semibold"
                      >
                        <RefreshCw className={cn('h-4 w-4', triggering && 'animate-spin')} />
                        {triggering ? 'Running...' : 'Run Cycle'}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Trading Cycle Pipeline — top position */}
            <TradingCyclePipeline cycleRunning={triggering || (cycleProgress > 0 && cycleProgress < 100)} />

            {/* Controls + System — 2-column grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Column - Controls (Control Panel + Scheduled Execution) */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
              >
                <Card className="h-full">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <PlayCircle className="h-5 w-5" />
                      Controls
                    </CardTitle>
                    <CardDescription>
                      Trading execution, lifecycle, and scheduling
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {/* Trading State Warning */}
                    {systemStatus && systemStatus.state !== 'ACTIVE' && lifecycleCounts.active > 0 && (
                      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <AlertCircle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-yellow-300 text-sm font-medium">Trading Not Active</p>
                            <p className="text-yellow-400/80 text-xs mt-1">
                              You have {lifecycleCounts.active} strategies ready but trading is {systemStatus.state}.
                              Start trading to begin signal generation and order execution.
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Trading Controls */}
                    <div>
                      <h3 className="text-sm font-semibold mb-3">Signal Generation & Order Execution</h3>
                      <div className="grid grid-cols-2 gap-3">
                        {(!systemStatus || systemStatus.state === 'STOPPED') && (
                          <Button
                            onClick={handleStartTrading}
                            disabled={tradingAction}
                            variant="outline"
                            className="w-full justify-start gap-2 border-accent-green/30 text-accent-green hover:bg-accent-green/10"
                          >
                            <PlayCircle className="h-4 w-4" />
                            {tradingAction ? 'Starting...' : 'Start Trading'}
                          </Button>
                        )}

                        {systemStatus?.state === 'ACTIVE' && (
                          <>
                            <Button
                              onClick={handlePauseTrading}
                              disabled={tradingAction}
                              variant="outline"
                              className="w-full justify-start gap-2 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10"
                            >
                              <PauseCircle className="h-4 w-4" />
                              {tradingAction ? 'Pausing...' : 'Pause Trading'}
                            </Button>
                            <Button
                              onClick={handleStopTrading}
                              disabled={tradingAction}
                              variant="outline"
                              className="w-full justify-start gap-2 border-accent-red/30 text-accent-red hover:bg-accent-red/10"
                            >
                              <AlertCircle className="h-4 w-4" />
                              {tradingAction ? 'Stopping...' : 'Stop Trading'}
                            </Button>
                          </>
                        )}

                        {systemStatus?.state === 'PAUSED' && (
                          <>
                            <Button
                              onClick={handleResumeTrading}
                              disabled={tradingAction}
                              variant="outline"
                              className="w-full justify-start gap-2 border-accent-green/30 text-accent-green hover:bg-accent-green/10"
                            >
                              <PlayCircle className="h-4 w-4" />
                              {tradingAction ? 'Resuming...' : 'Resume Trading'}
                            </Button>
                            <Button
                              onClick={handleStopTrading}
                              disabled={tradingAction}
                              variant="outline"
                              className="w-full justify-start gap-2 border-accent-red/30 text-accent-red hover:bg-accent-red/10"
                            >
                              <AlertCircle className="h-4 w-4" />
                              {tradingAction ? 'Stopping...' : 'Stop Trading'}
                            </Button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Strategy Lifecycle Controls */}
                    <div>
                      <h3 className="text-sm font-semibold mb-3">Strategy Lifecycle</h3>
                      <div className="grid grid-cols-2 gap-3">
                        <Button
                          onClick={() => navigate('/settings')}
                          variant="outline"
                          className="w-full justify-start gap-2"
                        >
                          <Settings className="h-4 w-4" />
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
                          variant="outline"
                          className="w-full justify-start gap-2 col-span-2 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10"
                        >
                          <Trash2 className="h-4 w-4" />
                          Clear Blacklists & WF Cache
                        </Button>
                      </div>
                    </div>

                    {/* Warning when system is disabled */}
                    {autonomousStatus && !autonomousStatus.enabled && (
                      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <AlertCircle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-yellow-300 text-sm font-medium">Auto-Management Disabled</p>
                            <p className="text-yellow-400/80 text-xs mt-1">
                              Automatic strategy proposal and retirement is disabled. Enable it in settings.
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Scheduled Execution */}
                    <div>
                      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                        <Calendar className="h-4 w-4" />
                        Scheduled Execution
                      </h3>
                      {scheduleConfig ? (
                        <div className="space-y-3">
                          {/* Enable/Disable toggle */}
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">
                              {scheduleConfig.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                            <button
                              onClick={handleToggleSchedule}
                              disabled={scheduleUpdating}
                              className={cn(
                                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none',
                                scheduleConfig.enabled ? 'bg-accent-green' : 'bg-gray-600'
                              )}
                            >
                              <span
                                className={cn(
                                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                                  scheduleConfig.enabled ? 'translate-x-6' : 'translate-x-1'
                                )}
                              />
                            </button>
                          </div>

                          {/* Frequency selector */}
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Frequency</label>
                            <div className="flex gap-1">
                              {['daily', 'weekly'].map((freq) => (
                                <button
                                  key={freq}
                                  onClick={() => {
                                    setEditFrequency(freq);
                                    if (freq === 'daily' && editHour === 2) setEditHour(22);
                                    if (freq === 'weekly' && editHour === 22) setEditHour(2);
                                  }}
                                  className={cn(
                                    'px-3 py-1 text-xs rounded-md border transition-colors',
                                    editFrequency === freq
                                      ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                                      : 'border-border text-muted-foreground hover:border-blue-500/50'
                                  )}
                                >
                                  {freq.charAt(0).toUpperCase() + freq.slice(1)}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Day of week (only for weekly) */}
                          {editFrequency === 'weekly' && (
                            <div className="space-y-1">
                              <label className="text-xs text-muted-foreground">Day of Week</label>
                              <select
                                value={editDay}
                                onChange={(e) => setEditDay(e.target.value)}
                                className="w-full bg-background border border-border rounded-md px-2 py-1 text-sm"
                              >
                                {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map((day) => (
                                  <option key={day} value={day}>
                                    {day.charAt(0).toUpperCase() + day.slice(1)}
                                    {day === 'saturday' ? ' (recommended)' : ''}
                                  </option>
                                ))}
                              </select>
                            </div>
                          )}

                          {/* Time picker */}
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Time (UTC)</label>
                            <div className="flex gap-2 items-center">
                              <select
                                value={editHour}
                                onChange={(e) => setEditHour(parseInt(e.target.value))}
                                className="bg-background border border-border rounded-md px-2 py-1 text-sm w-16"
                              >
                                {Array.from({ length: 24 }, (_, i) => (
                                  <option key={i} value={i}>{i.toString().padStart(2, '0')}</option>
                                ))}
                              </select>
                              <span className="text-muted-foreground">:</span>
                              <select
                                value={editMinute}
                                onChange={(e) => setEditMinute(parseInt(e.target.value))}
                                className="bg-background border border-border rounded-md px-2 py-1 text-sm w-16"
                              >
                                {[0, 15, 30, 45].map((m) => (
                                  <option key={m} value={m}>{m.toString().padStart(2, '0')}</option>
                                ))}
                              </select>
                              <span className="text-xs text-muted-foreground">UTC</span>
                            </div>
                          </div>

                          {/* Save button (show when config changed) */}
                          {(editFrequency !== scheduleConfig.frequency ||
                            editDay !== scheduleConfig.day_of_week ||
                            editHour !== scheduleConfig.hour ||
                            editMinute !== scheduleConfig.minute) && (
                            <button
                              onClick={handleSaveSchedule}
                              disabled={scheduleUpdating}
                              className="w-full px-3 py-1.5 text-xs rounded-md bg-blue-500 hover:bg-blue-600 text-white transition-colors disabled:opacity-50"
                            >
                              {scheduleUpdating ? 'Saving...' : 'Save Schedule'}
                            </button>
                          )}

                          {/* Next run display */}
                          {nextScheduledRun && scheduleConfig.enabled && (
                            <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-2">
                              <Clock className="h-4 w-4 text-blue-400 flex-shrink-0" />
                              <div>
                                <div className="text-xs text-muted-foreground">Next Scheduled Run</div>
                                <div className="text-sm font-mono text-blue-400">
                                  {new Date(nextScheduledRun).toLocaleString('en-US', {
                                    weekday: 'short',
                                    month: 'short',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    timeZoneName: 'short',
                                  })}
                                </div>
                              </div>
                            </div>
                          )}
                          {lastScheduledRun && (
                            <div className="text-xs text-muted-foreground">
                              Last scheduled run: {formatTimestamp(lastScheduledRun)}
                            </div>
                          )}
                          {!scheduleConfig.enabled && (
                            <div className="text-xs text-yellow-400/80">
                              Scheduled runs are disabled. Toggle to enable.
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-sm text-muted-foreground">Loading schedule...</div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>

              {/* Right Column - System (System Status + Research Filters) */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.2 }}
              >
                <Card className="h-full">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5" />
                      System
                    </CardTitle>
                    <CardDescription>
                      System metrics, cycle info, and research filters
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {autonomousStatus && (
                      <div className="space-y-4">
                        {/* Market Regime */}
                        <div className="bg-muted rounded-lg p-4">
                          <div className="text-xs text-muted-foreground mb-2">Market Regime</div>
                          <div className={cn(
                            'text-xl font-mono font-semibold flex items-center gap-2',
                            getRegimeColor(autonomousStatus.market_regime)
                          )}>
                            {getRegimeIcon(autonomousStatus.market_regime)} {autonomousStatus.market_regime}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            Confidence: <span className={getConfidenceLabel(autonomousStatus.market_confidence).color}>{getConfidenceLabel(autonomousStatus.market_confidence).label}</span> ({(autonomousStatus.market_confidence * 100).toFixed(0)}%)
                          </div>
                        </div>

                        {/* System Metrics */}
                        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
                          {systemStatus && (
                            <>
                              <div>
                                <div className="text-xs text-muted-foreground mb-1">Active Strategies</div>
                                <div className="text-2xl font-mono font-semibold">{systemStatus.active_strategies}</div>
                              </div>
                              <div>
                                <div className="text-xs text-muted-foreground mb-1">Open Positions</div>
                                <div className="text-2xl font-mono font-semibold">{systemStatus.open_positions}</div>
                              </div>
                              <div>
                                <div className="text-xs text-muted-foreground mb-1">Uptime</div>
                                <div className="text-lg font-mono font-semibold">
                                  {Math.floor(systemStatus.uptime_seconds / 3600)}h{' '}
                                  {Math.floor((systemStatus.uptime_seconds % 3600) / 60)}m
                                </div>
                              </div>
                              <div>
                                <div className="text-xs text-muted-foreground mb-1">Last Signal</div>
                                <div className="text-sm font-mono">
                                  {systemStatus.last_signal_generated 
                                    ? formatTimestamp(systemStatus.last_signal_generated)
                                    : 'Never'}
                                </div>
                              </div>
                            </>
                          )}
                        </div>

                        {/* Cumulative Cycle Stats */}
                        <div className="grid grid-cols-3 gap-3 pt-4 border-t border-border">
                          <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <div className="text-xs text-muted-foreground mb-1">Last Cycle</div>
                            <div className="text-sm font-mono font-semibold text-gray-200">
                              {autonomousStatus.last_cycle_time ? formatTimestamp(autonomousStatus.last_cycle_time) : '—'}
                            </div>
                          </div>
                          <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <div className="text-xs text-muted-foreground mb-1">Total Activated</div>
                            <div className="text-2xl font-mono font-semibold text-accent-green">
                              {autonomousStatus.cycle_stats.activated_count}
                            </div>
                          </div>
                          <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <div className="text-xs text-muted-foreground mb-1">Total Retired</div>
                            <div className="text-2xl font-mono font-semibold text-accent-red">
                              {autonomousStatus.cycle_stats.retired_count}
                            </div>
                          </div>
                        </div>

                        {/* Last Cycle Metrics */}
                        {lastCycleData && (
                          <div className="pt-4 border-t border-border">
                            <div className="text-xs font-semibold text-muted-foreground mb-2">Last Cycle Results</div>
                            <div className="grid grid-cols-2 gap-3">
                              <div className="bg-muted/30 rounded-lg p-2.5">
                                <div className="text-xs text-muted-foreground">Duration</div>
                                <div className="text-sm font-mono font-semibold">
                                  {lastCycleData.duration_seconds != null
                                    ? lastCycleData.duration_seconds < 60
                                      ? `${lastCycleData.duration_seconds.toFixed(0)}s`
                                      : `${Math.floor(lastCycleData.duration_seconds / 60)}m ${Math.floor(lastCycleData.duration_seconds % 60)}s`
                                    : '—'}
                                </div>
                              </div>
                              <div className="bg-muted/30 rounded-lg p-2.5">
                                <div className="text-xs text-muted-foreground">Proposals</div>
                                <div className="text-sm font-mono font-semibold text-blue-400">{lastCycleData.proposals_generated}</div>
                              </div>
                              <div className="bg-muted/30 rounded-lg p-2.5">
                                <div className="text-xs text-muted-foreground">BT Pass Rate</div>
                                <div className="text-sm font-mono font-semibold text-purple-400">
                                  {lastCycleData.backtested > 0
                                    ? `${((lastCycleData.backtest_passed / lastCycleData.backtested) * 100).toFixed(0)}%`
                                    : '—'}
                                </div>
                              </div>
                              <div className="bg-muted/30 rounded-lg p-2.5">
                                <div className="text-xs text-muted-foreground">Net Activations</div>
                                <div className={cn(
                                  'text-sm font-mono font-semibold',
                                  (lastCycleData.activated - lastCycleData.strategies_retired) >= 0 ? 'text-accent-green' : 'text-accent-red'
                                )}>
                                  {lastCycleData.activated - lastCycleData.strategies_retired >= 0 ? '+' : ''}{lastCycleData.activated - lastCycleData.strategies_retired}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            {/* Trading Mode Warning */}
            {tradingMode === 'DEMO' && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.5 }}
              >
                <Card className="border-yellow-500/30 bg-yellow-500/5">
                  <CardContent className="pt-6">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-semibold text-yellow-400 mb-1">
                          Demo Mode Active
                        </p>
                        <p className="text-xs text-yellow-400/80">
                          All trades are simulated. No real money is at risk.
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </TabsContent>

          {/* Tab 2: Strategy Lifecycle */}
          <TabsContent value="lifecycle" className="space-y-6">
            {/* Lifecycle Visualization */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Strategy Lifecycle Flow</CardTitle>
                  <CardDescription>
                    Track strategies through their lifecycle stages
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <button
                      onClick={() => setStrategyStageFilter('PROPOSED')}
                      className={cn(
                        'bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 transition-all hover:scale-105 cursor-pointer',
                        strategyStageFilter === 'PROPOSED' && 'ring-2 ring-blue-500'
                      )}
                    >
                      <div className="text-center">
                        <div className="text-sm font-mono font-semibold text-blue-400 mb-2">
                          Proposed
                        </div>
                        <div className="text-3xl font-mono font-bold text-gray-200 mb-2">
                          {lifecycleCounts.proposed}
                        </div>
                        <div className="text-xs text-gray-500">
                          Generated from templates
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => setStrategyStageFilter('BACKTESTED')}
                      className={cn(
                        'bg-purple-500/10 border border-purple-500/30 rounded-lg p-4 transition-all hover:scale-105 cursor-pointer',
                        strategyStageFilter === 'BACKTESTED' && 'ring-2 ring-purple-500'
                      )}
                    >
                      <div className="text-center">
                        <div className="text-sm font-mono font-semibold text-purple-400 mb-2">
                          Backtested
                        </div>
                        <div className="text-3xl font-mono font-bold text-gray-200 mb-2">
                          {lifecycleCounts.backtested}
                        </div>
                        <div className="text-xs text-gray-500">
                          Historical validation
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => setStrategyStageFilter(strategyStageFilter === 'DEMO' || strategyStageFilter === 'LIVE' ? 'all' : 'DEMO')}
                      className={cn(
                        'bg-accent-green/10 border border-accent-green/30 rounded-lg p-4 transition-all hover:scale-105 cursor-pointer',
                        (strategyStageFilter === 'DEMO' || strategyStageFilter === 'LIVE') && 'ring-2 ring-accent-green'
                      )}
                    >
                      <div className="text-center">
                        <div className="text-sm font-mono font-semibold text-accent-green mb-2">
                          Active
                        </div>
                        <div className="text-3xl font-mono font-bold text-gray-200 mb-2">
                          {lifecycleCounts.active}
                        </div>
                        <div className="text-xs text-gray-500">
                          Live trading
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => setStrategyStageFilter('RETIRED')}
                      className={cn(
                        'bg-accent-red/10 border border-accent-red/30 rounded-lg p-4 transition-all hover:scale-105 cursor-pointer',
                        strategyStageFilter === 'RETIRED' && 'ring-2 ring-accent-red'
                      )}
                    >
                      <div className="text-center">
                        <div className="text-sm font-mono font-semibold text-accent-red mb-2">
                          Retired
                        </div>
                        <div className="text-3xl font-mono font-bold text-gray-200 mb-2">
                          {lifecycleCounts.retired}
                        </div>
                        <div className="text-xs text-gray-500">
                          Underperforming
                        </div>
                      </div>
                    </button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Strategies Table */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
              <Card>
                <CardHeader>
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div>
                      <CardTitle>Strategies</CardTitle>
                      <CardDescription>
                        {filteredStrategies.length} of {strategies.length} strategies
                        {strategyStageFilter !== 'all' && ` in ${strategyStageFilter} stage`}
                      </CardDescription>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search strategy..."
                          value={strategySearch}
                          onChange={(e) => setStrategySearch(e.target.value)}
                          className="pl-9 w-full sm:w-[200px]"
                        />
                      </div>
                      <Select value={strategyStageFilter} onValueChange={setStrategyStageFilter}>
                        <SelectTrigger className="w-full sm:w-[140px]">
                          <SelectValue placeholder="Stage" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Stages</SelectItem>
                          <SelectItem value="PROPOSED">Proposed</SelectItem>
                          <SelectItem value="BACKTESTED">Backtested</SelectItem>
                          <SelectItem value="DEMO">Demo</SelectItem>
                          <SelectItem value="LIVE">Live</SelectItem>
                          <SelectItem value="RETIRED">Retired</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {filteredStrategies.length > 0 ? (
                    <div className="max-h-[600px] overflow-y-auto">
                      <DataTable
                        columns={strategyColumns}
                        data={filteredStrategies}
                        pageSize={20}
                        showPagination={true}
                      />
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      {strategySearch || strategyStageFilter !== 'all'
                        ? 'No strategies match your filters'
                        : 'No strategies found'}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          {/* Tab 3: Recent Activity */}
          <TabsContent value="activity" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Recent Autonomous Orders</CardTitle>
                    <CardDescription>
                      Last 50 orders from autonomous strategies • {filteredOrders.length} of {orders.length} orders
                    </CardDescription>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        placeholder="Search symbol..."
                        value={orderSearch}
                        onChange={(e) => setOrderSearch(e.target.value)}
                        className="pl-9 w-full sm:w-[200px]"
                      />
                    </div>
                    <Select value={orderStatusFilter} onValueChange={setOrderStatusFilter}>
                      <SelectTrigger className="w-full sm:w-[140px]">
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Status</SelectItem>
                        <SelectItem value="PENDING">Pending</SelectItem>
                        <SelectItem value="FILLED">Filled</SelectItem>
                        <SelectItem value="PARTIALLY_FILLED">Partial</SelectItem>
                        <SelectItem value="CANCELLED">Cancelled</SelectItem>
                        <SelectItem value="REJECTED">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select value={orderSideFilter} onValueChange={setOrderSideFilter}>
                      <SelectTrigger className="w-full sm:w-[120px]">
                        <SelectValue placeholder="Side" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Sides</SelectItem>
                        <SelectItem value="BUY">Buy</SelectItem>
                        <SelectItem value="SELL">Sell</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {filteredOrders.length > 0 ? (
                  <div className="max-h-[600px] overflow-y-auto">
                    <DataTable
                      columns={orderColumns}
                      data={filteredOrders}
                      pageSize={20}
                      showPagination={true}
                    />
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    {orderSearch || orderStatusFilter !== 'all' || orderSideFilter !== 'all'
                      ? 'No orders match your filters'
                      : 'No autonomous orders found'}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 4: Signal Activity */}
          <TabsContent value="signals" className="space-y-6">
            {/* Summary Cards */}
            <div className="flex items-center justify-between mb-2">
              <div />
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefreshSignals}
                disabled={signalRefreshing}
                className="gap-2"
              >
                <RefreshCw className={cn('h-4 w-4', signalRefreshing && 'animate-spin')} />
                Refresh
              </Button>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                label="Signals Generated"
                value={signalData?.summary.total ?? 0}
                icon={Zap}
              />
              <MetricCard
                label="Accepted"
                value={signalData?.summary.accepted ?? 0}
                icon={TrendingUp}
                trend="up"
              />
              <MetricCard
                label="Rejected"
                value={signalData?.summary.rejected ?? 0}
                icon={AlertCircle}
                trend="down"
              />
              <MetricCard
                label="Acceptance Rate"
                value={`${signalData?.summary.acceptance_rate ?? 0}%`}
                icon={BarChart3}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Rejection Reasons Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Rejection Reasons</CardTitle>
                  <CardDescription>Why signals were rejected</CardDescription>
                </CardHeader>
                <CardContent>
                  {signalData?.summary.rejection_reasons && signalData.summary.rejection_reasons.length > 0 ? (
                    <div className="space-y-3">
                      {signalData.summary.rejection_reasons.map((r) => (
                        <div key={r.reason}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-gray-300 truncate">{r.reason}</span>
                            <span className="text-muted-foreground ml-2 whitespace-nowrap">{r.count} ({r.percentage.toFixed(0)}%)</span>
                          </div>
                          <div className="w-full bg-muted rounded-full h-2">
                            <div
                              className="bg-accent-red/70 h-2 rounded-full transition-all"
                              style={{ width: `${Math.min(r.percentage, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-sm">No rejections recorded yet.</p>
                  )}
                </CardContent>
              </Card>

              {/* Recent Signals Table */}
              <Card className="lg:col-span-2">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-sm">Recent Signals</CardTitle>
                      <CardDescription>Latest signal decisions</CardDescription>
                    </div>
                    <Select value={signalFilter} onValueChange={setSignalFilter}>
                      <SelectTrigger className="w-[130px]">
                        <SelectValue placeholder="Filter" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="ACCEPTED">Accepted</SelectItem>
                        <SelectItem value="REJECTED">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="max-h-[400px] overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-card">
                        <tr className="border-b border-border text-muted-foreground text-xs">
                          <th className="text-left py-2 pr-2">Time</th>
                          <th className="text-left py-2 pr-2">Symbol</th>
                          <th className="text-left py-2 pr-2">Side</th>
                          <th className="text-left py-2 pr-2">Decision</th>
                          <th className="text-left py-2">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(signalData?.signals ?? [])
                          .filter(s => signalFilter === 'all' || s.decision === signalFilter)
                          .slice(0, 50)
                          .map((s) => (
                          <tr key={s.id} className="border-b border-border/50 hover:bg-muted/30">
                            <td className="py-2 pr-2 text-xs text-muted-foreground whitespace-nowrap">
                              {utcToLocal(s.created_at).toLocaleString('en-US', {
                                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                              })}
                            </td>
                            <td className="py-2 pr-2 font-mono font-semibold">{s.symbol}</td>
                            <td className="py-2 pr-2">
                              <span className={cn(
                                'px-1.5 py-0.5 rounded text-xs font-mono',
                                s.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'
                              )}>
                                {s.side}
                              </span>
                            </td>
                            <td className="py-2 pr-2">
                              <span className={cn(
                                'px-1.5 py-0.5 rounded text-xs font-mono font-semibold',
                                s.decision === 'ACCEPTED'
                                  ? 'bg-accent-green/20 text-accent-green'
                                  : 'bg-accent-red/20 text-accent-red'
                              )}>
                                {s.decision}
                              </span>
                            </td>
                            <td className="py-2 text-xs text-muted-foreground truncate max-w-[200px]" title={s.rejection_reason || ''}>
                              {s.rejection_reason || '—'}
                            </td>
                          </tr>
                        ))}
                        {(!signalData?.signals || signalData.signals.length === 0) && (
                          <tr>
                            <td colSpan={5} className="py-8 text-center text-muted-foreground">
                              No signal decisions recorded yet. Signals will appear here when the trading system generates them.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Tab 5: Performance */}
          <TabsContent value="performance" className="space-y-6">
            {/* Performance Summary */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    Autonomous Performance Summary
                  </CardTitle>
                  <CardDescription>
                    Overall system performance metrics
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <MetricCard
                      label="Avg Sharpe Ratio"
                      value={avgSharpe.toFixed(2)}
                      format="text"
                      icon={BarChart3}
                      tooltip="Average Sharpe ratio across active strategies"
                    />
                    <MetricCard
                      label="Avg Return"
                      value={avgReturn}
                      format="percentage"
                      trend={avgReturn >= 0 ? 'up' : 'down'}
                      icon={TrendingUp}
                      tooltip="Average return across active strategies"
                    />
                    <MetricCard
                      label="Avg Win Rate"
                      value={avgWinRate}
                      format="percentage"
                      icon={Activity}
                      tooltip="Average win rate across active strategies"
                    />
                    <MetricCard
                      label="Active Strategies"
                      value={lifecycleCounts.active}
                      format="number"
                      icon={Zap}
                      tooltip="Number of currently active strategies"
                    />
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Lifecycle Metrics */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Lifecycle Metrics</CardTitle>
                  <CardDescription>
                    Strategy proposal, activation, and retirement statistics
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-xs text-muted-foreground mb-2">Total Proposed</div>
                      <div className="text-2xl font-mono font-bold text-gray-200">
                        {totalProposed}
                      </div>
                    </div>
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-xs text-muted-foreground mb-2">Total Activated</div>
                      <div className="text-2xl font-mono font-bold text-accent-green">
                        {totalActivated}
                      </div>
                    </div>
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-xs text-muted-foreground mb-2">Activation Rate</div>
                      <div className="text-2xl font-mono font-bold text-blue-400">
                        {activationRate.toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-xs text-muted-foreground mb-2">Retirement Rate</div>
                      <div className="text-2xl font-mono font-bold text-accent-red">
                        {retirementRate.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Template Performance */}
            {autonomousStatus && autonomousStatus.template_stats.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.3 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>Performance by Template</CardTitle>
                    <CardDescription>
                      Success rates and usage statistics for each template
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {autonomousStatus.template_stats.map((template) => (
                        <div key={template.name} className="bg-muted rounded-lg p-3">
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-mono font-semibold text-sm">{template.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {template.usage_count} uses
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1 bg-dark-bg rounded-full h-2 overflow-hidden">
                              <div
                                className={cn(
                                  'h-full transition-all',
                                  template.success_rate >= 0.6 ? 'bg-accent-green' :
                                  template.success_rate >= 0.4 ? 'bg-yellow-400' :
                                  'bg-accent-red'
                                )}
                                style={{ width: `${template.success_rate * 100}%` }}
                              />
                            </div>
                            <div className="text-xs font-mono font-semibold min-w-[45px] text-right">
                              {(template.success_rate * 100).toFixed(0)}%
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Configuration Quick Access */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.4 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Configuration Quick Access
                  </CardTitle>
                  <CardDescription>
                    Current activation and retirement thresholds
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold mb-2">Activation Thresholds</h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Min Sharpe</div>
                          <div className="text-sm font-mono font-semibold">1.5</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Max Drawdown</div>
                          <div className="text-sm font-mono font-semibold">15%</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Min Win Rate</div>
                          <div className="text-sm font-mono font-semibold">50%</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Min Trades</div>
                          <div className="text-sm font-mono font-semibold">20</div>
                        </div>
                      </div>
                    </div>

                    <div>
                      <h3 className="text-sm font-semibold mb-2">Retirement Triggers</h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Max Sharpe</div>
                          <div className="text-sm font-mono font-semibold">0.5</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Max Drawdown</div>
                          <div className="text-sm font-mono font-semibold">15%</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Min Win Rate</div>
                          <div className="text-sm font-mono font-semibold">40%</div>
                        </div>
                        <div className="bg-muted rounded-lg p-2">
                          <div className="text-xs text-muted-foreground">Min Trades</div>
                          <div className="text-sm font-mono font-semibold">30</div>
                        </div>
                      </div>
                    </div>

                    <Button
                      onClick={() => navigate('/settings')}
                      variant="outline"
                      className="w-full sm:w-auto gap-2"
                    >
                      <Settings className="h-4 w-4" />
                      Configure Thresholds
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>
        </Tabs>
      </motion.div>
    </DashboardLayout>
  );
};

