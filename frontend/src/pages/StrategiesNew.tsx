import { type FC, useEffect, useState, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import { 
  Target, Activity,
  MoreVertical, Eye, Pause, Trash2, PlayCircle, RefreshCw,
} from 'lucide-react';

import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { DataTable } from '../components/trading/DataTable';
import { TemplateManager } from '../components/trading/TemplateManager';
import { SymbolManager } from '../components/trading/SymbolManager';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { SectionLabel } from '../components/ui/SectionLabel';
import { MetricGrid } from '../components/ui/MetricGrid';
import { FilterBar } from '../components/ui/FilterBar';
import { TvChart } from '../components/charts/TvChart';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '../components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Badge } from '../components/ui/Badge';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatPercentage, formatCurrency, formatTimestamp } from '../lib/utils';
import { classifyError } from '../lib/errors';
import type { Strategy, StrategyStatus } from '../types/index';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { usePolling } from '../hooks/usePolling';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { Tooltip as RadixTooltip, TooltipContent as RadixTooltipContent, TooltipProvider as RadixTooltipProvider, TooltipTrigger as RadixTooltipTrigger } from '../components/ui/tooltip';

interface StrategiesNewProps {
  onLogout: () => void;
}

export const StrategiesNew: FC<StrategiesNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  
  // State
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStrategies, setSelectedStrategies] = useState<Set<string>>(new Set());
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [showComparison, setShowComparison] = useState(false);
  const [comparedStrategies, setComparedStrategies] = useState<[Strategy, Strategy] | null>(null);
  
  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [templateFilter, setTemplateFilter] = useState<string>('all');
  const [regimeFilter, setRegimeFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [retiredLoaded, setRetiredLoaded] = useState(false);

  // Template Rankings, Blacklists, Idle Demotions state (Task 9.1)
  const [templateRankings, setTemplateRankings] = useState<any[]>([]);
  const [templateRankingsLoading, setTemplateRankingsLoading] = useState(false);
  const [templateRankingFamilyFilter, setTemplateRankingFamilyFilter] = useState<string>('all');
  const [templateRankingTimeframeFilter, setTemplateRankingTimeframeFilter] = useState<string>('all');
  const [templateRankingSortKey, setTemplateRankingSortKey] = useState<string>('win_rate');
  const [templateRankingSortDir, setTemplateRankingSortDir] = useState<'asc' | 'desc'>('desc');
  const [blacklists, setBlacklists] = useState<any[]>([]);
  const [idleDemotions, setIdleDemotions] = useState<any[]>([]);

  // Tab state for main panel
  const [strategiesTab, setStrategiesTab] = useState('overview');

  // Fetch strategies
  const fetchStrategies = useCallback(async () => {
    if (!tradingMode) return;
    
    try {
      setRefreshing(true);
      setError(null);
      const data = await apiClient.getStrategies(tradingMode, false);
      setStrategies(data);
      setLastFetchedAt(new Date());
      setLoading(false);

      // Fetch template rankings, blacklists, idle demotions in background (Task 9.1)
      setTemplateRankingsLoading(true);
      apiClient.getTemplateRankings(tradingMode).then((rankings) => {
        setTemplateRankings(rankings || []);
      }).catch(() => setTemplateRankings([])).finally(() => setTemplateRankingsLoading(false));

      // Fetch blacklists from dedicated endpoint
      apiClient.getBlacklistedCombos().then((bl) => {
        setBlacklists(bl || []);
      }).catch(() => setBlacklists([]));

      // Fetch idle demotions from dedicated endpoint
      apiClient.getIdleDemotions().then((dem) => {
        setIdleDemotions(dem || []);
      }).catch(() => setIdleDemotions([]));
    } catch (error) {
      const classified = classifyError(error, 'strategies');
      console.error('Failed to fetch strategies:', error);
      setError(classified.message);
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  }, [tradingMode]);

  const fetchRetiredStrategies = async () => {
    if (!tradingMode || retiredLoaded) return;
    try {
      const data = await apiClient.getStrategies(tradingMode, true);
      // Merge: keep non-retired from current state, add all from full fetch
      setStrategies(data);
      setRetiredLoaded(true);
    } catch (error) {
      console.error('Failed to fetch retired strategies:', error);
      toast.error('Failed to load retired strategies');
    }
  };

  // usePolling replaces manual useEffect + setInterval
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchStrategies,
    intervalMs: 60000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // WebSocket subscriptions
  useEffect(() => {
    const unsubscribe = wsManager.onStrategyUpdate((data: any) => {
      // Data might be the strategy object directly, or wrapped in a container
      const updatedStrategy = data?.id ? data : data?.strategy;
      if (!updatedStrategy?.id) return; // Skip if no valid strategy data

      setStrategies((prev) => {
        const index = prev.findIndex(s => s.id === updatedStrategy.id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = { ...prev[index], ...updatedStrategy };
          return updated;
        }
        return prev; // Don't add unknown strategies
      });
      if (updatedStrategy.name) {
        toast.success(`Strategy updated: ${updatedStrategy.name}`);
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // Get unique values for filters
  const availableTemplates = useMemo(() => {
    const templates = new Set<string>();
    strategies.forEach(s => {
      if (s.template_name) templates.add(s.template_name);
    });
    return Array.from(templates).sort();
  }, [strategies]);

  const availableRegimes = useMemo(() => {
    const regimes = new Set<string>();
    strategies.forEach(s => {
      if (s.market_regime) regimes.add(s.market_regime);
    });
    return Array.from(regimes).sort();
  }, [strategies]);

  const availableTypes = useMemo(() => {
    const types = new Set<string>();
    strategies.forEach(s => {
      const type = s.strategy_type || s.metadata?.template_type;
      if (type) {
        types.add(type);
      }
    });
    return Array.from(types).sort();
  }, [strategies]);

  // Filter strategies by status
  const activeStrategies = useMemo(() => 
    strategies.filter(s => s.status === 'DEMO' || s.status === 'LIVE'),
    [strategies]
  );

  const backtestedStrategies = useMemo(() => 
    strategies.filter(s => s.status === 'BACKTESTED'),
    [strategies]
  );

  const retiredStrategies = useMemo(() => 
    strategies.filter(s => s.status === 'RETIRED'),
    [strategies]
  );

  // Apply filters
  const filterStrategies = (strategyList: Strategy[]) => {
    return strategyList.filter(strategy => {
      const matchesSearch = 
        strategy.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        strategy.symbols.some(s => s.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesStatus = statusFilter === 'all' || strategy.status === statusFilter;
      const matchesTemplate = templateFilter === 'all' || strategy.template_name === templateFilter;
      const matchesRegime = regimeFilter === 'all' || strategy.market_regime === regimeFilter;
      const matchesSource = sourceFilter === 'all' || strategy.source === sourceFilter;
      
      // Category filter
      const strategyCategory = strategy.strategy_category || strategy.metadata?.strategy_category || (strategy.template_name ? 'template_based' : 'manual');
      const matchesCategory = categoryFilter === 'all' || strategyCategory === categoryFilter;
      
      // Type filter
      const strategyType = strategy.strategy_type || strategy.metadata?.template_type;
      const matchesType = typeFilter === 'all' || strategyType === typeFilter;
      
      return matchesSearch && matchesStatus && matchesTemplate && matchesRegime && matchesSource && matchesCategory && matchesType;
    });
  };

  const filteredActiveStrategies = useMemo(() => 
    filterStrategies(activeStrategies),
    [activeStrategies, searchQuery, statusFilter, templateFilter, regimeFilter, sourceFilter, categoryFilter, typeFilter]
  );

  const filteredBacktestedStrategies = useMemo(() => 
    filterStrategies(backtestedStrategies),
    [backtestedStrategies, searchQuery, statusFilter, templateFilter, regimeFilter, sourceFilter, categoryFilter, typeFilter]
  );

  const filteredRetiredStrategies = useMemo(() => 
    filterStrategies(retiredStrategies),
    [retiredStrategies, searchQuery, statusFilter, templateFilter, regimeFilter, sourceFilter, categoryFilter, typeFilter]
  );

  // Check if selected strategies contain BACKTESTED or active (DEMO/LIVE) strategies
  const selectedStrategiesInfo = useMemo(() => {
    const selectedList = Array.from(selectedStrategies)
      .map(id => strategies.find(s => s.id === id))
      .filter(Boolean) as Strategy[];
    
    const hasBacktested = selectedList.some(s => s.status === 'BACKTESTED');
    const hasActive = selectedList.some(s => s.status === 'DEMO' || s.status === 'LIVE');
    
    return { hasBacktested, hasActive };
  }, [selectedStrategies, strategies]);

  // Calculate summary metrics
  const summaryMetrics = useMemo(() => {
    const active = activeStrategies.length;
    const backtested = backtestedStrategies.length;
    const avgPerformance = activeStrategies.length > 0
      ? activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.total_return || 0), 0) / activeStrategies.length
      : 0;
    const successRate = strategies.length > 0
      ? (activeStrategies.length / strategies.length) * 100
      : 0;

    return { active, backtested, avgPerformance, successRate };
  }, [strategies, activeStrategies, backtestedStrategies]);

  // Template distribution
  const templateDistribution = useMemo(() => {
    const distribution: Record<string, number> = {};
    activeStrategies.forEach(s => {
      const template = s.template_name || 'Manual';
      distribution[template] = (distribution[template] || 0) + 1;
    });
    return Object.entries(distribution).map(([name, count]) => ({ name, count }));
  }, [activeStrategies]);

  // Category distribution
  const categoryDistribution = useMemo(() => {
    const distribution: Record<string, number> = {};
    activeStrategies.forEach(s => {
      const category = s.strategy_category || s.metadata?.strategy_category || (s.template_name ? 'template_based' : 'manual');
      const label = category === 'alpha_edge' ? 'Alpha Edge' : category === 'template_based' ? 'Template-Based' : 'Manual';
      distribution[label] = (distribution[label] || 0) + 1;
    });
    return Object.entries(distribution).map(([name, count]) => ({ name, count }));
  }, [activeStrategies]);

  // Type distribution
  const typeDistribution = useMemo(() => {
    const distribution: Record<string, number> = {};
    activeStrategies.forEach(s => {
      const rawType = s.strategy_type || s.metadata?.template_type;
      if (rawType) {
        const type = rawType
          .split('_')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
        distribution[type] = (distribution[type] || 0) + 1;
      }
    });
    return Object.entries(distribution).map(([name, count]) => ({ name, count }));
  }, [activeStrategies]);

  // Top performing strategies
  const topPerformingStrategies = useMemo(() => {
    return [...activeStrategies]
      .sort((a, b) => (b.performance_metrics?.total_return || 0) - (a.performance_metrics?.total_return || 0))
      .slice(0, 5);
  }, [activeStrategies]);

  // Bulk action handlers
  const handleBulkActivate = async () => {
    if (selectedStrategies.size === 0) return;
    
    if (!confirm(`Activate ${selectedStrategies.size} selected strategies? They will start generating signals.`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const strategyId of selectedStrategies) {
      try {
        await apiClient.activateStrategy(strategyId, tradingMode!);
        successCount++;
      } catch (err) {
        console.error(`Failed to activate strategy ${strategyId}:`, err);
        failCount++;
      }
    }

    setSelectedStrategies(new Set());
    await fetchStrategies();
    
    toast.success(`Activated ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
  };

  const handleBulkDeactivate = async () => {
    if (selectedStrategies.size === 0) return;
    
    if (!confirm(`Deactivate ${selectedStrategies.size} selected strategies? They will be moved to BACKTESTED status and stop generating signals.`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const strategyId of selectedStrategies) {
      try {
        await apiClient.deactivateStrategy(strategyId, tradingMode!);
        successCount++;
      } catch (err) {
        console.error(`Failed to deactivate strategy ${strategyId}:`, err);
        failCount++;
      }
    }

    setSelectedStrategies(new Set());
    await fetchStrategies();
    
    toast.success(`Deactivated ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
  };

  const handleBulkRetire = async () => {
    if (selectedStrategies.size === 0) return;
    
    if (!confirm(`Retire ${selectedStrategies.size} selected strategies? This action cannot be undone and will permanently remove them.`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const strategyId of selectedStrategies) {
      try {
        await apiClient.retireStrategy(strategyId, tradingMode!);
        successCount++;
      } catch (err) {
        console.error(`Failed to retire strategy ${strategyId}:`, err);
        failCount++;
      }
    }

    setSelectedStrategies(new Set());
    await fetchStrategies();
    
    toast.success(`Retired ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
  };

  const handleBulkBacktest = async () => {
    if (selectedStrategies.size === 0) return;
    
    if (!confirm(`Run backtest for ${selectedStrategies.size} selected strategies? This may take several minutes.`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const strategyId of selectedStrategies) {
      try {
        await apiClient.backtestStrategy(strategyId);
        successCount++;
      } catch (err) {
        console.error(`Failed to backtest strategy ${strategyId}:`, err);
        failCount++;
      }
    }

    setSelectedStrategies(new Set());
    await fetchStrategies();
    
    toast.success(`Backtested ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
  };

  // Individual action handlers
  const handleViewDetails = (strategy: Strategy) => {
    setSelectedStrategy(strategy);
    setDetailsDialogOpen(true);
  };

  const handleBacktest = async (strategyId: string) => {
    try {
      await apiClient.backtestStrategy(strategyId);
      await fetchStrategies();
      toast.success('Backtest completed successfully');
    } catch (error) {
      console.error('Failed to backtest strategy:', error);
      toast.error('Failed to backtest strategy');
    }
  };

  const handleActivate = async (strategyId: string) => {
    if (!confirm('Activate this strategy? It will start generating signals.')) {
      return;
    }

    try {
      await apiClient.activateStrategy(strategyId, tradingMode!);
      await fetchStrategies();
      toast.success('Strategy activated successfully');
    } catch (error) {
      console.error('Failed to activate strategy:', error);
      toast.error('Failed to activate strategy');
    }
  };

  const handleDeactivate = async (strategyId: string) => {
    if (!confirm('Deactivate this strategy? It will be moved to BACKTESTED status and stop generating signals.')) {
      return;
    }

    try {
      await apiClient.deactivateStrategy(strategyId, tradingMode!);
      await fetchStrategies();
      toast.success('Strategy deactivated successfully');
    } catch (error) {
      console.error('Failed to deactivate strategy:', error);
      toast.error('Failed to deactivate strategy');
    }
  };

  const handleRetire = async (strategyId: string) => {
    if (!confirm('Are you sure you want to retire this strategy? This action cannot be undone and will permanently remove it.')) {
      return;
    }

    try {
      await apiClient.retireStrategy(strategyId, tradingMode!);
      await fetchStrategies();
      toast.success('Strategy retired successfully');
    } catch (error) {
      console.error('Failed to retire strategy:', error);
      toast.error('Failed to retire strategy');
    }
  };

  const handlePermanentDelete = async (strategyId: string) => {
    if (!confirm('⚠️ PERMANENT DELETE: This will permanently delete this retired strategy from the database. This action CANNOT be undone. Are you absolutely sure?')) {
      return;
    }

    try {
      await apiClient.permanentlyDeleteStrategy(strategyId, tradingMode!);
      await fetchStrategies();
      toast.success('Strategy permanently deleted');
    } catch (error) {
      console.error('Failed to permanently delete strategy:', error);
      toast.error('Failed to permanently delete strategy');
    }
  };

  const handleBulkPermanentDelete = async () => {
    if (selectedStrategies.size === 0) return;
    
    if (!confirm(`⚠️ PERMANENT DELETE: This will permanently delete ${selectedStrategies.size} retired strategies from the database. This action CANNOT be undone. Are you absolutely sure?`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const strategyId of selectedStrategies) {
      try {
        await apiClient.permanentlyDeleteStrategy(strategyId, tradingMode!);
        successCount++;
      } catch (err) {
        console.error(`Failed to permanently delete strategy ${strategyId}:`, err);
        failCount++;
      }
    }

    setSelectedStrategies(new Set());
    await fetchStrategies();
    
    toast.success(`Permanently deleted ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
  };

  // Helper functions
  const getStatusBadgeVariant = (status: StrategyStatus): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' => {
    switch (status) {
      case 'PROPOSED': return 'secondary';
      case 'BACKTESTED': return 'default';
      case 'DEMO': return 'warning';
      case 'LIVE': return 'success';
      case 'RETIRED': return 'destructive';
      default: return 'default';
    }
  };

  const formatMetric = (value: number | undefined, decimals: number = 2): string => {
    if (value === undefined || value === null) return 'N/A';
    return value.toFixed(decimals);
  };

  const getStrategyCategory = (strategy: Strategy): { label: string; variant: string } => {
    // Use top-level strategy_category (resolved by backend), fall back to metadata
    const category = strategy.strategy_category || strategy.metadata?.strategy_category || 
      (strategy.template_name ? 'template_based' : 'manual');
    
    if (category === 'alpha_edge') {
      return { label: 'Alpha Edge', variant: 'purple' };
    } else if (category === 'template_based') {
      return { label: 'Template', variant: 'blue' };
    } else {
      return { label: 'Manual', variant: 'gray' };
    }
  };

  const getStrategyType = (strategy: Strategy): string => {
    // Use top-level strategy_type (resolved by backend), fall back to metadata
    const type = strategy.strategy_type || strategy.metadata?.template_type || strategy.metadata?.alpha_edge_type;
    if (!type) return 'N/A';
    
    // Custom labels for specific types
    const typeLabels: Record<string, string> = {
      'gap_reversal': 'Gap Reversal',
      'volume_climax_reversal': 'Volume Climax',
      'obv_divergence': 'OBV Divergence',
      'vix_regime': 'VIX Regime',
      'pairs_trading': 'Pairs Trading',
      'end_of_month_momentum': 'Month-End Momentum',
      'dividend_aristocrat': 'Dividend Aristocrat',
      'insider_buying': 'Insider Buying',
      'revenue_acceleration': 'Revenue Accel.',
      'relative_value': 'Relative Value',
      'earnings_momentum': 'Earnings Momentum',
      'sector_rotation': 'Sector Rotation',
      'quality_mean_reversion': 'Quality Mean Rev.',
      'mean_reversion': 'Mean Reversion',
      'trend_following': 'Trend Following',
      'breakout': 'Breakout',
      'momentum': 'Momentum',
      'volatility': 'Volatility',
    };
    
    return typeLabels[type] || type.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  // Table columns for active strategies
  const activeStrategyColumns: ColumnDef<Strategy>[] = [
    {
      id: 'select',
      header: () => {
        const allSelected = filteredActiveStrategies.length > 0 && 
          filteredActiveStrategies.every(s => selectedStrategies.has(s.id));
        
        return (
          <input
            type="checkbox"
            checked={allSelected}
            onChange={(e) => {
              if (e.target.checked) {
                // Select all strategies across all pages
                setSelectedStrategies(new Set(filteredActiveStrategies.map(s => s.id)));
              } else {
                // Deselect all
                setSelectedStrategies(new Set());
              }
            }}
            className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
          />
        );
      },
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={(e) => row.toggleSelected(!!e.target.checked)}
          className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
        />
      ),
    },
    {
      accessorKey: 'name',
      header: 'Strategy',
      cell: ({ row }) => {
        const symbols = row.original.symbols || [];
        const primarySymbol = symbols[0] || '';
        const extraCount = symbols.length - 1;
        const meta = row.original.metadata || {};
        const isSuperseded = meta.superseded === true;
        const isPendingRetirement = meta.pending_retirement === true;
        const isDemotedFromActive = meta.demoted_from_active === true;
        return (
          <div>
            <RadixTooltipProvider delayDuration={300}>
              <RadixTooltip>
                <RadixTooltipTrigger asChild>
                  <div className="font-mono text-xs text-gray-200 truncate max-w-[200px] cursor-default">{row.original.name}</div>
                </RadixTooltipTrigger>
                <RadixTooltipContent className="bg-gray-900 text-gray-100 border-gray-700 text-xs font-mono">
                  {row.original.name}
                  {isSuperseded && meta.superseded_reason && (
                    <div className="text-amber-400 mt-1">{meta.superseded_reason}</div>
                  )}
                  {isPendingRetirement && meta.pending_retirement_reason && (
                    <div className="text-red-400 mt-1">{meta.pending_retirement_reason}</div>
                  )}
                  {isDemotedFromActive && meta.demotion_reason && (
                    <div className="text-blue-400 mt-1">{meta.demotion_reason}</div>
                  )}
                </RadixTooltipContent>
              </RadixTooltip>
            </RadixTooltipProvider>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-xs text-gray-400 font-mono font-semibold">{primarySymbol}</span>
              {extraCount > 0 && (
                <span className="text-xs text-blue-400 font-mono">(+{extraCount})</span>
              )}
              {isSuperseded && (
                <span className="text-[10px] px-1 py-0 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 font-mono">
                  Superseded
                </span>
              )}
              {isPendingRetirement && !isSuperseded && (
                <span className="text-[10px] px-1 py-0 rounded bg-red-500/20 text-red-400 border border-red-500/30 font-mono">
                  Retiring
                </span>
              )}
              {isDemotedFromActive && (
                <span className="text-[10px] px-1 py-0 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-mono">
                  Re-eval
                </span>
              )}
            </div>
          </div>
        );
      },
    },
    {
      id: 'sparkline',
      header: 'Equity',
      cell: ({ row }) => {
        const curve = row.original.backtest_results?.equity_curve;
        // Sample up to 20 points for the sparkline
        const step = Math.max(1, Math.floor(curve.length / 20));
        const sampled = curve.filter((_: any, i: number) => i % step === 0 || i === curve.length - 1);
        const lastVal = sampled[sampled.length - 1]?.equity ?? 0;
        const firstVal = sampled[0]?.equity ?? 0;
        const color = lastVal >= firstVal ? '#22c55e' : '#ef4444';
        const values = sampled.map((d: any) => d.equity ?? 0);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;
        const points = values.map((v: number, i: number) =>
          `${(i / (values.length - 1)) * 60},${24 - ((v - min) / range) * 24}`
        ).join(' ');
        return (
          <div className="w-[60px] h-[24px]">
            <svg width="60" height="24" viewBox="0 0 60 24">
              <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
            </svg>
          </div>
        );
      },
      size: 80,
    },
    {
      accessorKey: 'metadata.strategy_category',
      header: 'Category',
      cell: ({ row }) => {
        const { label, variant } = getStrategyCategory(row.original);
        return (
          <Badge 
            className={cn(
              "font-mono text-xs",
              variant === 'purple' && "bg-purple-500/20 text-purple-300 border-purple-500/30",
              variant === 'blue' && "bg-blue-500/20 text-blue-300 border-blue-500/30",
              variant === 'gray' && "bg-gray-500/20 text-gray-300 border-gray-500/30"
            )}
          >
            {label}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'metadata.template_type',
      header: 'Type',
      cell: ({ row }) => {
        const type = getStrategyType(row.original);
        return (
          <div className="text-xs text-gray-400 font-mono">
            {type}
          </div>
        );
      },
    },
    {
      id: 'direction',
      header: 'Direction',
      cell: ({ row }) => {
        const direction = row.original.metadata?.direction;
        const name = row.original.name || '';
        const isShort = direction === 'SHORT' || direction === 'short' || 
          (!direction && (name.toLowerCase().includes('short') || name.toLowerCase().includes('bear')));
        const label = isShort ? 'SHORT' : 'LONG';
        return (
          <Badge 
            className={cn(
              "font-mono text-xs",
              isShort 
                ? "bg-red-500/20 text-red-300 border-red-500/30" 
                : "bg-green-500/20 text-green-300 border-green-500/30"
            )}
          >
            {label}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'symbols',
      header: 'Symbols',
      cell: ({ row }) => {
        const tradedSymbols = (row.original as unknown as Record<string, unknown>).traded_symbols as string[] | undefined;
        const watchlist = row.original.symbols || [];
        const displaySymbols = tradedSymbols && tradedSymbols.length > 0 ? tradedSymbols : watchlist;
        return (
          <div className="text-sm font-mono text-gray-300">
            {displaySymbols.join(', ') || '—'}
          </div>
        );
      },
    },
    {
      id: 'positions',
      header: () => <div className="text-right">Positions</div>,
      cell: ({ row }) => {
        const count = row.original.performance_metrics?.open_positions || 0;
        return (
          <div className={cn(
            'text-right font-mono text-xs',
            count > 0 ? 'text-accent-green font-semibold' : 'text-gray-500'
          )}>
            {count}
          </div>
        );
      },
    },
    {
      id: 'orders',
      header: () => <div className="text-right">Pending Orders</div>,
      cell: ({ row }) => {
        const count = row.original.performance_metrics?.live_orders || 0;
        return (
          <div className={cn(
            'text-right font-mono text-xs',
            count > 0 ? 'text-amber-400 font-semibold' : 'text-gray-500'
          )}>
            {count}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.total_return',
      header: () => <div className="text-right">Return</div>,
      cell: ({ row }) => {
        const value = row.original.performance_metrics?.total_return;
        return (
          <div className={cn(
            'text-right font-mono text-xs font-semibold',
            value && value >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {value !== undefined ? formatPercentage(value * 100) : 'N/A'}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.sharpe_ratio',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs">
          {formatMetric(row.original.performance_metrics?.sharpe_ratio)}
        </div>
      ),
    },
    {
      id: 'alpha_vs_spy',
      header: () => <div className="text-right">Alpha</div>,
      cell: ({ row }) => {
        const alpha = (row.original as any).alpha_vs_spy;
        if (alpha == null) return <div className="text-right font-mono text-xs text-gray-600">—</div>;
        return (
          <div className={cn(
            'text-right font-mono text-xs font-semibold',
            alpha >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {alpha >= 0 ? '+' : ''}{(alpha * 100).toFixed(1)}%
          </div>
        );
      },
    },
    {
      id: 'win_rate',
      header: () => <div className="text-right">Win Rate</div>,
      cell: ({ row }) => {
        const winRate = row.original.performance_metrics?.win_rate;
        return (
          <div className="text-right font-mono text-xs text-gray-300">
            {winRate !== undefined ? formatPercentage(winRate * 100) : 'N/A'}
          </div>
        );
      },
    },
    {
      id: 'unrealized_pnl',
      header: () => <div className="text-right">Unreal. P&L</div>,
      cell: ({ row }) => {
        const pnl = row.original.performance_metrics?.unrealized_pnl;
        return (
          <div className={cn(
            'text-right font-mono text-xs font-semibold',
            pnl && pnl > 0 ? 'text-accent-green' : pnl && pnl < 0 ? 'text-accent-red' : 'text-gray-500'
          )}>
            {pnl !== undefined && pnl !== 0 ? formatCurrency(pnl) : '$0.00'}
          </div>
        );
      },
    },
    {
      id: 'health_score',
      accessorFn: (row) => row.performance_metrics?.health_score ?? -1,
      header: () => <div className="text-center">Health</div>,
      cell: ({ row }) => {
        const score = row.original.performance_metrics?.health_score;
        if (score === null || score === undefined) {
          return <div className="text-center text-gray-600 text-sm">—</div>;
        }
        const colors: Record<number, string> = {
          0: 'bg-red-500/30 text-red-300 border-red-500/40',
          1: 'bg-red-500/20 text-red-400 border-red-500/30',
          2: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
          3: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
          4: 'bg-green-500/20 text-green-400 border-green-500/30',
          5: 'bg-green-500/30 text-green-300 border-green-500/40',
        };
        return (
          <div className="flex justify-center">
            <span className={cn(
              'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-semibold border',
              colors[score] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
            )}>
              {score}
            </span>
          </div>
        );
      },
    },
    {
      id: 'decay_score',
      accessorFn: (row) => row.performance_metrics?.decay_score ?? -1,
      header: () => <div className="text-center">Decay</div>,
      cell: ({ row }) => {
        const score = row.original.performance_metrics?.decay_score;
        if (score === null || score === undefined) {
          return <div className="text-center text-gray-600 text-sm">—</div>;
        }
        let color = 'bg-green-500/20 text-green-400 border-green-500/30';
        if (score <= 0) color = 'bg-red-500/30 text-red-300 border-red-500/40';
        else if (score <= 2) color = 'bg-red-500/20 text-red-400 border-red-500/30';
        else if (score <= 4) color = 'bg-amber-500/20 text-amber-400 border-amber-500/30';
        else if (score <= 6) color = 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30';
        return (
          <div className="flex justify-center">
            <span className={cn(
              'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-semibold border',
              color
            )}>
              {score}
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: 'allocation_percent',
      header: () => <div className="text-right">Allocation</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs">
          {formatPercentage(row.original.allocation_percent)}
        </div>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Actions</div>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleViewDetails(row.original)}>
                <Eye className="mr-2 h-4 w-4" />
                View Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBacktest(row.original.id)}>
                <Activity className="mr-2 h-4 w-4" />
                Backtest
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {row.original.status === 'BACKTESTED' ? (
                <DropdownMenuItem 
                  onClick={() => handleActivate(row.original.id)}
                  className="text-accent-green"
                >
                  <PlayCircle className="mr-2 h-4 w-4" />
                  Activate
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem 
                  onClick={() => handleDeactivate(row.original.id)}
                  className="text-yellow-500"
                >
                  <Pause className="mr-2 h-4 w-4" />
                  Deactivate
                </DropdownMenuItem>
              )}
              <DropdownMenuItem 
                onClick={() => handleRetire(row.original.id)}
                className="text-accent-red"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Retire
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  // Table columns for retired strategies
  const retiredStrategyColumns: ColumnDef<Strategy>[] = [
    {
      id: 'select',
      header: () => {
        const allSelected = filteredRetiredStrategies.length > 0 && 
          filteredRetiredStrategies.every(s => selectedStrategies.has(s.id));
        
        return (
          <input
            type="checkbox"
            checked={allSelected}
            onChange={(e) => {
              if (e.target.checked) {
                setSelectedStrategies(new Set(filteredRetiredStrategies.map(s => s.id)));
              } else {
                setSelectedStrategies(new Set());
              }
            }}
            className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
          />
        );
      },
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={(e) => row.toggleSelected(!!e.target.checked)}
          className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
        />
      ),
    },
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <div>
          <div className="font-mono text-xs text-gray-200">{row.original.name}</div>
          <div className="text-xs text-gray-500 font-mono">{row.original.symbols.join(', ')}</div>
        </div>
      ),
    },

    {
      accessorKey: 'metadata.strategy_category',
      header: 'Category',
      cell: ({ row }) => {
        const { label, variant } = getStrategyCategory(row.original);
        return (
          <Badge 
            className={cn(
              "font-mono text-xs",
              variant === 'purple' && "bg-purple-500/20 text-purple-300 border-purple-500/30",
              variant === 'blue' && "bg-blue-500/20 text-blue-300 border-blue-500/30",
              variant === 'gray' && "bg-gray-500/20 text-gray-300 border-gray-500/30"
            )}
          >
            {label}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'metadata.template_type',
      header: 'Type',
      cell: ({ row }) => {
        const type = getStrategyType(row.original);
        return (
          <div className="text-xs text-gray-400 font-mono">
            {type}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.total_return',
      header: () => <div className="text-right">Final Return</div>,
      cell: ({ row }) => {
        const value = row.original.performance_metrics?.total_return;
        return (
          <div className={cn(
            'text-right font-mono text-xs font-semibold',
            value && value >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {value !== undefined ? formatPercentage(value * 100) : 'N/A'}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.sharpe_ratio',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs">
          {formatMetric(row.original.performance_metrics?.sharpe_ratio)}
        </div>
      ),
    },
    {
      accessorKey: 'performance_metrics.total_trades',
      header: () => <div className="text-right">Trades</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs text-gray-300">
          {row.original.performance_metrics?.total_trades || 0}
        </div>
      ),
    },
    {
      accessorKey: 'retired_at',
      header: 'Retired',
      cell: ({ row }) => {
        const retiredAt = row.original.retired_at;
        return (
          <div className="text-xs text-gray-500 font-mono">
            {retiredAt ? formatTimestamp(retiredAt, { includeTime: false }) : 'Unknown'}
          </div>
        );
      },
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Actions</div>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleViewDetails(row.original)}>
                <Eye className="mr-2 h-4 w-4" />
                View Details
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem 
                onClick={() => handlePermanentDelete(row.original.id)}
                className="text-accent-red"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Permanently Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  // Table columns for backtested strategies
  const backtestedStrategyColumns: ColumnDef<Strategy>[] = [
    {
      id: 'select',
      header: () => {
        const allSelected = filteredBacktestedStrategies.length > 0 && 
          filteredBacktestedStrategies.every(s => selectedStrategies.has(s.id));
        
        return (
          <input
            type="checkbox"
            checked={allSelected}
            onChange={(e) => {
              if (e.target.checked) {
                setSelectedStrategies(new Set(filteredBacktestedStrategies.map(s => s.id)));
              } else {
                setSelectedStrategies(new Set());
              }
            }}
            className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
          />
        );
      },
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={(e) => row.toggleSelected(!!e.target.checked)}
          className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
        />
      ),
    },
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <div>
          <div className="font-mono text-xs text-gray-200">{row.original.name}</div>
          <div className="text-xs text-gray-500 font-mono">{row.original.symbols.join(', ')}</div>
        </div>
      ),
    },

    {
      accessorKey: 'metadata.strategy_category',
      header: 'Category',
      cell: ({ row }) => {
        const { label, variant } = getStrategyCategory(row.original);
        return (
          <Badge 
            className={cn(
              "font-mono text-xs",
              variant === 'purple' && "bg-purple-500/20 text-purple-300 border-purple-500/30",
              variant === 'blue' && "bg-blue-500/20 text-blue-300 border-blue-500/30",
              variant === 'gray' && "bg-gray-500/20 text-gray-300 border-gray-500/30"
            )}
          >
            {label}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'metadata.template_type',
      header: 'Type',
      cell: ({ row }) => {
        const type = getStrategyType(row.original);
        return (
          <div className="text-xs text-gray-400 font-mono">
            {type}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.total_return',
      header: () => <div className="text-right">Backtest Return</div>,
      cell: ({ row }) => {
        const value = row.original.performance_metrics?.total_return;
        return (
          <div className={cn(
            'text-right font-mono text-xs font-semibold',
            value && value >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {value !== undefined ? formatPercentage(value * 100) : 'N/A'}
          </div>
        );
      },
    },
    {
      accessorKey: 'performance_metrics.sharpe_ratio',
      header: () => <div className="text-right">Sharpe</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs">
          {formatMetric(row.original.performance_metrics?.sharpe_ratio)}
        </div>
      ),
    },
    {
      accessorKey: 'performance_metrics.win_rate',
      header: () => <div className="text-right">Win Rate</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-xs">
          {row.original.performance_metrics?.win_rate 
            ? formatPercentage(row.original.performance_metrics.win_rate * 100)
            : 'N/A'}
        </div>
      ),
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => (
        <div className="text-xs text-gray-500 font-mono">
          {formatTimestamp(row.original.created_at, { includeTime: false })}
        </div>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Actions</div>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleViewDetails(row.original)}>
                <Eye className="mr-2 h-4 w-4" />
                View Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBacktest(row.original.id)}>
                <Activity className="mr-2 h-4 w-4" />
                Re-Backtest
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem 
                onClick={() => handleActivate(row.original.id)}
                className="text-accent-green"
              >
                <PlayCircle className="mr-2 h-4 w-4" />
                Activate
              </DropdownMenuItem>
              <DropdownMenuItem 
                onClick={() => handleRetire(row.original.id)}
                className="text-accent-red"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Retire
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  // ── Side panel computed data ──────────────────────────────────────
  const sideMetrics: CompactMetric[] = useMemo(() => [
    { label: 'Active', value: summaryMetrics.active, trend: summaryMetrics.active > 0 ? 'up' as const : 'neutral' as const },
    { label: 'Backtested', value: summaryMetrics.backtested, trend: 'neutral' as const },
    {
      label: 'Avg Sharpe',
      value: activeStrategies.length > 0
        ? (activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.sharpe_ratio || 0), 0) / activeStrategies.length).toFixed(2)
        : 'N/A',
      trend: 'neutral' as const,
    },
    {
      label: 'Avg Win Rate',
      value: activeStrategies.length > 0
        ? formatPercentage(
            (activeStrategies.reduce((sum, s) => sum + (s.performance_metrics?.win_rate || 0), 0) / activeStrategies.length) * 100
          )
        : 'N/A',
      trend: 'neutral' as const,
    },
  ], [summaryMetrics, activeStrategies]);

  // Top 5 template rankings for sidebar
  const top5Rankings = useMemo(() => {
    return [...templateRankings]
      .sort((a: any, b: any) => (b.win_rate ?? 0) - (a.win_rate ?? 0))
      .slice(0, 5);
  }, [templateRankings]);

  // Recent lifecycle events (activations, retirements, demotions)
  const recentLifecycleEvents = useMemo(() => {
    const events: Array<{ type: string; name: string; timestamp: string; color: string }> = [];

    // Recent activations (strategies that are DEMO/LIVE, sorted by updated_at)
    activeStrategies
      .filter(s => s.updated_at)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 3)
      .forEach(s => events.push({
        type: 'Activated',
        name: s.name,
        timestamp: s.updated_at,
        color: 'text-accent-green',
      }));

    // Recent retirements
    retiredStrategies
      .filter(s => s.retired_at)
      .sort((a, b) => new Date(b.retired_at!).getTime() - new Date(a.retired_at!).getTime())
      .slice(0, 3)
      .forEach(s => events.push({
        type: 'Retired',
        name: s.name,
        timestamp: s.retired_at!,
        color: 'text-accent-red',
      }));

    // Recent demotions
    idleDemotions.slice(0, 3).forEach((d: any) => events.push({
      type: 'Demoted',
      name: d.name,
      timestamp: d.timestamp || '',
      color: 'text-yellow-400',
    }));

    return events
      .filter(e => e.timestamp)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, 8);
  }, [activeStrategies, retiredStrategies, idleDemotions]);

  // Header actions for PageTemplate
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <button
        onClick={fetchStrategies}
        disabled={refreshing}
        className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
        title="Refresh"
      >
        <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
      </button>
    </div>
  );

  if (loading || tradingModeLoading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8">
          <PageSkeleton />
        </div>
      </DashboardLayout>
    );
  }

  if (error && strategies.length === 0) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8">
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <Target className="h-8 w-8 text-accent-red" />
            <div className="text-gray-400 font-mono">Failed to load strategies</div>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchStrategies}>Retry</Button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // ── Main Panel (65%) ─────────────────────────────────────────────────
  const strategyTabButtons = [
    { value: 'overview', label: 'Overview' },
    { value: 'active', label: `Active (${filteredActiveStrategies.length})` },
    { value: 'backtested', label: `Backtested (${filteredBacktestedStrategies.length})` },
    { value: 'retired', label: `Retired (${filteredRetiredStrategies.length})` },
    { value: 'templates', label: 'DSL Templates' },
    { value: 'ae-templates', label: 'AE Templates' },
    { value: 'symbols', label: 'Symbols' },
    { value: 'rankings', label: 'Rankings' },
    { value: 'blacklists', label: `Blacklists (${blacklists.length})` },
    { value: 'demotions', label: `Demotions (${idleDemotions.length})` },
  ];

  const mainPanel = (
    <div className="flex flex-col h-full">
      {/* Single 32px header row: title + inline tabs + actions */}
      <div className="flex items-center px-3 min-h-[32px] max-h-[32px] shrink-0 bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]">
        <div className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide flex-1 min-w-0">
          {strategyTabButtons.map((tab) => (
            <button
              key={tab.value}
              onClick={() => {
                setStrategiesTab(tab.value);
                if (tab.value === 'retired') fetchRetiredStrategies();
              }}
              className={cn(
                'px-3 py-1 text-[13px] font-medium rounded whitespace-nowrap transition-colors shrink-0',
                strategiesTab === tab.value
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
            onClick={fetchStrategies}
            className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} className={cn(refreshing && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-auto">
        <Tabs value={strategiesTab} onValueChange={(v) => { setStrategiesTab(v); if (v === 'retired') fetchRetiredStrategies(); }} className="flex flex-col h-full">
          {/* Hidden TabsList — we use custom buttons above */}
          <TabsList className="hidden">
            {strategyTabButtons.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>{tab.label}</TabsTrigger>
            ))}
          </TabsList>

          <div className="flex-1 min-h-0 overflow-auto">

          {/* Overview Tab */}
          <TabsContent value="overview" className="p-2 space-y-2">
            <MetricGrid items={[
              { label: 'Active', value: summaryMetrics.active, color: summaryMetrics.active > 0 ? 'text-[#22c55e]' : undefined },
              { label: 'Backtested', value: summaryMetrics.backtested },
              { label: 'Avg Perf', value: formatPercentage(summaryMetrics.avgPerformance * 100), color: summaryMetrics.avgPerformance >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]' },
              { label: 'Success Rate', value: formatPercentage(summaryMetrics.successRate), color: summaryMetrics.successRate >= 50 ? 'text-[#22c55e]' : 'text-[#ef4444]' },
            ]} cols={4} />

            {/* Template Distribution — simple bars, no Card */}
            <div className="border-t border-[var(--color-dark-border)] pt-2">
              <SectionLabel>Template Distribution</SectionLabel>
              <div className="space-y-1">
                {templateDistribution.map(({ name, count }) => (
                  <div key={name} className="flex items-center gap-2 px-1">
                    <span className="text-xs font-mono text-gray-400 w-28 truncate">{name}</span>
                    <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full bg-accent-green" style={{ width: `${(count / Math.max(activeStrategies.length, 1)) * 100}%` }} />
                    </div>
                    <span className="text-xs font-mono text-gray-500 w-6 text-right">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Category + Type Distribution — side by side, no Card */}
            <div className="grid grid-cols-2 gap-2 border-t border-[var(--color-dark-border)] pt-2">
              <div>
                <SectionLabel>By Category</SectionLabel>
                <div className="space-y-1">
                  {categoryDistribution.map(({ name, count }) => (
                    <div key={name} className="flex items-center gap-2 px-1">
                      <span className="text-xs font-mono text-gray-400 w-24 truncate">{name}</span>
                      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                        <div className={cn("h-full", name === 'Alpha Edge' ? "bg-purple-500" : name === 'Template-Based' ? "bg-blue-500" : "bg-gray-500")}
                          style={{ width: `${(count / Math.max(activeStrategies.length, 1)) * 100}%` }} />
                      </div>
                      <span className="text-xs font-mono text-gray-500 w-6 text-right">{count}</span>
                    </div>
                  ))}
                  {categoryDistribution.length === 0 && <div className="text-xs text-gray-600 px-1">No data</div>}
                </div>
              </div>
              <div>
                <SectionLabel>By Type</SectionLabel>
                <div className="space-y-1">
                  {typeDistribution.map(({ name, count }) => (
                    <div key={name} className="flex items-center gap-2 px-1">
                      <span className="text-xs font-mono text-gray-400 w-24 truncate">{name}</span>
                      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full bg-accent-green" style={{ width: `${(count / Math.max(activeStrategies.length, 1)) * 100}%` }} />
                      </div>
                      <span className="text-xs font-mono text-gray-500 w-6 text-right">{count}</span>
                    </div>
                  ))}
                  {typeDistribution.length === 0 && <div className="text-xs text-gray-600 px-1">No data</div>}
                </div>
              </div>
            </div>

            {/* Top Performing — simple list, no Card */}
            <div className="border-t border-[var(--color-dark-border)] pt-2">
              <SectionLabel>Top 5 by Return</SectionLabel>
              <div className="space-y-0.5">
                {topPerformingStrategies.map((strategy, index) => (
                  <div key={strategy.id} className="flex items-center justify-between px-2 py-1.5 hover:bg-gray-800/40 rounded">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-mono text-gray-500 w-4">{index + 1}</span>
                      <div className="min-w-0">
                        <div className="text-xs font-mono text-gray-200 truncate">{strategy.name}</div>
                        <div className="text-xs text-gray-500 font-mono truncate">{strategy.symbols.join(', ')}</div>
                      </div>
                    </div>
                    <div className="text-right shrink-0 ml-2">
                      <div className={cn('text-xs font-mono font-bold', (strategy.performance_metrics?.total_return || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                        {formatPercentage((strategy.performance_metrics?.total_return || 0) * 100)}
                      </div>
                      <div className="text-xs text-gray-500 font-mono">S: {formatMetric(strategy.performance_metrics?.sharpe_ratio)}</div>
                    </div>
                  </div>
                ))}
                {topPerformingStrategies.length === 0 && (
                  <div className="text-center text-gray-600 text-xs py-4">No active strategies</div>
                )}
              </div>
            </div>

            {/* Strategy Equity Curves Overlay — normalized to 100 */}
            {(() => {
              const strategiesWithCurves = activeStrategies
                .filter(s => s.backtest_results?.equity_curve && s.backtest_results.equity_curve.length >= 2)
                .slice(0, 12);
              if (strategiesWithCurves.length < 2) return null;
              const CURVE_COLORS = ['#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#f97316','#84cc16','#6366f1','#14b8a6','#a78bfa'];
              const series = strategiesWithCurves.map((s, i) => {
                const raw = s.backtest_results!.equity_curve!;
                const base = raw[0].equity || 1;
                return {
                  id: `strat_${s.id}`,
                  type: 'line' as const,
                  data: raw.map(p => ({ time: p.timestamp.slice(0, 10), value: (p.equity / base) * 100 })),
                  color: CURVE_COLORS[i % CURVE_COLORS.length],
                  lineWidth: 1,
                };
              });
              return (
                <div className="border-t border-[var(--color-dark-border)] pt-2">
                  <SectionLabel>Strategy Equity Curves (Normalized)</SectionLabel>
                  <TvChart series={series} height={200} showTimeScale autoResize />
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 px-1">
                    {strategiesWithCurves.map((s, i) => (
                      <div key={s.id} className="flex items-center gap-1">
                        <div className="w-2.5 h-0.5 rounded" style={{ backgroundColor: CURVE_COLORS[i % CURVE_COLORS.length] }} />
                        <span className="text-[10px] font-mono text-gray-500 truncate max-w-[80px]">{s.symbols[0] || s.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </TabsContent>

          {/* Active Strategies Tab */}
          <TabsContent value="active" className="p-2 space-y-2">
            <FilterBar
              info={`${filteredActiveStrategies.length} of ${activeStrategies.length}`}
              searchValue={searchQuery}
              onSearchChange={setSearchQuery}
              searchPlaceholder="Search..."
            >
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="BACKTESTED">Backtested</SelectItem>
                  <SelectItem value="DEMO">Demo</SelectItem>
                  <SelectItem value="LIVE">Live</SelectItem>
                </SelectContent>
              </Select>
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Category" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                  <SelectItem value="template_based">Template-Based</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  {availableTypes.map(type => (
                    <SelectItem key={type} value={type}>{type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={templateFilter} onValueChange={setTemplateFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Template" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Templates</SelectItem>
                  {availableTemplates.map(template => (
                    <SelectItem key={template} value={template}>{template}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Regime" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Regimes</SelectItem>
                  {availableRegimes.map(regime => (
                    <SelectItem key={regime} value={regime}>{regime}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Source" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sources</SelectItem>
                  <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                  <SelectItem value="USER">Manual</SelectItem>
                </SelectContent>
              </Select>
            </FilterBar>

            {/* Bulk Actions */}
            {selectedStrategies.size > 0 && (
              <div className="flex items-center gap-2 py-1 border-t border-[var(--color-dark-border)]">
                <span className="text-xs text-gray-500 font-mono">{selectedStrategies.size} sel</span>
                <Button onClick={handleBulkBacktest} variant="outline" size="sm" className="h-6 text-xs px-2">Backtest</Button>
                {selectedStrategiesInfo.hasBacktested && (
                  <Button onClick={handleBulkActivate} variant="outline" size="sm" className="h-6 text-xs px-2 text-accent-green border-accent-green/30">Activate</Button>
                )}
                {selectedStrategiesInfo.hasActive && (
                  <Button onClick={handleBulkDeactivate} variant="outline" size="sm" className="h-6 text-xs px-2 text-yellow-500 border-yellow-500/30">Deactivate</Button>
                )}
                <Button onClick={handleBulkRetire} variant="destructive" size="sm" className="h-6 text-xs px-2">Retire</Button>
                {selectedStrategies.size === 2 && (
                  <Button onClick={() => {
                    const selected = Array.from(selectedStrategies).map(id => strategies.find(s => s.id === id)).filter(Boolean) as Strategy[];
                    if (selected.length === 2) { setComparedStrategies([selected[0], selected[1]]); setShowComparison(true); }
                  }} variant="outline" size="sm" className="h-6 text-xs px-2 text-blue-400 border-blue-400/30">Compare</Button>
                )}
                <Button onClick={() => setSelectedStrategies(new Set())} variant="ghost" size="sm" className="h-6 text-xs px-2 ml-auto">Clear</Button>
              </div>
            )}

            <DataTable
              columns={activeStrategyColumns}
              data={filteredActiveStrategies}
              pageSize={20}
              getRowId={(row) => row.id}
              onRowClick={(row) => handleViewDetails(row)}
              rowSelection={Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]))}
              onRowSelectionChange={(updaterOrValue) => {
                const currentSelection = Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]));
                const newSelection = typeof updaterOrValue === 'function' ? updaterOrValue(currentSelection) : updaterOrValue;
                setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
              }}
            />
          </TabsContent>

          {/* Backtested Strategies Tab */}
          <TabsContent value="backtested" className="p-2 space-y-2">
            <FilterBar
              info={`${filteredBacktestedStrategies.length} of ${backtestedStrategies.length}`}
              searchValue={searchQuery}
              onSearchChange={setSearchQuery}
              searchPlaceholder="Search..."
            >
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Category" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                  <SelectItem value="template_based">Template-Based</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  {availableTypes.map(type => (
                    <SelectItem key={type} value={type}>{type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={templateFilter} onValueChange={setTemplateFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Template" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Templates</SelectItem>
                  {availableTemplates.map(template => (<SelectItem key={template} value={template}>{template}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Regime" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Regimes</SelectItem>
                  {availableRegimes.map(regime => (<SelectItem key={regime} value={regime}>{regime}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Source" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sources</SelectItem>
                  <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                  <SelectItem value="USER">Manual</SelectItem>
                </SelectContent>
              </Select>
            </FilterBar>

            {/* Bulk Actions */}
            {selectedStrategies.size > 0 && (
              <div className="flex items-center gap-2 py-1 border-t border-[var(--color-dark-border)]">
                <span className="text-xs text-gray-500 font-mono">{selectedStrategies.size} sel</span>
                <Button onClick={handleBulkBacktest} variant="outline" size="sm" className="h-6 text-xs px-2">Re-Backtest</Button>
                <Button onClick={handleBulkActivate} variant="outline" size="sm" className="h-6 text-xs px-2 text-accent-green border-accent-green/30">Activate</Button>
                <Button onClick={handleBulkRetire} variant="destructive" size="sm" className="h-6 text-xs px-2">Retire</Button>
                <Button onClick={() => setSelectedStrategies(new Set())} variant="ghost" size="sm" className="h-6 text-xs px-2 ml-auto">Clear</Button>
              </div>
            )}

            <DataTable
              columns={backtestedStrategyColumns}
              data={filteredBacktestedStrategies}
              pageSize={20}
              getRowId={(row) => row.id}
              onRowClick={(row) => handleViewDetails(row)}
              rowSelection={Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]))}
              onRowSelectionChange={(updaterOrValue) => {
                const currentSelection = Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]));
                const newSelection = typeof updaterOrValue === 'function' ? updaterOrValue(currentSelection) : updaterOrValue;
                setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
              }}
            />
          </TabsContent>

          {/* Retired Strategies Tab */}
          <TabsContent value="retired" className="p-2 space-y-2">
            <FilterBar
              info={`${filteredRetiredStrategies.length} of ${retiredStrategies.length}`}
              searchValue={searchQuery}
              onSearchChange={setSearchQuery}
              searchPlaceholder="Search..."
            >
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Category" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                  <SelectItem value="template_based">Template-Based</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  {availableTypes.map(type => (
                    <SelectItem key={type} value={type}>{type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={templateFilter} onValueChange={setTemplateFilter}>
                <SelectTrigger className="h-7 text-xs w-[120px]"><SelectValue placeholder="Template" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Templates</SelectItem>
                  {availableTemplates.map(template => (<SelectItem key={template} value={template}>{template}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Regime" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Regimes</SelectItem>
                  {availableRegimes.map(regime => (<SelectItem key={regime} value={regime}>{regime}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="h-7 text-xs w-[110px]"><SelectValue placeholder="Source" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sources</SelectItem>
                  <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                  <SelectItem value="USER">Manual</SelectItem>
                </SelectContent>
              </Select>
            </FilterBar>

            {/* Bulk Actions */}
            {selectedStrategies.size > 0 && (
              <div className="flex items-center gap-2 py-1 border-t border-[var(--color-dark-border)]">
                <span className="text-xs text-gray-500 font-mono">{selectedStrategies.size} sel</span>
                <Button onClick={handleBulkPermanentDelete} variant="destructive" size="sm" className="h-6 text-xs px-2">Permanently Delete</Button>
                <Button onClick={() => setSelectedStrategies(new Set())} variant="ghost" size="sm" className="h-6 text-xs px-2 ml-auto">Clear</Button>
              </div>
            )}

            <DataTable
              columns={retiredStrategyColumns}
              data={filteredRetiredStrategies}
              pageSize={20}
              getRowId={(row) => row.id}
              rowSelection={Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]))}
              onRowSelectionChange={(updaterOrValue) => {
                const currentSelection = Object.fromEntries(Array.from(selectedStrategies).map(id => [id, true]));
                const newSelection = typeof updaterOrValue === 'function' ? updaterOrValue(currentSelection) : updaterOrValue;
                setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
              }}
            />
          </TabsContent>

          {/* DSL Templates Tab */}
          <TabsContent value="templates" className="p-2">
            <TemplateManager category="dsl" />
          </TabsContent>

          {/* AE Templates Tab */}
          <TabsContent value="ae-templates" className="p-2">
            <TemplateManager category="alpha_edge" />
          </TabsContent>

          {/* Symbols Tab */}
          <TabsContent value="symbols" className="p-2">
            <SymbolManager />
          </TabsContent>

          {/* Template Rankings Tab (Task 9.1) */}
          <TabsContent value="rankings" className="p-2">
              {templateRankingsLoading ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">Loading rankings...</div>
              ) : templateRankings.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No template ranking data available</div>
              ) : (
                <>
                  <FilterBar>
                    <Select value={templateRankingFamilyFilter} onValueChange={setTemplateRankingFamilyFilter}>
                      <SelectTrigger className="w-[140px] h-7 text-xs"><SelectValue placeholder="Family" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Families</SelectItem>
                        {Array.from(new Set(templateRankings.map((t: any) => t.family || t.template_type || 'unknown'))).sort().map((f) => (
                          <SelectItem key={String(f)} value={String(f)}>{String(f)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={templateRankingTimeframeFilter} onValueChange={setTemplateRankingTimeframeFilter}>
                      <SelectTrigger className="w-[140px] h-7 text-xs"><SelectValue placeholder="Timeframe" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Timeframes</SelectItem>
                        {Array.from(new Set(templateRankings.map((t: any) => t.timeframe).filter(Boolean))).sort().map((tf) => (
                          <SelectItem key={String(tf)} value={String(tf)}>{String(tf)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FilterBar>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono table-dense">
                      <thead>
                        <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                          {[
                            { key: 'name', label: 'Template' },
                            { key: 'win_rate', label: 'Win Rate' },
                            { key: 'avg_sharpe', label: 'Avg Sharpe' },
                            { key: 'total_trades', label: 'Trades' },
                            { key: 'active_count', label: 'Active' },
                            { key: 'last_proposal_date', label: 'Last Proposal' },
                          ].map((col) => (
                            <th key={col.key} className={cn('py-1.5 px-2 text-left cursor-pointer hover:text-gray-200 text-xs', col.key !== 'name' && 'text-right')}
                              onClick={() => { if (templateRankingSortKey === col.key) { setTemplateRankingSortDir((d) => d === 'asc' ? 'desc' : 'asc'); } else { setTemplateRankingSortKey(col.key); setTemplateRankingSortDir('desc'); } }}>
                              {col.label} {templateRankingSortKey === col.key ? (templateRankingSortDir === 'desc' ? '↓' : '↑') : ''}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {templateRankings
                          .filter((t: any) => {
                            const matchFamily = templateRankingFamilyFilter === 'all' || (t.family || t.template_type || 'unknown') === templateRankingFamilyFilter;
                            const matchTf = templateRankingTimeframeFilter === 'all' || t.timeframe === templateRankingTimeframeFilter;
                            return matchFamily && matchTf;
                          })
                          .sort((a: any, b: any) => {
                            const av = a[templateRankingSortKey] ?? 0;
                            const bv = b[templateRankingSortKey] ?? 0;
                            if (typeof av === 'string') return templateRankingSortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
                            return templateRankingSortDir === 'asc' ? av - bv : bv - av;
                          })
                          .map((t: any, idx: number) => (
                            <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                              <td className="py-1.5 px-2 text-gray-200 truncate max-w-[200px] text-xs">{t.name || t.template_name || '—'}</td>
                              <td className={cn('py-1.5 px-2 text-right text-[13px]', (t.win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-accent-red')}>{t.win_rate != null ? `${(t.win_rate).toFixed(1)}%` : '—'}</td>
                              <td className="py-1.5 px-2 text-right text-[13px]">{t.avg_sharpe != null ? t.avg_sharpe.toFixed(2) : '—'}</td>
                              <td className="py-1.5 px-2 text-right text-[13px]">{t.total_trades ?? '—'}</td>
                              <td className="py-1.5 px-2 text-right text-[13px]">{t.active_count ?? '—'}</td>
                              <td className="py-1.5 px-2 text-right text-xs text-gray-500">{t.last_proposal_date ? new Date(t.last_proposal_date).toLocaleDateString() : '—'}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
          </TabsContent>

          {/* Blacklists Tab (Task 9.1) */}
          <TabsContent value="blacklists" className="p-2">
              {blacklists.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No blacklisted combinations</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)] text-gray-500 text-xs">
                        <th className="py-1.5 px-2 text-left">Template</th>
                        <th className="py-1.5 px-2 text-left">Symbol</th>
                        <th className="py-1.5 px-2 text-left">Type</th>
                        <th className="py-1.5 px-2 text-right">Rejections</th>
                        <th className="py-1.5 px-2 text-left">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blacklists.map((bl: any, idx: number) => (
                        <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                          <td className="py-1.5 px-2 text-gray-200 truncate max-w-[180px] text-xs">{bl.template}</td>
                          <td className="py-1.5 px-2 text-gray-300 text-xs">{bl.symbol}</td>
                          <td className="py-1.5 px-2"><Badge variant="secondary" className="text-xs">{bl.type === 'rejection' ? 'Rejection' : 'Zero Trade'}</Badge></td>
                          <td className="py-1.5 px-2 text-right text-gray-300 text-xs">{bl.count}</td>
                          <td className="py-1.5 px-2 text-gray-500 text-xs">{bl.timestamp ? new Date(bl.timestamp).toLocaleDateString() : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
          </TabsContent>

          {/* Idle Demotions Tab (Task 9.1) */}
          <TabsContent value="demotions" className="p-2">
              {idleDemotions.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No recent demotions</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)] text-gray-500 text-xs">
                        <th className="py-1.5 px-2 text-left">Strategy</th>
                        <th className="py-1.5 px-2 text-left">Timestamp</th>
                        <th className="py-1.5 px-2 text-left">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {idleDemotions.map((d: any, idx: number) => (
                        <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                          <td className="py-1.5 px-2 text-gray-200 text-xs">{d.name}</td>
                          <td className="py-1.5 px-2 text-gray-500 text-xs">{d.timestamp ? formatTimestamp(d.timestamp) : '—'}</td>
                          <td className="py-1.5 px-2 text-gray-500 text-xs">{d.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
          </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );

  // ── Side Panel (35%) ─────────────────────────────────────────────────
  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Intelligence"
        panelId="strategies-side"
        onRefresh={fetchStrategies}
      >
        <div className="flex flex-col gap-1 p-1.5 h-full">
          {/* CompactMetricRow */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Top 5 Rankings — direct table, no nested PanelHeader */}
          <div className="border-t border-[var(--color-dark-border)] pt-1.5">
            <SectionLabel>Top 5 Rankings</SectionLabel>
            {templateRankingsLoading ? (
              <div className="text-center py-3 text-xs text-gray-500">Loading...</div>
            ) : top5Rankings.length === 0 ? (
              <div className="text-center py-3 text-xs text-gray-500">No ranking data</div>
            ) : (
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                    <th className="py-1 px-1.5 text-left text-xs">Template</th>
                    <th className="py-1 px-1.5 text-right text-[13px]">WR</th>
                    <th className="py-1 px-1.5 text-right text-[13px]">Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {top5Rankings.map((t: any, idx: number) => (
                    <tr key={idx} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                      <td className="py-1 px-1.5 text-gray-200 truncate max-w-[120px] text-[13px]">{t.name || t.template_name || '—'}</td>
                      <td className={cn('py-1 px-1.5 text-right text-[13px]', (t.win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-accent-red')}>
                        {t.win_rate != null ? `${t.win_rate.toFixed(1)}%` : '—'}
                      </td>
                      <td className="py-1 px-1.5 text-right text-[13px]">{t.avg_sharpe != null ? t.avg_sharpe.toFixed(2) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Strategy Allocation Viz (Sprint 7.4) */}
          {activeStrategies.length > 0 && (
            <div className="border-t border-[var(--color-dark-border)] pt-1.5">
              <SectionLabel>Allocation vs Deployed</SectionLabel>
              <div className="space-y-1 overflow-auto max-h-[200px]">
                {activeStrategies.slice(0, 10).map((s: any) => {
                  const allocated = s.allocated_capital ?? 0;
                  const deployed = s.deployed_capital ?? 0;
                  const pct = allocated > 0 ? Math.min(deployed / allocated, 1.5) : 0;
                  const isOver = pct > 1.0;
                  const isNear = pct > 0.9 && !isOver;
                  return (
                    <div key={s.id} className="px-1">
                      <div className="flex items-center justify-between text-[10px] font-mono mb-0.5">
                        <span className="text-gray-400 truncate max-w-[120px]">{s.name?.replace(/ V\d+$/, '') || s.id.slice(0, 8)}</span>
                        <div className="flex items-center gap-1">
                          {isOver && <span className="text-accent-red font-bold">OVER</span>}
                          {isNear && <span className="text-yellow-400 font-bold">90%+</span>}
                          <span className="text-gray-500">{allocated > 0 ? `$${(deployed/1000).toFixed(0)}k/$${(allocated/1000).toFixed(0)}k` : '—'}</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all', isOver ? 'bg-accent-red' : isNear ? 'bg-yellow-400' : 'bg-accent-green')}
                          style={{ width: `${Math.min(pct * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent Lifecycle Events — direct list, no nested PanelHeader */}
          <div className="border-t border-[var(--color-dark-border)] pt-1.5">
            <SectionLabel>Recent Events</SectionLabel>
            {recentLifecycleEvents.length === 0 ? (
              <div className="text-center py-3 text-xs text-gray-500">No recent events</div>
            ) : (
              <div className="space-y-0.5 overflow-auto max-h-[300px]">
                {recentLifecycleEvents.map((event, idx) => (
                  <div key={idx} className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-gray-800/40">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={cn(
                        'text-xs font-mono font-semibold px-1 py-0.5 rounded',
                        event.type === 'Activated' && 'bg-accent-green/20 text-accent-green',
                        event.type === 'Retired' && 'bg-accent-red/20 text-accent-red',
                        event.type === 'Demoted' && 'bg-yellow-400/20 text-yellow-400',
                      )}>
                        {event.type}
                      </span>
                      <span className="font-mono text-[13px] text-gray-200 truncate">{event.name}</span>
                    </div>
                    <span className="text-xs text-gray-500 shrink-0 ml-1">{formatTimestamp(event.timestamp)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Return: 2-panel layout ─────────────────────────────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Strategies"
        description={tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading'}
        actions={headerActions}
        compact={true}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={pollingRefreshing && !loading} />
          <ResizablePanelLayout
            layoutId="strategies-panels"
            direction="horizontal"
            panels={[
              {
                id: 'strategies-main',
                defaultSize: 65,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'strategies-side',
                defaultSize: 35,
                minSize: 250,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>

      {/* Strategy Details Dialog */}
      <Dialog open={detailsDialogOpen} onOpenChange={setDetailsDialogOpen}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Target className="h-5 w-5" />
                {selectedStrategy?.name}
              </DialogTitle>
              <DialogDescription>
                Strategy details and performance metrics
              </DialogDescription>
            </DialogHeader>
            
            {selectedStrategy && (
              <div className="space-y-6">
                {/* Basic Info with Badges */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Status</div>
                    <Badge variant={getStatusBadgeVariant(selectedStrategy.status)}>
                      {selectedStrategy.status}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Template</div>
                    <div className="text-sm font-mono">{selectedStrategy.template_name || 'Manual'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Type</div>
                    <div className="text-sm font-mono">{getStrategyType(selectedStrategy)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Direction</div>
                    <Badge className={cn(
                      "font-mono text-xs",
                      (selectedStrategy.metadata?.direction === 'SHORT' || selectedStrategy.metadata?.direction === 'short' || 
                        (!selectedStrategy.metadata?.direction && (selectedStrategy.name || '').toLowerCase().includes('short')))
                        ? "bg-red-500/20 text-red-300 border-red-500/30" 
                        : "bg-green-500/20 text-green-300 border-green-500/30"
                    )}>
                      {(selectedStrategy.metadata?.direction === 'SHORT' || selectedStrategy.metadata?.direction === 'short' || 
                        (!selectedStrategy.metadata?.direction && (selectedStrategy.name || '').toLowerCase().includes('short')))
                        ? 'SHORT' : 'LONG'}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Allocation</div>
                    <div className="text-sm font-mono">{formatPercentage(selectedStrategy.allocation_percent)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Symbols</div>
                    <div className="text-sm font-mono">
                      {selectedStrategy.symbols[0] || '\u2014'}
                      {selectedStrategy.symbols.length > 1 && (
                        <span className="text-blue-400 ml-1">(+{selectedStrategy.symbols.length - 1})</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Live Trading Stats */}
                {selectedStrategy.performance_metrics && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Live Trading Stats</div>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Open Positions</div>
                        <div className={cn(
                          'text-lg font-mono font-bold',
                          (selectedStrategy.performance_metrics.open_positions || 0) > 0 ? 'text-accent-green' : 'text-gray-500'
                        )}>
                          {selectedStrategy.performance_metrics.open_positions || 0}
                        </div>
                      </div>
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Pending Orders</div>
                        <div className={cn(
                          'text-lg font-mono font-bold',
                          (selectedStrategy.performance_metrics.live_orders || 0) > 0 ? 'text-amber-400' : 'text-gray-500'
                        )}>
                          {selectedStrategy.performance_metrics.live_orders || 0}
                        </div>
                      </div>
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Unrealized P&L</div>
                        <div className={cn(
                          'text-lg font-mono font-bold',
                          (selectedStrategy.performance_metrics.unrealized_pnl || 0) > 0 ? 'text-accent-green' 
                            : (selectedStrategy.performance_metrics.unrealized_pnl || 0) < 0 ? 'text-accent-red' 
                            : 'text-gray-500'
                        )}>
                          {formatCurrency(selectedStrategy.performance_metrics.unrealized_pnl || 0)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Watchlist */}
                {selectedStrategy.symbols && selectedStrategy.symbols.length > 1 && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Watchlist ({selectedStrategy.symbols.length} symbols)</div>
                    <div className="flex flex-wrap gap-2 p-3 bg-dark-surface rounded-lg border border-dark-border">
                      {selectedStrategy.symbols.map((symbol, idx) => (
                        <Badge key={idx} className="font-mono text-xs bg-dark-bg text-gray-300 border-dark-border">
                          {symbol}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Strategy Category and Scores */}
                {selectedStrategy.metadata && (
                  <div className="flex flex-wrap gap-2">
                    {/* Strategy Category Badge */}
                    {(selectedStrategy.strategy_category || selectedStrategy.metadata.strategy_category) === 'alpha_edge' ? (
                      <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/30">
                        Alpha Edge
                      </Badge>
                    ) : (selectedStrategy.strategy_category || selectedStrategy.metadata.strategy_category) === 'template_based' || selectedStrategy.template_name ? (
                      <Badge className="bg-blue-500/20 text-blue-300 border-blue-500/30">
                        Template-Based
                      </Badge>
                    ) : (
                      <Badge className="bg-gray-500/20 text-gray-300 border-gray-500/30">
                        Manual
                      </Badge>
                    )}
                    
                    {/* Alpha Edge Type Badge */}
                    {(selectedStrategy.strategy_category || selectedStrategy.metadata.strategy_category) === 'alpha_edge' && 
                      (selectedStrategy.metadata.alpha_edge_type || selectedStrategy.strategy_type) && (
                      <Badge className="bg-purple-500/10 text-purple-200 border-purple-500/20 font-mono text-xs">
                        {getStrategyType(selectedStrategy)}
                      </Badge>
                    )}
                    
                    {/* Conviction Score Badge */}
                    {selectedStrategy.metadata.conviction_score !== undefined && (
                      <Badge 
                        className={cn(
                          "font-mono",
                          selectedStrategy.metadata.conviction_score >= 80 
                            ? "bg-green-500/20 text-green-300 border-green-500/30"
                            : selectedStrategy.metadata.conviction_score >= 70
                            ? "bg-yellow-500/20 text-yellow-300 border-yellow-500/30"
                            : "bg-red-500/20 text-red-300 border-red-500/30"
                        )}
                      >
                        Conviction: {selectedStrategy.metadata.conviction_score.toFixed(0)}
                      </Badge>
                    )}
                    
                    {/* ML Confidence Badge */}
                    {selectedStrategy.metadata.ml_confidence !== undefined && (
                      <Badge 
                        className={cn(
                          "font-mono",
                          selectedStrategy.metadata.ml_confidence >= 0.8 
                            ? "bg-green-500/20 text-green-300 border-green-500/30"
                            : selectedStrategy.metadata.ml_confidence >= 0.7
                            ? "bg-yellow-500/20 text-yellow-300 border-yellow-500/30"
                            : "bg-red-500/20 text-red-300 border-red-500/30"
                        )}
                      >
                        ML Confidence: {(selectedStrategy.metadata.ml_confidence * 100).toFixed(0)}%
                      </Badge>
                    )}
                  </div>
                )}

                {/* Fundamental Data */}
                {selectedStrategy.metadata?.fundamental_data && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Fundamental Data</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 p-3 bg-dark-surface rounded-lg border border-dark-border">
                      {selectedStrategy.metadata.fundamental_data.eps !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">EPS</div>
                          <div className="text-sm font-mono text-gray-200">
                            ${selectedStrategy.metadata.fundamental_data.eps.toFixed(2)}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.metadata.fundamental_data.revenue_growth !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">Revenue Growth</div>
                          <div className={cn(
                            "text-sm font-mono font-semibold",
                            selectedStrategy.metadata.fundamental_data.revenue_growth >= 0 
                              ? "text-accent-green" 
                              : "text-accent-red"
                          )}>
                            {formatPercentage(selectedStrategy.metadata.fundamental_data.revenue_growth * 100)}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.metadata.fundamental_data.pe_ratio !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">P/E Ratio</div>
                          <div className="text-sm font-mono text-gray-200">
                            {selectedStrategy.metadata.fundamental_data.pe_ratio.toFixed(2)}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.metadata.fundamental_data.roe !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">ROE</div>
                          <div className={cn(
                            "text-sm font-mono font-semibold",
                            selectedStrategy.metadata.fundamental_data.roe >= 0.15 
                              ? "text-accent-green" 
                              : "text-gray-200"
                          )}>
                            {formatPercentage(selectedStrategy.metadata.fundamental_data.roe * 100)}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.metadata.fundamental_data.debt_to_equity !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">Debt/Equity</div>
                          <div className={cn(
                            "text-sm font-mono font-semibold",
                            selectedStrategy.metadata.fundamental_data.debt_to_equity <= 0.5 
                              ? "text-accent-green" 
                              : "text-yellow-500"
                          )}>
                            {selectedStrategy.metadata.fundamental_data.debt_to_equity.toFixed(2)}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.metadata.fundamental_data.market_cap !== undefined && (
                        <div>
                          <div className="text-xs text-gray-500">Market Cap</div>
                          <div className="text-sm font-mono text-gray-200">
                            ${(selectedStrategy.metadata.fundamental_data.market_cap / 1e9).toFixed(2)}B
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Fundamental Checks */}
                {selectedStrategy.metadata?.fundamental_checks && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Fundamental Checks</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(selectedStrategy.metadata.fundamental_checks).map(([check, passed]) => (
                        <Badge 
                          key={check}
                          variant={passed ? "success" : "destructive"}
                          className="font-mono text-xs"
                        >
                          {check.replace(/_/g, ' ')}: {passed ? '✓' : '✗'}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Description */}
                <div>
                  <div className="text-xs text-gray-500 mb-2">Description</div>
                  <div className="text-sm text-gray-300 p-3 bg-dark-surface rounded-lg border border-dark-border">
                    {selectedStrategy.description}
                  </div>
                </div>

                {/* Entry/Exit Rules */}
                {(selectedStrategy.entry_rules || selectedStrategy.exit_rules) && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Trading Rules (DSL)</div>
                    <div className="space-y-3 p-3 bg-dark-surface rounded-lg border border-dark-border">
                      {selectedStrategy.entry_rules && selectedStrategy.entry_rules.length > 0 && (
                        <div>
                          <div className="text-xs text-accent-green mb-2 font-mono font-semibold">Entry Rules:</div>
                          <div className="space-y-1">
                            {selectedStrategy.entry_rules.map((rule, idx) => (
                              <div key={idx} className="text-xs font-mono text-gray-300 bg-dark-bg px-3 py-2 rounded">
                                {rule}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {selectedStrategy.exit_rules && selectedStrategy.exit_rules.length > 0 && (
                        <div>
                          <div className="text-xs text-accent-red mb-2 font-mono font-semibold">Exit Rules:</div>
                          <div className="space-y-1">
                            {selectedStrategy.exit_rules.map((rule, idx) => (
                              <div key={idx} className="text-xs font-mono text-gray-300 bg-dark-bg px-3 py-2 rounded">
                                {rule}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Performance Metrics */}
                {selectedStrategy.performance_metrics && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Performance Metrics</div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Total Return</div>
                        <div className={cn(
                          'text-lg font-mono font-bold',
                          selectedStrategy.performance_metrics.total_return >= 0 ? 'text-accent-green' : 'text-accent-red'
                        )}>
                          {formatPercentage(selectedStrategy.performance_metrics.total_return * 100)}
                        </div>
                      </div>
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Sharpe Ratio</div>
                        <div className="text-lg font-mono font-bold text-gray-200">
                          {formatMetric(selectedStrategy.performance_metrics.sharpe_ratio)}
                        </div>
                      </div>
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Max Drawdown</div>
                        <div className="text-lg font-mono font-bold text-accent-red">
                          {formatPercentage(selectedStrategy.performance_metrics.max_drawdown * 100)}
                        </div>
                      </div>
                      <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                        <div className="text-xs text-gray-500 mb-1">Win Rate</div>
                        <div className="text-lg font-mono font-bold text-gray-200">
                          {formatPercentage(selectedStrategy.performance_metrics.win_rate * 100)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Walk-Forward Results */}
                {selectedStrategy.walk_forward_results && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">Walk-Forward Validation</div>
                    <div className="p-3 bg-dark-surface rounded-lg border border-dark-border">
                      <div className="mb-3">
                        <span className="text-sm font-mono text-gray-300">Consistency Score: </span>
                        <span className="text-sm font-mono font-bold text-accent-green">
                          {formatPercentage(selectedStrategy.walk_forward_results.consistency_score * 100)}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-blue-400 mb-2 font-mono font-semibold">In-Sample</div>
                          <div className="space-y-1 text-xs">
                            <div>
                              <span className="text-gray-500">Sharpe: </span>
                              <span className="text-gray-300 font-mono">
                                {formatMetric(selectedStrategy.walk_forward_results.in_sample.sharpe_ratio)}
                              </span>
                            </div>
                            <div>
                              <span className="text-gray-500">Return: </span>
                              <span className="text-gray-300 font-mono">
                                {formatPercentage(selectedStrategy.walk_forward_results.in_sample.total_return * 100)}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-amber-400 mb-2 font-mono font-semibold">Out-of-Sample</div>
                          <div className="space-y-1 text-xs">
                            <div>
                              <span className="text-gray-500">Sharpe: </span>
                              <span className="text-gray-300 font-mono">
                                {formatMetric(selectedStrategy.walk_forward_results.out_of_sample.sharpe_ratio)}
                              </span>
                            </div>
                            <div>
                              <span className="text-gray-500">Return: </span>
                              <span className="text-gray-300 font-mono">
                                {formatPercentage(selectedStrategy.walk_forward_results.out_of_sample.total_return * 100)}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Strategy Comparison Dialog */}
        <Dialog open={showComparison} onOpenChange={setShowComparison}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Strategy Comparison</DialogTitle>
              <DialogDescription>Side-by-side comparison of key metrics</DialogDescription>
            </DialogHeader>
            {comparedStrategies && (
              <div className="space-y-4">
                {/* Strategy Names */}
                <div className="grid grid-cols-3 gap-4 pb-3 border-b border-dark-border">
                  <div className="text-xs text-gray-500 font-mono">Metric</div>
                  <div className="text-sm font-mono font-semibold text-gray-200 truncate" title={comparedStrategies[0].name}>
                    {comparedStrategies[0].name}
                  </div>
                  <div className="text-sm font-mono font-semibold text-gray-200 truncate" title={comparedStrategies[1].name}>
                    {comparedStrategies[1].name}
                  </div>
                </div>
                {/* Metrics rows */}
                {(() => {
                  const metrics: Array<{
                    label: string;
                    getValue: (s: Strategy) => number | undefined;
                    format: (v: number | undefined) => string;
                    higherIsBetter: boolean | null; // null = neutral
                  }> = [
                    {
                      label: 'Total Return',
                      getValue: (s) => s.performance_metrics?.total_return,
                      format: (v) => v !== undefined ? formatPercentage(v * 100) : 'N/A',
                      higherIsBetter: true,
                    },
                    {
                      label: 'Sharpe Ratio',
                      getValue: (s) => s.performance_metrics?.sharpe_ratio,
                      format: (v) => v !== undefined ? v.toFixed(2) : 'N/A',
                      higherIsBetter: true,
                    },
                    {
                      label: 'Max Drawdown',
                      getValue: (s) => s.performance_metrics?.max_drawdown,
                      format: (v) => v !== undefined ? formatPercentage(v * 100) : 'N/A',
                      higherIsBetter: false,
                    },
                    {
                      label: 'Win Rate',
                      getValue: (s) => s.performance_metrics?.win_rate,
                      format: (v) => v !== undefined ? formatPercentage(v * 100) : 'N/A',
                      higherIsBetter: true,
                    },
                    {
                      label: 'Total Trades',
                      getValue: (s) => s.performance_metrics?.total_trades,
                      format: (v) => v !== undefined ? String(v) : 'N/A',
                      higherIsBetter: null,
                    },
                    {
                      label: 'Allocation %',
                      getValue: (s) => s.allocation_percent,
                      format: (v) => v !== undefined ? formatPercentage(v) : 'N/A',
                      higherIsBetter: null,
                    },
                  ];

                  return metrics.map((metric) => {
                    const v1 = metric.getValue(comparedStrategies[0]);
                    const v2 = metric.getValue(comparedStrategies[1]);

                    let color1 = 'text-gray-300';
                    let color2 = 'text-gray-300';

                    if (metric.higherIsBetter !== null && v1 !== undefined && v2 !== undefined && v1 !== v2) {
                      if (metric.higherIsBetter) {
                        // Higher is better (but for drawdown, values are negative, so "higher" = less negative = better)
                        if (metric.label === 'Max Drawdown') {
                          // Drawdown: less negative is better (higher value)
                          color1 = v1 > v2 ? 'text-accent-green' : 'text-accent-red';
                          color2 = v2 > v1 ? 'text-accent-green' : 'text-accent-red';
                        } else {
                          color1 = v1 > v2 ? 'text-accent-green' : 'text-accent-red';
                          color2 = v2 > v1 ? 'text-accent-green' : 'text-accent-red';
                        }
                      } else {
                        // Lower is better (max drawdown - more negative = worse)
                        color1 = v1 < v2 ? 'text-accent-green' : 'text-accent-red';
                        color2 = v2 < v1 ? 'text-accent-green' : 'text-accent-red';
                      }
                    }

                    return (
                      <div key={metric.label} className="grid grid-cols-3 gap-4 py-2 border-b border-dark-border/50">
                        <div className="text-xs text-gray-500 font-mono">{metric.label}</div>
                        <div className={cn('text-sm font-mono font-semibold', color1)}>
                          {metric.format(v1)}
                        </div>
                        <div className={cn('text-sm font-mono font-semibold', color2)}>
                          {metric.format(v2)}
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
            )}
          </DialogContent>
        </Dialog>
    </DashboardLayout>
  );
};
