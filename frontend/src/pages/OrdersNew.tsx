import React, { type FC, useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { 
  Activity, TrendingUp, Clock, AlertCircle, Search,
  RefreshCw, Download, MoreVertical, X, Calendar
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '../lib/utils';
import { classifyError } from '../lib/errors';
import type { Order, OrderStatus, Position, ExecutionQualityData } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { format, subDays, startOfDay, endOfDay, formatDistanceToNow } from 'date-fns';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import { usePolling } from '../hooks/usePolling';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';

interface OrdersNewProps {
  onLogout: () => void;
}

// Extended order type with execution metrics
interface OrderWithMetrics extends Order {
  slippage?: number;
  fill_time_seconds?: number;
  rejection_reason?: string;
}

// Market hours helper — US stock market (NYSE/NASDAQ)
const getMarketStatus = (): { isOpen: boolean; nextOpen: Date | null; label: string } => {
  const now = new Date();
  const utcHour = now.getUTCHours();
  const utcMinute = now.getUTCMinutes();
  const utcDay = now.getUTCDay(); // 0=Sun, 6=Sat

  // US market hours: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC (EST) or 13:30 - 20:00 UTC (EDT)
  // Using approximate EDT hours
  const marketOpenUTC = 13 * 60 + 30; // 13:30 UTC
  const marketCloseUTC = 20 * 60; // 20:00 UTC
  const currentMinutes = utcHour * 60 + utcMinute;

  const isWeekday = utcDay >= 1 && utcDay <= 5;
  const isDuringHours = currentMinutes >= marketOpenUTC && currentMinutes < marketCloseUTC;
  const isOpen = isWeekday && isDuringHours;

  // Calculate next market open
  let nextOpen: Date | null = null;
  if (!isOpen) {
    const next = new Date(now);
    if (isWeekday && currentMinutes < marketOpenUTC) {
      // Today before open
      next.setUTCHours(13, 30, 0, 0);
    } else {
      // After close or weekend — find next weekday
      let daysToAdd = 1;
      if (utcDay === 5) daysToAdd = 3; // Friday → Monday
      else if (utcDay === 6) daysToAdd = 2; // Saturday → Monday
      else if (utcDay === 0) daysToAdd = 1; // Sunday → Monday
      next.setDate(next.getDate() + daysToAdd);
      next.setUTCHours(13, 30, 0, 0);
    }
    nextOpen = next;
  }

  const label = isOpen ? 'Market Open' : 'Market Closed';
  return { isOpen, nextOpen, label };
};

export const OrdersNew: FC<OrdersNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  
  // State
  const [orders, setOrders] = useState<OrderWithMetrics[]>([]);
  const [pendingClosures, setPendingClosures] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [executionQuality, setExecutionQuality] = useState<ExecutionQualityData | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Cancel confirmation dialog state
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<{ id: string; symbol: string; side: string; quantity: number } | null>(null);

  // Manual order form state
  const [orderFormOpen, setOrderFormOpen] = useState(false);
  const [orderFormStep, setOrderFormStep] = useState<'fill' | 'review'>('fill');
  const [orderForm, setOrderForm] = useState({
    symbol: '',
    side: 'BUY' as 'BUY' | 'SELL',
    orderType: 'MARKET' as 'MARKET' | 'LIMIT',
    quantity: '',
    price: '',
  });
  const [orderFormErrors, setOrderFormErrors] = useState<Record<string, string>>({});
  const [orderSubmitting, setOrderSubmitting] = useState(false);
  
  // Filter states for All Orders tab
  const [orderSearch, setOrderSearch] = useState('');
  const [orderStatusFilter, setOrderStatusFilter] = useState<string>('all');
  const [orderSideFilter, setOrderSideFilter] = useState<string>('all');
  const [orderSourceFilter, setOrderSourceFilter] = useState<string>('all');
  const [orderStrategyFilter, setOrderStrategyFilter] = useState<string>('all');
  
  // Bulk selection state
  const [selectedOrders, setSelectedOrders] = useState<Set<string>>(new Set());
  const [selectedClosures, setSelectedClosures] = useState<Set<string>>(new Set());
  
  // Date range filter
  const [dateRange, setDateRange] = useState<{ from: Date | null; to: Date | null }>({
    from: null,
    to: null,
  });
  const [showDatePicker, setShowDatePicker] = useState(false);
  
  // Analytics period
  const [analyticsPeriod, setAnalyticsPeriod] = useState<'1D' | '1W' | '1M'>('1W');

  // Fetch core order data (fast - just DB queries)
  const fetchData = useCallback(async () => {
    if (!tradingMode) return;
    
    try {
      setRefreshing(true);
      setError(null);
      
      // Fetch orders and pending closures in parallel (skip execution quality for speed)
      const [ordersData, pendingClosuresData] = await Promise.all([
        apiClient.getOrders(tradingMode),
        apiClient.getPendingClosures(tradingMode).catch(err => {
          console.warn('Failed to fetch pending closures:', err);
          return [];
        }),
      ]);
      
      // Sort by created_at descending (most recent first)
      const sortedOrders = ordersData.sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      
      // Map as OrderWithMetrics (execution metrics populated later if analytics tab is viewed)
      const ordersWithMetrics: OrderWithMetrics[] = sortedOrders.map(order => ({
        ...order,
        slippage: undefined,
        fill_time_seconds: undefined,
        rejection_reason: undefined,
      }));
      
      setOrders(ordersWithMetrics);
      setPendingClosures(pendingClosuresData);
      setLastUpdated(new Date());
      setLoading(false);
    } catch (error) {
      const classified = classifyError(error, 'orders');
      console.error('Failed to fetch orders data:', error);
      setError(classified.message);
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  }, [tradingMode]);

  // Fetch execution quality data (heavier - only when analytics tab is viewed)
  const fetchExecutionQuality = async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getExecutionQuality(tradingMode, analyticsPeriod);
      setExecutionQuality(data);
    } catch (err) {
      console.warn('Failed to fetch execution quality:', err);
    }
  };

  // usePolling replaces manual useEffect + setInterval
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchData,
    intervalMs: 15000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // Sync orders with eToro
  const handleSyncOrders = async () => {
    if (!tradingMode) return;
    
    try {
      setSyncing(true);
      const result = await apiClient.syncOrders(tradingMode);
      toast.success(result.message || 'Orders synced with eToro');
      if (result.filled > 0 || result.cancelled > 0) {
        toast.info(`Updated: ${result.filled} executed, ${result.cancelled} cancelled`);
      }
      await fetchData(); // Refresh data after sync
    } catch (error) {
      console.error('Failed to sync orders:', error);
      toast.error('Failed to sync orders with eToro');
    } finally {
      setSyncing(false);
    }
  };

  // WebSocket subscriptions
  useEffect(() => {
    const unsubscribeOrder = wsManager.onOrderUpdate((order: Order) => {
      setOrders((prev) => {
        const index = prev.findIndex(o => o.id === order.id);
        // Use order data as-is from WebSocket (backend should provide execution metrics)
        const orderWithMetrics: OrderWithMetrics = {
          ...order,
          // Only add execution metrics if not already present from backend
          slippage: (order as OrderWithMetrics).slippage ?? undefined,
          fill_time_seconds: (order as OrderWithMetrics).fill_time_seconds ?? undefined,
          rejection_reason: (order as OrderWithMetrics).rejection_reason ?? undefined,
        };
        
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = orderWithMetrics;
          return updated;
        }
        return [orderWithMetrics, ...prev];
      });
      toast.info(`Order ${order.status.toLowerCase()}: ${order.symbol}`);
    });

    return () => {
      unsubscribeOrder();
    };
  }, [tradingMode]);

  // Calculate metrics
  const totalOrders = orders.length;
  const pendingOrders = orders.filter(o => o.status === 'PENDING' || (o.status as string) === 'SUBMITTED').length;
  const filledOrders = orders.filter(o => o.status === 'FILLED').length;
  const cancelledOrders = orders.filter(o => o.status === 'CANCELLED').length;
  const rejectedOrders = orders.filter(o => o.status === 'REJECTED').length;
  
  // Count filled orders with metrics for display
  const filledOrdersWithMetrics = orders.filter(o => o.status === 'FILLED' && o.slippage !== undefined);
  
  // Execution quality metrics - use backend data if available, otherwise calculate from orders
  const avgSlippage = (executionQuality as any)?.avg_slippage_bps ?? (() => {
    return filledOrdersWithMetrics.length > 0
      ? filledOrdersWithMetrics.reduce((sum, o) => sum + (o.slippage || 0), 0) / filledOrdersWithMetrics.length
      : 0;
  })();
  
  const fillRate = executionQuality?.fill_rate ?? (totalOrders > 0 ? (filledOrders / totalOrders) * 100 : 0);
  
  const avgFillTime = (executionQuality as any)?.avg_fill_time_seconds ?? (() => {
    return filledOrdersWithMetrics.length > 0
      ? filledOrdersWithMetrics.reduce((sum, o) => sum + (o.fill_time_seconds || 0), 0) / filledOrdersWithMetrics.length
      : 0;
  })();

  // Get unique strategies for filters
  const uniqueStrategies = Array.from(new Set(
    orders
      .map(o => o.strategy_id)
      .filter(Boolean)
  ));

  // Queued orders (PENDING or SUBMITTED status) for the Order Queue tab
  const queuedOrders = orders.filter(o => o.status === 'PENDING' || (o.status as string) === 'SUBMITTED');
  const marketStatus = getMarketStatus();

  // Cancel all queued orders
  const handleCancelAllQueued = async () => {
    if (queuedOrders.length === 0 || !tradingMode) return;
    
    if (!confirm(`Cancel all ${queuedOrders.length} queued orders? This action cannot be undone.`)) {
      return;
    }
    
    let successCount = 0;
    let failCount = 0;
    
    for (const order of queuedOrders) {
      try {
        await apiClient.cancelOrder(order.id, tradingMode);
        successCount++;
        setOrders(prev => prev.map(o => o.id === order.id ? { ...o, status: 'CANCELLED' as OrderStatus } : o));
      } catch (error) {
        console.error(`Failed to cancel order ${order.id}:`, error);
        failCount++;
      }
    }
    
    if (successCount > 0) toast.success(`Cancelled ${successCount} queued orders`);
    if (failCount > 0) toast.error(`Failed to cancel ${failCount} orders`);
  };

  // Filter orders
  const filteredOrders = orders.filter(order => {
    const matchesSearch = order.symbol.toLowerCase().includes(orderSearch.toLowerCase());
    const matchesStatus = orderStatusFilter === 'all' || order.status === orderStatusFilter;
    const matchesSide = orderSideFilter === 'all' || order.side === orderSideFilter;
    const matchesSource = orderSourceFilter === 'all' || 
      (orderSourceFilter === 'autonomous' && order.strategy_id && order.strategy_id !== 'manual_order') ||
      (orderSourceFilter === 'manual' && (!order.strategy_id || order.strategy_id === 'manual_order'));
    const matchesStrategy = orderStrategyFilter === 'all' || order.strategy_id === orderStrategyFilter;
    
    let matchesDate = true;
    if (dateRange.from || dateRange.to) {
      const orderDate = new Date(order.created_at);
      if (dateRange.from && orderDate < startOfDay(dateRange.from)) matchesDate = false;
      if (dateRange.to && orderDate > endOfDay(dateRange.to)) matchesDate = false;
    }
    
    return matchesSearch && matchesStatus && matchesSide && matchesSource && matchesStrategy && matchesDate;
  });

  // Order flow timeline (last 24 hours)
  const last24Hours = orders.filter(o => {
    const orderTime = new Date(o.created_at).getTime();
    const now = Date.now();
    return now - orderTime <= 24 * 60 * 60 * 1000;
  });
  
  const orderFlowData = Array.from({ length: 24 }, (_, i) => {
    const hour = 23 - i;
    const hourStart = Date.now() - (hour + 1) * 60 * 60 * 1000;
    const hourEnd = Date.now() - hour * 60 * 60 * 1000;
    const hourOrders = last24Hours.filter(o => {
      const orderTime = new Date(o.created_at).getTime();
      return orderTime >= hourStart && orderTime < hourEnd;
    });
    return {
      hour: `${hour}h ago`,
      orders: hourOrders.length,
    };
  }).reverse();

  // Filter orders by analytics period
  const getPeriodDays = () => {
    switch (analyticsPeriod) {
      case '1D': return 1;
      case '1W': return 7;
      case '1M': return 30;
      default: return 7;
    }
  };
  
  const periodDays = getPeriodDays();
  const periodStart = startOfDay(subDays(new Date(), periodDays)).getTime();
  const analyticsOrders = orders.filter(o => {
    const orderTime = new Date(o.created_at).getTime();
    return orderTime >= periodStart;
  });

  // Slippage by strategy data - use backend data if available
  const slippageByStrategy = (executionQuality as any)?.slippage_by_strategy 
    ? Object.entries((executionQuality as any).slippage_by_strategy).map(([strategy, slippage]) => ({
        strategy: strategy.substring(0, 8) || 'Unknown',
        slippage: slippage || 0,
      })).filter((d) => d.slippage !== 0)
    : uniqueStrategies.map(strategyId => {
    const strategyOrders = analyticsOrders.filter(o => o.strategy_id === strategyId && o.slippage !== undefined);
    const avgSlip = strategyOrders.length > 0
      ? strategyOrders.reduce((sum, o) => sum + (o.slippage || 0), 0) / strategyOrders.length
      : 0;
    return {
      strategy: strategyId?.substring(0, 8) || 'Unknown',
      slippage: avgSlip,
    };
  }).filter(d => d.slippage !== 0);

  // Fill rate trend (based on selected period)
  const getTrendDays = () => {
    switch (analyticsPeriod) {
      case '1D': return 24; // 24 hours
      case '1W': return 7;  // 7 days
      case '1M': return 30; // 30 days
      default: return 7;
    }
  };
  
  const trendDays = getTrendDays();
  const fillRateTrend = Array.from({ length: trendDays }, (_, i) => {
    const day = trendDays - 1 - i;
    const dayStart = analyticsPeriod === '1D' 
      ? Date.now() - (day + 1) * 60 * 60 * 1000  // Hours for 1D
      : startOfDay(subDays(new Date(), day)).getTime();
    const dayEnd = analyticsPeriod === '1D'
      ? Date.now() - day * 60 * 60 * 1000
      : endOfDay(subDays(new Date(), day)).getTime();
    const dayOrders = orders.filter(o => {
      const orderTime = new Date(o.created_at).getTime();
      return orderTime >= dayStart && orderTime <= dayEnd;
    });
    const dayFilled = dayOrders.filter(o => o.status === 'FILLED').length;
    const rate = dayOrders.length > 0 ? (dayFilled / dayOrders.length) * 100 : 0;
    return {
      date: analyticsPeriod === '1D' 
        ? `${day}h ago`
        : format(subDays(new Date(), day), 'MMM dd'),
      fillRate: rate,
    };
  }).reverse();

  // Rejection reasons breakdown - use backend data if available
  const rejectionData = (executionQuality as any)?.rejection_reasons
    ? Object.entries((executionQuality as any).rejection_reasons).map(([reason, count]) => ({
        name: reason || 'Unknown',
        value: count || 0,
      }))
    : (() => {
    const rejectionReasons = analyticsOrders
      .filter(o => o.status === 'REJECTED' && o.rejection_reason)
      .reduce((acc, o) => {
        const reason = o.rejection_reason || 'Unknown';
        acc[reason] = (acc[reason] || 0) + 1;
        return acc;
      }, {} as Record<string, number>);
    
    return Object.entries(rejectionReasons).map(([name, value]) => ({
      name,
      value,
    }));
  })();

  const COLORS = ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6', '#ec4899'];

  // Handle order actions
  const handleCancelOrder = async (orderId: string) => {
    if (!tradingMode) return;
    
    try {
      await apiClient.cancelOrder(orderId, tradingMode);
      toast.success('Order cancelled successfully');
      setOrders(prev => prev.map(o => o.id === orderId ? { ...o, status: 'CANCELLED' as OrderStatus } : o));
    } catch (error) {
      console.error('Failed to cancel order:', error);
      toast.error('Failed to cancel order');
    }
  };

  const handleDeleteOrder = async (orderId: string) => {
    if (!tradingMode) return;
    
    if (!confirm('Permanently delete this order from history? This action cannot be undone.')) {
      return;
    }
    
    try {
      await apiClient.deleteOrderPermanent(orderId, tradingMode);
      toast.success('Order deleted successfully');
      setOrders(prev => prev.filter(o => o.id !== orderId));
    } catch (error) {
      console.error('Failed to delete order:', error);
      toast.error('Failed to delete order');
    }
  };

  const handleCloseFilledOrderPosition = async (orderId: string) => {
    if (!tradingMode) return;
    
    if (!confirm('Close the position created by this order on eToro? This will execute a market order.')) {
      return;
    }
    
    try {
      await apiClient.closeFilledOrderPosition(orderId, tradingMode);
      toast.success('Position closed successfully on eToro');
      await fetchData(); // Refresh to get updated positions
    } catch (error) {
      console.error('Failed to close position:', error);
      toast.error('Failed to close position');
    }
  };

  // Bulk cancel orders
  const handleBulkCancelOrders = async () => {
    if (selectedOrders.size === 0) return;
    
    // Filter to only cancellable orders (PENDING or SUBMITTED status)
    const cancellableOrders = Array.from(selectedOrders).filter(orderId => {
      const order = orders.find(o => o.id === orderId);
      return order && (order.status === 'PENDING' || (order.status as string) === 'SUBMITTED');
    });
    
    if (cancellableOrders.length === 0) {
      toast.error('No cancellable orders selected. Only Pending orders can be cancelled.');
      return;
    }
    
    if (!confirm(`Cancel ${cancellableOrders.length} selected Pending orders? This action cannot be undone.`)) {
      return;
    }
    
    let successCount = 0;
    let failCount = 0;
    
    for (const orderId of cancellableOrders) {
      try {
        await apiClient.cancelOrder(orderId, tradingMode!);
        successCount++;
        setOrders(prev => prev.map(o => o.id === orderId ? { ...o, status: 'CANCELLED' as OrderStatus } : o));
      } catch (error) {
        console.error(`Failed to cancel order ${orderId}:`, error);
        failCount++;
      }
    }
    
    setSelectedOrders(new Set());
    
    if (successCount > 0) {
      toast.success(`Cancelled ${successCount} orders successfully`);
    }
    if (failCount > 0) {
      toast.error(`Failed to cancel ${failCount} orders`);
    }
  };

  // Smart bulk action - handles different order statuses
  const handleSmartBulkAction = async () => {
    if (selectedOrders.size === 0) return;
    
    const selectedOrdersList = Array.from(selectedOrders).map(id => orders.find(o => o.id === id)!).filter(Boolean);
    
    const pendingOrders = selectedOrdersList.filter(o => o.status === 'PENDING' || (o.status as string) === 'SUBMITTED');
    const filledOrders = selectedOrdersList.filter(o => o.status === 'FILLED');
    const cancelledOrders = selectedOrdersList.filter(o => o.status === 'CANCELLED');
    const failedOrders = selectedOrdersList.filter(o => (o.status as string) === 'FAILED');
    
    const actions = [];
    if (pendingOrders.length > 0) actions.push(`Cancel ${pendingOrders.length} Pending order(s)`);
    if (filledOrders.length > 0) actions.push(`Close ${filledOrders.length} position(s) on eToro and delete`);
    if (cancelledOrders.length > 0) actions.push(`Delete ${cancelledOrders.length} Cancelled order(s)`);
    if (failedOrders.length > 0) actions.push(`Delete ${failedOrders.length} Failed order(s)`);
    
    if (actions.length === 0) {
      toast.error('No actionable orders selected.');
      return;
    }
    
    if (!confirm(`This will:\n• ${actions.join('\n• ')}\n\nContinue?`)) {
      return;
    }
    
    let cancelledCount = 0;
    let positionsClosedCount = 0;
    let deletedCount = 0;
    let failCount = 0;
    
    // Cancel PENDING orders
    for (const order of pendingOrders) {
      try {
        await apiClient.cancelOrder(order.id, tradingMode!);
        cancelledCount++;
        setOrders(prev => prev.map(o => o.id === order.id ? { ...o, status: 'CANCELLED' as OrderStatus } : o));
      } catch (error) {
        console.error(`Failed to cancel order ${order.id}:`, error);
        failCount++;
      }
    }
    
    // Close positions for FILLED orders
    for (const order of filledOrders) {
      try {
        await apiClient.closeFilledOrderPosition(order.id, tradingMode!);
        positionsClosedCount++;
      } catch (error) {
        console.error(`Failed to close position for order ${order.id}:`, error);
        // Continue anyway - we'll try to delete the order
      }
    }
    
    // Delete FILLED, CANCELLED, and FAILED orders
    const ordersToDelete = [...filledOrders, ...cancelledOrders, ...failedOrders];
    if (ordersToDelete.length > 0) {
      try {
        const result = await apiClient.bulkDeleteOrders(ordersToDelete.map(o => o.id), tradingMode!);
        deletedCount = result.success_count;
        failCount += result.fail_count;
        setOrders(prev => prev.filter(o => !result.deleted_order_ids.includes(o.id)));
      } catch (error) {
        console.error('Failed to bulk delete orders:', error);
        failCount += ordersToDelete.length;
      }
    }
    
    setSelectedOrders(new Set());
    
    // Refresh data to get updated positions
    await fetchData();
    
    const messages = [];
    if (cancelledCount > 0) messages.push(`Cancelled ${cancelledCount} order(s)`);
    if (positionsClosedCount > 0) messages.push(`Closed ${positionsClosedCount} position(s)`);
    if (deletedCount > 0) messages.push(`Deleted ${deletedCount} order(s)`);
    
    if (messages.length > 0) {
      toast.success(messages.join(', '));
    }
    if (failCount > 0) {
      toast.error(`Failed to process ${failCount} order(s)`);
    }
  };

  // Bulk delete orders
  const handleBulkDeleteOrders = async () => {
    if (selectedOrders.size === 0) return;
    
    // Filter to only deletable orders (CANCELLED, FAILED, or FILLED status)
    const deletableOrders = Array.from(selectedOrders).filter(orderId => {
      const order = orders.find(o => o.id === orderId);
      return order && (order.status === 'CANCELLED' || order.status === 'FILLED' || (order.status as string) === 'FAILED');
    });
    
    if (deletableOrders.length === 0) {
      toast.error('No deletable orders selected. Only CANCELLED, FAILED, or FILLED orders can be deleted.');
      return;
    }
    
    if (!confirm(`Permanently delete ${deletableOrders.length} selected orders? This action cannot be undone.`)) {
      return;
    }
    
    try {
      const result = await apiClient.bulkDeleteOrders(deletableOrders, tradingMode!);
      
      setSelectedOrders(new Set());
      setOrders(prev => prev.filter(o => !result.deleted_order_ids.includes(o.id)));
      
      if (result.success_count > 0) {
        toast.success(`Deleted ${result.success_count} orders successfully`);
      }
      if (result.fail_count > 0) {
        toast.error(`Failed to delete ${result.fail_count} orders`);
      }
    } catch (error) {
      console.error('Failed to bulk delete orders:', error);
      toast.error('Failed to delete orders');
    }
  };

  // Approve single position closure
  const handleApproveClosure = async (positionId: string) => {
    if (!tradingMode) return;
    
    try {
      await apiClient.approvePositionClosure(positionId, tradingMode);
      toast.success('Position closed successfully');
      setPendingClosures(prev => prev.filter(p => p.id !== positionId));
      await fetchData(); // Refresh data
    } catch (error) {
      console.error('Failed to close position:', error);
      toast.error('Failed to close position');
    }
  };

  // Bulk approve closures
  const handleBulkApproveClosures = async () => {
    if (selectedClosures.size === 0) return;
    
    if (!confirm(`Close ${selectedClosures.size} selected positions? This will execute market orders on eToro.`)) {
      return;
    }
    
    try {
      const result = await apiClient.approveBulkClosures(Array.from(selectedClosures), tradingMode!);
      
      setSelectedClosures(new Set());
      await fetchData(); // Refresh data
      
      if (result.success_count > 0) {
        toast.success(`Closed ${result.success_count} positions successfully`);
      }
      if (result.fail_count > 0) {
        toast.error(`Failed to close ${result.fail_count} positions`);
      }
    } catch (error) {
      console.error('Failed to bulk close positions:', error);
      toast.error('Failed to close positions');
    }
  };

  const handleViewDetails = (order: OrderWithMetrics) => {
    toast.info(`Order Details: ${order.symbol} ${order.side} ${order.quantity}`);
  };

  // Manual order form validation
  const validateOrderForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!orderForm.symbol.trim()) errors.symbol = 'Symbol is required';
    const qty = parseFloat(orderForm.quantity);
    if (!orderForm.quantity || isNaN(qty) || qty <= 0) errors.quantity = 'Quantity must be a positive number';
    if (orderForm.orderType === 'LIMIT') {
      const price = parseFloat(orderForm.price);
      if (!orderForm.price || isNaN(price) || price <= 0) errors.price = 'Price is required for LIMIT orders';
    }
    setOrderFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleOrderFormNext = () => {
    if (validateOrderForm()) {
      setOrderFormStep('review');
    }
  };

  const handleOrderFormSubmit = async () => {
    if (!tradingMode) return;
    setOrderSubmitting(true);
    try {
      await apiClient.placeOrder({
        strategy_id: 'manual_order',
        symbol: orderForm.symbol.toUpperCase().trim(),
        side: orderForm.side as any,
        order_type: orderForm.orderType as any,
        quantity: parseFloat(orderForm.quantity),
        price: orderForm.orderType === 'LIMIT' ? parseFloat(orderForm.price) : undefined,
        mode: tradingMode,
      });
      toast.success(`Order placed: ${orderForm.side} ${orderForm.quantity} ${orderForm.symbol.toUpperCase()}`);
      setOrderFormOpen(false);
      setOrderFormStep('fill');
      setOrderForm({ symbol: '', side: 'BUY', orderType: 'MARKET', quantity: '', price: '' });
      setOrderFormErrors({});
      await fetchData();
    } catch (err) {
      const classified = classifyError(err, 'order placement');
      toast.error(classified.message);
    } finally {
      setOrderSubmitting(false);
    }
  };

  const resetOrderForm = () => {
    setOrderFormStep('fill');
    setOrderForm({ symbol: '', side: 'BUY', orderType: 'MARKET', quantity: '', price: '' });
    setOrderFormErrors({});
  };

  // Export to CSV
  const exportToCSV = () => {
    if (filteredOrders.length === 0) {
      toast.error('No data to export');
      return;
    }

    const csvContent = [
      'Symbol,Side,Action,Type,Quantity,Price,Status,Strategy,Created At,Slippage,Fill Time',
      ...filteredOrders.map(o => 
        `${o.symbol},${o.side},${(o as any).order_action || 'entry'},${o.type},${o.quantity},${o.price || 'Market'},${o.status},${o.strategy_id || 'Manual'},${o.created_at},${o.slippage?.toFixed(4) || 'N/A'},${o.fill_time_seconds?.toFixed(2) || 'N/A'}`
      )
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `orders_${format(new Date(), 'yyyy-MM-dd')}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('Orders exported successfully');
  };

  // Clear date range
  const clearDateRange = () => {
    setDateRange({ from: null, to: null });
    setShowDatePicker(false);
  };

  // Table columns for all orders
  const orderColumns: ColumnDef<OrderWithMetrics>[] = [
    {
      id: 'select',
      header: ({ table }) => {
        const ref = React.useRef<HTMLInputElement>(null);
        React.useEffect(() => {
          if (ref.current) {
            ref.current.indeterminate = table.getIsSomePageRowsSelected();
          }
        }, [table.getIsSomePageRowsSelected()]);
        
        return (
          <input
            ref={ref}
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={(e) => table.toggleAllPageRowsSelected(!!e.target.checked)}
            className="rounded border-gray-600 bg-dark-card text-accent-blue focus:ring-accent-blue focus:ring-offset-0"
          />
        );
      },
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={(e) => row.toggleSelected(!!e.target.checked)}
          onClick={(e) => e.stopPropagation()}
          className="rounded border-gray-600 bg-dark-card text-accent-blue focus:ring-accent-blue focus:ring-offset-0"
        />
      ),
      enableSorting: false,
      enableHiding: false,
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
          {row.original.side}
        </span>
      ),
    },
    {
      accessorKey: 'order_action',
      header: 'Action',
      cell: ({ row }) => {
        const action = (row.original as any).order_action || 'entry';
        const actionColors: Record<string, string> = {
          entry: 'bg-accent-green/20 text-accent-green',
          close: 'bg-amber-500/20 text-amber-400',
          retirement: 'bg-accent-red/20 text-accent-red',
        };
        const actionLabels: Record<string, string> = {
          entry: 'Entry',
          close: 'Close',
          retirement: 'Retire',
        };
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold whitespace-nowrap',
            actionColors[action] || actionColors.entry
          )}>
            {actionLabels[action] || action}
          </span>
        );
      },
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
      header: () => <div className="text-right">Amount</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency(row.original.quantity)}</span>
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
          SUBMITTED: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
          FILLED: 'bg-accent-green/20 text-accent-green border-accent-green/30',
          PARTIALLY_FILLED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
          CANCELLED: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
          REJECTED: 'bg-accent-red/20 text-accent-red border-accent-red/30',
        };
        // Map internal status to eToro-standard display labels
        const statusLabels: Record<string, string> = {
          PENDING: 'Pending',
          SUBMITTED: 'Pending',
          FILLED: 'Executed',
          PARTIALLY_FILLED: 'Partial',
          CANCELLED: 'Cancelled',
          REJECTED: 'Rejected',
          FAILED: 'Failed',
        };
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold border whitespace-nowrap',
            statusColors[row.original.status] || statusColors.PENDING
          )}>
            {statusLabels[row.original.status] || row.original.status}
          </span>
        );
      },
    },
    {
      accessorKey: 'strategy_id',
      header: 'Source',
      cell: ({ row }) => {
        const isAutonomous = row.original.strategy_id && row.original.strategy_id !== 'manual_order';
        return (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className={cn(
                  'px-2 py-0.5 rounded text-xs font-mono whitespace-nowrap cursor-help',
                  isAutonomous ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-500/20 text-gray-400'
                )}>
                  {isAutonomous ? 'Auto' : 'Manual'}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">
                  {isAutonomous 
                    ? `Strategy: ${row.original.strategy_id?.substring(0, 12)}...` 
                    : 'Manual order entry'}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    },
    {
      accessorKey: 'created_at',
      header: () => <div className="text-right">Time</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {formatTimestamp(row.original.created_at)}
          </span>
        </div>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Actions</div>,
      cell: ({ row }) => {
        const canCancel = row.original.status === 'PENDING' || (row.original.status as string) === 'SUBMITTED';
        const canDelete = row.original.status === 'CANCELLED' || row.original.status === 'FILLED';
        const canClosePosition = row.original.status === 'FILLED';
        return (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleViewDetails(row.original)}>
                  View Details
                </DropdownMenuItem>
                {canCancel ? (
                  <DropdownMenuItem
                    onClick={() => {
                      setCancelTarget({ id: row.original.id, symbol: row.original.symbol, side: row.original.side, quantity: row.original.quantity });
                      setCancelDialogOpen(true);
                    }}
                    className="text-accent-red"
                  >
                    Cancel Order
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem disabled className="text-gray-500">
                    Cancel Order (Not Available)
                  </DropdownMenuItem>
                )}
                {canClosePosition && (
                  <DropdownMenuItem
                    onClick={() => handleCloseFilledOrderPosition(row.original.id)}
                    className="text-accent-red"
                  >
                    Close Position
                  </DropdownMenuItem>
                )}
                {canDelete && (
                  <DropdownMenuItem
                    onClick={() => handleDeleteOrder(row.original.id)}
                    className="text-accent-red"
                  >
                    Delete Order
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
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

  if (error && orders.length === 0) {
    const classified = classifyError(new Error(error), 'orders');
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8">
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <AlertCircle className="h-8 w-8 text-accent-red" />
            <div className="text-gray-400 font-mono">{classified.title}</div>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchData}>Retry</Button>
          </div>
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
        <RefreshIndicator visible={pollingRefreshing && !loading} />
        {/* Header */}
        <div className="mb-6 lg:mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-2">
              ◆ Orders
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-gray-400 text-sm">
                Order execution monitoring and analytics
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastUpdated} />
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="default"
              size="sm"
              onClick={() => { resetOrderForm(); setOrderFormOpen(true); }}
              className="gap-2 bg-accent-green hover:bg-accent-green/80 text-black"
            >
              + New Order
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={exportToCSV}
              className="gap-2"
            >
              <Download className="h-4 w-4" />
              Export
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSyncOrders}
              disabled={syncing}
              className="gap-2"
              title="Sync order statuses with eToro"
            >
              <RefreshCw className={cn('h-4 w-4', syncing && 'animate-spin')} />
              {syncing ? 'Syncing...' : '🔄 Sync eToro'}
            </Button>
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
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="queue" className={queuedOrders.length > 0 ? 'text-amber-400' : ''}>
              Order Queue {queuedOrders.length > 0 && `(${queuedOrders.length})`}
            </TabsTrigger>
            <TabsTrigger value="all">
              All Orders ({filteredOrders.length})
            </TabsTrigger>
            <TabsTrigger value="pending-closures">
              Pending Closures ({pendingClosures.length})
            </TabsTrigger>
            <TabsTrigger value="analytics" onClick={fetchExecutionQuality}>
              Execution Analytics
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            {/* Order Summary Metrics */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="grid grid-cols-2 md:grid-cols-5 gap-4"
            >
              <MetricCard
                label="Total Orders"
                value={totalOrders}
                format="number"
                icon={Activity}
                tooltip="Total number of orders"
              />
              <MetricCard
                label="Pending"
                value={pendingOrders}
                format="number"
                icon={Clock}
                tooltip="Orders awaiting execution"
              />
              <MetricCard
                label="Executed"
                value={filledOrders}
                format="number"
                icon={TrendingUp}
                tooltip="Successfully executed orders"
              />
              <MetricCard
                label="Cancelled"
                value={cancelledOrders}
                format="number"
                icon={X}
                tooltip="Cancelled orders"
              />
              <MetricCard
                label="Rejected"
                value={rejectedOrders}
                format="number"
                icon={AlertCircle}
                tooltip="Rejected orders"
              />
            </motion.div>

            {/* Execution Quality Cards */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
              className="grid grid-cols-1 md:grid-cols-3 gap-4"
            >
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Avg Slippage</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={cn(
                    'text-2xl font-bold font-mono',
                    avgSlippage >= 0 ? 'text-accent-red' : 'text-accent-green'
                  )}>
                    {formatPercentage(avgSlippage)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Based on {filledOrdersWithMetrics.length} filled orders
                  </p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Fill Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold font-mono text-accent-green">
                    {formatPercentage(fillRate)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {filledOrders} of {totalOrders} orders filled
                  </p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Avg Fill Time</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold font-mono text-blue-400">
                    {avgFillTime.toFixed(1)}s
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Average execution time
                  </p>
                </CardContent>
              </Card>
            </motion.div>

            {/* Order Flow Timeline */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Order Flow Timeline</CardTitle>
                  <CardDescription>
                    Order activity over the last 24 hours
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {orderFlowData.some(d => d.orders > 0) ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={orderFlowData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis 
                          dataKey="hour" 
                          stroke="#9ca3af"
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: '#1f2937',
                            border: '1px solid #374151',
                            borderRadius: '0.5rem',
                          }}
                        />
                        <Bar dataKey="orders" fill="#3b82f6" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      No orders in the last 24 hours
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          {/* Order Queue Tab */}
          <TabsContent value="queue" className="space-y-4">
            {/* Market Status Banner */}
            <Card className={cn(
              'border',
              marketStatus.isOpen ? 'border-accent-green/30 bg-accent-green/5' : 'border-amber-500/30 bg-amber-500/5'
            )}>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'h-3 w-3 rounded-full animate-pulse',
                      marketStatus.isOpen ? 'bg-accent-green' : 'bg-amber-500'
                    )} />
                    <div>
                      <p className={cn(
                        'text-sm font-semibold',
                        marketStatus.isOpen ? 'text-accent-green' : 'text-amber-400'
                      )}>
                        {marketStatus.label}
                      </p>
                      {!marketStatus.isOpen && marketStatus.nextOpen && (
                        <p className="text-xs text-gray-400">
                          Next open: {format(marketStatus.nextOpen, 'EEE, MMM d \'at\' h:mm a')} UTC
                          {' '}({formatDistanceToNow(marketStatus.nextOpen, { addSuffix: true })})
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="text-sm font-mono text-gray-400">
                    {queuedOrders.length} order{queuedOrders.length !== 1 ? 's' : ''} queued
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className={queuedOrders.length > 0 ? 'border-amber-500/30' : ''}>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Clock className={cn('h-5 w-5', queuedOrders.length > 0 ? 'text-amber-500' : 'text-muted-foreground')} />
                      Order Queue
                    </CardTitle>
                    <CardDescription>
                      {queuedOrders.length > 0
                        ? `${queuedOrders.length} pending order${queuedOrders.length !== 1 ? 's' : ''} waiting for execution`
                        : 'No orders currently queued'}
                    </CardDescription>
                  </div>
                  {queuedOrders.length > 0 && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleCancelAllQueued}
                      className="gap-2"
                    >
                      <X className="h-4 w-4" />
                      Cancel All ({queuedOrders.length})
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {queuedOrders.length === 0 ? (
                  <div className="text-center py-12">
                    <Clock className="h-12 w-12 text-gray-600 mx-auto mb-3" />
                    <div className="text-gray-400 font-mono mb-2">No queued orders</div>
                    <div className="text-sm text-gray-500">
                      Orders placed when the market is closed will appear here
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {queuedOrders.map((order) => {
                      const age = formatDistanceToNow(new Date(order.created_at), { addSuffix: true });
                      const isWaitingForMarket = !marketStatus.isOpen;
                      return (
                        <motion.div
                          key={order.id}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center justify-between p-4 rounded-lg border border-amber-500/20 bg-amber-500/5"
                        >
                          <div className="flex items-center gap-4 min-w-0">
                            <div className="flex flex-col">
                              <span className="font-mono font-semibold text-sm text-gray-200">
                                {order.symbol}
                              </span>
                              <span className={cn(
                                'text-xs font-mono font-semibold',
                                order.side === 'BUY' ? 'text-accent-green' : 'text-accent-red'
                              )}>
                                {order.side}
                              </span>
                            </div>
                            <div className="flex flex-col">
                              <span className="text-sm text-gray-300 font-mono">
                                {formatCurrency(order.quantity)}
                              </span>
                              <span className="text-xs text-gray-500">
                                {order.price ? `@ ${formatCurrency(order.price)}` : 'Market'}
                              </span>
                            </div>
                            <div className="flex flex-col">
                              <span className="text-xs text-gray-400">
                                Queued {age}
                              </span>
                              <span className={cn(
                                'text-xs px-1.5 py-0.5 rounded mt-0.5 w-fit',
                                isWaitingForMarket
                                  ? 'bg-amber-500/20 text-amber-400'
                                  : 'bg-blue-500/20 text-blue-400'
                              )}>
                                {isWaitingForMarket ? 'Waiting for market open' : 'Processing'}
                              </span>
                            </div>
                            {!marketStatus.isOpen && marketStatus.nextOpen && (
                              <div className="hidden md:flex flex-col">
                                <span className="text-xs text-gray-500">Est. execution</span>
                                <span className="text-xs text-amber-400 font-mono">
                                  {formatDistanceToNow(marketStatus.nextOpen, { addSuffix: true })}
                                </span>
                              </div>
                            )}
                            {order.strategy_id && order.strategy_id !== 'manual_order' && (
                              <span className="hidden lg:inline text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 font-mono">
                                {order.strategy_id.substring(0, 8)}...
                              </span>
                            )}
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleCancelOrder(order.id)}
                            className="border-accent-red/30 text-accent-red hover:bg-accent-red/10 gap-1 shrink-0"
                          >
                            <X className="h-3.5 w-3.5" />
                            Cancel
                          </Button>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* All Orders Tab */}
          <TabsContent value="all" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>All Orders</CardTitle>
                    <CardDescription>
                      Complete order history with advanced filtering • {filteredOrders.length} of {orders.length} orders
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
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
                        <SelectItem value="SUBMITTED">Pending (Submitted)</SelectItem>
                        <SelectItem value="FILLED">Executed</SelectItem>
                        <SelectItem value="PARTIALLY_FILLED">Partial</SelectItem>
                        <SelectItem value="CANCELLED">Cancelled</SelectItem>
                        <SelectItem value="FAILED">Failed</SelectItem>
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
                    
                    <Select value={orderSourceFilter} onValueChange={setOrderSourceFilter}>
                      <SelectTrigger className="w-full sm:w-[140px]">
                        <SelectValue placeholder="Source" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Sources</SelectItem>
                        <SelectItem value="autonomous">Autonomous</SelectItem>
                        <SelectItem value="manual">Manual</SelectItem>
                      </SelectContent>
                    </Select>
                    
                    {uniqueStrategies.length > 0 && (
                      <Select value={orderStrategyFilter} onValueChange={setOrderStrategyFilter}>
                        <SelectTrigger className="w-full sm:w-[140px]">
                          <SelectValue placeholder="Strategy" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Strategies</SelectItem>
                          {uniqueStrategies.map(strategy => (
                            <SelectItem key={strategy} value={strategy!}>
                              {strategy?.substring(0, 8)}...
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    
                    <Popover open={showDatePicker} onOpenChange={setShowDatePicker}>
                      <PopoverTrigger asChild>
                        <Button variant="outline" size="sm" className="gap-2">
                          <Calendar className="h-4 w-4" />
                          {dateRange.from || dateRange.to ? 'Date Range' : 'All Dates'}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-4" align="end">
                        <div className="space-y-4">
                          <div>
                            <label className="text-xs text-muted-foreground mb-1 block">From</label>
                            <Input
                              type="date"
                              value={dateRange.from ? format(dateRange.from, 'yyyy-MM-dd') : ''}
                              onChange={(e) => setDateRange(prev => ({ ...prev, from: e.target.value ? new Date(e.target.value) : null }))}
                            />
                          </div>
                          <div>
                            <label className="text-xs text-muted-foreground mb-1 block">To</label>
                            <Input
                              type="date"
                              value={dateRange.to ? format(dateRange.to, 'yyyy-MM-dd') : ''}
                              onChange={(e) => setDateRange(prev => ({ ...prev, to: e.target.value ? new Date(e.target.value) : null }))}
                            />
                          </div>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={clearDateRange} className="flex-1">
                              Clear
                            </Button>
                            <Button size="sm" onClick={() => setShowDatePicker(false)} className="flex-1">
                              Apply
                            </Button>
                          </div>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Bulk Actions Toolbar */}
                {selectedOrders.size > 0 && (
                  <div className="flex items-center gap-3 mb-4 p-3 bg-dark-lighter rounded-lg border border-dark-border">
                    <span className="text-sm text-gray-400 font-mono">
                      {selectedOrders.size} selected
                    </span>
                    <Button
                      onClick={handleSmartBulkAction}
                      variant="default"
                      size="sm"
                      className="gap-2"
                    >
                      <X className="h-4 w-4" />
                      Clean Up Selected
                    </Button>
                    <Button
                      onClick={handleBulkCancelOrders}
                      variant="destructive"
                      size="sm"
                      className="gap-2"
                    >
                      <X className="h-4 w-4" />
                      Cancel Selected
                    </Button>
                    <Button
                      onClick={handleBulkDeleteOrders}
                      variant="destructive"
                      size="sm"
                      className="gap-2"
                    >
                      <X className="h-4 w-4" />
                      Delete Selected
                    </Button>
                    <Button
                      onClick={() => setSelectedOrders(new Set())}
                      variant="ghost"
                      size="sm"
                    >
                      Clear Selection
                    </Button>
                  </div>
                )}
                
                {filteredOrders.length > 0 ? (
                  <div className="max-h-[600px] overflow-y-auto">
                    <DataTable
                      columns={orderColumns}
                      data={filteredOrders}
                      pageSize={20}
                      showPagination={true}
                      getRowId={(row) => row.id}
                      rowSelection={Object.fromEntries(
                        Array.from(selectedOrders).map(id => [id, true])
                      )}
                      onRowSelectionChange={(updaterOrValue) => {
                        const currentSelection = Object.fromEntries(
                          Array.from(selectedOrders).map(id => [id, true])
                        );
                        const newSelection = typeof updaterOrValue === 'function' 
                          ? updaterOrValue(currentSelection)
                          : updaterOrValue;
                        setSelectedOrders(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
                      }}
                    />
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    {orderSearch || orderStatusFilter !== 'all' || orderSideFilter !== 'all' || orderSourceFilter !== 'all' || orderStrategyFilter !== 'all' || dateRange.from || dateRange.to
                      ? 'No orders match your filters' 
                      : 'No orders found'}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Pending Closures Tab */}
          <TabsContent value="pending-closures" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Pending Position Closures</CardTitle>
                    <CardDescription>
                      Positions from retired strategies awaiting closure approval • {pendingClosures.length} positions
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {pendingClosures.length === 0 ? (
                  <div className="text-center py-12">
                    <div className="text-gray-400 font-mono mb-2">No pending closures</div>
                    <div className="text-sm text-gray-500">
                      Positions from retired strategies will appear here for approval
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Bulk Actions */}
                    {selectedClosures.size > 0 && (
                      <div className="flex items-center gap-4 p-4 bg-dark-card border border-gray-700 rounded-lg">
                        <span className="text-sm text-gray-300 font-mono">
                          {selectedClosures.size} selected
                        </span>
                        <Button
                          onClick={handleBulkApproveClosures}
                          variant="default"
                          size="sm"
                          className="gap-2"
                        >
                          <X className="h-4 w-4" />
                          Close Selected
                        </Button>
                      </div>
                    )}

                    {/* Pending Closures Table */}
                    <DataTable
                      columns={[
                        {
                          id: 'select',
                          header: () => {
                            const allSelected = pendingClosures.length > 0 && 
                              pendingClosures.every(p => selectedClosures.has(p.id));
                            
                            return (
                              <input
                                type="checkbox"
                                checked={allSelected}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setSelectedClosures(new Set(pendingClosures.map(p => p.id)));
                                  } else {
                                    setSelectedClosures(new Set());
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
                          accessorKey: 'symbol',
                          header: 'Symbol',
                          cell: ({ row }) => (
                            <div className="font-mono text-sm text-gray-200">
                              {row.original.symbol}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'side',
                          header: 'Side',
                          cell: ({ row }) => (
                            <div className={cn(
                              'font-mono text-sm font-semibold',
                              row.original.side === 'BUY' ? 'text-accent-green' : 'text-accent-red'
                            )}>
                              {row.original.side}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'quantity',
                          header: () => <div className="text-right">Quantity</div>,
                          cell: ({ row }) => (
                            <div className="text-right font-mono text-sm">
                              {row.original.quantity}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'entry_price',
                          header: () => <div className="text-right">Entry</div>,
                          cell: ({ row }) => (
                            <div className="text-right font-mono text-sm">
                              {formatCurrency(row.original.entry_price)}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'current_price',
                          header: () => <div className="text-right">Current</div>,
                          cell: ({ row }) => (
                            <div className="text-right font-mono text-sm">
                              {formatCurrency(row.original.current_price)}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'unrealized_pnl',
                          header: () => <div className="text-right">P&L</div>,
                          cell: ({ row }) => {
                            const pnl = row.original.unrealized_pnl;
                            const pnlPercent = row.original.unrealized_pnl_percent;
                            return (
                              <div className="text-right">
                                <div className={cn(
                                  'font-mono text-sm font-semibold',
                                  pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
                                )}>
                                  {formatCurrency(pnl)}
                                </div>
                                <div className={cn(
                                  'font-mono text-xs',
                                  pnl >= 0 ? 'text-accent-green/70' : 'text-accent-red/70'
                                )}>
                                  {formatPercentage(pnlPercent)}
                                </div>
                              </div>
                            );
                          },
                        },
                        {
                          accessorKey: 'strategy_id',
                          header: 'Strategy',
                          cell: ({ row }) => (
                            <div className="font-mono text-sm text-gray-400">
                              {row.original.strategy_id}
                            </div>
                          ),
                        },
                        {
                          accessorKey: 'closure_reason',
                          header: 'Reason',
                          cell: ({ row }) => (
                            <div className="text-sm text-gray-400 max-w-xs truncate">
                              {row.original.closure_reason || 'Strategy retired'}
                            </div>
                          ),
                        },
                        {
                          id: 'actions',
                          header: () => <div className="text-right">Actions</div>,
                          cell: ({ row }) => (
                            <div className="flex justify-end">
                              <Button
                                variant="default"
                                size="sm"
                                onClick={() => handleApproveClosure(row.original.id)}
                                className="gap-2"
                              >
                                <X className="h-4 w-4" />
                                Close
                              </Button>
                            </div>
                          ),
                        },
                      ]}
                      data={pendingClosures}
                      getRowId={(row) => row.id}
                      rowSelection={Object.fromEntries(
                        Array.from(selectedClosures).map(id => [id, true])
                      )}
                      onRowSelectionChange={(updater) => {
                        const newSelection = typeof updater === 'function'
                          ? updater(Object.fromEntries(Array.from(selectedClosures).map(id => [id, true])))
                          : updater;
                        setSelectedClosures(new Set(Object.keys(newSelection).filter(id => newSelection[id])));
                      }}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Execution Analytics Tab */}
          <TabsContent value="analytics" className="space-y-6">
            {/* Period Selector */}
            <div className="flex justify-end">
              <div className="flex gap-2">
                <Button
                  variant={analyticsPeriod === '1D' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setAnalyticsPeriod('1D')}
                >
                  1D
                </Button>
                <Button
                  variant={analyticsPeriod === '1W' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setAnalyticsPeriod('1W')}
                >
                  1W
                </Button>
                <Button
                  variant={analyticsPeriod === '1M' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setAnalyticsPeriod('1M')}
                >
                  1M
                </Button>
              </div>
            </div>

            {/* Slippage by Strategy */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Slippage by Strategy</CardTitle>
                  <CardDescription>
                    Average slippage for each strategy
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {slippageByStrategy.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={slippageByStrategy} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 12 }} />
                        <YAxis 
                          type="category" 
                          dataKey="strategy" 
                          stroke="#9ca3af"
                          tick={{ fontSize: 12 }}
                          width={80}
                        />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: '#1f2937',
                            border: '1px solid #374151',
                            borderRadius: '0.5rem',
                          }}
                          formatter={(value: number | string | undefined) => {
                            if (value === undefined || value === null) return 'N/A';
                            if (typeof value === 'number') return `${value.toFixed(4)}%`;
                            return value;
                          }}
                        />
                        <Bar dataKey="slippage" fill="#f59e0b" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      No slippage data available
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Fill Rate Trend */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Fill Rate Trend</CardTitle>
                  <CardDescription>
                    Daily fill rate over the last 7 days
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {fillRateTrend.some(d => d.fillRate > 0) ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={fillRateTrend}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis 
                          dataKey="date" 
                          stroke="#9ca3af"
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis 
                          stroke="#9ca3af" 
                          tick={{ fontSize: 12 }}
                          domain={[0, 100]}
                        />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: '#1f2937',
                            border: '1px solid #374151',
                            borderRadius: '0.5rem',
                          }}
                          formatter={(value: number | string | undefined) => {
                            if (value === undefined || value === null) return 'N/A';
                            if (typeof value === 'number') return `${value.toFixed(1)}%`;
                            return value;
                          }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="fillRate" 
                          stroke="#10b981" 
                          strokeWidth={2}
                          dot={{ fill: '#10b981', r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      No fill rate data available
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Rejection Reasons Breakdown */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Rejection Reasons Breakdown</CardTitle>
                  <CardDescription>
                    Distribution of order rejection reasons
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {rejectionData.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <ResponsiveContainer width="100%" height={250}>
                        <PieChart>
                          <Pie
                            data={rejectionData}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            label={false}
                            outerRadius={80}
                            fill="#8884d8"
                            dataKey="value"
                          >
                            {rejectionData.map((_, index) => (
                              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                          </Pie>
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '0.5rem',
                            }}
                          />
                          <Legend
                            verticalAlign="bottom"
                            height={36}
                            iconType="circle"
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      
                      <div className="space-y-3">
                        {rejectionData.map((item, index) => (
                          <div key={item.name} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                            <div className="flex items-center gap-3">
                              <div 
                                className="w-3 h-3 rounded-full" 
                                style={{ backgroundColor: COLORS[index % COLORS.length] }}
                              />
                              <span className="text-sm text-gray-200">{item.name}</span>
                            </div>
                            <span className="text-sm font-mono font-semibold text-gray-200">
                              {String(item.value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      No rejected orders
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>
        </Tabs>

        {/* Cancel Order Confirmation Dialog */}
        <ConfirmDialog
          open={cancelDialogOpen}
          onOpenChange={setCancelDialogOpen}
          title="Cancel Order"
          description={cancelTarget ? `Cancel ${cancelTarget.side} order for ${formatCurrency(cancelTarget.quantity)} ${cancelTarget.symbol}?` : 'Cancel this order?'}
          confirmLabel="Cancel Order"
          confirmVariant="destructive"
          onConfirm={async () => {
            if (cancelTarget) {
              await handleCancelOrder(cancelTarget.id);
              setCancelTarget(null);
            }
          }}
        />

        {/* Manual Order Form Dialog */}
        <Dialog open={orderFormOpen} onOpenChange={(open) => { setOrderFormOpen(open); if (!open) resetOrderForm(); }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{orderFormStep === 'fill' ? 'New Order' : 'Review Order'}</DialogTitle>
              <DialogDescription>
                {orderFormStep === 'fill' ? 'Enter order details' : 'Confirm your order before submitting'}
              </DialogDescription>
            </DialogHeader>

            {orderFormStep === 'fill' ? (
              <div className="space-y-4">
                {/* Symbol */}
                <div className="space-y-1">
                  <div className="text-sm font-medium text-gray-300">Symbol</div>
                  <Input
                    placeholder="e.g. AAPL"
                    value={orderForm.symbol}
                    onChange={(e) => { setOrderForm(f => ({ ...f, symbol: e.target.value })); setOrderFormErrors(e2 => ({ ...e2, symbol: '' })); }}
                    className={orderFormErrors.symbol ? 'border-accent-red' : ''}
                  />
                  {orderFormErrors.symbol && <p className="text-xs text-accent-red">{orderFormErrors.symbol}</p>}
                </div>

                {/* Side */}
                <div className="space-y-1">
                  <div className="text-sm font-medium text-gray-300">Side</div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant={orderForm.side === 'BUY' ? 'default' : 'outline'}
                      size="sm"
                      className={cn('flex-1', orderForm.side === 'BUY' && 'bg-accent-green hover:bg-accent-green/80 text-black')}
                      onClick={() => setOrderForm(f => ({ ...f, side: 'BUY' }))}
                    >
                      BUY
                    </Button>
                    <Button
                      type="button"
                      variant={orderForm.side === 'SELL' ? 'default' : 'outline'}
                      size="sm"
                      className={cn('flex-1', orderForm.side === 'SELL' && 'bg-accent-red hover:bg-accent-red/80 text-white')}
                      onClick={() => setOrderForm(f => ({ ...f, side: 'SELL' }))}
                    >
                      SELL
                    </Button>
                  </div>
                </div>

                {/* Order Type */}
                <div className="space-y-1">
                  <div className="text-sm font-medium text-gray-300">Order Type</div>
                  <Select value={orderForm.orderType} onValueChange={(v) => setOrderForm(f => ({ ...f, orderType: v as 'MARKET' | 'LIMIT' }))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MARKET">Market</SelectItem>
                      <SelectItem value="LIMIT">Limit</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Quantity */}
                <div className="space-y-1">
                  <div className="text-sm font-medium text-gray-300">Quantity</div>
                  <Input
                    type="number"
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    value={orderForm.quantity}
                    onChange={(e) => { setOrderForm(f => ({ ...f, quantity: e.target.value })); setOrderFormErrors(e2 => ({ ...e2, quantity: '' })); }}
                    className={orderFormErrors.quantity ? 'border-accent-red' : ''}
                  />
                  {orderFormErrors.quantity && <p className="text-xs text-accent-red">{orderFormErrors.quantity}</p>}
                </div>

                {/* Price (only for LIMIT) */}
                {orderForm.orderType === 'LIMIT' && (
                  <div className="space-y-1">
                    <div className="text-sm font-medium text-gray-300">Limit Price</div>
                    <Input
                      type="number"
                      placeholder="0.00"
                      min="0"
                      step="0.01"
                      value={orderForm.price}
                      onChange={(e) => { setOrderForm(f => ({ ...f, price: e.target.value })); setOrderFormErrors(e2 => ({ ...e2, price: '' })); }}
                      className={orderFormErrors.price ? 'border-accent-red' : ''}
                    />
                    {orderFormErrors.price && <p className="text-xs text-accent-red">{orderFormErrors.price}</p>}
                  </div>
                )}

                <DialogFooter>
                  <Button variant="outline" onClick={() => setOrderFormOpen(false)}>Cancel</Button>
                  <Button onClick={handleOrderFormNext}>Review Order</Button>
                </DialogFooter>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Review summary */}
                <div className="p-4 bg-dark-surface rounded-lg border border-dark-border space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Symbol</span>
                    <span className="text-sm font-mono font-semibold text-gray-200">{orderForm.symbol.toUpperCase()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Side</span>
                    <span className={cn('text-sm font-mono font-semibold', orderForm.side === 'BUY' ? 'text-accent-green' : 'text-accent-red')}>
                      {orderForm.side}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Type</span>
                    <span className="text-sm font-mono text-gray-200">{orderForm.orderType}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Quantity</span>
                    <span className="text-sm font-mono text-gray-200">{parseFloat(orderForm.quantity).toFixed(2)}</span>
                  </div>
                  {orderForm.orderType === 'LIMIT' && (
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">Limit Price</span>
                      <span className="text-sm font-mono text-gray-200">{formatCurrency(parseFloat(orderForm.price))}</span>
                    </div>
                  )}
                </div>

                <DialogFooter>
                  <Button variant="outline" onClick={() => setOrderFormStep('fill')}>Back</Button>
                  <Button
                    onClick={handleOrderFormSubmit}
                    disabled={orderSubmitting}
                    className={cn(orderForm.side === 'BUY' ? 'bg-accent-green hover:bg-accent-green/80 text-black' : 'bg-accent-red hover:bg-accent-red/80 text-white')}
                  >
                    {orderSubmitting ? 'Submitting...' : `Submit ${orderForm.side} Order`}
                  </Button>
                </DialogFooter>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </motion.div>
    </DashboardLayout>
  );
};
