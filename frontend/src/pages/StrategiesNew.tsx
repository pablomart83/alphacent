import { type FC, useEffect, useState, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, Target, Activity, BarChart3, Search,
  MoreVertical, Eye, Pause, Trash2, PlayCircle, RefreshCw,
  Layers,
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { TemplateManager } from '../components/trading/TemplateManager';
import { SymbolManager } from '../components/trading/SymbolManager';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
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
        return (
          <div>
            <RadixTooltipProvider delayDuration={300}>
              <RadixTooltip>
                <RadixTooltipTrigger asChild>
                  <div className="font-mono text-xs text-gray-200 truncate max-w-[200px] cursor-default">{row.original.name}</div>
                </RadixTooltipTrigger>
                <RadixTooltipContent className="bg-gray-900 text-gray-100 border-gray-700 text-xs font-mono">
                  {row.original.name}
                </RadixTooltipContent>
              </RadixTooltip>
            </RadixTooltipProvider>
            <div className="text-xs text-gray-500 font-mono">
              <span className="font-semibold text-gray-400">{primarySymbol}</span>
              {extraCount > 0 && (
                <span className="ml-1 text-blue-400">(+{extraCount})</span>
              )}
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: 'description',
      header: 'Description',
      cell: ({ row }) => (
        <div>
          <div className="text-xs text-gray-400">{row.original.description || 'No description available'}</div>
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
      accessorKey: 'description',
      header: 'Strategy',
      cell: ({ row }) => (
        <div>
          <div className="text-xs text-gray-400">{row.original.description || 'No description available'}</div>
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
      accessorKey: 'description',
      header: 'Strategy',
      cell: ({ row }) => (
        <div>
          <div className="text-xs text-gray-400">{row.original.description || 'No description available'}</div>
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

  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto relative">
        <RefreshIndicator visible={pollingRefreshing && !loading} />
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-2 flex items-center gap-3">
                <Target className="h-8 w-8 text-accent-green" />
                Strategies
              </h1>
              <div className="flex items-center gap-3">
                <p className="text-gray-400 text-sm">
                  Manage and monitor your trading strategies
                </p>
                <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
              </div>
            </div>
            <Button
              onClick={fetchStrategies}
              disabled={refreshing}
              variant="outline"
              size="sm"
              title="Reload strategies from database"
            >
              <RefreshCw className={cn('h-4 w-4 mr-2', refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>
        </motion.div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="bg-dark-surface border border-dark-border">
            <TabsTrigger value="overview" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <BarChart3 className="h-4 w-4 mr-2" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="active" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <TrendingUp className="h-4 w-4 mr-2" />
              Active ({filteredActiveStrategies.length})
            </TabsTrigger>
            <TabsTrigger value="backtested" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <Activity className="h-4 w-4 mr-2" />
              Backtested ({filteredBacktestedStrategies.length})
            </TabsTrigger>
            <TabsTrigger value="retired" onClick={fetchRetiredStrategies} className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <Trash2 className="h-4 w-4 mr-2" />
              Retired ({filteredRetiredStrategies.length})
            </TabsTrigger>
            <TabsTrigger value="templates" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <Layers className="h-4 w-4 mr-2" />
              DSL Templates
            </TabsTrigger>
            <TabsTrigger value="ae-templates" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <Layers className="h-4 w-4 mr-2" />
              AE Templates
            </TabsTrigger>
            <TabsTrigger value="symbols" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
              <Target className="h-4 w-4 mr-2" />
              Symbols
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            {/* Summary Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                label="Total Active"
                value={summaryMetrics.active.toString()}
                icon={TrendingUp}
                trend="neutral"
              />
              <MetricCard
                label="Total Backtested"
                value={summaryMetrics.backtested.toString()}
                icon={Activity}
                trend="neutral"
              />
              <MetricCard
                label="Avg Performance"
                value={formatPercentage(summaryMetrics.avgPerformance * 100)}
                icon={BarChart3}
                trend={summaryMetrics.avgPerformance >= 0 ? 'up' : 'down'}
              />
              <MetricCard
                label="Success Rate"
                value={formatPercentage(summaryMetrics.successRate)}
                icon={Target}
                trend={summaryMetrics.successRate >= 50 ? 'up' : 'down'}
              />
            </div>

            {/* Template Distribution */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Template Distribution
                </CardTitle>
                <CardDescription>Active strategies by template</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {templateDistribution.map(({ name, count }) => (
                    <div key={name} className="flex items-center justify-between">
                      <span className="text-sm font-mono text-gray-300">{name}</span>
                      <div className="flex items-center gap-3">
                        <div className="w-32 h-2 bg-dark-surface rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-accent-green"
                            style={{ width: `${(count / activeStrategies.length) * 100}%` }}
                          />
                        </div>
                        <span className="text-sm font-mono text-gray-400 w-12 text-right">{count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Strategy Distribution Charts */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Category Distribution */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Target className="h-5 w-5" />
                    Category Distribution
                  </CardTitle>
                  <CardDescription>Active strategies by category</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {categoryDistribution.map(({ name, count }) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="text-sm font-mono text-gray-300">{name}</span>
                        <div className="flex items-center gap-3">
                          <div className="w-32 h-2 bg-dark-surface rounded-full overflow-hidden">
                            <div 
                              className={cn(
                                "h-full",
                                name === 'Alpha Edge' && "bg-purple-500",
                                name === 'Template-Based' && "bg-blue-500",
                                name === 'Manual' && "bg-gray-500"
                              )}
                              style={{ width: `${(count / activeStrategies.length) * 100}%` }}
                            />
                          </div>
                          <span className="text-sm font-mono text-gray-400 w-12 text-right">{count}</span>
                        </div>
                      </div>
                    ))}
                    {categoryDistribution.length === 0 && (
                      <div className="text-center text-gray-500 text-sm py-4">
                        No active strategies
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Type Distribution */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Type Distribution
                  </CardTitle>
                  <CardDescription>Active strategies by type</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {typeDistribution.map(({ name, count }) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="text-sm font-mono text-gray-300">{name}</span>
                        <div className="flex items-center gap-3">
                          <div className="w-32 h-2 bg-dark-surface rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-accent-green"
                              style={{ width: `${(count / activeStrategies.length) * 100}%` }}
                            />
                          </div>
                          <span className="text-sm font-mono text-gray-400 w-12 text-right">{count}</span>
                        </div>
                      </div>
                    ))}
                    {typeDistribution.length === 0 && (
                      <div className="text-center text-gray-500 text-sm py-4">
                        No template-based strategies
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Top Performing Strategies */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Top Performing Strategies
                </CardTitle>
                <CardDescription>Top 5 strategies by return</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {topPerformingStrategies.map((strategy, index) => (
                    <div key={strategy.id} className="flex items-center justify-between p-3 bg-dark-surface rounded-lg border border-dark-border">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-accent-green/20 text-accent-green font-mono font-bold text-sm">
                          {index + 1}
                        </div>
                        <div>
                          <div className="font-mono font-semibold text-sm text-gray-200">{strategy.name}</div>
                          <div className="text-xs text-gray-500 font-mono">{strategy.symbols.join(', ')}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={cn(
                          'font-mono font-bold text-sm',
                          (strategy.performance_metrics?.total_return || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'
                        )}>
                          {formatPercentage((strategy.performance_metrics?.total_return || 0) * 100)}
                        </div>
                        <div className="text-xs text-gray-500 font-mono">
                          Sharpe: {formatMetric(strategy.performance_metrics?.sharpe_ratio)}
                        </div>
                      </div>
                    </div>
                  ))}
                  {topPerformingStrategies.length === 0 && (
                    <div className="text-center text-gray-500 text-sm py-8">
                      No active strategies with performance data
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Active Strategies Tab */}
          <TabsContent value="active" className="space-y-6">
            {/* Filters */}
            <Card>
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  <div className="relative xl:col-span-2">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <Input
                      placeholder="Search by name or symbol..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                  
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Statuses</SelectItem>
                      <SelectItem value="BACKTESTED">Backtested</SelectItem>
                      <SelectItem value="DEMO">Demo</SelectItem>
                      <SelectItem value="LIVE">Live</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                      <SelectItem value="template_based">Template-Based</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      {availableTypes.map(type => (
                        <SelectItem key={type} value={type}>
                          {type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={templateFilter} onValueChange={setTemplateFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Template" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Templates</SelectItem>
                      {availableTemplates.map(template => (
                        <SelectItem key={template} value={template}>{template}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Regime" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Regimes</SelectItem>
                      {availableRegimes.map(regime => (
                        <SelectItem key={regime} value={regime}>{regime}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={sourceFilter} onValueChange={setSourceFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Sources</SelectItem>
                      <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                      <SelectItem value="USER">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Bulk Actions */}
                {selectedStrategies.size > 0 && (
                  <div className="flex items-center gap-3 pt-4 border-t border-dark-border">
                    <span className="text-xs text-gray-500 font-mono">
                      {selectedStrategies.size} selected
                    </span>
                    <Button
                      onClick={handleBulkBacktest}
                      variant="outline"
                      size="sm"
                    >
                      <Activity className="h-4 w-4 mr-2" />
                      Backtest Selected
                    </Button>
                    {selectedStrategiesInfo.hasBacktested && (
                      <Button
                        onClick={handleBulkActivate}
                        variant="outline"
                        size="sm"
                        className="text-accent-green border-accent-green/30 hover:bg-accent-green/10"
                      >
                        <PlayCircle className="h-4 w-4 mr-2" />
                        Activate Selected
                      </Button>
                    )}
                    {selectedStrategiesInfo.hasActive && (
                      <Button
                        onClick={handleBulkDeactivate}
                        variant="outline"
                        size="sm"
                        className="text-yellow-500 border-yellow-500/30 hover:bg-yellow-500/10"
                      >
                        <Pause className="h-4 w-4 mr-2" />
                        Deactivate Selected
                      </Button>
                    )}
                    <Button
                      onClick={handleBulkRetire}
                      variant="destructive"
                      size="sm"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Retire Selected
                    </Button>
                    {selectedStrategies.size === 2 && (
                      <Button
                        onClick={() => {
                          const selected = Array.from(selectedStrategies)
                            .map(id => strategies.find(s => s.id === id))
                            .filter(Boolean) as Strategy[];
                          if (selected.length === 2) {
                            setComparedStrategies([selected[0], selected[1]]);
                            setShowComparison(true);
                          }
                        }}
                        variant="outline"
                        size="sm"
                        className="text-blue-400 border-blue-400/30 hover:bg-blue-400/10"
                      >
                        <BarChart3 className="h-4 w-4 mr-2" />
                        Compare Selected
                      </Button>
                    )}
                    <Button
                      onClick={() => setSelectedStrategies(new Set())}
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                    >
                      Clear Selection
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Strategies Table */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    Active Strategies
                  </span>
                  <span className="text-sm font-mono text-gray-400">
                    {selectedStrategies.size > 0 
                      ? `${selectedStrategies.size} selected of ${filteredActiveStrategies.length} (${activeStrategies.length} total)`
                      : `${filteredActiveStrategies.length} of ${activeStrategies.length} strategies`
                    }
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                <DataTable
                  columns={activeStrategyColumns}
                  data={filteredActiveStrategies}
                  pageSize={20}
                  getRowId={(row) => row.id}
                  rowSelection={Object.fromEntries(
                    Array.from(selectedStrategies).map(id => [id, true])
                  )}
                  onRowSelectionChange={(updaterOrValue) => {
                    const currentSelection = Object.fromEntries(
                      Array.from(selectedStrategies).map(id => [id, true])
                    );
                    const newSelection = typeof updaterOrValue === 'function' 
                      ? updaterOrValue(currentSelection)
                      : updaterOrValue;
                    setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
                  }}
                />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Backtested Strategies Tab */}
          <TabsContent value="backtested" className="space-y-6">
            {/* Filters */}
            <Card>
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  <div className="relative xl:col-span-2">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <Input
                      placeholder="Search by name or symbol..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>

                  <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                      <SelectItem value="template_based">Template-Based</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      {availableTypes.map(type => (
                        <SelectItem key={type} value={type}>
                          {type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  
                  <Select value={templateFilter} onValueChange={setTemplateFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Template" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Templates</SelectItem>
                      {availableTemplates.map(template => (
                        <SelectItem key={template} value={template}>{template}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Regime" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Regimes</SelectItem>
                      {availableRegimes.map(regime => (
                        <SelectItem key={regime} value={regime}>{regime}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={sourceFilter} onValueChange={setSourceFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Sources</SelectItem>
                      <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                      <SelectItem value="USER">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Bulk Actions for Backtested */}
                {selectedStrategies.size > 0 && (
                  <div className="flex items-center gap-3 pt-4 border-t border-dark-border">
                    <span className="text-xs text-gray-500 font-mono">
                      {selectedStrategies.size} selected
                    </span>
                    <Button
                      onClick={handleBulkBacktest}
                      variant="outline"
                      size="sm"
                    >
                      <Activity className="h-4 w-4 mr-2" />
                      Re-Backtest Selected
                    </Button>
                    <Button
                      onClick={handleBulkActivate}
                      variant="outline"
                      size="sm"
                      className="text-accent-green border-accent-green/30 hover:bg-accent-green/10"
                    >
                      <PlayCircle className="h-4 w-4 mr-2" />
                      Activate Selected
                    </Button>
                    <Button
                      onClick={handleBulkRetire}
                      variant="destructive"
                      size="sm"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Retire Selected
                    </Button>
                    <Button
                      onClick={() => setSelectedStrategies(new Set())}
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                    >
                      Clear Selection
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Backtested Strategies Table */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Backtested Strategies
                  </span>
                  <span className="text-sm font-mono text-gray-400">
                    {selectedStrategies.size > 0 
                      ? `${selectedStrategies.size} selected of ${filteredBacktestedStrategies.length} (${backtestedStrategies.length} total)`
                      : `${filteredBacktestedStrategies.length} of ${backtestedStrategies.length} strategies`
                    }
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DataTable
                  columns={backtestedStrategyColumns}
                  data={filteredBacktestedStrategies}
                  pageSize={20}
                  getRowId={(row) => row.id}
                  rowSelection={Object.fromEntries(
                    Array.from(selectedStrategies).map(id => [id, true])
                  )}
                  onRowSelectionChange={(updaterOrValue) => {
                    const currentSelection = Object.fromEntries(
                      Array.from(selectedStrategies).map(id => [id, true])
                    );
                    const newSelection = typeof updaterOrValue === 'function' 
                      ? updaterOrValue(currentSelection)
                      : updaterOrValue;
                    setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
                  }}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Retired Strategies Tab */}
          <TabsContent value="retired" className="space-y-6">
            {/* Filters */}
            <Card>
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  <div className="relative xl:col-span-2">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <Input
                      placeholder="Search by name or symbol..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>

                  <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
                      <SelectItem value="template_based">Template-Based</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      {availableTypes.map(type => (
                        <SelectItem key={type} value={type}>
                          {type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  
                  <Select value={templateFilter} onValueChange={setTemplateFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Template" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Templates</SelectItem>
                      {availableTemplates.map(template => (
                        <SelectItem key={template} value={template}>{template}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={regimeFilter} onValueChange={setRegimeFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Regime" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Regimes</SelectItem>
                      {availableRegimes.map(regime => (
                        <SelectItem key={regime} value={regime}>{regime}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={sourceFilter} onValueChange={setSourceFilter}>
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Sources</SelectItem>
                      <SelectItem value="TEMPLATE">Autonomous</SelectItem>
                      <SelectItem value="USER">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Bulk Actions for Retired */}
                {selectedStrategies.size > 0 && (
                  <div className="flex items-center gap-3 pt-4 border-t border-dark-border">
                    <span className="text-xs text-gray-500 font-mono">
                      {selectedStrategies.size} selected
                    </span>
                    <Button
                      onClick={handleBulkPermanentDelete}
                      variant="destructive"
                      size="sm"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Permanently Delete Selected
                    </Button>
                    <Button
                      onClick={() => setSelectedStrategies(new Set())}
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                    >
                      Clear Selection
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Retired Strategies Table */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Trash2 className="h-5 w-5" />
                    Retired Strategies
                  </span>
                  <span className="text-sm font-mono text-gray-400">
                    {selectedStrategies.size > 0 
                      ? `${selectedStrategies.size} selected of ${filteredRetiredStrategies.length} (${retiredStrategies.length} total)`
                      : `${filteredRetiredStrategies.length} of ${retiredStrategies.length} strategies`
                    }
                  </span>
                </CardTitle>
                <CardDescription>
                  These strategies have been retired. You can permanently delete them from the database.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DataTable
                  columns={retiredStrategyColumns}
                  data={filteredRetiredStrategies}
                  pageSize={20}
                  getRowId={(row) => row.id}
                  rowSelection={Object.fromEntries(
                    Array.from(selectedStrategies).map(id => [id, true])
                  )}
                  onRowSelectionChange={(updaterOrValue) => {
                    const currentSelection = Object.fromEntries(
                      Array.from(selectedStrategies).map(id => [id, true])
                    );
                    const newSelection = typeof updaterOrValue === 'function' 
                      ? updaterOrValue(currentSelection)
                      : updaterOrValue;
                    setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
                  }}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* DSL Templates Tab */}
          <TabsContent value="templates" className="space-y-6">
            <TemplateManager category="dsl" />
          </TabsContent>

          {/* AE Templates Tab */}
          <TabsContent value="ae-templates" className="space-y-6">
            <TemplateManager category="alpha_edge" />
          </TabsContent>

          {/* Symbols Tab */}
          <TabsContent value="symbols" className="space-y-6">
            <SymbolManager />
          </TabsContent>
        </Tabs>

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
      </div>
    </DashboardLayout>
  );
};
