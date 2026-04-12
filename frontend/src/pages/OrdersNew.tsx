import React, { type FC, useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { 
  Clock, AlertCircle, Search,
  RefreshCw, Download, MoreVertical, X, Calendar
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { DataTable } from '../components/trading/DataTable';
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
import { utcToLocal } from '../lib/date-utils';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { OrderFlowTimeline } from '../components/charts/OrderFlowTimeline';
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
  const utcDay = now.getUTCDay();

  const marketOpenUTC = 13 * 60 + 30;
  const marketCloseUTC = 20 * 60;
  const currentMinutes = utcHour * 60 + utcMinute;

  const isWeekday = utcDay >= 1 && utcDay <= 5;
  const isDuringHours = currentMinutes >= marketOpenUTC && currentMinutes < marketCloseUTC;
  const isOpen = isWeekday && isDuringHours;

  let nextOpen: Date | null = null;
  if (!isOpen) {
    const next = new Date(now);
    if (isWeekday && currentMinutes < marketOpenUTC) {
      next.setUTCHours(13, 30, 0, 0);
    } else {
      let daysToAdd = 1;
      if (utcDay === 5) daysToAdd = 3;
      else if (utcDay === 6) daysToAdd = 2;
      else if (utcDay === 0) daysToAdd = 1;
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
      
      const [ordersData, pendingClosuresData] = await Promise.all([
        apiClient.getOrders(tradingMode),
        apiClient.getPendingClosures(tradingMode).catch(err => {
          console.warn('Failed to fetch pending closures:', err);
          return [];
        }),
      ]);
      
      const sortedOrders = ordersData.sort((a, b) => 
        utcToLocal(b.created_at).getTime() - utcToLocal(a.created_at).getTime()
      );
      
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

  // Fetch execution quality data
  const fetchExecutionQuality = async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getExecutionQuality(tradingMode, analyticsPeriod);
      setExecutionQuality(data);
    } catch (err) {
      console.warn('Failed to fetch execution quality:', err);
    }
  };

  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchData,
    intervalMs: 15000,
    enabled: !!tradingMode && !tradingModeLoading,
    skipWhenWsConnected: true,
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
      await fetchData();
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
        const orderWithMetrics: OrderWithMetrics = {
          ...order,
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
  
  const filledOrdersWithMetrics = orders.filter(o => o.status === 'FILLED' && o.slippage !== undefined);
  
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

  const uniqueStrategies = Array.from(new Set(
    orders.map(o => o.strategy_id).filter(Boolean)
  ));

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
      const orderDate = utcToLocal(order.created_at);
      if (dateRange.from && orderDate < startOfDay(dateRange.from)) matchesDate = false;
      if (dateRange.to && orderDate > endOfDay(dateRange.to)) matchesDate = false;
    }
    
    return matchesSearch && matchesStatus && matchesSide && matchesSource && matchesStrategy && matchesDate;
  });

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
    const orderTime = utcToLocal(o.created_at).getTime();
    return orderTime >= periodStart;
  });

  // Slippage by strategy data
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

  // Fill rate trend
  const getTrendDays = () => {
    switch (analyticsPeriod) {
      case '1D': return 24;
      case '1W': return 7;
      case '1M': return 30;
      default: return 7;
    }
  };
  
  const trendDays = getTrendDays();
  const fillRateTrend = Array.from({ length: trendDays }, (_, i) => {
    const day = trendDays - 1 - i;
    const dayStart = analyticsPeriod === '1D' 
      ? Date.now() - (day + 1) * 60 * 60 * 1000
      : startOfDay(subDays(new Date(), day)).getTime();
    const dayEnd = analyticsPeriod === '1D'
      ? Date.now() - day * 60 * 60 * 1000
      : endOfDay(subDays(new Date(), day)).getTime();
    const dayOrders = orders.filter(o => {
      const orderTime = utcToLocal(o.created_at).getTime();
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

  // Rejection reasons breakdown
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
      await fetchData();
    } catch (error) {
      console.error('Failed to close position:', error);
      toast.error('Failed to close position');
    }
  };

  // Bulk cancel orders
  const handleBulkCancelOrders = async () => {
    if (selectedOrders.size === 0) return;
    
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

  // Smart bulk action
  const handleSmartBulkAction = async () => {
    if (selectedOrders.size === 0) return;
    
    const selectedOrdersList = Array.from(selectedOrders).map(id => orders.find(o => o.id === id)!).filter(Boolean);
    
    const pendingOrdrs = selectedOrdersList.filter(o => o.status === 'PENDING' || (o.status as string) === 'SUBMITTED');
    const filledOrdrs = selectedOrdersList.filter(o => o.status === 'FILLED');
    const cancelledOrdrs = selectedOrdersList.filter(o => o.status === 'CANCELLED');
    const failedOrdrs = selectedOrdersList.filter(o => (o.status as string) === 'FAILED');
    
    const actions = [];
    if (pendingOrdrs.length > 0) actions.push(`Cancel ${pendingOrdrs.length} Pending order(s)`);
    if (filledOrdrs.length > 0) actions.push(`Close ${filledOrdrs.length} position(s) on eToro and delete`);
    if (cancelledOrdrs.length > 0) actions.push(`Delete ${cancelledOrdrs.length} Cancelled order(s)`);
    if (failedOrdrs.length > 0) actions.push(`Delete ${failedOrdrs.length} Failed order(s)`);
    
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
    
    for (const order of pendingOrdrs) {
      try {
        await apiClient.cancelOrder(order.id, tradingMode!);
        cancelledCount++;
        setOrders(prev => prev.map(o => o.id === order.id ? { ...o, status: 'CANCELLED' as OrderStatus } : o));
      } catch (error) {
        console.error(`Failed to cancel order ${order.id}:`, error);
        failCount++;
      }
    }
    
    for (const order of filledOrdrs) {
      try {
        await apiClient.closeFilledOrderPosition(order.id, tradingMode!);
        positionsClosedCount++;
      } catch (error) {
        console.error(`Failed to close position for order ${order.id}:`, error);
      }
    }
    
    const ordersToDelete = [...filledOrdrs, ...cancelledOrdrs, ...failedOrdrs];
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
      await fetchData();
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
      await fetchData();
      
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

  // Recent fills for side panel (last 10 filled orders)
  const recentFills = orders
    .filter(o => o.status === 'FILLED')
    .slice(0, 10);

  // Compact metrics for side panel
  const sideMetrics: CompactMetric[] = [
    { label: 'Total', value: totalOrders, trend: 'neutral' },
    { label: 'Fill Rate', value: `${fillRate.toFixed(1)}%`, trend: fillRate >= 80 ? 'up' : fillRate >= 50 ? 'neutral' : 'down' },
    { label: 'Avg Slip', value: `${avgSlippage.toFixed(2)}%`, trend: avgSlippage <= 0 ? 'up' : 'down' },
    { label: 'Pending', value: pendingOrders, trend: pendingOrders > 0 ? 'neutral' : 'up', color: pendingOrders > 0 ? '#eab308' : undefined },
  ];

  // Loading state
  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8">
          <PageSkeleton />
        </div>
      </DashboardLayout>
    );
  }

  // Error state
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

  // Header actions for PageTemplate
  const headerActions = (
    <>
      <DataFreshnessIndicator lastFetchedAt={lastUpdated} />
      <Button
        variant="default"
        size="sm"
        onClick={() => { resetOrderForm(); setOrderFormOpen(true); }}
        className="gap-2 bg-accent-green hover:bg-accent-green/80 text-black"
      >
        + New Order
      </Button>
      <Button variant="outline" size="sm" onClick={exportToCSV} className="gap-2">
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
        {syncing ? 'Syncing...' : '🔄 Sync'}
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
    </>
  );

  // ── Main Panel (65%) ─────────────────────────────────────────────────
  const mainPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader
        title="Orders"
        panelId="orders-main"
        onRefresh={fetchData}
      >
        <div className="flex flex-col h-full overflow-hidden">
          {/* OrderFlowTimeline hero — top ~40% */}
          <div className="shrink-0" style={{ height: '40%', minHeight: '180px' }}>
            <div className="p-3 h-full">
              <div className="text-xs text-gray-500 mb-1 font-semibold uppercase tracking-wide">Order Flow — Last 7 Days</div>
              <OrderFlowTimeline
                orders={orders.map((o) => ({
                  id: o.id,
                  symbol: o.symbol,
                  status: o.status,
                  side: o.side,
                  created_at: o.created_at,
                  quantity: o.quantity,
                }))}
                days={7}
              />
            </div>
          </div>

          {/* Orders DenseTable with tabs — bottom ~60% */}
          <div className="flex-1 min-h-0 overflow-hidden border-t border-[var(--color-dark-border)]">
            <Tabs defaultValue="all" className="flex flex-col h-full">
              <div className="shrink-0 px-3 pt-2">
                <TabsList className="w-full overflow-x-auto">
                  <TabsTrigger value="all">
                    All ({filteredOrders.length})
                  </TabsTrigger>
                  <TabsTrigger value="queue" className={queuedOrders.length > 0 ? 'text-amber-400' : ''}>
                    Queue {queuedOrders.length > 0 && `(${queuedOrders.length})`}
                  </TabsTrigger>
                  <TabsTrigger value="pending-closures">
                    Closures ({pendingClosures.length})
                  </TabsTrigger>
                  <TabsTrigger value="analytics" onClick={fetchExecutionQuality}>
                    Analytics
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* All Orders Tab */}
              <TabsContent value="all" className="flex-1 min-h-0 overflow-hidden px-3 pb-2">
                <div className="flex flex-col h-full gap-2">
                  {/* Filters row */}
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder="Search symbol..."
                        value={orderSearch}
                        onChange={(e) => setOrderSearch(e.target.value)}
                        className="pl-8 h-8 text-xs w-[150px]"
                      />
                    </div>
                    <Select value={orderStatusFilter} onValueChange={setOrderStatusFilter}>
                      <SelectTrigger className="w-[120px] h-8 text-xs">
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Status</SelectItem>
                        <SelectItem value="PENDING">Pending</SelectItem>
                        <SelectItem value="SUBMITTED">Submitted</SelectItem>
                        <SelectItem value="FILLED">Executed</SelectItem>
                        <SelectItem value="PARTIALLY_FILLED">Partial</SelectItem>
                        <SelectItem value="CANCELLED">Cancelled</SelectItem>
                        <SelectItem value="FAILED">Failed</SelectItem>
                        <SelectItem value="REJECTED">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select value={orderSideFilter} onValueChange={setOrderSideFilter}>
                      <SelectTrigger className="w-[100px] h-8 text-xs">
                        <SelectValue placeholder="Side" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Sides</SelectItem>
                        <SelectItem value="BUY">Buy</SelectItem>
                        <SelectItem value="SELL">Sell</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select value={orderSourceFilter} onValueChange={setOrderSourceFilter}>
                      <SelectTrigger className="w-[120px] h-8 text-xs">
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
                        <SelectTrigger className="w-[120px] h-8 text-xs">
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
                        <Button variant="outline" size="sm" className="gap-1 h-8 text-xs">
                          <Calendar className="h-3.5 w-3.5" />
                          {dateRange.from || dateRange.to ? 'Dates' : 'All'}
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
                            <Button size="sm" variant="outline" onClick={clearDateRange} className="flex-1">Clear</Button>
                            <Button size="sm" onClick={() => setShowDatePicker(false)} className="flex-1">Apply</Button>
                          </div>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>

                  {/* Bulk Actions */}
                  {selectedOrders.size > 0 && (
                    <div className="flex items-center gap-2 p-2 bg-dark-lighter rounded border border-dark-border shrink-0">
                      <span className="text-xs text-gray-400 font-mono">{selectedOrders.size} selected</span>
                      <Button onClick={handleSmartBulkAction} variant="default" size="sm" className="gap-1 h-7 text-xs">
                        <X className="h-3 w-3" /> Clean Up
                      </Button>
                      <Button onClick={handleBulkCancelOrders} variant="destructive" size="sm" className="gap-1 h-7 text-xs">
                        Cancel
                      </Button>
                      <Button onClick={handleBulkDeleteOrders} variant="destructive" size="sm" className="gap-1 h-7 text-xs">
                        Delete
                      </Button>
                      <Button onClick={() => setSelectedOrders(new Set())} variant="ghost" size="sm" className="h-7 text-xs">
                        Clear
                      </Button>
                    </div>
                  )}

                  {/* Table */}
                  <div className="flex-1 min-h-0 overflow-auto">
                    {filteredOrders.length > 0 ? (
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
                    ) : (
                      <div className="text-center py-8 text-muted-foreground text-sm">
                        {orderSearch || orderStatusFilter !== 'all' || orderSideFilter !== 'all' || orderSourceFilter !== 'all' || orderStrategyFilter !== 'all' || dateRange.from || dateRange.to
                          ? 'No orders match your filters' 
                          : 'No orders found'}
                      </div>
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* Order Queue Tab */}
              <TabsContent value="queue" className="flex-1 min-h-0 overflow-auto px-3 pb-2">
                {/* Market Status Banner */}
                <div className={cn(
                  'flex items-center justify-between p-3 rounded-lg border mb-3',
                  marketStatus.isOpen ? 'border-accent-green/30 bg-accent-green/5' : 'border-amber-500/30 bg-amber-500/5'
                )}>
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      'h-2.5 w-2.5 rounded-full animate-pulse',
                      marketStatus.isOpen ? 'bg-accent-green' : 'bg-amber-500'
                    )} />
                    <div>
                      <p className={cn(
                        'text-xs font-semibold',
                        marketStatus.isOpen ? 'text-accent-green' : 'text-amber-400'
                      )}>
                        {marketStatus.label}
                      </p>
                      {!marketStatus.isOpen && marketStatus.nextOpen && (
                        <p className="text-[10px] text-gray-400">
                          Next: {format(marketStatus.nextOpen, 'EEE, MMM d h:mm a')} UTC
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-gray-400">
                      {queuedOrders.length} queued
                    </span>
                    {queuedOrders.length > 0 && (
                      <Button variant="destructive" size="sm" onClick={handleCancelAllQueued} className="gap-1 h-7 text-xs">
                        <X className="h-3 w-3" /> Cancel All
                      </Button>
                    )}
                  </div>
                </div>

                {queuedOrders.length === 0 ? (
                  <div className="text-center py-8">
                    <Clock className="h-8 w-8 text-gray-600 mx-auto mb-2" />
                    <div className="text-gray-400 font-mono text-sm mb-1">No queued orders</div>
                    <div className="text-xs text-gray-500">Orders placed when market is closed appear here</div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {queuedOrders.map((order) => {
                      const age = formatDistanceToNow(utcToLocal(order.created_at), { addSuffix: true });
                      const isWaitingForMarket = !marketStatus.isOpen;
                      return (
                        <div
                          key={order.id}
                          className="flex items-center justify-between p-3 rounded-lg border border-amber-500/20 bg-amber-500/5"
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="flex flex-col">
                              <span className="font-mono font-semibold text-xs text-gray-200">{order.symbol}</span>
                              <span className={cn('text-[10px] font-mono font-semibold', order.side === 'BUY' ? 'text-accent-green' : 'text-accent-red')}>
                                {order.side}
                              </span>
                            </div>
                            <div className="flex flex-col">
                              <span className="text-xs text-gray-300 font-mono">{formatCurrency(order.quantity)}</span>
                              <span className="text-[10px] text-gray-500">{order.price ? `@ ${formatCurrency(order.price)}` : 'Market'}</span>
                            </div>
                            <div className="flex flex-col">
                              <span className="text-[10px] text-gray-400">Queued {age}</span>
                              <span className={cn(
                                'text-[10px] px-1 py-0.5 rounded mt-0.5 w-fit',
                                isWaitingForMarket ? 'bg-amber-500/20 text-amber-400' : 'bg-blue-500/20 text-blue-400'
                              )}>
                                {isWaitingForMarket ? 'Waiting for market' : 'Processing'}
                              </span>
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleCancelOrder(order.id)}
                            className="border-accent-red/30 text-accent-red hover:bg-accent-red/10 gap-1 shrink-0 h-7 text-xs"
                          >
                            <X className="h-3 w-3" /> Cancel
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              {/* Pending Closures Tab */}
              <TabsContent value="pending-closures" className="flex-1 min-h-0 overflow-auto px-3 pb-2">
                {pendingClosures.length === 0 ? (
                  <div className="text-center py-8">
                    <div className="text-gray-400 font-mono text-sm mb-1">No pending closures</div>
                    <div className="text-xs text-gray-500">Positions from retired strategies appear here</div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {selectedClosures.size > 0 && (
                      <div className="flex items-center gap-3 p-2 bg-dark-card border border-gray-700 rounded">
                        <span className="text-xs text-gray-300 font-mono">{selectedClosures.size} selected</span>
                        <Button onClick={handleBulkApproveClosures} variant="default" size="sm" className="gap-1 h-7 text-xs">
                          Close Selected
                        </Button>
                      </div>
                    )}
                    <DataTable
                      columns={[
                        {
                          id: 'select',
                          header: () => {
                            const allSelected = pendingClosures.length > 0 && pendingClosures.every(p => selectedClosures.has(p.id));
                            return (
                              <input
                                type="checkbox"
                                checked={allSelected}
                                onChange={(e) => {
                                  if (e.target.checked) setSelectedClosures(new Set(pendingClosures.map(p => p.id)));
                                  else setSelectedClosures(new Set());
                                }}
                                className="w-4 h-4 rounded border-gray-600"
                              />
                            );
                          },
                          cell: ({ row }) => (
                            <input
                              type="checkbox"
                              checked={row.getIsSelected()}
                              onChange={(e) => row.toggleSelected(!!e.target.checked)}
                              className="w-4 h-4 rounded border-gray-600"
                            />
                          ),
                        },
                        {
                          accessorKey: 'symbol',
                          header: 'Symbol',
                          cell: ({ row }) => <div className="font-mono text-xs">{row.original.symbol}</div>,
                        },
                        {
                          accessorKey: 'side',
                          header: 'Side',
                          cell: ({ row }) => (
                            <span className={cn('font-mono text-xs font-semibold', row.original.side === 'BUY' ? 'text-accent-green' : 'text-accent-red')}>
                              {row.original.side}
                            </span>
                          ),
                        },
                        {
                          accessorKey: 'quantity',
                          header: () => <div className="text-right">Qty</div>,
                          cell: ({ row }) => <div className="text-right font-mono text-xs">{row.original.quantity}</div>,
                        },
                        {
                          accessorKey: 'unrealized_pnl',
                          header: () => <div className="text-right">P&L</div>,
                          cell: ({ row }) => {
                            const pnl = row.original.unrealized_pnl;
                            return (
                              <div className={cn('text-right font-mono text-xs font-semibold', pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                                {formatCurrency(pnl)}
                              </div>
                            );
                          },
                        },
                        {
                          id: 'actions',
                          header: () => <div className="text-right">Actions</div>,
                          cell: ({ row }) => (
                            <div className="flex justify-end">
                              <Button variant="default" size="sm" onClick={() => handleApproveClosure(row.original.id)} className="h-7 text-xs">
                                Close
                              </Button>
                            </div>
                          ),
                        },
                      ]}
                      data={pendingClosures}
                      getRowId={(row) => row.id}
                      rowSelection={Object.fromEntries(Array.from(selectedClosures).map(id => [id, true]))}
                      onRowSelectionChange={(updater) => {
                        const newSelection = typeof updater === 'function'
                          ? updater(Object.fromEntries(Array.from(selectedClosures).map(id => [id, true])))
                          : updater;
                        setSelectedClosures(new Set(Object.keys(newSelection).filter(id => newSelection[id])));
                      }}
                    />
                  </div>
                )}
              </TabsContent>

              {/* Execution Analytics Tab */}
              <TabsContent value="analytics" className="flex-1 min-h-0 overflow-auto px-3 pb-2 space-y-4">
                {/* Period Selector */}
                <div className="flex justify-end">
                  <div className="flex gap-1">
                    {(['1D', '1W', '1M'] as const).map(p => (
                      <Button
                        key={p}
                        variant={analyticsPeriod === p ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setAnalyticsPeriod(p)}
                        className="h-7 text-xs px-2"
                      >
                        {p}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Slippage by Strategy */}
                <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
                  <div className="text-xs font-semibold text-gray-300 mb-2">Slippage by Strategy</div>
                  {slippageByStrategy.length > 0 ? (
                    <ResponsiveContainer width="100%" height={180}>
                      <BarChart data={slippageByStrategy} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="strategy" stroke="#9ca3af" tick={{ fontSize: 10 }} width={60} />
                        <RechartsTooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem' }}
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
                    <div className="text-center py-6 text-muted-foreground text-xs">No slippage data</div>
                  )}
                </div>

                {/* Fill Rate Trend */}
                <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
                  <div className="text-xs font-semibold text-gray-300 mb-2">Fill Rate Trend</div>
                  {fillRateTrend.some(d => d.fillRate > 0) ? (
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={fillRateTrend}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                        <YAxis stroke="#9ca3af" tick={{ fontSize: 10 }} domain={[0, 100]} />
                        <RechartsTooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem' }}
                          formatter={(value: number | string | undefined) => {
                            if (value === undefined || value === null) return 'N/A';
                            if (typeof value === 'number') return `${value.toFixed(1)}%`;
                            return value;
                          }}
                        />
                        <Line type="monotone" dataKey="fillRate" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981', r: 3 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-6 text-muted-foreground text-xs">No fill rate data</div>
                  )}
                </div>

                {/* Rejection Reasons */}
                <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
                  <div className="text-xs font-semibold text-gray-300 mb-2">Rejection Reasons</div>
                  {rejectionData.length > 0 ? (
                    <div className="grid grid-cols-2 gap-3">
                      <ResponsiveContainer width="100%" height={150}>
                        <PieChart>
                          <Pie data={rejectionData} cx="50%" cy="50%" labelLine={false} label={false} outerRadius={55} fill="#8884d8" dataKey="value">
                            {rejectionData.map((_, index) => (
                              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                          </Pie>
                          <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem' }} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="space-y-1.5">
                        {rejectionData.map((item, index) => (
                          <div key={item.name} className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-1.5">
                              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                              <span className="text-gray-300 truncate">{item.name}</span>
                            </div>
                            <span className="font-mono font-semibold text-gray-200">{String(item.value)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-6 text-muted-foreground text-xs">No rejected orders</div>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (35%) ─────────────────────────────────────────────────
  const sidePanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader
        title="Execution"
        panelId="orders-side"
        onRefresh={fetchExecutionQuality}
      >
        <div className="flex flex-col gap-3 p-3 overflow-auto h-full">
          {/* CompactMetricRow: total orders, fill rate, avg slippage, pending */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Execution Quality Mini-Chart (fill rate sparkline) */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Execution Quality</div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="text-center">
                <div className={cn('text-lg font-bold font-mono', avgSlippage >= 0 ? 'text-accent-red' : 'text-accent-green')}>
                  {formatPercentage(avgSlippage)}
                </div>
                <div className="text-[10px] text-gray-500">Avg Slippage</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold font-mono text-accent-green">
                  {formatPercentage(fillRate)}
                </div>
                <div className="text-[10px] text-gray-500">Fill Rate</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold font-mono text-blue-400">
                  {avgFillTime.toFixed(1)}s
                </div>
                <div className="text-[10px] text-gray-500">Avg Fill Time</div>
              </div>
            </div>
            {/* Mini fill rate trend chart */}
            {fillRateTrend.some(d => d.fillRate > 0) ? (
              <ResponsiveContainer width="100%" height={80}>
                <LineChart data={fillRateTrend}>
                  <Line type="monotone" dataKey="fillRate" stroke="#10b981" strokeWidth={1.5} dot={false} />
                  <YAxis domain={[0, 100]} hide />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem', fontSize: 10 }}
                    formatter={(value: number | string | undefined) => {
                      if (typeof value === 'number') return `${value.toFixed(1)}%`;
                      return value;
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-4 text-[10px] text-gray-500">No trend data</div>
            )}
          </div>

          {/* Recent Fills List */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3 flex-1 min-h-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">
              Recent Fills ({recentFills.length})
            </div>
            {recentFills.length === 0 ? (
              <div className="text-center py-4 text-xs text-gray-500">No filled orders</div>
            ) : (
              <div className="space-y-1.5 overflow-auto max-h-[300px]">
                {recentFills.map((order) => (
                  <div
                    key={order.id}
                    className="flex items-center justify-between py-1.5 px-2 rounded bg-[var(--color-dark-surface)] hover:bg-[var(--color-dark-surface)]/80 transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={cn(
                        'text-[10px] font-mono font-semibold px-1 py-0.5 rounded',
                        order.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'
                      )}>
                        {order.side}
                      </span>
                      <span className="font-mono text-xs font-semibold text-gray-200 truncate">
                        {order.symbol}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-mono text-xs text-gray-300">
                        {formatCurrency(order.quantity)}
                      </span>
                      <span className="text-[10px] text-gray-500">
                        {formatTimestamp(order.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Order Status Breakdown */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Status Breakdown</div>
            <div className="space-y-1.5">
              {[
                { label: 'Executed', count: filledOrders, color: 'text-accent-green', bg: 'bg-accent-green' },
                { label: 'Pending', count: pendingOrders, color: 'text-yellow-400', bg: 'bg-yellow-400' },
                { label: 'Cancelled', count: cancelledOrders, color: 'text-gray-400', bg: 'bg-gray-400' },
                { label: 'Rejected', count: rejectedOrders, color: 'text-accent-red', bg: 'bg-accent-red' },
              ].map(item => (
                <div key={item.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <div className={cn('w-1.5 h-1.5 rounded-full', item.bg)} />
                    <span className="text-xs text-gray-400">{item.label}</span>
                  </div>
                  <span className={cn('text-xs font-mono font-semibold', item.color)}>{item.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Return: 2-panel layout ─────────────────────────────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Orders"
        description={tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading'}
        actions={headerActions}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={pollingRefreshing && !loading} />
          <ResizablePanelLayout
            layoutId="orders-panels"
            direction="horizontal"
            panels={[
              {
                id: 'orders-main',
                defaultSize: 65,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'orders-side',
                defaultSize: 35,
                minSize: 250,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>

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
    </DashboardLayout>
  );
};
