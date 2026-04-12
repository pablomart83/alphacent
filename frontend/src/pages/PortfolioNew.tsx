import { type FC, useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Activity, Search,
  RefreshCw, Download, MoreVertical, X, AlertTriangle, Check, XCircle, Clock, Trash2
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { DataTable } from '../components/trading/DataTable';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../components/ui/dropdown-menu';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '../lib/utils';
import { classifyError, type ClassifiedError } from '../lib/errors';
import type { AccountInfo, Position, FundamentalAlert } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { Cell, PieChart, Pie, ResponsiveContainer, Tooltip } from 'recharts';

interface PortfolioNewProps {
  onLogout: () => void;
}

/** Get invested amount — prefer invested_amount field, fall back to quantity * entry_price */
function getInvested(p: any): number {
  if (p.invested_amount != null && p.invested_amount > 0) return p.invested_amount;
  return (p.quantity || 0) * (p.entry_price || 0);
}

// Closed position type (for Tab 3)
interface ClosedPosition {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  realized_pnl_percent: number;
  strategy_id?: string;
  strategy_name?: string;
  opened_at: string;
  closed_at: string;
  holding_time_hours: number;
  exit_reason?: string;
}

export const PortfolioNew: FC<PortfolioNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const navigate = useNavigate();
  
  // State
  const [accountInfo, setAccountInfo] = useState<AccountInfo | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [closedPositions, setClosedPositions] = useState<ClosedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [closingPositionId, setClosingPositionId] = useState<string | null>(null);
  const [modifyingPosition, setModifyingPosition] = useState<{ id: string; type: 'sl' | 'tp' } | null>(null);
  const [modifyPrice, setModifyPrice] = useState('');
  
  // Selection state for Open Positions
  const [selectedPositions, setSelectedPositions] = useState<Set<string>>(new Set());
  const [closingSelected, setClosingSelected] = useState(false);
  const [closingAll, setClosingAll] = useState(false);
  const [showCloseAllConfirm, setShowCloseAllConfirm] = useState(false);
  const [syncing, setSyncing] = useState(false);
  
  // Filter states for Open Positions
  const [positionSearch, setPositionSearch] = useState('');
  const [positionStrategyFilter, setPositionStrategyFilter] = useState<string>('all');
  const [positionSideFilter, setPositionSideFilter] = useState<string>('all');
  
  // Filter states for Closed Positions
  const [closedSearch, setClosedSearch] = useState('');
  const [closedStrategyFilter, setClosedStrategyFilter] = useState<string>('all');
  const [closedDateFilter, setClosedDateFilter] = useState<string>('all');
  const [selectedClosedPositions, setSelectedClosedPositions] = useState<Set<string>>(new Set());
  const [deletingClosedPositions, setDeletingClosedPositions] = useState(false);

  // Pending closures state
  const [pendingClosures, setPendingClosures] = useState<Position[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [dismissingId, setDismissingId] = useState<string | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);

  // Fundamental alerts state
  const [fundamentalAlerts, setFundamentalAlerts] = useState<FundamentalAlert[]>([]);
  const [dismissingAlertId, setDismissingAlertId] = useState<string | null>(null);
  const [closingAlertId, setClosingAlertId] = useState<string | null>(null);
  const [closingAllAlerts, setClosingAllAlerts] = useState(false);
  const [triggeringCheck, setTriggeringCheck] = useState(false);

  // Confirmation dialog state
  const [confirmClosePosition, setConfirmClosePosition] = useState<Position | null>(null);
  const [showBulkCloseConfirm, setShowBulkCloseConfirm] = useState(false);

  // Data freshness and error state
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<ClassifiedError | null>(null);
  const [pendingClosuresLoading, setPendingClosuresLoading] = useState(false);
  const [fundamentalAlertsLoading, setFundamentalAlertsLoading] = useState(false);

  // Active tab state — controlled so we can render tabs in PanelHeader
  const [activeTab, setActiveTab] = useState<string>('open');

  // Fetch pending closures
  const fetchPendingClosures = useCallback(async () => {
    if (!tradingMode) return;
    try {
      setPendingClosuresLoading(true);
      const data = await apiClient.getPendingClosures(tradingMode);
      setPendingClosures(data);
    } catch (err) {
      console.warn('Failed to fetch pending closures:', err);
    } finally {
      setPendingClosuresLoading(false);
    }
  }, [tradingMode]);

  // Fetch fundamental alerts
  const fetchFundamentalAlerts = useCallback(async () => {
    if (!tradingMode) return;
    try {
      setFundamentalAlertsLoading(true);
      const data = await apiClient.getFundamentalAlerts(tradingMode);
      setFundamentalAlerts(data.alerts || []);
    } catch (err) {
      console.warn('Failed to fetch fundamental alerts:', err);
    } finally {
      setFundamentalAlertsLoading(false);
    }
  }, [tradingMode]);

  // Fetch all data
  const fetchData = useCallback(async () => {
    if (!tradingMode) return;
    
    try {
      setRefreshing(true);
      setFetchError(null);
      const [account, positionsData, closedPositionsData] = await Promise.all([
        apiClient.getAccountInfo(tradingMode),
        apiClient.getPositions(tradingMode),
        apiClient.getClosedPositions(tradingMode, 100).catch(err => {
          console.warn('Failed to fetch closed positions:', err);
          return [];
        }),
      ]);

      setAccountInfo(account);
      setPositions(positionsData);

      // Secondary data — load in background
      setPendingClosuresLoading(true);
      apiClient.getPendingClosures(tradingMode).then(data => {
        setPendingClosures(data);
      }).catch(err => {
        console.warn('Failed to fetch pending closures:', err);
      }).finally(() => {
        setPendingClosuresLoading(false);
      });

      setFundamentalAlertsLoading(true);
      apiClient.getFundamentalAlerts(tradingMode).then(data => {
        setFundamentalAlerts(data.alerts || []);
      }).catch(err => {
        console.warn('Failed to fetch fundamental alerts:', err);
      }).finally(() => {
        setFundamentalAlertsLoading(false);
      });
      
      const closed: ClosedPosition[] = closedPositionsData
        .filter(p => p.closed_at)
        .map(p => {
          const openedAt = new Date(p.opened_at);
          const closedAt = new Date(p.closed_at!);
          const holdingTimeHours = (closedAt.getTime() - openedAt.getTime()) / (1000 * 60 * 60);
          const realizedPnl = p.realized_pnl ?? 0;
          const invested = getInvested(p);
          const pnlPercent = invested > 0 && realizedPnl !== 0
            ? (realizedPnl / invested) * 100 
            : 0;
          
          return {
            id: p.id,
            symbol: p.symbol,
            side: p.side,
            quantity: p.quantity,
            entry_price: p.entry_price,
            exit_price: p.current_price,
            realized_pnl: realizedPnl,
            realized_pnl_percent: pnlPercent,
            strategy_id: p.strategy_id,
            strategy_name: (p as any).strategy_name || undefined,
            opened_at: p.opened_at,
            closed_at: p.closed_at!,
            holding_time_hours: holdingTimeHours,
            exit_reason: (p as any).closure_reason || 'Closed',
          };
        });
      
      setClosedPositions(closed);
      setLoading(false);
      setLastFetchedAt(new Date());
    } catch (error) {
      console.error('Failed to fetch portfolio data:', error);
      const classified = classifyError(error, 'portfolio data');
      setFetchError(classified);
      if (classified.isNetwork) {
        toast.error(classified.message);
      } else {
        toast.error(classified.title);
      }
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  }, [tradingMode]);

  // Polling
  const { refresh, isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchData,
    intervalMs: 15000,
    enabled: !!tradingMode && !tradingModeLoading,
    skipWhenWsConnected: true,
  });

  // WebSocket subscriptions
  useEffect(() => {
    const unsubscribeAccount = wsManager.onPositionUpdate(() => {
      if (tradingMode) {
        apiClient.getAccountInfo(tradingMode).then(setAccountInfo).catch(console.error);
      }
    });

    const unsubscribePosition = wsManager.onPositionUpdate((position: Position) => {
      setPositions((prev) => {
        const index = prev.findIndex(p => p.id === position.id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = position;
          return updated;
        }
        return [...prev, position];
      });
    });

    const unsubscribePendingClosure = wsManager.on('pending_closure', () => {
      fetchPendingClosures();
    });

    return () => {
      unsubscribeAccount();
      unsubscribePosition();
      unsubscribePendingClosure();
    };
  }, [tradingMode, fetchPendingClosures]);

  // Calculate metrics
  const totalPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
  const totalPnLPercent = accountInfo ? (totalPnL / accountInfo.balance) * 100 : 0;
  const totalPositionValue = accountInfo?.margin_used || 0;
  const totalPortfolioValue = accountInfo?.equity || (accountInfo?.balance || 0);
  
  const winningPositions = positions.filter(p => p.unrealized_pnl > 0).length;
  const winRate = positions.length > 0 ? (winningPositions / positions.length) * 100 : 0;
  const closedWins = closedPositions.filter(p => p.realized_pnl > 0).length;
  const closedWinRate = closedPositions.length > 0 ? (closedWins / closedPositions.length) * 100 : 0;

  // Get unique strategies for filters
  const uniqueStrategies = Array.from(new Set(
    [...positions, ...closedPositions]
      .map(p => p.strategy_id)
      .filter(Boolean)
  ));

  // Filter positions
  const filteredPositions = positions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
    const matchesStrategy = positionStrategyFilter === 'all' || position.strategy_id === positionStrategyFilter;
    const matchesSide = positionSideFilter === 'all' || position.side === positionSideFilter;
    return matchesSearch && matchesStrategy && matchesSide;
  });

  // Filter closed positions
  const filteredClosedPositions = closedPositions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(closedSearch.toLowerCase());
    const matchesStrategy = closedStrategyFilter === 'all' || position.strategy_id === closedStrategyFilter;
    
    let matchesDate = true;
    if (closedDateFilter !== 'all') {
      const closedDate = new Date(position.closed_at);
      const now = new Date();
      const daysDiff = (now.getTime() - closedDate.getTime()) / (1000 * 60 * 60 * 24);
      
      switch (closedDateFilter) {
        case '1d': matchesDate = daysDiff <= 1; break;
        case '7d': matchesDate = daysDiff <= 7; break;
        case '30d': matchesDate = daysDiff <= 30; break;
      }
    }
    
    return matchesSearch && matchesStrategy && matchesDate;
  });

  // Prepare allocation chart data
  const pieChartData = positions.reduce((acc, position) => {
    const value = Math.abs(getInvested(position));
    if (value === 0) return acc;
    const symbolName = position.symbol || 'Unknown';
    const existing = acc.find(item => item.name === symbolName);
    if (existing) {
      existing.value += value;
    } else {
      acc.push({ name: symbolName, value });
    }
    return acc;
  }, [] as Array<{ name: string; value: number }>);

  const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

  // Asset class summary
  const assetClassSummary = useMemo(() => {
    const map = new Map<string, { count: number; totalPnl: number }>();
    positions.forEach(p => {
      const ac = (p as any).asset_class || 'Unknown';
      const existing = map.get(ac) || { count: 0, totalPnl: 0 };
      existing.count += 1;
      existing.totalPnl += p.unrealized_pnl;
      map.set(ac, existing);
    });
    return Array.from(map.entries())
      .map(([assetClass, data]) => ({ assetClass, ...data }))
      .sort((a, b) => b.count - a.count);
  }, [positions]);

  // Sector exposure
  const sectorExposure = useMemo(() => {
    const map = new Map<string, number>();
    positions.forEach(p => {
      const sector = (p as any).sector || (p as any).asset_class || 'Other';
      const value = Math.abs(getInvested(p));
      map.set(sector, (map.get(sector) || 0) + value);
    });
    return Array.from(map.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  // Allocation breakdown
  const allocationData = useMemo(() => {
    const totalValue = pieChartData.reduce((sum, d) => sum + d.value, 0);
    return pieChartData
      .sort((a, b) => b.value - a.value)
      .slice(0, 10)
      .map(d => ({
        name: d.name,
        value: d.value,
        pct: totalValue > 0 ? (d.value / totalValue) * 100 : 0,
      }));
  }, [pieChartData]);

  // ── Action handlers (all preserved from original) ──────────────────

  const handleClosePosition = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setClosingPositionId(positionId);
      await apiClient.closePosition(positionId, tradingMode);
      toast.success('Position closed successfully');
      setPositions(prev => prev.filter(p => p.id !== positionId));
      fetchData();
    } catch (error) {
      console.error('Failed to close position:', error);
      toast.error('Failed to close position');
    } finally {
      setClosingPositionId(null);
    }
  };

  const handleModifyStopLoss = async () => {
    if (!modifyingPosition || !modifyPrice || !tradingMode) return;
    const price = parseFloat(modifyPrice);
    if (isNaN(price) || price <= 0) { toast.error('Please enter a valid price'); return; }
    try {
      await apiClient.modifyStopLoss(modifyingPosition.id, price, tradingMode);
      toast.success('Stop loss updated successfully');
      setModifyingPosition(null);
      setModifyPrice('');
      fetchData();
    } catch (error) {
      console.error('Failed to modify stop loss:', error);
      toast.error('Failed to modify stop loss');
    }
  };

  const handleModifyTakeProfit = async () => {
    if (!modifyingPosition || !modifyPrice || !tradingMode) return;
    const price = parseFloat(modifyPrice);
    if (isNaN(price) || price <= 0) { toast.error('Please enter a valid price'); return; }
    try {
      await apiClient.modifyTakeProfit(modifyingPosition.id, price, tradingMode);
      toast.success('Take profit updated successfully');
      setModifyingPosition(null);
      setModifyPrice('');
      fetchData();
    } catch (error) {
      console.error('Failed to modify take profit:', error);
      toast.error('Failed to modify take profit');
    }
  };

  const handleModifySubmit = () => {
    if (modifyingPosition?.type === 'sl') handleModifyStopLoss();
    else handleModifyTakeProfit();
  };

  const handleApproveClosure = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setApprovingId(positionId);
      await apiClient.approvePositionClosure(positionId, tradingMode);
      toast.success('Position closure approved');
      setPendingClosures(prev => prev.filter(p => p.id !== positionId));
      fetchData();
    } catch (error) {
      console.error('Failed to approve closure:', error);
      toast.error('Failed to approve closure');
    } finally {
      setApprovingId(null);
    }
  };

  const handleApproveAll = async () => {
    if (!tradingMode || pendingClosures.length === 0) return;
    try {
      setApprovingAll(true);
      const ids = pendingClosures.map(p => p.id);
      const result = await apiClient.approveBulkClosures(ids, tradingMode);
      toast.success(`Closed ${result.success_count} positions${result.fail_count > 0 ? `, ${result.fail_count} failed` : ''}`);
      fetchPendingClosures();
      fetchData();
    } catch (error) {
      console.error('Failed to approve all closures:', error);
      toast.error('Failed to approve all closures');
    } finally {
      setApprovingAll(false);
    }
  };

  const handleDismissClosure = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setDismissingId(positionId);
      await apiClient.dismissPositionClosure(positionId, tradingMode);
      toast.success('Closure dismissed — position will remain open');
      setPendingClosures(prev => prev.filter(p => p.id !== positionId));
    } catch (error) {
      console.error('Failed to dismiss closure:', error);
      toast.error('Failed to dismiss closure');
    } finally {
      setDismissingId(null);
    }
  };

  const handleDismissAlert = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setDismissingAlertId(positionId);
      await apiClient.dismissFundamentalAlert(positionId, tradingMode);
      toast.success('Alert dismissed — position will remain open');
      setFundamentalAlerts(prev => prev.filter(a => a.id !== positionId));
      fetchPendingClosures();
    } catch (error) {
      console.error('Failed to dismiss alert:', error);
      toast.error('Failed to dismiss alert');
    } finally {
      setDismissingAlertId(null);
    }
  };

  const handleCloseAlertPosition = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setClosingAlertId(positionId);
      await apiClient.approvePositionClosure(positionId, tradingMode);
      toast.success('Position closure approved');
      setFundamentalAlerts(prev => prev.filter(a => a.id !== positionId));
      fetchData();
    } catch (error) {
      console.error('Failed to close position:', error);
      toast.error('Failed to close position');
    } finally {
      setClosingAlertId(null);
    }
  };

  const handleCloseAllAlerts = async () => {
    if (!tradingMode || fundamentalAlerts.length === 0) return;
    try {
      setClosingAllAlerts(true);
      const ids = fundamentalAlerts.map(a => a.id);
      const result = await apiClient.approveBulkClosures(ids, tradingMode);
      toast.success(`Closed ${result.success_count} flagged positions${result.fail_count > 0 ? `, ${result.fail_count} failed` : ''}`);
      fetchFundamentalAlerts();
      fetchData();
    } catch (error) {
      console.error('Failed to close all flagged positions:', error);
      toast.error('Failed to close all flagged positions');
    } finally {
      setClosingAllAlerts(false);
    }
  };

  const handleTriggerFundamentalCheck = async () => {
    if (!tradingMode) return;
    try {
      setTriggeringCheck(true);
      const result = await apiClient.triggerFundamentalCheck(tradingMode);
      toast.success(result.message);
      fetchFundamentalAlerts();
      fetchPendingClosures();
    } catch (error) {
      console.error('Failed to trigger fundamental check:', error);
      toast.error('Failed to trigger fundamental check');
    } finally {
      setTriggeringCheck(false);
    }
  };

  const handleTogglePosition = (positionId: string) => {
    setSelectedPositions(prev => {
      const next = new Set(prev);
      if (next.has(positionId)) next.delete(positionId);
      else next.add(positionId);
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedPositions.size === filteredPositions.length) setSelectedPositions(new Set());
    else setSelectedPositions(new Set(filteredPositions.map(p => p.id)));
  };

  const handleCloseSelected = async () => {
    if (!tradingMode || selectedPositions.size === 0) return;
    try {
      setClosingSelected(true);
      const result = await apiClient.closePositions(Array.from(selectedPositions), tradingMode);
      toast.success(result.message);
      setSelectedPositions(new Set());
      fetchData();
    } catch (error) {
      console.error('Failed to close selected positions:', error);
      toast.error('Failed to close selected positions');
    } finally {
      setClosingSelected(false);
    }
  };

  const handleCloseAllPositions = async () => {
    if (!tradingMode) return;
    try {
      setClosingAll(true);
      const result = await apiClient.closeAllPositions(tradingMode);
      toast.success(result.message);
      setShowCloseAllConfirm(false);
      setSelectedPositions(new Set());
      fetchData();
    } catch (error) {
      console.error('Failed to close all positions:', error);
      toast.error('Failed to close all positions');
    } finally {
      setClosingAll(false);
    }
  };

  const handleSyncPositions = async () => {
    if (!tradingMode) return;
    try {
      setSyncing(true);
      const result = await apiClient.syncPositions(tradingMode);
      toast.success(result.message);
      fetchData();
    } catch (error) {
      console.error('Failed to sync positions:', error);
      toast.error('Failed to sync positions with eToro');
    } finally {
      setSyncing(false);
    }
  };

  const exportToCSV = (data: Position[] | ClosedPosition[], filename: string) => {
    if (data.length === 0) { toast.error('No data to export'); return; }
    const isClosedPosition = (item: any): item is ClosedPosition => 'exit_price' in item;
    let csvContent = '';
    if (isClosedPosition(data[0])) {
      csvContent = 'Symbol,Side,Quantity,Entry Price,Exit Price,Realized P&L,P&L %,Opened At,Closed At,Holding Time (hours),Exit Reason\n';
      (data as ClosedPosition[]).forEach(pos => {
        csvContent += `${pos.symbol},${pos.side},${pos.quantity},${pos.entry_price},${pos.exit_price},${pos.realized_pnl},${pos.realized_pnl_percent.toFixed(2)},${pos.opened_at},${pos.closed_at},${pos.holding_time_hours.toFixed(2)},${pos.exit_reason || 'N/A'}\n`;
      });
    } else {
      csvContent = 'Symbol,Side,Quantity,Entry Price,Current Price,Unrealized P&L,P&L %,Opened At\n';
      (data as Position[]).forEach(pos => {
        csvContent += `${pos.symbol},${pos.side},${pos.quantity},${pos.entry_price},${pos.current_price},${pos.unrealized_pnl},${pos.unrealized_pnl_percent.toFixed(2)},${pos.opened_at}\n`;
      });
    }
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('Data exported successfully');
  };

  const getPositionStatus = (position: Position): string => {
    if (position.pending_closure) return 'Pending Close';
    return 'Open';
  };

  // ── Table columns ──────────────────────────────────────────────────

  const positionColumns: ColumnDef<Position>[] = [
    {
      id: 'select',
      header: () => (
        <div className="flex items-center justify-center">
          <input type="checkbox" checked={filteredPositions.length > 0 && selectedPositions.size === filteredPositions.length}
            onChange={handleSelectAll} className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer" />
        </div>
      ),
      cell: ({ row }) => (
        <div className="flex items-center justify-center">
          <input type="checkbox" checked={selectedPositions.has(row.original.id)}
            onChange={() => handleTogglePosition(row.original.id)} className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer" />
        </div>
      ),
      size: 32,
    },
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div className="font-mono font-semibold text-[13px] text-blue-400 hover:text-blue-300 cursor-pointer"
          onClick={() => navigate(`/portfolio/${encodeURIComponent(row.original.symbol)}`)}>
          {row.original.symbol}
        </div>
      ),
    },
    {
      accessorKey: 'strategy_name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div className="font-mono text-[11px] text-muted-foreground truncate max-w-[140px]" title={row.original.strategy_name || row.original.strategy_id}>
          {row.original.strategy_name || row.original.strategy_id?.slice(0, 8) || '—'}
        </div>
      ),
    },
    {
      accessorKey: 'side',
      header: 'Side',
      cell: ({ row }) => (
        <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap',
          row.original.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red')}>
          {row.original.side}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = getPositionStatus(row.original);
        return (
          <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap',
            status === 'Open' ? 'bg-blue-500/20 text-blue-400' : 'bg-amber-500/20 text-amber-400')}>
            {status}
          </span>
        );
      },
    },
    {
      accessorKey: 'quantity',
      header: () => <div className="text-right">Invested</div>,
      cell: ({ row }) => {
        const invested = getInvested(row.original);
        return <div className="text-right font-mono text-[13px]">{formatCurrency(invested)}</div>;
      },
    },
    {
      accessorKey: 'entry_price',
      header: () => <div className="text-right">Open</div>,
      cell: ({ row }) => <div className="text-right font-mono text-[13px]">{formatCurrency(row.original.entry_price)}</div>,
    },
    {
      accessorKey: 'current_price',
      header: () => <div className="text-right">Current</div>,
      cell: ({ row }) => <div className="text-right font-mono text-[13px]">{formatCurrency(row.original.current_price)}</div>,
    },
    {
      accessorKey: 'unrealized_pnl',
      header: () => <div className="text-right">P&L</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <div className={cn('font-mono font-semibold text-[13px]', row.original.unrealized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
            {formatCurrency(row.original.unrealized_pnl)}
          </div>
          <div className={cn('text-[10px] font-mono', row.original.unrealized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
            {formatPercentage(row.original.unrealized_pnl_percent || 0)}
          </div>
        </div>
      ),
    },
    {
      id: 'holding',
      header: 'Hold',
      cell: ({ row }) => {
        const days = Math.floor((Date.now() - new Date(row.original.opened_at).getTime()) / (1000 * 60 * 60 * 24));
        const color = days < 7 ? 'text-[#22c55e]' : days <= 30 ? 'text-amber-400' : 'text-[#ef4444]';
        const bg = days < 7 ? 'bg-[#22c55e]/10' : days <= 30 ? 'bg-amber-400/10' : 'bg-[#ef4444]/10';
        return <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold', color, bg)}>{days}d</span>;
      },
      sortingFn: (rowA, rowB) => {
        return new Date(rowA.original.opened_at).getTime() - new Date(rowB.original.opened_at).getTime();
      },
    },
    {
      id: 'portfolioPct',
      header: () => <div className="text-right">%Port</div>,
      cell: ({ row }) => {
        const totalValue = positions.reduce((sum, p) => sum + Math.abs(getInvested(p)), 0);
        const posValue = Math.abs(getInvested(row.original));
        const pct = totalValue > 0 ? (posValue / totalValue) * 100 : 0;
        return <div className="text-right font-mono text-[11px] text-muted-foreground">{pct.toFixed(1)}%</div>;
      },
    },
    {
      id: 'stopTp',
      header: 'SL/TP',
      cell: ({ row }) => {
        const { entry_price, current_price, stop_loss, take_profit } = row.original;
        if (!stop_loss && !take_profit) return <span className="text-[11px] text-muted-foreground">—</span>;
        const prices = [stop_loss, entry_price, current_price, take_profit].filter((p): p is number => p != null && p > 0);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        const range = max - min || 1;
        const toPos = (v: number) => ((v - min) / range) * 100;
        return (
          <div className="w-20 h-3 relative bg-gray-800 rounded overflow-hidden" title={`SL: ${stop_loss?.toFixed(2) ?? '—'} | TP: ${take_profit?.toFixed(2) ?? '—'}`}>
            {stop_loss != null && stop_loss > 0 && <div className="absolute top-0 bottom-0 w-0.5 bg-[#ef4444]" style={{ left: `${toPos(stop_loss)}%` }} />}
            <div className="absolute top-0 bottom-0 w-0.5 bg-blue-400" style={{ left: `${toPos(entry_price)}%` }} />
            {take_profit != null && take_profit > 0 && <div className="absolute top-0 bottom-0 w-0.5 bg-[#22c55e]" style={{ left: `${toPos(take_profit)}%` }} />}
            <div className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-white border border-gray-600" style={{ left: `calc(${toPos(current_price)}% - 3px)` }} />
          </div>
        );
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                <MoreVertical className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setModifyingPosition({ id: row.original.id, type: 'sl' })}>Modify Stop Loss</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setModifyingPosition({ id: row.original.id, type: 'tp' })}>Modify Take Profit</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setConfirmClosePosition(row.original)} className="text-[#ef4444]"
                disabled={closingPositionId === row.original.id}>
                {closingPositionId === row.original.id ? 'Closing...' : 'Close Position'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  const closedPositionColumns: ColumnDef<ClosedPosition>[] = [
    {
      id: 'select',
      header: () => (
        <div className="flex items-center justify-center">
          <input type="checkbox" checked={filteredClosedPositions.length > 0 && selectedClosedPositions.size === filteredClosedPositions.length}
            onChange={() => {
              if (selectedClosedPositions.size === filteredClosedPositions.length) setSelectedClosedPositions(new Set());
              else setSelectedClosedPositions(new Set(filteredClosedPositions.map(p => p.id)));
            }} className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer" />
        </div>
      ),
      cell: ({ row }) => (
        <div className="flex items-center justify-center">
          <input type="checkbox" checked={selectedClosedPositions.has(row.original.id)}
            onChange={() => {
              setSelectedClosedPositions(prev => {
                const next = new Set(prev);
                if (next.has(row.original.id)) next.delete(row.original.id);
                else next.add(row.original.id);
                return next;
              });
            }} className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer" />
        </div>
      ),
      size: 32,
    },
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => <div className="font-mono font-semibold text-[13px]">{row.original.symbol}</div>,
    },
    {
      accessorKey: 'strategy_name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div className="font-mono text-[11px] text-muted-foreground truncate max-w-[140px]" title={row.original.strategy_name || row.original.strategy_id}>
          {row.original.strategy_name || '—'}
        </div>
      ),
    },
    {
      accessorKey: 'realized_pnl',
      header: () => <div className="text-right">Realized P&L</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <div className={cn('font-mono font-semibold text-[13px]', row.original.realized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
            {formatCurrency(row.original.realized_pnl)}
          </div>
          <div className={cn('text-[10px] font-mono', row.original.realized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
            {formatPercentage(row.original.realized_pnl_percent)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'holding_time_hours',
      header: () => <div className="text-right">Hold</div>,
      cell: ({ row }) => (
        <div className="text-right text-[11px] text-muted-foreground font-mono">
          {row.original.holding_time_hours < 24 
            ? `${row.original.holding_time_hours.toFixed(1)}h`
            : `${(row.original.holding_time_hours / 24).toFixed(1)}d`}
        </div>
      ),
    },
    {
      accessorKey: 'exit_reason',
      header: 'Exit',
      cell: ({ row }) => <div className="text-[11px] text-muted-foreground">{row.original.exit_reason || 'N/A'}</div>,
    },
    {
      accessorKey: 'closed_at',
      header: () => <div className="text-right">Closed</div>,
      cell: ({ row }) => <div className="text-right text-[11px] text-muted-foreground whitespace-nowrap font-mono">{formatTimestamp(row.original.closed_at)}</div>,
    },
  ];

  // ── Loading state ──────────────────────────────────────────────────

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  // ── Header actions (compact — just refresh + freshness) ────────────
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <button
        onClick={refresh}
        disabled={refreshing || pollingRefreshing}
        className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
        title="Refresh"
      >
        <RefreshCw className={cn('h-3.5 w-3.5', (refreshing || pollingRefreshing) && 'animate-spin')} />
      </button>
    </div>
  );

  // ── Tab buttons for PanelHeader ────────────────────────────────────
  const tabButtons = (
    <div className="flex items-center gap-0 border-b-0">
      {[
        { id: 'open', label: `Open (${filteredPositions.length})` },
        { id: 'closed', label: `Closed (${filteredClosedPositions.length})` },
        { id: 'pending', label: `Pending${pendingClosures.length > 0 ? ` (${pendingClosures.length})` : ''}`, highlight: pendingClosures.length > 0 ? 'text-amber-400' : '' },
        { id: 'alerts', label: `Alerts${fundamentalAlerts.length > 0 ? ` (${fundamentalAlerts.length})` : ''}`, highlight: fundamentalAlerts.length > 0 ? 'text-orange-400' : '' },
      ].map(tab => (
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={cn(
            'px-3 py-1 text-[13px] font-medium rounded whitespace-nowrap transition-colors shrink-0',
            activeTab === tab.id
              ? 'bg-gray-700/60 text-gray-100'
              : cn('text-gray-500 hover:text-gray-300 hover:bg-gray-800/40', tab.highlight)
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );

  // ── Filter controls for the active tab (rendered inline in header area) ──
  const renderFilters = () => {
    if (activeTab === 'open') {
      return (
        <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-[var(--color-dark-border)] bg-[var(--color-dark-bg)]/50">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input placeholder="Search..." value={positionSearch} onChange={(e) => setPositionSearch(e.target.value)} className="pl-7 h-7 w-[130px] text-[11px]" />
          </div>
          <Select value={positionStrategyFilter} onValueChange={setPositionStrategyFilter}>
            <SelectTrigger className="w-[110px] h-7 text-[11px]"><SelectValue placeholder="Strategy" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Strategies</SelectItem>
              {uniqueStrategies.map(s => <SelectItem key={s} value={s!}>{s?.substring(0, 8)}...</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={positionSideFilter} onValueChange={setPositionSideFilter}>
            <SelectTrigger className="w-[80px] h-7 text-[11px]"><SelectValue placeholder="Side" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="BUY">BUY</SelectItem>
              <SelectItem value="SELL">SELL</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={handleSyncPositions} disabled={syncing} className="gap-1 h-7 text-[10px] px-2" title="Sync with eToro">
            <RefreshCw className={cn('h-3 w-3', syncing && 'animate-spin')} />
            Sync
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportToCSV(filteredPositions, 'open-positions.csv')} className="gap-1 h-7 text-[10px] px-2">
            <Download className="h-3 w-3" />
          </Button>
          {selectedPositions.size > 0 && (
            <Button size="sm" variant="destructive" onClick={() => setShowBulkCloseConfirm(true)} disabled={closingSelected} className="gap-1 h-7 text-[10px] px-2 ml-auto">
              <X className="h-3 w-3" /> Close ({selectedPositions.size})
            </Button>
          )}
          {positions.length > 0 && selectedPositions.size === 0 && (
            <Button size="sm" variant="outline" onClick={() => setShowCloseAllConfirm(true)} className="gap-1 h-7 text-[10px] px-2 ml-auto border-[#ef4444]/30 text-[#ef4444] hover:bg-[#ef4444]/10">
              <XCircle className="h-3 w-3" /> Close All
            </Button>
          )}
        </div>
      );
    }
    if (activeTab === 'closed') {
      return (
        <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-[var(--color-dark-border)] bg-[var(--color-dark-bg)]/50">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input placeholder="Search..." value={closedSearch} onChange={(e) => setClosedSearch(e.target.value)} className="pl-7 h-7 w-[130px] text-[11px]" />
          </div>
          <Select value={closedStrategyFilter} onValueChange={setClosedStrategyFilter}>
            <SelectTrigger className="w-[110px] h-7 text-[11px]"><SelectValue placeholder="Strategy" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Strategies</SelectItem>
              {uniqueStrategies.map(s => <SelectItem key={s} value={s!}>{s?.substring(0, 8)}...</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={closedDateFilter} onValueChange={setClosedDateFilter}>
            <SelectTrigger className="w-[90px] h-7 text-[11px]"><SelectValue placeholder="Date" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Time</SelectItem>
              <SelectItem value="1d">Last 24h</SelectItem>
              <SelectItem value="7d">Last 7d</SelectItem>
              <SelectItem value="30d">Last 30d</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => exportToCSV(filteredClosedPositions, 'closed-positions.csv')} className="gap-1 h-7 text-[10px] px-2">
            <Download className="h-3 w-3" />
          </Button>
          {selectedClosedPositions.size > 0 && (
            <Button size="sm" variant="destructive" onClick={async () => {
              if (!tradingMode) return;
              try { setDeletingClosedPositions(true); await apiClient.deleteClosedPositions(Array.from(selectedClosedPositions), tradingMode); toast.success(`Deleted ${selectedClosedPositions.size} closed position(s)`); setSelectedClosedPositions(new Set()); fetchData(); } catch { toast.error('Failed to delete closed positions'); } finally { setDeletingClosedPositions(false); }
            }} disabled={deletingClosedPositions} className="gap-1 h-7 text-[10px] px-2 ml-auto">
              <Trash2 className="h-3 w-3" /> Delete ({selectedClosedPositions.size})
            </Button>
          )}
        </div>
      );
    }
    return null;
  };

  // ── Tab content rendering ──────────────────────────────────────────

  const renderTabContent = () => {
    if (activeTab === 'open') {
      return filteredPositions.length > 0 ? (
        <div className="flex-1 overflow-auto min-h-0">
          <DataTable columns={positionColumns} data={filteredPositions} pageSize={50} showPagination={filteredPositions.length > 50} className="[&_table]:table-dense [&_td]:py-1 [&_th]:py-1" />
        </div>
      ) : (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-[11px]">
          {positionSearch || positionStrategyFilter !== 'all' || positionSideFilter !== 'all' ? 'No positions match filters' : 'No open positions'}
        </div>
      );
    }

    if (activeTab === 'closed') {
      return filteredClosedPositions.length > 0 ? (
        <div className="flex-1 overflow-auto min-h-0">
          <DataTable columns={closedPositionColumns} data={filteredClosedPositions} pageSize={50} showPagination={filteredClosedPositions.length > 50} className="[&_table]:table-dense [&_td]:py-1 [&_th]:py-1" />
        </div>
      ) : (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-[11px]">
          {closedSearch || closedStrategyFilter !== 'all' || closedDateFilter !== 'all' ? 'No closed positions match filters' : 'No closed positions'}
        </div>
      );
    }

    if (activeTab === 'pending') {
      return (
        <div className="flex-1 overflow-auto min-h-0 p-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] text-muted-foreground">
              Positions flagged for closure.{pendingClosures.length > 0 && ' Auto-close within 60s.'}
            </p>
            {pendingClosures.length > 0 && (
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" onClick={fetchPendingClosures} className="gap-1 h-6 text-[10px] px-2">
                  <RefreshCw className="h-2.5 w-2.5" /> Refresh
                </Button>
                <Button size="sm" onClick={handleApproveAll} disabled={approvingAll} className="gap-1 h-6 text-[10px] px-2 bg-amber-600 hover:bg-amber-700 text-white">
                  <Check className="h-2.5 w-2.5" /> {approvingAll ? 'Closing...' : `Approve All (${pendingClosures.length})`}
                </Button>
              </div>
            )}
          </div>
          {pendingClosuresLoading && pendingClosures.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <RefreshCw className="h-3.5 w-3.5 animate-spin mr-2" /><span className="text-[11px]">Loading...</span>
            </div>
          ) : pendingClosures.length > 0 ? (
            <div className="space-y-1.5">
              {pendingClosures.map((position) => {
                const hoursAgo = Math.floor((Date.now() - new Date(position.opened_at).getTime()) / (1000 * 60 * 60));
                return (
                  <motion.div key={position.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                    className="flex items-center justify-between px-2 py-1.5 rounded border border-amber-500/20 bg-amber-500/5">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-semibold text-[13px]">{position.symbol}</span>
                          <span className={cn('px-1 py-0.5 rounded text-[10px] font-mono font-semibold', position.side === 'BUY' ? 'bg-[#22c55e]/20 text-[#22c55e]' : 'bg-[#ef4444]/20 text-[#ef4444]')}>{position.side}</span>
                          <span className="text-[11px] text-muted-foreground font-mono">{formatCurrency(getInvested(position))}</span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {position.closure_reason && <span className="text-[10px] text-amber-400">{position.closure_reason}</span>}
                          <span className="flex items-center gap-0.5 text-[11px] text-muted-foreground"><Clock className="h-2.5 w-2.5" />{hoursAgo < 1 ? 'Now' : hoursAgo < 24 ? `${hoursAgo}h` : `${Math.floor(hoursAgo / 24)}d`}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <div className="text-right mr-1">
                        <div className={cn('font-mono font-semibold text-[13px]', position.unrealized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatCurrency(position.unrealized_pnl)}</div>
                        <div className={cn('text-[10px] font-mono', position.unrealized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatPercentage(position.unrealized_pnl_percent || 0)}</div>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => handleDismissClosure(position.id)} disabled={dismissingId === position.id} className="h-6 text-[10px] px-2">
                        {dismissingId === position.id ? '...' : 'Dismiss'}
                      </Button>
                      <Button size="sm" onClick={() => handleApproveClosure(position.id)} disabled={approvingId === position.id} className="h-6 text-[10px] px-2 bg-amber-600 hover:bg-amber-700 text-white">
                        {approvingId === position.id ? '...' : 'Approve'}
                      </Button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <AlertTriangle className="h-5 w-5 mx-auto mb-1.5 opacity-30" />
              <p className="text-[11px]">No positions pending closure</p>
            </div>
          )}
        </div>
      );
    }

    if (activeTab === 'alerts') {
      return (
        <div className="flex-1 overflow-auto min-h-0 p-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] text-muted-foreground">Positions flagged by fundamental exit monitoring.</p>
            <div className="flex gap-1.5">
              <Button variant="outline" size="sm" onClick={handleTriggerFundamentalCheck} disabled={triggeringCheck} className="gap-1 h-6 text-[10px] px-2">
                <RefreshCw className={cn('h-2.5 w-2.5', triggeringCheck && 'animate-spin')} /> {triggeringCheck ? 'Checking...' : 'Run Check'}
              </Button>
              {fundamentalAlerts.length > 0 && (
                <Button size="sm" onClick={handleCloseAllAlerts} disabled={closingAllAlerts} className="gap-1 h-6 text-[10px] px-2 bg-orange-600 hover:bg-orange-700 text-white">
                  <XCircle className="h-2.5 w-2.5" /> {closingAllAlerts ? 'Closing...' : `Close All (${fundamentalAlerts.length})`}
                </Button>
              )}
            </div>
          </div>
          {fundamentalAlertsLoading && fundamentalAlerts.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <RefreshCw className="h-3.5 w-3.5 animate-spin mr-2" /><span className="text-[11px]">Loading...</span>
            </div>
          ) : fundamentalAlerts.length > 0 ? (
            <div className="space-y-1.5">
              {fundamentalAlerts.map((alert) => {
                const pnl = alert.unrealized_pnl || 0;
                const pnlPercent = alert.unrealized_pnl_percent || 0;
                const flagReason = alert.flag_reason || 'Fundamental Exit';
                const fundamentalDetail = alert.fundamental_detail || alert.closure_reason || '';
                const reasonColor = flagReason === 'Earnings Miss' ? 'bg-red-500/20 text-red-400' : flagReason === 'Revenue Decline' ? 'bg-amber-500/20 text-amber-400' : flagReason === 'Sector Rotation' ? 'bg-blue-500/20 text-blue-400' : 'bg-orange-500/20 text-orange-400';
                return (
                  <motion.div key={alert.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                    className="flex items-center justify-between px-2 py-1.5 rounded border border-orange-500/20 bg-orange-500/5">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-mono font-semibold text-[13px]">{alert.symbol}</span>
                          <span className={cn('px-1 py-0.5 rounded text-[10px] font-mono font-semibold', alert.side === 'BUY' ? 'bg-[#22c55e]/20 text-[#22c55e]' : 'bg-[#ef4444]/20 text-[#ef4444]')}>{alert.side}</span>
                          <span className={cn('px-1 py-0.5 rounded text-[10px] font-semibold', reasonColor)}>{flagReason}</span>
                        </div>
                        {fundamentalDetail && <div className="mt-0.5 text-[10px] text-orange-300/80 font-mono truncate max-w-xs" title={fundamentalDetail}>{fundamentalDetail}</div>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <div className="text-right mr-1">
                        <div className={cn('font-mono font-semibold text-[13px]', pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatCurrency(pnl)}</div>
                        <div className={cn('text-[10px] font-mono', pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatPercentage(pnlPercent)}</div>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => handleDismissAlert(alert.id)} disabled={dismissingAlertId === alert.id} className="h-6 text-[10px] px-2">
                        {dismissingAlertId === alert.id ? '...' : 'Dismiss'}
                      </Button>
                      <Button size="sm" onClick={() => handleCloseAlertPosition(alert.id)} disabled={closingAlertId === alert.id} className="h-6 text-[10px] px-2 bg-orange-600 hover:bg-orange-700 text-white">
                        {closingAlertId === alert.id ? '...' : 'Close'}
                      </Button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Activity className="h-5 w-5 mx-auto mb-1.5 opacity-30" />
              <p className="text-[11px]">No fundamental alerts</p>
              <Button variant="outline" size="sm" onClick={handleTriggerFundamentalCheck} disabled={triggeringCheck} className="mt-2 gap-1 h-6 text-[10px] px-2">
                <RefreshCw className={cn('h-2.5 w-2.5', triggeringCheck && 'animate-spin')} /> {triggeringCheck ? 'Running...' : 'Run Check Now'}
              </Button>
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  // ── Main Panel (70%) — Positions ───────────────────────────────────
  // PanelHeader has: title "Positions" on left, tabs inline, filter controls on right — ALL IN ONE 32px ROW
  // Below: immediately the data table, edge-to-edge, no padding, no card wrapper

  const mainPanel = (
    <div className="flex flex-col h-full">
      {/* Panel header row: title + tabs + actions — single 32px bar */}
      <div className="flex items-center justify-between px-2 min-h-[32px] shrink-0 bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]">
        <div className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide flex-1 min-w-0">
          {tabButtons}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={refresh} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Refresh">
            <RefreshCw size={11} className={cn((refreshing || pollingRefreshing) && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Alert banners — simple colored divs, no Card wrapper */}
      {pendingClosures.length > 0 && activeTab !== 'pending' && (
        <div className="flex items-center justify-between px-2 py-1 bg-amber-500/5 border-b border-amber-500/20">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
            <span className="text-[10px] font-semibold text-amber-400">{pendingClosures.length} pending closure{pendingClosures.length !== 1 ? 's' : ''}</span>
          </div>
          <button onClick={() => setActiveTab('pending')} className="text-[10px] text-amber-400 hover:text-amber-300 underline">Review</button>
        </div>
      )}
      {fundamentalAlerts.length > 0 && activeTab !== 'alerts' && (
        <div className="flex items-center justify-between px-2 py-1 bg-orange-500/5 border-b border-orange-500/20">
          <div className="flex items-center gap-1.5">
            <Activity className="h-3 w-3 text-orange-500 shrink-0" />
            <span className="text-[10px] font-semibold text-orange-400">{fundamentalAlerts.length} flagged position{fundamentalAlerts.length !== 1 ? 's' : ''}</span>
          </div>
          <button onClick={() => setActiveTab('alerts')} className="text-[10px] text-orange-400 hover:text-orange-300 underline">Review</button>
        </div>
      )}

      {/* Error state — simple div, no Card */}
      {fetchError && !loading && positions.length === 0 && (
        <div className="flex items-center justify-between px-2 py-1.5 bg-[#ef4444]/5 border-b border-[#ef4444]/20">
          <div className="flex items-center gap-1.5">
            <XCircle className="h-3.5 w-3.5 text-[#ef4444] shrink-0" />
            <div>
              <span className="text-[10px] font-semibold text-[#ef4444]">{fetchError.title}</span>
              <span className="text-[11px] text-muted-foreground ml-1.5">{fetchError.message}</span>
            </div>
          </div>
          {fetchError.retryable && (
            <button onClick={refresh} className="text-[10px] text-[#ef4444] hover:text-red-300 underline">Retry</button>
          )}
        </div>
      )}

      <RefreshIndicator visible={pollingRefreshing} />

      {/* Filter row — simple inline, no Card wrapper */}
      {renderFilters()}

      {/* Tab content — edge-to-edge, fills remaining space */}
      <div className="flex-1 min-h-0 flex flex-col">
        {renderTabContent()}
      </div>
    </div>
  );

  // ── Side Panel (30%) — Summary ─────────────────────────────────────
  // Direct key-value pairs, no Card wrappers, no "Account" sub-header
  // Compact, every pixel shows data

  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Summary" panelId="portfolio-summary">
        <div className="flex-1 min-h-0 overflow-auto">
          {/* Key-value pairs — directly in panel, no Card wrapper */}
          <div className="px-2 py-2 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Equity</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{formatCurrency(totalPortfolioValue)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Cash</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{accountInfo ? formatCurrency(accountInfo.buying_power) : '---'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Invested</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{formatCurrency(totalPositionValue)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">P&L</span>
              <span className={cn('text-sm font-mono font-semibold', totalPnL >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
                {totalPnL >= 0 ? '+' : ''}{formatCurrency(totalPnL)} ({formatPercentage(totalPnLPercent)})
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Positions</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{positions.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Win Rate</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{winRate.toFixed(1)}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">Win Rate (Closed)</span>
              <span className="text-sm font-mono font-semibold text-gray-100">{closedWinRate.toFixed(1)}%</span>
            </div>
          </div>

          {/* Thin separator */}
          <div className="h-px bg-[var(--color-dark-border)] mx-2" />

          {/* By Asset Class — compact list, no Card */}
          <div className="px-2 py-2">
            <div className="text-[10px] font-semibold text-gray-500 tracking-wide mb-1">By Asset Class</div>
            {assetClassSummary.length > 0 ? (
              <div className="space-y-0.5">
                {assetClassSummary.map((ac) => (
                  <div key={ac.assetClass} className="flex items-center justify-between py-0.5">
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-gray-300">{ac.assetClass}</span>
                      <span className="text-[11px] text-muted-foreground font-mono">({ac.count})</span>
                    </div>
                    <span className={cn('text-[10px] font-mono font-semibold', ac.totalPnl > 0 ? 'text-[#22c55e]' : ac.totalPnl < 0 ? 'text-[#ef4444]' : 'text-gray-400')}>
                      {ac.totalPnl >= 0 ? '+' : ''}{formatCurrency(ac.totalPnl)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground text-center py-2">No open positions</p>
            )}
          </div>

          {/* Thin separator */}
          <div className="h-px bg-[var(--color-dark-border)] mx-2" />

          {/* Sector Exposure Pie Chart — directly rendered, no Card */}
          <div className="px-2 py-2">
            <div className="text-[10px] font-semibold text-gray-500 tracking-wide mb-1">Sector Exposure</div>
            {sectorExposure.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie data={sectorExposure} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={58} innerRadius={28} paddingAngle={2} stroke="none">
                      {sectorExposure.map((_, index) => (
                        <Cell key={`sector-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Exposure']}
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem', fontSize: '10px' }}
                      labelStyle={{ color: '#d1d5db' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
                  {sectorExposure.slice(0, 8).map((s, i) => (
                    <div key={s.name} className="flex items-center gap-1">
                      <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                      <span className="text-[11px] text-gray-400 truncate max-w-[70px]">{s.name}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-[11px] text-muted-foreground text-center py-2">No data</p>
            )}
          </div>

          {/* Thin separator */}
          <div className="h-px bg-[var(--color-dark-border)] mx-2" />

          {/* Allocation Breakdown — directly rendered, no Card */}
          <div className="px-2 py-2">
            <div className="text-[10px] font-semibold text-gray-500 tracking-wide mb-1">Allocation</div>
            {allocationData.length > 0 ? (
              <div className="space-y-1">
                {allocationData.map((item, i) => (
                  <div key={item.name}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[10px] text-gray-300 truncate max-w-[100px]">{item.name}</span>
                      <span className="text-[10px] font-mono text-gray-400">{item.pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${item.pct}%`, backgroundColor: COLORS[i % COLORS.length] }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground text-center py-2">No positions</p>
            )}
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Return: compact PageTemplate + 2-panel layout ──────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="Portfolio"
        compact={true}
        actions={headerActions}
      >
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }} className="h-full">
          <ResizablePanelLayout
            layoutId="portfolio-panels"
            direction="horizontal"
            panels={[
              { id: 'portfolio-main', defaultSize: 70, minSize: 400, content: mainPanel },
              { id: 'portfolio-side', defaultSize: 30, minSize: 250, content: sidePanel },
            ]}
          />
        </motion.div>
      </PageTemplate>

      {/* Single Position Close Confirmation Dialog */}
      <ConfirmDialog
        open={!!confirmClosePosition}
        onOpenChange={(open) => !open && setConfirmClosePosition(null)}
        title="Close Position"
        description={`Close ${confirmClosePosition?.symbol} position?`}
        confirmLabel="Close Position"
        confirmVariant="destructive"
        onConfirm={() => handleClosePosition(confirmClosePosition!.id)}
      >
        <div className="space-y-1.5 text-[11px] font-mono">
          <div className="flex justify-between"><span className="text-muted-foreground">Symbol</span><span>{confirmClosePosition?.symbol}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Invested</span><span>{formatCurrency(getInvested(confirmClosePosition || {}))}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">P&L</span><span className={cn(
            (confirmClosePosition?.unrealized_pnl || 0) >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'
          )}>{formatCurrency(confirmClosePosition?.unrealized_pnl || 0)}</span></div>
        </div>
      </ConfirmDialog>

      {/* Bulk Close Confirmation Dialog */}
      <ConfirmDialog
        open={showBulkCloseConfirm}
        onOpenChange={setShowBulkCloseConfirm}
        title="Close Selected Positions"
        description={`Close ${selectedPositions.size} selected position${selectedPositions.size !== 1 ? 's' : ''}?`}
        confirmLabel={`Close ${selectedPositions.size} Position${selectedPositions.size !== 1 ? 's' : ''}`}
        confirmVariant="destructive"
        onConfirm={handleCloseSelected}
      >
        <div className="space-y-1 text-[11px] font-mono max-h-48 overflow-y-auto">
          {positions.filter(p => selectedPositions.has(p.id)).map(p => (
            <div key={p.id} className="flex justify-between">
              <span>{p.symbol}</span>
              <span className={cn(p.unrealized_pnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatCurrency(p.unrealized_pnl)}</span>
            </div>
          ))}
          <div className="pt-1.5 border-t border-[var(--color-dark-border)] flex justify-between font-semibold">
            <span>Total P&L Impact</span>
            <span className={cn(positions.filter(p => selectedPositions.has(p.id)).reduce((sum, p) => sum + p.unrealized_pnl, 0) >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>
              {formatCurrency(positions.filter(p => selectedPositions.has(p.id)).reduce((sum, p) => sum + p.unrealized_pnl, 0))}
            </span>
          </div>
        </div>
      </ConfirmDialog>

      {/* Close All Positions Confirmation Dialog */}
      <ConfirmDialog
        open={showCloseAllConfirm}
        onOpenChange={setShowCloseAllConfirm}
        title="Close All Trades"
        description={`This will close all ${positions.length} open position${positions.length !== 1 ? 's' : ''}. This action cannot be undone.`}
        confirmLabel={closingAll ? 'Closing All...' : 'Yes, Close All Trades'}
        confirmVariant="destructive"
        onConfirm={handleCloseAllPositions}
      >
        <div className="text-[11px] font-mono text-muted-foreground space-y-1">
          <div className="flex justify-between"><span>Total Positions</span><span>{positions.length}</span></div>
          <div className="flex justify-between">
            <span>Total Unrealized P&L</span>
            <span className={cn(totalPnL >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]')}>{formatCurrency(totalPnL)}</span>
          </div>
        </div>
      </ConfirmDialog>

      {/* Modify Position Modal */}
      {modifyingPosition && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-card border border-border rounded-lg p-4 max-w-sm w-full mx-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-foreground font-mono">
                Modify {modifyingPosition.type === 'sl' ? 'Stop Loss' : 'Take Profit'}
              </h3>
              <Button variant="ghost" size="sm" onClick={() => { setModifyingPosition(null); setModifyPrice(''); }} className="h-6 w-6 p-0">
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="mb-3">
              <label className="block text-[11px] text-muted-foreground mb-1">
                {modifyingPosition.type === 'sl' ? 'Stop Loss Price' : 'Take Profit Price'}
              </label>
              <Input type="number" step="0.01" value={modifyPrice} onChange={(e) => setModifyPrice(e.target.value)} placeholder="Enter price" autoFocus className="h-8 text-[11px]" />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleModifySubmit} disabled={!modifyPrice} className="flex-1 h-8 text-[11px]">Confirm</Button>
              <Button variant="outline" onClick={() => { setModifyingPosition(null); setModifyPrice(''); }} className="flex-1 h-8 text-[11px]">Cancel</Button>
            </div>
          </motion.div>
        </div>
      )}
    </DashboardLayout>
  );
};
