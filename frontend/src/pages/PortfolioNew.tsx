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
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { DataTable } from '../components/trading/DataTable';
import { Card, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
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

  // Fundamental alerts state (Task 11.10.3)
  const [fundamentalAlerts, setFundamentalAlerts] = useState<FundamentalAlert[]>([]);
  const [dismissingAlertId, setDismissingAlertId] = useState<string | null>(null);
  const [closingAlertId, setClosingAlertId] = useState<string | null>(null);
  const [closingAllAlerts, setClosingAllAlerts] = useState(false);
  const [triggeringCheck, setTriggeringCheck] = useState(false);

  // Confirmation dialog state (Task 4.1)
  const [confirmClosePosition, setConfirmClosePosition] = useState<Position | null>(null);
  const [showBulkCloseConfirm, setShowBulkCloseConfirm] = useState(false);

  // Data freshness and error state (Task 4.2)
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<ClassifiedError | null>(null);
  const [pendingClosuresLoading, setPendingClosuresLoading] = useState(false);
  const [fundamentalAlertsLoading, setFundamentalAlertsLoading] = useState(false);

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

  // Fetch fundamental alerts (Task 11.10.3)
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
      // Core data — fast DB queries, must complete before page renders
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

      // Secondary data — can be slow, load in background without blocking page render
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
      
      // Convert closed positions to ClosedPosition format
      const closed: ClosedPosition[] = closedPositionsData
        .filter(p => p.closed_at) // Only positions that are actually closed
        .map(p => {
          const openedAt = new Date(p.opened_at);
          const closedAt = new Date(p.closed_at!);
          const holdingTimeHours = (closedAt.getTime() - openedAt.getTime()) / (1000 * 60 * 60);
          
          // Calculate realized P&L percent from invested amount
          const realizedPnl = p.realized_pnl ?? 0;
          const invested = (p as any).invested_amount || p.quantity * (p.entry_price || 1);
          const pnlPercent = invested > 0 && realizedPnl !== 0
            ? (realizedPnl / invested) * 100 
            : 0;
          
          return {
            id: p.id,
            symbol: p.symbol,
            side: p.side,
            quantity: p.quantity,
            entry_price: p.entry_price,
            exit_price: p.current_price, // Last known price when closed
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

  // Polling for data refresh (Task 4.2) — skip REST polling when WS connected
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

    // Subscribe to pending closure events
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
  // Use equity for P&L percent (equity = balance + unrealized, gives accurate %)
  const totalPnLPercent = accountInfo ? (totalPnL / accountInfo.balance) * 100 : 0;
  // Position value = margin_used (actual capital deployed), not leveraged notional
  const totalPositionValue = accountInfo?.margin_used || 0;
  // Total portfolio = equity (balance + unrealized P&L)
  const totalPortfolioValue = accountInfo?.equity || (accountInfo?.balance || 0);
  
  const winningPositions = positions.filter(p => p.unrealized_pnl > 0).length;
  const winRate = positions.length > 0 ? (winningPositions / positions.length) * 100 : 0;

  // Win Rate from closed positions (Task 4.2)
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
        case '1d':
          matchesDate = daysDiff <= 1;
          break;
        case '7d':
          matchesDate = daysDiff <= 7;
          break;
        case '30d':
          matchesDate = daysDiff <= 30;
          break;
      }
    }
    
    return matchesSearch && matchesStrategy && matchesDate;
  });

  // Prepare allocation chart data
  const pieChartData = positions.reduce((acc, position) => {
    // Try invested_amount first, then calculate from quantity * current_price, then entry_price
    const value = Math.abs(
      (position as any).invested_amount ||
      (position.quantity * (position.current_price || position.entry_price || 0)) ||
      0
    );
    if (value === 0) return acc; // Skip zero-value positions
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

  // Asset class summary for side panel
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

  // Sector exposure for pie chart in side panel
  const sectorExposure = useMemo(() => {
    const map = new Map<string, number>();
    positions.forEach(p => {
      const sector = (p as any).sector || (p as any).asset_class || 'Other';
      const value = Math.abs(
        (p as any).invested_amount ||
        (p.quantity * (p.current_price || p.entry_price || 0)) ||
        0
      );
      map.set(sector, (map.get(sector) || 0) + value);
    });
    return Array.from(map.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  // Allocation breakdown for bar chart in side panel
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

  // Handle position actions
  const handleClosePosition = async (positionId: string) => {
    if (!tradingMode) return;
    
    try {
      setClosingPositionId(positionId);
      await apiClient.closePosition(positionId, tradingMode);
      toast.success('Position closed successfully');
      setPositions(prev => prev.filter(p => p.id !== positionId));
      fetchData(); // Refresh to update closed positions
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
    if (isNaN(price) || price <= 0) {
      toast.error('Please enter a valid price');
      return;
    }

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
    if (isNaN(price) || price <= 0) {
      toast.error('Please enter a valid price');
      return;
    }

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
    if (modifyingPosition?.type === 'sl') {
      handleModifyStopLoss();
    } else {
      handleModifyTakeProfit();
    }
  };

  // Handle pending closure actions
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

  // Fundamental alert handlers (Task 11.10.3)
  const handleDismissAlert = async (positionId: string) => {
    if (!tradingMode) return;
    try {
      setDismissingAlertId(positionId);
      await apiClient.dismissFundamentalAlert(positionId, tradingMode);
      toast.success('Alert dismissed — position will remain open');
      setFundamentalAlerts(prev => prev.filter(a => a.id !== positionId));
      // Also refresh pending closures since the position was unflagged
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
      // Refresh alerts after the check
      fetchFundamentalAlerts();
      fetchPendingClosures();
    } catch (error) {
      console.error('Failed to trigger fundamental check:', error);
      toast.error('Failed to trigger fundamental check');
    } finally {
      setTriggeringCheck(false);
    }
  };

  // Handle position selection
  const handleTogglePosition = (positionId: string) => {
    setSelectedPositions(prev => {
      const next = new Set(prev);
      if (next.has(positionId)) {
        next.delete(positionId);
      } else {
        next.add(positionId);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedPositions.size === filteredPositions.length) {
      setSelectedPositions(new Set());
    } else {
      setSelectedPositions(new Set(filteredPositions.map(p => p.id)));
    }
  };

  // Handle close selected positions
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

  // Handle close all positions
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

  // Handle sync positions with eToro
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

  // Export to CSV
  const exportToCSV = (data: Position[] | ClosedPosition[], filename: string) => {
    if (data.length === 0) {
      toast.error('No data to export');
      return;
    }

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

  // Helper: get display status for eToro terminology
  const getPositionStatus = (position: Position): string => {
    if (position.pending_closure) return 'Pending Close';
    return 'Open';
  };

  // Table columns for open positions
  const positionColumns: ColumnDef<Position>[] = [
    {
      id: 'select',
      header: () => (
        <div className="flex items-center justify-center">
          <input
            type="checkbox"
            checked={filteredPositions.length > 0 && selectedPositions.size === filteredPositions.length}
            onChange={handleSelectAll}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
          />
        </div>
      ),
      cell: ({ row }) => (
        <div className="flex items-center justify-center">
          <input
            type="checkbox"
            checked={selectedPositions.has(row.original.id)}
            onChange={() => handleTogglePosition(row.original.id)}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
          />
        </div>
      ),
      size: 40,
    },
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div
          className="font-mono font-semibold text-sm text-blue-400 hover:text-blue-300 cursor-pointer"
          onClick={() => navigate(`/portfolio/${encodeURIComponent(row.original.symbol)}`)}
        >
          {row.original.symbol}
        </div>
      ),
    },
    {
      accessorKey: 'strategy_name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div className="font-mono text-xs text-muted-foreground truncate max-w-[180px]" title={row.original.strategy_name || row.original.strategy_id}>
          {row.original.strategy_name || row.original.strategy_id?.slice(0, 8) || '—'}
        </div>
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
          {row.original.side === 'BUY' ? 'BUY' : 'SELL'}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = getPositionStatus(row.original);
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold whitespace-nowrap',
            status === 'Open' ? 'bg-blue-500/20 text-blue-400' : 'bg-amber-500/20 text-amber-400'
          )}>
            {status}
          </span>
        );
      },
    },
    {
      accessorKey: 'quantity',
      header: () => <div className="text-right">Invested</div>,
      cell: ({ row }) => {
        const invested = (row.original as any).invested_amount || row.original.quantity * row.original.entry_price;
        return (
          <div className="text-right">
            <span className="font-mono text-sm">{formatCurrency(invested)}</span>
          </div>
        );
      },
    },
    {
      accessorKey: 'entry_price',
      header: () => <div className="text-right">Open Rate</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency(row.original.entry_price)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'current_price',
      header: () => <div className="text-right">Current Rate</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency(row.original.current_price)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'unrealized_pnl',
      header: () => <div className="text-right">P&L <span className="text-[10px] text-muted-foreground">(vs balance)</span></div>,
      cell: ({ row }) => (
        <div className="text-right">
          <div className={cn(
            'font-mono font-semibold text-sm',
            row.original.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {formatCurrency(row.original.unrealized_pnl)}
          </div>
          <div className={cn(
            'text-xs font-mono',
            row.original.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {formatPercentage(row.original.unrealized_pnl_percent || 0)}
          </div>
        </div>
      ),
    },
    {
      id: 'holding',
      header: 'Holding',
      cell: ({ row }) => {
        const openedAt = new Date(row.original.opened_at);
        const now = new Date();
        const days = Math.floor((now.getTime() - openedAt.getTime()) / (1000 * 60 * 60 * 24));
        const color = days < 7 ? 'text-accent-green' : days <= 30 ? 'text-amber-400' : 'text-accent-red';
        const bg = days < 7 ? 'bg-accent-green/10' : days <= 30 ? 'bg-amber-400/10' : 'bg-accent-red/10';
        return (
          <span className={cn('px-2 py-0.5 rounded text-xs font-mono font-semibold', color, bg)}>
            {days}d
          </span>
        );
      },
      sortingFn: (rowA, rowB) => {
        const daysA = new Date().getTime() - new Date(rowA.original.opened_at).getTime();
        const daysB = new Date().getTime() - new Date(rowB.original.opened_at).getTime();
        return daysA - daysB;
      },
    },
    {
      id: 'portfolioPct',
      header: () => <div className="text-right">% Port</div>,
      cell: ({ row }) => {
        const totalValue = positions.reduce((sum, p) => sum + Math.abs((p as any).invested_amount || p.current_price * p.quantity), 0);
        const posValue = Math.abs((row.original as any).invested_amount || row.original.current_price * row.original.quantity);
        const pct = totalValue > 0 ? (posValue / totalValue) * 100 : 0;
        return (
          <div className="text-right">
            <span className="font-mono text-xs text-muted-foreground">{pct.toFixed(1)}%</span>
          </div>
        );
      },
    },
    {
      id: 'stopTp',
      header: 'Stop/TP',
      cell: ({ row }) => {
        const { entry_price, current_price, stop_loss, take_profit } = row.original;
        if (!stop_loss && !take_profit) return <span className="text-xs text-muted-foreground">—</span>;
        const prices = [stop_loss, entry_price, current_price, take_profit].filter((p): p is number => p != null && p > 0);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        const range = max - min || 1;
        const toPos = (v: number) => ((v - min) / range) * 100;
        return (
          <div className="w-24 h-4 relative bg-gray-800 rounded overflow-hidden" title={`SL: ${stop_loss?.toFixed(2) ?? '—'} | TP: ${take_profit?.toFixed(2) ?? '—'}`}>
            {stop_loss != null && stop_loss > 0 && (
              <div className="absolute top-0 bottom-0 w-0.5 bg-accent-red" style={{ left: `${toPos(stop_loss)}%` }} />
            )}
            <div className="absolute top-0 bottom-0 w-0.5 bg-blue-400" style={{ left: `${toPos(entry_price)}%` }} />
            {take_profit != null && take_profit > 0 && (
              <div className="absolute top-0 bottom-0 w-0.5 bg-accent-green" style={{ left: `${toPos(take_profit)}%` }} />
            )}
            <div className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-white border border-gray-600" style={{ left: `calc(${toPos(current_price)}% - 4px)` }} />
          </div>
        );
      },
    },
    {
      id: 'strategy',
      header: 'Strategy',
      cell: ({ row }) => {
        const sid = row.original.strategy_id;
        if (!sid) return <span className="text-xs text-muted-foreground">—</span>;
        const isAlphaEdge = sid.toLowerCase().includes('alpha_edge') || sid.toLowerCase().includes('earnings') || sid.toLowerCase().includes('sector_rotation') || sid.toLowerCase().includes('mean_reversion');
        return (
          <span className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap',
            isAlphaEdge ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
          )}>
            {isAlphaEdge ? 'Alpha Edge' : 'Template'}
          </span>
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
              <DropdownMenuItem
                onClick={() => setModifyingPosition({ id: row.original.id, type: 'sl' })}
              >
                Modify Stop Loss
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setModifyingPosition({ id: row.original.id, type: 'tp' })}
              >
                Modify Take Profit
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setConfirmClosePosition(row.original)}
                className="text-accent-red"
                disabled={closingPositionId === row.original.id}
              >
                {closingPositionId === row.original.id ? 'Closing...' : 'Close Position'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  // Table columns for closed positions
  const closedPositionColumns: ColumnDef<ClosedPosition>[] = [
    {
      id: 'select',
      header: () => (
        <div className="flex items-center justify-center">
          <input
            type="checkbox"
            checked={filteredClosedPositions.length > 0 && selectedClosedPositions.size === filteredClosedPositions.length}
            onChange={() => {
              if (selectedClosedPositions.size === filteredClosedPositions.length) {
                setSelectedClosedPositions(new Set());
              } else {
                setSelectedClosedPositions(new Set(filteredClosedPositions.map(p => p.id)));
              }
            }}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
          />
        </div>
      ),
      cell: ({ row }) => (
        <div className="flex items-center justify-center">
          <input
            type="checkbox"
            checked={selectedClosedPositions.has(row.original.id)}
            onChange={() => {
              setSelectedClosedPositions(prev => {
                const next = new Set(prev);
                if (next.has(row.original.id)) {
                  next.delete(row.original.id);
                } else {
                  next.add(row.original.id);
                }
                return next;
              });
            }}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
          />
        </div>
      ),
      size: 40,
    },
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div className="font-mono font-semibold text-sm">{row.original.symbol}</div>
      ),
    },
    {
      accessorKey: 'strategy_name',
      header: 'Strategy',
      cell: ({ row }) => (
        <div className="font-mono text-xs text-muted-foreground truncate max-w-[180px]" title={row.original.strategy_name || row.original.strategy_id}>
          {row.original.strategy_name || '—'}
        </div>
      ),
    },
    {
      accessorKey: 'realized_pnl',
      header: () => <div className="text-right">Realized P&L</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <div className={cn(
            'font-mono font-semibold text-sm',
            row.original.realized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {formatCurrency(row.original.realized_pnl)}
          </div>
          <div className={cn(
            'text-xs font-mono',
            row.original.realized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {formatPercentage(row.original.realized_pnl_percent)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'holding_time_hours',
      header: () => <div className="text-right">Holding Time</div>,
      cell: ({ row }) => (
        <div className="text-right text-sm text-muted-foreground">
          {row.original.holding_time_hours < 24 
            ? `${row.original.holding_time_hours.toFixed(1)}h`
            : `${(row.original.holding_time_hours / 24).toFixed(1)}d`
          }
        </div>
      ),
    },
    {
      accessorKey: 'exit_reason',
      header: 'Exit Reason',
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          {row.original.exit_reason || 'N/A'}
        </div>
      ),
    },
    {
      accessorKey: 'closed_at',
      header: () => <div className="text-right">Closed At</div>,
      cell: ({ row }) => (
        <div className="text-right text-xs text-muted-foreground whitespace-nowrap">
          {formatTimestamp(row.original.closed_at)}
        </div>
      ),
    },
  ];

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  // ── Header actions for PageTemplate ──────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-2">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <Button
        variant="outline"
        size="sm"
        onClick={refresh}
        disabled={refreshing || pollingRefreshing}
        className="gap-2"
      >
        <RefreshCw className={cn('h-4 w-4', (refreshing || pollingRefreshing) && 'animate-spin')} />
        Refresh
      </Button>
    </div>
  );

  // ── Main Panel (70%) — Positions with tabs ─────────────────────────
  const mainPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Positions" panelId="portfolio-positions" onRefresh={refresh}>
        <div className="flex-1 overflow-auto min-h-0 p-3">
          <RefreshIndicator visible={pollingRefreshing} />

          {/* Error state */}
          {fetchError && !loading && positions.length === 0 && (
            <Card className="mb-4 border-accent-red/50 bg-accent-red/5">
              <CardContent className="py-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-5 w-5 text-accent-red shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-accent-red">{fetchError.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{fetchError.message}</p>
                    </div>
                  </div>
                  {fetchError.retryable && (
                    <Button variant="outline" size="sm" onClick={refresh} className="border-accent-red/30 text-accent-red hover:bg-accent-red/10">
                      Retry
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Pending Closures Alert Banner */}
          {pendingClosures.length > 0 && (
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-3">
              <Card className="border-amber-500/50 bg-amber-500/5">
                <CardContent className="py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                      <p className="text-xs font-semibold text-amber-400">
                        {pendingClosures.length} pending closure{pendingClosures.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10 text-xs h-7"
                      onClick={() => { const el = document.getElementById('pending-closures-tab'); if (el) el.click(); }}>
                      Review
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Fundamental Alerts Banner */}
          {fundamentalAlerts.length > 0 && (
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-3">
              <Card className="border-orange-500/50 bg-orange-500/5">
                <CardContent className="py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Activity className="h-4 w-4 text-orange-500 shrink-0" />
                      <p className="text-xs font-semibold text-orange-400">
                        {fundamentalAlerts.length} position{fundamentalAlerts.length !== 1 ? 's' : ''} flagged
                      </p>
                    </div>
                    <Button variant="outline" size="sm" className="border-orange-500/30 text-orange-400 hover:bg-orange-500/10 text-xs h-7"
                      onClick={() => { const el = document.getElementById('fundamental-alerts-tab'); if (el) el.click(); }}>
                      Review
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Tabs */}
          <Tabs defaultValue="open" className="space-y-3">
            <TabsList className="w-full overflow-x-auto">
              <TabsTrigger value="open">Open ({filteredPositions.length})</TabsTrigger>
              <TabsTrigger value="closed">Closed ({filteredClosedPositions.length})</TabsTrigger>
              <TabsTrigger value="pending" id="pending-closures-tab" className={pendingClosures.length > 0 ? 'text-amber-400' : ''}>
                Pending {pendingClosures.length > 0 && `(${pendingClosures.length})`}
              </TabsTrigger>
              <TabsTrigger value="fundamental-alerts" id="fundamental-alerts-tab" className={fundamentalAlerts.length > 0 ? 'text-orange-400' : ''}>
                Alerts {fundamentalAlerts.length > 0 && `(${fundamentalAlerts.length})`}
              </TabsTrigger>
            </TabsList>

            {/* Open Positions Tab */}
            <TabsContent value="open" className="space-y-3">
              {/* Filters */}
              <div className="flex flex-wrap gap-2 items-center">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input placeholder="Search..." value={positionSearch} onChange={(e) => setPositionSearch(e.target.value)} className="pl-8 h-8 w-[160px] text-xs" />
                </div>
                <Select value={positionStrategyFilter} onValueChange={setPositionStrategyFilter}>
                  <SelectTrigger className="w-[130px] h-8 text-xs"><SelectValue placeholder="Strategy" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Strategies</SelectItem>
                    {uniqueStrategies.map(s => <SelectItem key={s} value={s!}>{s?.substring(0, 8)}...</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={positionSideFilter} onValueChange={setPositionSideFilter}>
                  <SelectTrigger className="w-[100px] h-8 text-xs"><SelectValue placeholder="Side" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="BUY">BUY</SelectItem>
                    <SelectItem value="SELL">SELL</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={handleSyncPositions} disabled={syncing} className="gap-1 h-8 text-xs" title="Sync with eToro">
                  <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} />
                  {syncing ? 'Syncing...' : 'Sync'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => exportToCSV(filteredPositions, 'open-positions.csv')} className="gap-1 h-8 text-xs">
                  <Download className="h-3.5 w-3.5" /> Export
                </Button>
              </div>
              {/* Bulk actions */}
              {(selectedPositions.size > 0 || positions.length > 0) && (
                <div className="flex gap-2">
                  {selectedPositions.size > 0 && (
                    <Button size="sm" variant="destructive" onClick={() => setShowBulkCloseConfirm(true)} disabled={closingSelected} className="gap-1 h-7 text-xs">
                      <X className="h-3.5 w-3.5" />
                      {closingSelected ? 'Closing...' : `Close Selected (${selectedPositions.size})`}
                    </Button>
                  )}
                  {positions.length > 0 && (
                    <Button size="sm" variant="outline" onClick={() => setShowCloseAllConfirm(true)} className="gap-1 h-7 text-xs border-accent-red/30 text-accent-red hover:bg-accent-red/10">
                      <XCircle className="h-3.5 w-3.5" /> Close All
                    </Button>
                  )}
                </div>
              )}
              {/* Table */}
              {filteredPositions.length > 0 ? (
                <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 380px)' }}>
                  <DataTable columns={positionColumns} data={filteredPositions} pageSize={20} showPagination={true} className="[&_table]:table-dense" />
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  {positionSearch || positionStrategyFilter !== 'all' || positionSideFilter !== 'all' ? 'No positions match your filters' : 'No open positions'}
                </div>
              )}
            </TabsContent>

            {/* Closed Positions Tab */}
            <TabsContent value="closed" className="space-y-3">
              <div className="flex flex-wrap gap-2 items-center">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input placeholder="Search..." value={closedSearch} onChange={(e) => setClosedSearch(e.target.value)} className="pl-8 h-8 w-[160px] text-xs" />
                </div>
                <Select value={closedStrategyFilter} onValueChange={setClosedStrategyFilter}>
                  <SelectTrigger className="w-[130px] h-8 text-xs"><SelectValue placeholder="Strategy" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Strategies</SelectItem>
                    {uniqueStrategies.map(s => <SelectItem key={s} value={s!}>{s?.substring(0, 8)}...</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={closedDateFilter} onValueChange={setClosedDateFilter}>
                  <SelectTrigger className="w-[110px] h-8 text-xs"><SelectValue placeholder="Date" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Time</SelectItem>
                    <SelectItem value="1d">Last 24h</SelectItem>
                    <SelectItem value="7d">Last 7 days</SelectItem>
                    <SelectItem value="30d">Last 30 days</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={() => exportToCSV(filteredClosedPositions, 'closed-positions.csv')} className="gap-1 h-8 text-xs">
                  <Download className="h-3.5 w-3.5" /> Export
                </Button>
              </div>
              {selectedClosedPositions.size > 0 && (
                <div className="flex gap-2">
                  <Button size="sm" variant="destructive" onClick={async () => {
                    if (!tradingMode) return;
                    try { setDeletingClosedPositions(true); await apiClient.deleteClosedPositions(Array.from(selectedClosedPositions), tradingMode); toast.success(`Deleted ${selectedClosedPositions.size} closed position(s)`); setSelectedClosedPositions(new Set()); fetchData(); } catch { toast.error('Failed to delete closed positions'); } finally { setDeletingClosedPositions(false); }
                  }} disabled={deletingClosedPositions} className="gap-1 h-7 text-xs">
                    <Trash2 className="h-3.5 w-3.5" />
                    {deletingClosedPositions ? 'Deleting...' : `Delete Selected (${selectedClosedPositions.size})`}
                  </Button>
                </div>
              )}
              {filteredClosedPositions.length > 0 ? (
                <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 380px)' }}>
                  <DataTable columns={closedPositionColumns} data={filteredClosedPositions} pageSize={20} showPagination={true} className="[&_table]:table-dense" />
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  {closedSearch || closedStrategyFilter !== 'all' || closedDateFilter !== 'all' ? 'No closed positions match your filters' : 'No closed positions'}
                </div>
              )}
            </TabsContent>

            {/* Pending Closures Tab */}
            <TabsContent value="pending" className="space-y-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-muted-foreground">
                  Positions flagged for closure.{pendingClosures.length > 0 && ' Auto-close within 60s.'}
                </p>
                {pendingClosures.length > 0 && (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchPendingClosures} className="gap-1 h-7 text-xs">
                      <RefreshCw className="h-3 w-3" /> Refresh
                    </Button>
                    <Button size="sm" onClick={handleApproveAll} disabled={approvingAll} className="gap-1 h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white">
                      <Check className="h-3 w-3" /> {approvingAll ? 'Closing...' : `Approve All (${pendingClosures.length})`}
                    </Button>
                  </div>
                )}
              </div>
              {pendingClosuresLoading && pendingClosures.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" /><span className="text-xs">Loading...</span>
                </div>
              ) : pendingClosures.length > 0 ? (
                <div className="space-y-2">
                  {pendingClosures.map((position) => {
                    const hoursAgo = Math.floor((Date.now() - new Date(position.opened_at).getTime()) / (1000 * 60 * 60));
                    return (
                      <motion.div key={position.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                        className="flex items-center justify-between p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-semibold text-xs">{position.symbol}</span>
                              <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold', position.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red')}>{position.side}</span>
                              <span className="text-[10px] text-muted-foreground font-mono">{formatCurrency((position as any).invested_amount || position.quantity * position.entry_price)}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              {position.closure_reason && <span className="text-[10px] text-amber-400">{position.closure_reason}</span>}
                              <span className="flex items-center gap-1 text-[10px] text-muted-foreground"><Clock className="h-2.5 w-2.5" />{hoursAgo < 1 ? 'Now' : hoursAgo < 24 ? `${hoursAgo}h` : `${Math.floor(hoursAgo / 24)}d`}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <div className="text-right mr-1">
                            <div className={cn('font-mono font-semibold text-xs', position.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(position.unrealized_pnl)}</div>
                            <div className={cn('text-[10px] font-mono', position.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(position.unrealized_pnl_percent || 0)}</div>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => handleDismissClosure(position.id)} disabled={dismissingId === position.id} className="h-7 text-xs">
                            {dismissingId === position.id ? '...' : 'Dismiss'}
                          </Button>
                          <Button size="sm" onClick={() => handleApproveClosure(position.id)} disabled={approvingId === position.id} className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white">
                            {approvingId === position.id ? '...' : 'Approve'}
                          </Button>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="h-6 w-6 mx-auto mb-2 opacity-30" />
                  <p className="text-xs">No positions pending closure</p>
                </div>
              )}
            </TabsContent>

            {/* Fundamental Alerts Tab */}
            <TabsContent value="fundamental-alerts" className="space-y-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-muted-foreground">Positions flagged by fundamental exit monitoring.</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={handleTriggerFundamentalCheck} disabled={triggeringCheck} className="gap-1 h-7 text-xs">
                    <RefreshCw className={cn('h-3 w-3', triggeringCheck && 'animate-spin')} /> {triggeringCheck ? 'Checking...' : 'Run Check'}
                  </Button>
                  {fundamentalAlerts.length > 0 && (
                    <Button size="sm" onClick={handleCloseAllAlerts} disabled={closingAllAlerts} className="gap-1 h-7 text-xs bg-orange-600 hover:bg-orange-700 text-white">
                      <XCircle className="h-3 w-3" /> {closingAllAlerts ? 'Closing...' : `Close All (${fundamentalAlerts.length})`}
                    </Button>
                  )}
                </div>
              </div>
              {fundamentalAlertsLoading && fundamentalAlerts.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" /><span className="text-xs">Loading...</span>
                </div>
              ) : fundamentalAlerts.length > 0 ? (
                <div className="space-y-2">
                  {fundamentalAlerts.map((alert) => {
                    const pnl = alert.unrealized_pnl || 0;
                    const pnlPercent = alert.unrealized_pnl_percent || 0;
                    const flagReason = alert.flag_reason || 'Fundamental Exit';
                    const fundamentalDetail = alert.fundamental_detail || alert.closure_reason || '';
                    const reasonColor = flagReason === 'Earnings Miss' ? 'bg-red-500/20 text-red-400' : flagReason === 'Revenue Decline' ? 'bg-amber-500/20 text-amber-400' : flagReason === 'Sector Rotation' ? 'bg-blue-500/20 text-blue-400' : 'bg-orange-500/20 text-orange-400';
                    return (
                      <motion.div key={alert.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                        className="flex items-center justify-between p-3 rounded-lg border border-orange-500/20 bg-orange-500/5">
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-mono font-semibold text-xs">{alert.symbol}</span>
                              <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold', alert.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red')}>{alert.side}</span>
                              <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-semibold', reasonColor)}>{flagReason}</span>
                            </div>
                            {fundamentalDetail && <div className="mt-1 text-[10px] text-orange-300/80 font-mono truncate max-w-xs" title={fundamentalDetail}>{fundamentalDetail}</div>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <div className="text-right mr-1">
                            <div className={cn('font-mono font-semibold text-xs', pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(pnl)}</div>
                            <div className={cn('text-[10px] font-mono', pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(pnlPercent)}</div>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => handleDismissAlert(alert.id)} disabled={dismissingAlertId === alert.id} className="h-7 text-xs">
                            {dismissingAlertId === alert.id ? '...' : 'Dismiss'}
                          </Button>
                          <Button size="sm" onClick={() => handleCloseAlertPosition(alert.id)} disabled={closingAlertId === alert.id} className="h-7 text-xs bg-orange-600 hover:bg-orange-700 text-white">
                            {closingAlertId === alert.id ? '...' : 'Close'}
                          </Button>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Activity className="h-6 w-6 mx-auto mb-2 opacity-30" />
                  <p className="text-xs">No fundamental alerts</p>
                  <Button variant="outline" size="sm" onClick={handleTriggerFundamentalCheck} disabled={triggeringCheck} className="mt-3 gap-1 h-7 text-xs">
                    <RefreshCw className={cn('h-3 w-3', triggeringCheck && 'animate-spin')} /> {triggeringCheck ? 'Running...' : 'Run Check Now'}
                  </Button>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (30%) — Summary ─────────────────────────────────────
  const portfolioMetrics: CompactMetric[] = [
    { label: 'Equity', value: formatCurrency(totalPortfolioValue) },
    { label: 'P&L', value: formatCurrency(totalPnL), trend: totalPnL > 0 ? 'up' : totalPnL < 0 ? 'down' : 'neutral' },
    { label: 'Positions', value: String(positions.length) },
    { label: 'Win Rate', value: `${winRate.toFixed(1)}%` },
  ];

  const sidePanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader title="Summary" panelId="portfolio-summary">
        <div className="flex-1 overflow-auto min-h-0 p-3 space-y-4">
          {/* Compact Metric Row */}
          <CompactMetricRow metrics={portfolioMetrics} className="flex-wrap h-auto min-h-0 max-h-none" />

          {/* Account Overview */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Account</div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Equity</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{formatCurrency(totalPortfolioValue)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Cash</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{accountInfo ? formatCurrency(accountInfo.buying_power) : '---'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Invested</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{formatCurrency(totalPositionValue)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Unrealized P&L</span>
                <span className={cn('text-xs font-mono font-semibold', totalPnL >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {formatCurrency(totalPnL)} ({formatPercentage(totalPnLPercent)})
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Positions</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{positions.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Win Rate (Open)</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{winRate.toFixed(1)}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Win Rate (Closed)</span>
                <span className="text-xs font-mono font-semibold text-gray-200">{closedWinRate.toFixed(1)}%</span>
              </div>
            </div>
          </div>

          {/* Position Summary by Asset Class */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">By Asset Class</div>
            {assetClassSummary.length > 0 ? (
              <div className="space-y-1">
                {assetClassSummary.map((ac) => (
                  <div key={ac.assetClass} className="flex items-center justify-between py-1 border-b border-border/30 last:border-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-gray-200">{ac.assetClass}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">({ac.count})</span>
                    </div>
                    <span className={cn('text-xs font-mono font-semibold', ac.totalPnl > 0 ? 'text-accent-green' : ac.totalPnl < 0 ? 'text-accent-red' : 'text-gray-400')}>
                      {ac.totalPnl >= 0 ? '+' : ''}{formatCurrency(ac.totalPnl)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-3">No open positions</p>
            )}
          </div>

          {/* Sector Exposure Pie Chart */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Sector Exposure</div>
            {sectorExposure.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={sectorExposure}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    innerRadius={35}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {sectorExposure.map((_, index) => (
                      <Cell key={`sector-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Exposure']}
                    contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem', fontSize: '11px' }}
                    labelStyle={{ color: '#d1d5db' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-3">No data</p>
            )}
            {/* Legend */}
            {sectorExposure.length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                {sectorExposure.slice(0, 8).map((s, i) => (
                  <div key={s.name} className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="text-[10px] text-gray-400 truncate max-w-[80px]">{s.name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Allocation Breakdown Bar */}
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Allocation</div>
            {allocationData.length > 0 ? (
              <div className="space-y-1.5">
                {allocationData.map((item, i) => (
                  <div key={item.name}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[10px] text-gray-300 truncate max-w-[120px]">{item.name}</span>
                      <span className="text-[10px] font-mono text-gray-400">{item.pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${item.pct}%`, backgroundColor: COLORS[i % COLORS.length] }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-3">No positions</p>
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
        title="◆ Portfolio"
        description={tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading'}
        actions={headerActions}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <ResizablePanelLayout
            layoutId="portfolio-panels"
            direction="horizontal"
            panels={[
              {
                id: 'portfolio-main',
                defaultSize: 70,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'portfolio-side',
                defaultSize: 30,
                minSize: 250,
                content: sidePanel,
              },
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
        <div className="space-y-2 text-sm">
          <div>Symbol: {confirmClosePosition?.symbol}</div>
          <div>Invested: {formatCurrency((confirmClosePosition as any)?.invested_amount || (confirmClosePosition?.quantity || 0) * (confirmClosePosition?.entry_price || 0))}</div>
          <div>P&L: {formatCurrency(confirmClosePosition?.unrealized_pnl || 0)}</div>
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
        <div className="space-y-2 text-sm max-h-48 overflow-y-auto">
          {positions.filter(p => selectedPositions.has(p.id)).map(p => (
            <div key={p.id} className="flex justify-between font-mono">
              <span>{p.symbol}</span>
              <span className={cn(p.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(p.unrealized_pnl)}</span>
            </div>
          ))}
          <div className="pt-2 border-t border-border flex justify-between font-semibold">
            <span>Total P&L Impact</span>
            <span className={cn(positions.filter(p => selectedPositions.has(p.id)).reduce((sum, p) => sum + p.unrealized_pnl, 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
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
        <div className="text-sm text-muted-foreground">
          <div className="flex justify-between font-mono"><span>Total Positions</span><span>{positions.length}</span></div>
          <div className="flex justify-between font-mono mt-1">
            <span>Total Unrealized P&L</span>
            <span className={cn(totalPnL >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(totalPnL)}</span>
          </div>
        </div>
      </ConfirmDialog>

      {/* Modify Position Modal */}
      {modifyingPosition && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-card border border-border rounded-lg p-6 max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground font-mono">
                Modify {modifyingPosition.type === 'sl' ? 'Stop Loss' : 'Take Profit'}
              </h3>
              <Button variant="ghost" size="sm" onClick={() => { setModifyingPosition(null); setModifyPrice(''); }} className="h-8 w-8 p-0">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="mb-4">
              <label className="block text-sm text-muted-foreground mb-2">
                {modifyingPosition.type === 'sl' ? 'Stop Loss Price' : 'Take Profit Price'}
              </label>
              <Input type="number" step="0.01" value={modifyPrice} onChange={(e) => setModifyPrice(e.target.value)} placeholder="Enter price" autoFocus />
            </div>
            <div className="flex gap-3">
              <Button onClick={handleModifySubmit} disabled={!modifyPrice} className="flex-1">Confirm</Button>
              <Button variant="outline" onClick={() => { setModifyingPosition(null); setModifyPrice(''); }} className="flex-1">Cancel</Button>
            </div>
          </motion.div>
        </div>
      )}
    </DashboardLayout>
  );
};
