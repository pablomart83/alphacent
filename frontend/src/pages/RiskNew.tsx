import { type FC, useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { 
  AlertTriangle, Shield, TrendingDown, Activity, BarChart3,
  RefreshCw, Search, AlertCircle, Settings as SettingsIcon,
  Zap,
} from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Cell, BarChart, Bar, PieChart, Pie } from 'recharts';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { Button } from '../components/ui/Button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Progress } from '../components/ui/progress';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { utcToLocal } from '../lib/date-utils';
import { classifyError, type ClassifiedError } from '../lib/errors';
import { CorrelationHeatmap } from '../components/charts/CorrelationHeatmap';
import { InteractiveChart } from '../components/charts/InteractiveChart';
import { chartTheme, colors as designColors } from '../lib/design-tokens';
import type { Position, RiskParams } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { useEffect } from 'react';

interface RiskNewProps {
  onLogout: () => void;
}

// Chart colors
const SECTOR_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#6366f1'];

// Risk metrics interface
interface RiskMetrics {
  var_95: number;
  max_drawdown: number;
  current_drawdown: number;
  leverage: number;
  beta: number;
  total_exposure: number;
  margin_utilization: number;
}

// Risk alert interface
interface RiskAlert {
  id: string;
  severity: 'info' | 'warning' | 'danger';
  title: string;
  message: string;
  timestamp: string;
}

// Position with risk metrics
interface PositionWithRisk extends Position {
  risk_level: 'low' | 'medium' | 'high';
  concentration_pct: number;
  var_contribution: number;
}

export const RiskNew: FC<RiskNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  
  // State
  const [positions, setPositions] = useState<PositionWithRisk[]>([]);
  const [riskMetrics, setRiskMetrics] = useState<RiskMetrics | null>(null);
  const [riskParams, setRiskParams] = useState<RiskParams | null>(null);
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([]);
  const [riskHistory, setRiskHistory] = useState<Array<{ date: string; exposure: number; drawdown: number; var_95: number }>>([]);
  const [, setPositionRisks] = useState<Array<{ symbol: string; risk_level?: string; beta?: number; var_95?: number; concentration_pct?: number; var_contribution?: number }>>([]);
  const [correlationMatrix, setCorrelationMatrix] = useState<Array<Record<string, number | string>>>([]);
  const [advancedRisk, setAdvancedRisk] = useState<any>(null);
  const [cioRisk, setCIORisk] = useState<any>(null);
  const [accountBalance, setAccountBalance] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<ClassifiedError | null>(null);
  
  // Filter states
  const [positionSearch, setPositionSearch] = useState('');
  const [riskLevelFilter, setRiskLevelFilter] = useState<string>('all');
  const [timePeriod, setTimePeriod] = useState<'1D' | '1W' | '1M' | '3M'>('1M');

  // Fetch risk data from backend
  const fetchRiskData = useCallback(async () => {
    if (!tradingMode) return;
    
    try {
      if (!riskMetrics) setLoading(true);
      setFetchError(null);
      
      // Phase 1: Essential data (fast — simple DB queries)
      const [metricsData, positionsData, paramsData, alertsData, accountData] = await Promise.all([
        apiClient.getRiskMetrics(tradingMode),
        apiClient.getPositions(tradingMode),
        apiClient.getRiskConfig(tradingMode),
        apiClient.getRiskAlerts(tradingMode),
        apiClient.getAccountInfo(tradingMode),
      ]);
      
      const balance = accountData.balance;
      setAccountBalance(balance);
      
      setRiskMetrics({
        var_95: metricsData.portfolio_var || 0,
        max_drawdown: metricsData.max_drawdown || 0,
        current_drawdown: metricsData.current_drawdown || 0,
        leverage: metricsData.leverage || 0,
        beta: metricsData.portfolio_beta || 0,
        total_exposure: metricsData.total_exposure || 0,
        margin_utilization: metricsData.margin_utilization || 0,
      });
      
      const enhancedPositions = enhancePositionsWithRisk(positionsData, metricsData.total_exposure, null, balance);
      setPositions(enhancedPositions);
      setRiskParams(paramsData);
      setRiskAlerts(alertsData.map((alert: any) => ({
        id: alert.id,
        severity: alert.severity as RiskAlert['severity'],
        title: alert.metric || alert.title || 'Risk Alert',
        message: alert.message,
        timestamp: alert.timestamp,
      })));
      
      setLoading(false);
      setLastFetchedAt(new Date());
      
      // Phase 2: Heavy data (background)
      const [historyData, positionRisksData, correlationData, advancedRiskData, cioRiskData] = await Promise.all([
        apiClient.getRiskHistory(tradingMode, timePeriod).catch(() => null),
        apiClient.getPositionRisks(tradingMode).catch(() => null),
        apiClient.getCorrelationMatrix(tradingMode, timePeriod).catch(() => null),
        apiClient.getAdvancedRisk(tradingMode).catch(() => null),
        apiClient.getCIORisk(tradingMode).catch(() => null),
      ]);
      
      if (positionRisksData) {
        const reEnhanced = enhancePositionsWithRisk(positionsData, metricsData.total_exposure, positionRisksData, balance);
        setPositions(reEnhanced);
        setPositionRisks(positionRisksData);
      }
      
      if (historyData && historyData.history) {
        setRiskHistory(historyData.history.map((item: any) => ({
          date: utcToLocal(item.timestamp).toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric',
            ...(timePeriod === '1D' ? { hour: '2-digit' } : {})
          }),
          exposure: item.exposure || item.leverage || 0,
          drawdown: item.drawdown || 0,
          var_95: item.var_95 || item.var || 0,
        })));
      } else {
        setRiskHistory([]);
      }
      
      if (positionRisksData) {
        setPositionRisks(positionRisksData);
      }
      
      if (correlationData && correlationData.matrix) {
        setCorrelationMatrix(correlationData.matrix);
      } else {
        setCorrelationMatrix([]);
      }
      
      if (advancedRiskData) {
        setAdvancedRisk(advancedRiskData);
      }
      
      if (cioRiskData) {
        setCIORisk(cioRiskData?.data || cioRiskData);
      }
      
      setLastFetchedAt(new Date());
    } catch (error) {
      console.error('Failed to fetch risk data:', error);
      const classified = classifyError(error, 'risk data');
      setFetchError(classified);
      toast.error(classified.title, { description: classified.message });
    } finally {
      setLoading(false);
    }
  }, [tradingMode, timePeriod, riskMetrics]);

  const enhancePositionsWithRisk = (positions: Position[], _totalExposure: number, positionRisksData: Array<{ symbol: string; risk_level?: string; beta?: number; var_95?: number; concentration_pct?: number; var_contribution?: number }> | null, balance: number): PositionWithRisk[] => {
    return positions.map(pos => {
      const positionValue = Math.abs((pos as any).invested_amount || pos.quantity);
      const concentration = balance > 0 ? (positionValue / balance) * 100 : 0;
      
      const backendRisk = positionRisksData?.find((r) => r.symbol === pos.symbol);
      
      let risk_level: 'low' | 'medium' | 'high' = 'low';
      if (backendRisk?.risk_level) {
        risk_level = backendRisk.risk_level as 'low' | 'medium' | 'high';
      } else {
        if (concentration > 20) risk_level = 'high';
        else if (concentration > 10) risk_level = 'medium';
      }
      
      return {
        ...pos,
        risk_level,
        concentration_pct: backendRisk?.concentration_pct ?? concentration,
        var_contribution: backendRisk?.var_contribution ?? (positionValue * 0.05),
      };
    });
  };

  const { refresh, isRefreshing } = usePolling({
    fetchFn: fetchRiskData,
    intervalMs: 60000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  useEffect(() => {
    if (tradingMode && !tradingModeLoading) {
      refresh();
    }
  }, [timePeriod]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const unsubscribePosition = wsManager.onPositionUpdate(() => {
      if (tradingMode) {
        refresh();
      }
    });
    return () => { unsubscribePosition(); };
  }, [tradingMode, refresh]);

  // Filter positions
  const filteredPositions = positions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
    const matchesRiskLevel = riskLevelFilter === 'all' || position.risk_level === riskLevelFilter;
    return matchesSearch && matchesRiskLevel;
  });

  // Risk status
  const getRiskStatus = (): { status: 'safe' | 'warning' | 'danger'; message: string; reasons: string[] } => {
    if (!riskMetrics || !riskParams) return { status: 'safe', message: 'Calculating...', reasons: [] };
    const backendScore = (riskMetrics as any).risk_score as string;
    const backendReasons = ((riskMetrics as any).risk_reasons || []) as string[];
    if (backendScore === 'danger') {
      return { status: 'danger', message: 'High Risk — Immediate attention required', reasons: backendReasons };
    } else if (backendScore === 'warning') {
      return { status: 'warning', message: 'Elevated Risk — Monitor closely', reasons: backendReasons };
    }
    return { status: 'safe', message: 'All risk metrics within acceptable limits', reasons: backendReasons };
  };

  const riskStatus = getRiskStatus();

  // Table columns for positions with risk
  const positionRiskColumns: ColumnDef<PositionWithRisk>[] = [
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div className="font-mono font-semibold text-sm">{row.original.symbol}</div>
      ),
    },
    {
      accessorKey: 'risk_level',
      header: 'Risk',
      cell: ({ row }) => {
        const colors = {
          low: 'bg-accent-green/20 text-accent-green border-accent-green/30',
          medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
          high: 'bg-accent-red/20 text-accent-red border-accent-red/30',
        };
        return (
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-mono font-semibold border whitespace-nowrap uppercase',
            colors[row.original.risk_level]
          )}>
            {row.original.risk_level}
          </span>
        );
      },
    },
    {
      accessorKey: 'concentration_pct',
      header: () => <div className="text-right">Concentration</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatPercentage(row.original.concentration_pct)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'quantity',
      header: () => <div className="text-right">Invested</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency((row.original as any).invested_amount || row.original.quantity)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'current_price',
      header: () => <div className="text-right">Price</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency(row.original.current_price)}</span>
        </div>
      ),
    },
    {
      accessorKey: 'unrealized_pnl',
      header: () => <div className="text-right">P&L</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <div className={cn(
            'font-mono font-semibold text-sm',
            row.original.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {formatCurrency(row.original.unrealized_pnl)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'var_contribution',
      header: () => <div className="text-right">VaR Contrib.</div>,
      cell: ({ row }) => (
        <div className="text-right">
          <span className="font-mono text-sm">{formatCurrency(row.original.var_contribution)}</span>
        </div>
      ),
    },
  ];

  const riskHistoryData = riskHistory;

  // ── Side panel computed data ──────────────────────────────────────────

  // Max sector exposure
  const sectorMap = new Map<string, number>();
  positions.forEach((p) => {
    const sector = (p as any).sector || (p as any).asset_class || 'Other';
    sectorMap.set(sector, (sectorMap.get(sector) || 0) + Math.abs((p as any).invested_amount || p.quantity));
  });
  const totalInvested = positions.reduce((s, p) => s + Math.abs((p as any).invested_amount || p.quantity), 0);
  const maxSectorExposure = totalInvested > 0
    ? Math.max(...Array.from(sectorMap.values()).map(v => (v / totalInvested) * 100), 0)
    : 0;

  // Long/short ratio
  const longValue = positions.filter(p => (p as any).side === 'BUY' || p.quantity > 0).reduce((s, p) => s + Math.abs((p as any).invested_amount || p.quantity), 0);
  const shortValue = positions.filter(p => (p as any).side === 'SELL' || p.quantity < 0).reduce((s, p) => s + Math.abs((p as any).invested_amount || p.quantity), 0);
  const longShortRatio = shortValue > 0 ? (longValue / shortValue) : longValue > 0 ? Infinity : 0;

  // Side panel metrics
  const sideMetrics: CompactMetric[] = [
    { label: 'VaR 95%', value: formatCurrency(riskMetrics?.var_95 || 0), trend: 'down' as const, color: '#ef4444' },
    { label: 'Max Sector', value: `${maxSectorExposure.toFixed(1)}%`, trend: maxSectorExposure > 40 ? 'down' as const : 'neutral' as const },
    { label: 'L/S Ratio', value: longShortRatio === Infinity ? '∞' : longShortRatio.toFixed(2), trend: 'neutral' as const },
    { label: 'Beta', value: riskMetrics?.beta?.toFixed(2) || '---', trend: (riskMetrics?.beta || 0) > 1.2 ? 'down' as const : 'neutral' as const },
  ];

  // Sector exposure pie data
  const sectorPieData = Array.from(sectorMap.entries()).map(([name, value]) => ({ name, value }));

  // Risk contribution top 5 bar data
  const totalVar = positions.reduce((sum, p) => sum + (p as any).var_contribution, 0);
  const riskContribTop5 = positions
    .map((p) => ({
      symbol: p.symbol,
      contribution: totalVar > 0 ? ((p as any).var_contribution / totalVar) * 100 : 0,
    }))
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, 5);

  // Header actions
  const headerActions = (
    <>
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <Button
        variant="outline"
        size="sm"
        onClick={refresh}
        disabled={isRefreshing}
        className="gap-2"
      >
        <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
        Refresh
      </Button>
    </>
  );

  // ── Main Panel (60%) ──────────────────────────────────────────────────
  const mainPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader
        title="Risk"
        panelId="risk-main"
        onRefresh={refresh}
      >
        <div className="flex flex-col h-full overflow-hidden">
          {/* CorrelationHeatmap hero — top ~50% */}
          <div className="shrink-0" style={{ height: '50%', minHeight: '200px' }}>
            <div className="p-3 h-full overflow-auto">
              <div className="text-[10px] text-gray-500 mb-1 font-semibold uppercase tracking-wide">Position Correlations</div>
              {correlationMatrix.length > 0 ? (
                <CorrelationHeatmap
                  data={correlationMatrix.map((cell: any) => ({
                    symbol1: cell.x || cell.row,
                    symbol2: cell.y || cell.col,
                    correlation: Number(cell.value || 0),
                  }))}
                  symbols={Array.from(new Set(correlationMatrix.flatMap((c: any) => [c.x || c.row, c.y || c.col]).filter(Boolean))).slice(0, 20) as string[]}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  <div className="text-center">
                    <BarChart3 className="h-10 w-10 mx-auto mb-2 opacity-50" />
                    <p>{positions.length >= 2 ? 'Correlation data loading...' : 'Need at least 2 positions'}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Tabs below — bottom ~50% */}
          <div className="flex-1 min-h-0 overflow-hidden border-t border-[var(--color-dark-border)]">
            <Tabs defaultValue="overview" className="flex flex-col h-full">
              <div className="shrink-0 px-3 pt-2">
                <TabsList className="w-full overflow-x-auto">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="positions">Positions ({filteredPositions.length})</TabsTrigger>
                  <TabsTrigger value="advanced">Advanced</TabsTrigger>
                  <TabsTrigger value="history">History</TabsTrigger>
                  <TabsTrigger value="exposure">Exposure</TabsTrigger>
                </TabsList>
              </div>

              <div className="flex-1 min-h-0 overflow-auto px-3 pb-3">
                {/* Overview Tab */}
                <TabsContent value="overview" className="space-y-4 mt-3">
                  {/* Risk Status Banner */}
                  <PanelHeader title="Risk Status" panelId="risk-status-card">
                    <div className={cn(
                      'p-3 border rounded-lg',
                      riskStatus.status === 'safe' && 'border-accent-green/30 bg-accent-green/5',
                      riskStatus.status === 'warning' && 'border-yellow-500/30 bg-yellow-500/5',
                      riskStatus.status === 'danger' && 'border-accent-red/30 bg-accent-red/5'
                    )}>
                      <div className="flex items-start gap-2">
                        {riskStatus.status === 'safe' && <Shield className="h-5 w-5 text-accent-green flex-shrink-0 mt-0.5" />}
                        {riskStatus.status === 'warning' && <AlertTriangle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />}
                        {riskStatus.status === 'danger' && <AlertCircle className="h-5 w-5 text-accent-red flex-shrink-0 mt-0.5" />}
                        <div className="flex-1">
                          <p className={cn(
                            'text-sm font-semibold mb-1',
                            riskStatus.status === 'safe' && 'text-accent-green',
                            riskStatus.status === 'warning' && 'text-yellow-400',
                            riskStatus.status === 'danger' && 'text-accent-red'
                          )}>
                            {riskStatus.status === 'safe' && 'Portfolio Risk: Safe'}
                            {riskStatus.status === 'warning' && 'Portfolio Risk: Warning'}
                            {riskStatus.status === 'danger' && 'Portfolio Risk: Danger'}
                          </p>
                          <p className="text-xs text-muted-foreground">{riskStatus.message}</p>
                          {riskStatus.reasons.length > 0 && riskStatus.status !== 'safe' && (
                            <div className="mt-1 space-y-0.5">
                              {riskStatus.reasons.map((reason, idx) => (
                                <p key={idx} className="text-[10px] font-mono text-muted-foreground flex items-center gap-1">
                                  <span className={cn('w-1 h-1 rounded-full flex-shrink-0', reason.includes('DANGER') ? 'bg-accent-red' : 'bg-yellow-400')} />
                                  {reason}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                        <Button variant="outline" size="sm" className="gap-1 text-xs" onClick={() => window.location.href = '/settings'}>
                          <SettingsIcon className="h-3 w-3" /> Limits
                        </Button>
                      </div>
                    </div>
                  </PanelHeader>

                  {/* Risk Metrics Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <MetricCard label="VaR (95%)" value={riskMetrics?.var_95 || 0} format="currency" icon={TrendingDown} tooltip="Value at Risk at 95% confidence level" />
                    <MetricCard label="Max Drawdown" value={riskMetrics?.max_drawdown || 0} format="percentage" icon={TrendingDown} tooltip="Maximum peak-to-trough decline" />
                    <MetricCard label="Current Drawdown" value={riskMetrics?.current_drawdown || 0} format="percentage" trend={riskMetrics && riskMetrics.current_drawdown > 5 ? 'down' : 'neutral'} icon={Activity} tooltip="Current drawdown from peak" />
                    <MetricCard label="Leverage" value={riskMetrics?.leverage || 0} format="number" icon={BarChart3} tooltip="Portfolio leverage ratio" />
                  </div>

                  {/* Risk Limits */}
                  <PanelHeader title="Risk Limits" panelId="risk-limits-card">
                    <div className="p-3 space-y-3">
                      {riskParams && riskMetrics && (
                        <>
                          <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Position Size</span>
                              <span className="font-mono font-semibold">
                                {formatPercentage(accountBalance && accountBalance > 0 && positions.length > 0 ? Math.max(...positions.map(p => (Math.abs((p as any).invested_amount || p.quantity * p.current_price) / accountBalance) * 100)) : 0)} / {formatPercentage(riskParams.max_position_size * 100)}
                              </span>
                            </div>
                            <Progress value={accountBalance && accountBalance > 0 && positions.length > 0 ? (Math.max(...positions.map(p => (Math.abs((p as any).invested_amount || p.quantity * p.current_price) / accountBalance) * 100)) / (riskParams.max_position_size * 100)) * 100 : 0} className="h-1.5" />
                          </div>
                          <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Portfolio Exposure</span>
                              <span className="font-mono font-semibold">
                                {formatPercentage(accountBalance && accountBalance > 0 ? (riskMetrics.total_exposure / accountBalance) * 100 : 0)} / {formatPercentage(riskParams.max_portfolio_exposure * 100)}
                              </span>
                            </div>
                            <Progress value={accountBalance && accountBalance > 0 ? ((riskMetrics.total_exposure / accountBalance) * 100 / (riskParams.max_portfolio_exposure * 100)) * 100 : 0} className="h-1.5" />
                          </div>
                          <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="text-muted-foreground">Daily Loss</span>
                              <span className="font-mono font-semibold">
                                {formatPercentage(riskMetrics.current_drawdown)} / {formatPercentage(riskParams.max_daily_loss * 100)}
                              </span>
                            </div>
                            <Progress value={(riskMetrics.current_drawdown / (riskParams.max_daily_loss * 100)) * 100} className="h-1.5" />
                          </div>
                        </>
                      )}
                    </div>
                  </PanelHeader>

                  {/* Risk Alerts */}
                  <PanelHeader title="Risk Alerts" panelId="risk-alerts-card">
                    <div className="p-3">
                      {riskAlerts.length > 0 ? (
                        <div className="space-y-2">
                          {riskAlerts.map(alert => (
                            <div key={alert.id} className={cn(
                              'p-2 rounded-lg border',
                              alert.severity === 'danger' && 'bg-accent-red/5 border-accent-red/30',
                              alert.severity === 'warning' && 'bg-yellow-500/5 border-yellow-500/30',
                              alert.severity === 'info' && 'bg-blue-500/5 border-blue-500/30'
                            )}>
                              <div className="flex items-start gap-2">
                                {alert.severity === 'danger' && <AlertCircle className="h-3.5 w-3.5 text-accent-red flex-shrink-0 mt-0.5" />}
                                {alert.severity === 'warning' && <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />}
                                {alert.severity === 'info' && <Activity className="h-3.5 w-3.5 text-blue-400 flex-shrink-0 mt-0.5" />}
                                <div className="flex-1 min-w-0">
                                  <p className="text-xs font-semibold">{alert.title}</p>
                                  <p className="text-[10px] text-muted-foreground">{alert.message}</p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-4 text-muted-foreground">
                          <Shield className="h-8 w-8 mx-auto mb-1 opacity-50" />
                          <p className="text-xs">No active risk alerts</p>
                        </div>
                      )}
                    </div>
                  </PanelHeader>
                </TabsContent>

                {/* Positions Tab */}
                <TabsContent value="positions" className="space-y-3 mt-3">
                  <PanelHeader title="Position Risk Analysis" panelId="risk-positions-card">
                    <div className="p-3">
                      <div className="flex flex-col sm:flex-row gap-2 mb-3">
                        <div className="relative flex-1">
                          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                          <Input placeholder="Search symbol..." value={positionSearch} onChange={(e) => setPositionSearch(e.target.value)} className="pl-8 h-8 text-xs" />
                        </div>
                        <Select value={riskLevelFilter} onValueChange={setRiskLevelFilter}>
                          <SelectTrigger className="w-[120px] h-8 text-xs">
                            <SelectValue placeholder="Risk Level" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Levels</SelectItem>
                            <SelectItem value="low">Low</SelectItem>
                            <SelectItem value="medium">Medium</SelectItem>
                            <SelectItem value="high">High</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      {filteredPositions.length > 0 ? (
                        <div className="max-h-[400px] overflow-y-auto">
                          <DataTable columns={positionRiskColumns} data={filteredPositions} pageSize={20} showPagination={true} />
                        </div>
                      ) : (
                        <div className="text-center py-8 text-xs text-muted-foreground">
                          {positionSearch || riskLevelFilter !== 'all' ? 'No positions match your filters' : 'No open positions'}
                        </div>
                      )}
                    </div>
                  </PanelHeader>
                </TabsContent>

                {/* Advanced Tab */}
                <TabsContent value="advanced" className="space-y-4 mt-3">
                  {/* VaR Section */}
                  <PanelHeader title="Value at Risk (VaR)" panelId="risk-var-card">
                    <div className="p-3">
                      <p className="text-[10px] text-muted-foreground mb-2">
                        Historical simulation using {advancedRisk?.var?.trading_days_used || 252} trading days
                      </p>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
                          <p className="text-[10px] text-muted-foreground mb-1">95% VaR (Daily)</p>
                          <p className="text-xl font-bold font-mono text-yellow-400">{formatCurrency(advancedRisk?.var?.var_95 || 0)}</p>
                        </div>
                        <div className="p-3 rounded-lg border border-accent-red/30 bg-accent-red/5">
                          <p className="text-[10px] text-muted-foreground mb-1">99% VaR (Daily)</p>
                          <p className="text-xl font-bold font-mono text-accent-red">{formatCurrency(advancedRisk?.var?.var_99 || 0)}</p>
                        </div>
                      </div>
                    </div>
                  </PanelHeader>

                  {/* Stress Tests */}
                  <PanelHeader title="Stress Test Scenarios" panelId="risk-stress-card">
                    <div className="p-3">
                      {(advancedRisk?.stress_tests || []).length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {(advancedRisk?.stress_tests || []).map((scenario: any, idx: number) => (
                            <div key={idx} className={cn(
                              'p-3 rounded-lg border',
                              scenario.estimated_loss_pct > 5 ? 'border-accent-red/30 bg-accent-red/5' : scenario.estimated_loss_pct > 2 ? 'border-yellow-500/30 bg-yellow-500/5' : 'border-blue-500/30 bg-blue-500/5'
                            )}>
                              <div className="flex items-start justify-between mb-1">
                                <p className="text-xs font-semibold">{scenario.name}</p>
                                <span className={cn('text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded', scenario.estimated_loss_pct > 5 ? 'bg-accent-red/20 text-accent-red' : scenario.estimated_loss_pct > 2 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-blue-500/20 text-blue-400')}>
                                  -{formatPercentage(scenario.estimated_loss_pct)}
                                </span>
                              </div>
                              <p className="text-[10px] text-muted-foreground mb-1">{scenario.description}</p>
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-mono font-semibold text-accent-red">-{formatCurrency(scenario.estimated_loss)}</span>
                                <span className="text-[10px] text-muted-foreground">{scenario.affected_positions} affected</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-6 text-muted-foreground">
                          <Zap className="h-8 w-8 mx-auto mb-1 opacity-50" />
                          <p className="text-xs">No open positions for stress testing</p>
                        </div>
                      )}
                    </div>
                  </PanelHeader>

                  {/* CIO Risk Metrics */}
                  {cioRisk && (
                    <PanelHeader title="CIO Risk Metrics" panelId="risk-cio-card">
                      <div className="p-3 space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-2 rounded border border-[var(--color-dark-border)]">
                            <p className="text-[10px] text-muted-foreground mb-0.5">Gross Exposure</p>
                            <p className="text-sm font-bold font-mono">{formatCurrency(cioRisk.gross_exposure)}</p>
                          </div>
                          <div className="p-2 rounded border border-[var(--color-dark-border)]">
                            <p className="text-[10px] text-muted-foreground mb-0.5">Net Exposure</p>
                            <p className={cn('text-sm font-bold font-mono', cioRisk.net_exposure >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioRisk.net_exposure)}</p>
                          </div>
                          <div className="p-2 rounded border border-[var(--color-dark-border)]">
                            <p className="text-[10px] text-muted-foreground mb-0.5">CVaR (95%)</p>
                            <p className="text-sm font-bold font-mono text-accent-red">{formatCurrency(cioRisk.cvar_95)}</p>
                          </div>
                          <div className="p-2 rounded border border-[var(--color-dark-border)]">
                            <p className="text-[10px] text-muted-foreground mb-0.5">CVaR (99%)</p>
                            <p className="text-sm font-bold font-mono text-accent-red">{formatCurrency(cioRisk.cvar_99)}</p>
                          </div>
                        </div>
                        {/* Risk Budget */}
                        <div className="space-y-2">
                          <div>
                            <div className="flex justify-between text-xs mb-0.5"><span className="text-muted-foreground">VaR Budget</span><span className="font-mono">{cioRisk.var_budget_used_pct?.toFixed(0)}%</span></div>
                            <Progress value={cioRisk.var_budget_used_pct || 0} className="h-1.5" />
                          </div>
                          <div>
                            <div className="flex justify-between text-xs mb-0.5"><span className="text-muted-foreground">Exposure Budget</span><span className="font-mono">{cioRisk.exposure_budget_used_pct?.toFixed(0)}%</span></div>
                            <Progress value={cioRisk.exposure_budget_used_pct || 0} className="h-1.5" />
                          </div>
                          <div>
                            <div className="flex justify-between text-xs mb-0.5"><span className="text-muted-foreground">Drawdown Budget</span><span className="font-mono">{cioRisk.drawdown_budget_used_pct?.toFixed(0)}%</span></div>
                            <Progress value={cioRisk.drawdown_budget_used_pct || 0} className="h-1.5" />
                          </div>
                        </div>
                      </div>
                    </PanelHeader>
                  )}
                </TabsContent>

                {/* History Tab */}
                <TabsContent value="history" className="space-y-4 mt-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground">Historical risk metrics</span>
                    <Select value={timePeriod} onValueChange={(v) => setTimePeriod(v as typeof timePeriod)}>
                      <SelectTrigger className="w-[100px] h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1D">1 Day</SelectItem>
                        <SelectItem value="1W">1 Week</SelectItem>
                        <SelectItem value="1M">1 Month</SelectItem>
                        <SelectItem value="3M">3 Months</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {riskHistory.length > 0 ? (
                    <>
                      <PanelHeader title="VaR Over Time" panelId="risk-var-history">
                        <div className="p-3">
                          <ResponsiveContainer width="100%" height={180}>
                            <LineChart data={riskHistoryData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis dataKey="date" stroke="#9ca3af" style={{ fontSize: '10px' }} />
                              <YAxis stroke="#9ca3af" style={{ fontSize: '10px' }} tickFormatter={(value) => `${(value / 1000).toFixed(1)}k`} />
                              <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', fontSize: '11px' }} formatter={(value: number | undefined) => value !== undefined ? [`${(value ?? 0).toFixed(0)}`, 'VaR'] : ['', 'VaR']} />
                              <Line type="monotone" dataKey="var_95" stroke="#ef4444" strokeWidth={2} dot={false} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </PanelHeader>
                      <PanelHeader title="Drawdown Over Time" panelId="risk-dd-history">
                        <div className="p-3">
                          <ResponsiveContainer width="100%" height={180}>
                            <AreaChart data={riskHistoryData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis dataKey="date" stroke="#9ca3af" style={{ fontSize: '10px' }} />
                              <YAxis stroke="#9ca3af" style={{ fontSize: '10px' }} tickFormatter={(value) => `${(value ?? 0).toFixed(1)}%`} />
                              <RechartsTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', fontSize: '11px' }} formatter={(value: number | undefined) => value !== undefined ? [`${(value ?? 0).toFixed(2)}%`, 'Drawdown'] : ['', 'Drawdown']} />
                              <Area type="monotone" dataKey="drawdown" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} strokeWidth={2} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </PanelHeader>
                    </>
                  ) : (
                    <div className="border border-dashed border-muted-foreground/30 rounded-lg p-6 text-center">
                      <BarChart3 className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
                      <p className="text-xs text-muted-foreground">Risk history data unavailable</p>
                      <Button variant="outline" size="sm" onClick={refresh} className="mt-2 gap-1 text-xs">
                        <RefreshCw className="h-3 w-3" /> Retry
                      </Button>
                    </div>
                  )}
                </TabsContent>

                {/* Exposure Tab */}
                <TabsContent value="exposure" className="space-y-4 mt-3">
                  <PanelHeader title="Sector Exposure" panelId="risk-sector-exposure-tab">
                    <div className="p-3">
                      {sectorPieData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={220}>
                          <PieChart>
                            <Pie data={sectorPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}>
                              {sectorPieData.map((_, idx) => (
                                <Cell key={idx} fill={SECTOR_COLORS[idx % SECTOR_COLORS.length]} />
                              ))}
                            </Pie>
                            <RechartsTooltip contentStyle={{ ...chartTheme.tooltip, fontFamily: chartTheme.fontFamily, fontSize: 11 }} formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(0)}`, 'Invested']} />
                          </PieChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex items-center justify-center h-32 text-xs text-muted-foreground">No position data</div>
                      )}
                    </div>
                  </PanelHeader>

                  {/* Long/Short Exposure */}
                  <PanelHeader title="Long/Short Exposure" panelId="risk-longshort-tab">
                    <div className="p-3">
                      {riskHistory.length > 0 ? (
                        <InteractiveChart
                          data={riskHistory.map((h: any) => ({
                            date: h.date,
                            long: Math.abs(h.exposure || 0) * 0.7,
                            short: -(Math.abs(h.exposure || 0) * 0.3),
                          }))}
                          dataKeys={[
                            { key: 'long', color: designColors.green, type: 'area' },
                            { key: 'short', color: designColors.red, type: 'area' },
                          ]}
                          xAxisKey="date"
                          height={200}
                        />
                      ) : (
                        <div className="flex items-center justify-center h-32 text-xs text-muted-foreground">No exposure history data</div>
                      )}
                    </div>
                  </PanelHeader>
                </TabsContent>
              </div>
            </Tabs>
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (40%) ──────────────────────────────────────────────────
  const sidePanel = (
    <div className="flex flex-col h-full overflow-hidden">
      <PanelHeader
        title="Risk Summary"
        panelId="risk-side"
        onRefresh={refresh}
      >
        <div className="flex flex-col gap-3 p-3 overflow-auto h-full">
          {/* CompactMetricRow: VaR, max sector exposure, long/short ratio, beta */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Sector Exposure Pie */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Sector Exposure</div>
            {sectorPieData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={sectorPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}>
                      {sectorPieData.map((_, idx) => (
                        <Cell key={idx} fill={SECTOR_COLORS[idx % SECTOR_COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem', fontSize: 10 }}
                      formatter={(value: number | string | undefined) => {
                        if (typeof value === 'number') return [formatCurrency(value), 'Invested'];
                        return [value, 'Invested'];
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Sector legend */}
                <div className="space-y-1 mt-2">
                  {sectorPieData.slice(0, 5).map((sector, idx) => (
                    <div key={sector.name} className="flex items-center justify-between text-[10px]">
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: SECTOR_COLORS[idx % SECTOR_COLORS.length] }} />
                        <span className="text-gray-400 truncate">{sector.name}</span>
                      </div>
                      <span className="font-mono text-gray-300">{totalInvested > 0 ? ((sector.value / totalInvested) * 100).toFixed(1) : '0.0'}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-center py-6 text-[10px] text-gray-500">No position data</div>
            )}
          </div>

          {/* Risk Contribution Top 5 Bar */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3 flex-1 min-h-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">
              Risk Contribution — Top 5
            </div>
            {riskContribTop5.length > 0 ? (
              <ResponsiveContainer width="100%" height={Math.max(120, riskContribTop5.length * 24)}>
                <BarChart data={riskContribTop5} layout="vertical" margin={{ left: 40, right: 10, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                  <XAxis type="number" tick={{ fill: chartTheme.axis, fontSize: 9, fontFamily: chartTheme.fontFamily }} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                  <YAxis type="category" dataKey="symbol" tick={{ fill: chartTheme.axis, fontSize: 9, fontFamily: chartTheme.fontFamily }} width={38} />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem', fontSize: 10 }}
                    formatter={(v: number | undefined) => [`${(v ?? 0).toFixed(1)}%`, 'Risk Contribution']}
                  />
                  <Bar dataKey="contribution" fill={designColors.blue} fillOpacity={0.8} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-6 text-[10px] text-gray-500">No position data</div>
            )}
          </div>

          {/* Portfolio Risk Summary */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Portfolio Summary</div>
            <div className="space-y-1.5">
              {[
                { label: 'Total Exposure', value: formatCurrency(riskMetrics?.total_exposure || 0), color: 'text-gray-200' },
                { label: 'Open Positions', value: String(positions.length), color: 'text-gray-200' },
                { label: 'High Risk', value: String(positions.filter(p => p.risk_level === 'high').length), color: 'text-accent-red' },
                { label: 'Margin Util.', value: formatPercentage(riskMetrics?.margin_utilization || 0), color: (riskMetrics?.margin_utilization || 0) > 50 ? 'text-yellow-400' : 'text-gray-200' },
              ].map(item => (
                <div key={item.label} className="flex items-center justify-between">
                  <span className="text-[10px] text-gray-400">{item.label}</span>
                  <span className={cn('text-xs font-mono font-semibold', item.color)}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Loading state ─────────────────────────────────────────────────────
  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="⚠️ Risk Management" description="Loading...">
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────
  if (fetchError && !riskMetrics) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="⚠️ Risk Management" description="Error loading data">
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <AlertCircle className="h-12 w-12 text-accent-red" />
            <h2 className="text-lg font-semibold text-accent-red">{fetchError.title}</h2>
            <p className="text-sm text-muted-foreground">{fetchError.message}</p>
            {fetchError.retryable && (
              <Button variant="outline" onClick={refresh} className="gap-2">
                <RefreshCw className="h-4 w-4" /> Retry
              </Button>
            )}
          </div>
        </PageTemplate>
      </DashboardLayout>
    );
  }

  // ── Return: 2-panel layout ────────────────────────────────────────────
  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="⚠️ Risk Management"
        description={tradingMode === 'DEMO' ? 'Demo Mode' : 'Live Trading'}
        actions={headerActions}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={isRefreshing && !loading} />
          <ResizablePanelLayout
            layoutId="risk-panels"
            direction="horizontal"
            panels={[
              {
                id: 'risk-main',
                defaultSize: 60,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'risk-side',
                defaultSize: 40,
                minSize: 280,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
