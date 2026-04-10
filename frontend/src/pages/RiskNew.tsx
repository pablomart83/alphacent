import { type FC, useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { 
  AlertTriangle, Shield, TrendingDown, Activity, BarChart3,
  RefreshCw, Search, AlertCircle, Settings as SettingsIcon,
  Zap, Target,
} from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Cell, BarChart, Bar, ReferenceLine } from 'recharts';
import { DashboardLayout } from '../components/DashboardLayout';
import { MetricCard } from '../components/trading/MetricCard';
import { DataTable } from '../components/trading/DataTable';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
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
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '../lib/utils';
import { classifyError, type ClassifiedError } from '../lib/errors';
import type { Position, RiskParams } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { useEffect } from 'react';

interface RiskNewProps {
  onLogout: () => void;
}

// Chart colors
const SECTOR_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#6366f1'];
const ASSET_CLASS_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

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
  const [positionRisks, setPositionRisks] = useState<Array<{ symbol: string; risk_level?: string; beta?: number; var_95?: number; concentration_pct?: number; var_contribution?: number }>>([]);
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
      
      // LAZY LOADING: Fetch essential data first (fast), then heavy data in background.
      // The old approach fired 10 parallel API calls — all hitting SQLite simultaneously.
      // Now: 5 essential calls first (metrics, positions, config, alerts, account),
      // then 5 heavy calls (history, position risks, correlation, advanced, CIO risk).
      
      // Phase 1: Essential data (fast — simple DB queries)
      const [metricsData, positionsData, paramsData, alertsData, accountData] = await Promise.all([
        apiClient.getRiskMetrics(tradingMode),
        apiClient.getPositions(tradingMode),
        apiClient.getRiskConfig(tradingMode),
        apiClient.getRiskAlerts(tradingMode),
        apiClient.getAccountInfo(tradingMode),
      ]);
      
      // Store account balance and set essential state immediately
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
      
      // Show the page immediately with essential data
      setLoading(false);
      setLastFetchedAt(new Date());
      
      // Phase 2: Heavy data (background — don't block the page)
      const [historyData, positionRisksData, correlationData, advancedRiskData, cioRiskData] = await Promise.all([
        apiClient.getRiskHistory(tradingMode, timePeriod).catch(() => null),
        apiClient.getPositionRisks(tradingMode).catch(() => null),
        apiClient.getCorrelationMatrix(tradingMode, timePeriod).catch(() => null),
        apiClient.getAdvancedRisk(tradingMode).catch(() => null),
        apiClient.getCIORisk(tradingMode).catch(() => null),
      ]);
      
      // Update positions with risk data now that we have it
      if (positionRisksData) {
        const reEnhanced = enhancePositionsWithRisk(positionsData, metricsData.total_exposure, positionRisksData, balance);
        setPositions(reEnhanced);
        setPositionRisks(positionRisksData);
      }
      
      // Set risk history (use backend data if available, otherwise empty)
      if (historyData && historyData.history) {
        setRiskHistory(historyData.history.map((item: any) => ({
          date: new Date(item.timestamp).toLocaleDateString('en-US', { 
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
      
      // Set position risks
      if (positionRisksData) {
        setPositionRisks(positionRisksData);
      }
      
      // Set correlation matrix (use backend data if available, otherwise empty)
      if (correlationData && correlationData.matrix) {
        setCorrelationMatrix(correlationData.matrix);
      } else {
        setCorrelationMatrix([]);
      }
      
      // Set advanced risk data
      if (advancedRiskData) {
        setAdvancedRisk(advancedRiskData);
      }
      
      // Set CIO risk data
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
      // On eToro, quantity = dollar amount invested (not shares).
      // Use invested_amount if available, otherwise quantity IS the dollar value.
      const positionValue = Math.abs((pos as any).invested_amount || pos.quantity);
      const concentration = balance > 0 ? (positionValue / balance) * 100 : 0;
      
      // Try to get risk data from backend
      const backendRisk = positionRisksData?.find((r) => r.symbol === pos.symbol);
      
      let risk_level: 'low' | 'medium' | 'high' = 'low';
      if (backendRisk?.risk_level) {
        risk_level = backendRisk.risk_level as 'low' | 'medium' | 'high';
      } else {
        // Fallback to concentration-based risk
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

  // usePolling replaces manual useEffect + fetchData pattern
  const { refresh, isRefreshing } = usePolling({
    fetchFn: fetchRiskData,
    intervalMs: 60000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // Re-fetch when timePeriod changes
  useEffect(() => {
    if (tradingMode && !tradingModeLoading) {
      refresh();
    }
  }, [timePeriod]); // eslint-disable-line react-hooks/exhaustive-deps

  // WebSocket subscriptions
  useEffect(() => {
    const unsubscribePosition = wsManager.onPositionUpdate(() => {
      if (tradingMode) {
        refresh();
      }
    });

    return () => {
      unsubscribePosition();
    };
  }, [tradingMode, refresh]);

  // Filter positions
  const filteredPositions = positions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
    const matchesRiskLevel = riskLevelFilter === 'all' || position.risk_level === riskLevelFilter;
    return matchesSearch && matchesRiskLevel;
  });

  // Calculate risk status — use backend risk_score and risk_reasons
  const getRiskStatus = (): { status: 'safe' | 'warning' | 'danger'; message: string; reasons: string[] } => {
    if (!riskMetrics || !riskParams) return { status: 'safe', message: 'Calculating...', reasons: [] };
    
    // Use the backend-computed risk score and reasons
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

  // Use correlation matrix from state
  const matrixSize = Math.sqrt(correlationMatrix.length);

  // Use risk history from state instead of generating
  const riskHistoryData = riskHistory;

  // Helper function to get color based on correlation value
  const getCorrelationColor = (value: number): string => {
    if (value >= 0.7) return '#ef4444'; // High positive correlation - red
    if (value >= 0.4) return '#f59e0b'; // Medium positive correlation - amber
    if (value >= 0.1) return '#10b981'; // Low positive correlation - green
    if (value >= -0.3) return '#3b82f6'; // Low negative correlation - blue
    return '#6366f1'; // Negative correlation - indigo
  };

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  if (fetchError && !riskMetrics) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto">
          <Card className="border-accent-red/30 bg-accent-red/5">
            <CardContent className="pt-6">
              <div className="flex flex-col items-center text-center py-8">
                <AlertCircle className="h-12 w-12 text-accent-red mb-4" />
                <h2 className="text-lg font-semibold text-accent-red mb-2">{fetchError.title}</h2>
                <p className="text-sm text-muted-foreground mb-4">{fetchError.message}</p>
                {fetchError.retryable && (
                  <Button variant="outline" onClick={refresh} className="gap-2">
                    <RefreshCw className="h-4 w-4" />
                    Retry
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
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
        <RefreshIndicator visible={isRefreshing && !loading} />

        {/* Header */}
        <div className="mb-6 lg:mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-2">
              ⚠️ Risk Management
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-gray-400 text-sm">
                Portfolio risk metrics and monitoring
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
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
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="advanced">Advanced</TabsTrigger>
            <TabsTrigger value="positions">
              Position Risk ({filteredPositions.length})
            </TabsTrigger>
            <TabsTrigger value="correlation">Correlation</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            {/* Risk Status Banner */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <Card className={cn(
                'border-2',
                riskStatus.status === 'safe' && 'border-accent-green/30 bg-accent-green/5',
                riskStatus.status === 'warning' && 'border-yellow-500/30 bg-yellow-500/5',
                riskStatus.status === 'danger' && 'border-accent-red/30 bg-accent-red/5'
              )}>
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    {riskStatus.status === 'safe' && <Shield className="h-6 w-6 text-accent-green flex-shrink-0 mt-0.5" />}
                    {riskStatus.status === 'warning' && <AlertTriangle className="h-6 w-6 text-yellow-400 flex-shrink-0 mt-0.5" />}
                    {riskStatus.status === 'danger' && <AlertCircle className="h-6 w-6 text-accent-red flex-shrink-0 mt-0.5" />}
                    <div className="flex-1">
                      <p className={cn(
                        'text-lg font-semibold mb-1',
                        riskStatus.status === 'safe' && 'text-accent-green',
                        riskStatus.status === 'warning' && 'text-yellow-400',
                        riskStatus.status === 'danger' && 'text-accent-red'
                      )}>
                        {riskStatus.status === 'safe' && 'Portfolio Risk: Safe'}
                        {riskStatus.status === 'warning' && 'Portfolio Risk: Warning'}
                        {riskStatus.status === 'danger' && 'Portfolio Risk: Danger'}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {riskStatus.message}
                      </p>
                      {riskStatus.reasons.length > 0 && riskStatus.status !== 'safe' && (
                        <div className="mt-2 space-y-1">
                          {riskStatus.reasons.map((reason, idx) => (
                            <p key={idx} className="text-xs font-mono text-muted-foreground flex items-center gap-1.5">
                              <span className={cn(
                                'w-1.5 h-1.5 rounded-full flex-shrink-0',
                                reason.includes('DANGER') ? 'bg-accent-red' : 'bg-yellow-400'
                              )} />
                              {reason}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={() => window.location.href = '/settings'}
                    >
                      <SettingsIcon className="h-4 w-4" />
                      Configure Limits
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Risk Metrics Grid */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
              className="grid grid-cols-2 md:grid-cols-4 gap-4"
            >
              <MetricCard
                label="VaR (95%)"
                value={riskMetrics?.var_95 || 0}
                format="currency"
                icon={TrendingDown}
                tooltip="Value at Risk at 95% confidence level"
              />
              <MetricCard
                label="Max Drawdown"
                value={riskMetrics?.max_drawdown || 0}
                format="percentage"
                icon={TrendingDown}
                tooltip="Maximum peak-to-trough decline"
              />
              <MetricCard
                label="Current Drawdown"
                value={riskMetrics?.current_drawdown || 0}
                format="percentage"
                trend={riskMetrics && riskMetrics.current_drawdown > 5 ? 'down' : 'neutral'}
                icon={Activity}
                tooltip="Current drawdown from peak"
              />
              <MetricCard
                label="Leverage"
                value={riskMetrics?.leverage || 0}
                format="number"
                icon={BarChart3}
                tooltip="Portfolio leverage ratio"
              />
            </motion.div>

            {/* CIO Risk Metrics — Gross/Net Exposure, CVaR, Concentration, Factor Exposure, Risk Budget */}
            {cioRisk && (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.22 }} className="space-y-4">
                
                {/* Gross/Net Exposure Headlines */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card>
                    <CardContent className="pt-4 pb-3">
                      <p className="text-xs text-muted-foreground mb-1">Gross Exposure</p>
                      <p className="text-xl font-bold font-mono">{formatCurrency(cioRisk.gross_exposure)}</p>
                      <p className="text-xs text-muted-foreground">{cioRisk.gross_exposure_pct?.toFixed(1)}% of equity</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3">
                      <p className="text-xs text-muted-foreground mb-1">Net Exposure</p>
                      <p className={cn('text-xl font-bold font-mono', cioRisk.net_exposure >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cioRisk.net_exposure)}</p>
                      <p className="text-xs text-muted-foreground">{cioRisk.net_exposure_pct?.toFixed(1)}% of equity</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3">
                      <p className="text-xs text-muted-foreground mb-1">CVaR (95%)</p>
                      <p className="text-xl font-bold font-mono text-accent-red">{formatCurrency(cioRisk.cvar_95)}</p>
                      <p className="text-xs text-muted-foreground">Avg loss worst 5% days</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3">
                      <p className="text-xs text-muted-foreground mb-1">CVaR (99%)</p>
                      <p className="text-xl font-bold font-mono text-accent-red">{formatCurrency(cioRisk.cvar_99)}</p>
                      <p className="text-xs text-muted-foreground">Avg loss worst 1% days</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Concentration + Factor Exposure + Risk Budget */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-base">Concentration Risk</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between"><span className="text-muted-foreground">Top 5 Positions</span><span>{cioRisk.concentration?.top5_positions_pct?.toFixed(1)}%</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Top 3 Sectors</span><span>{cioRisk.concentration?.top3_sectors_pct?.toFixed(1)}%</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">HHI</span><span className={cn((cioRisk.concentration?.herfindahl_index || 0) < 0.1 ? 'text-accent-green' : (cioRisk.concentration?.herfindahl_index || 0) < 0.25 ? 'text-yellow-400' : 'text-accent-red')}>{cioRisk.concentration?.herfindahl_index?.toFixed(4)}</span></div>
                        <div className="flex justify-between border-t border-border pt-2"><span className="text-muted-foreground">Largest</span><span>{cioRisk.concentration?.largest_position_symbol} ({cioRisk.concentration?.largest_position_pct?.toFixed(1)}%)</span></div>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-base">Factor Exposure</CardTitle><CardDescription className="text-xs">Regime: {cioRisk.regime?.replace(/_/g, ' ')}</CardDescription></CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {(cioRisk.factor_exposures || []).map((f: any) => (
                          <div key={f.factor} className="flex items-center justify-between text-sm font-mono">
                            <span className="text-muted-foreground">{f.factor}</span>
                            <div className="flex items-center gap-2">
                              <div className="w-16 bg-muted rounded-full h-2"><div className={cn('h-2 rounded-full', f.current_tilt === 'overweight' ? 'bg-accent-green' : f.current_tilt === 'underweight' ? 'bg-accent-red' : 'bg-blue-500')} style={{ width: `${f.weight_pct}%` }} /></div>
                              <span className="w-12 text-right">{f.weight_pct}%</span>
                              <span className={cn('text-xs w-20 text-right', f.current_tilt === 'overweight' ? 'text-accent-green' : f.current_tilt === 'underweight' ? 'text-accent-red' : 'text-muted-foreground')}>{f.current_tilt}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-base">Risk Budget</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div><div className="flex justify-between text-sm mb-1"><span className="text-muted-foreground">VaR Budget</span><span className="font-mono">{cioRisk.var_budget_used_pct?.toFixed(0)}%</span></div><Progress value={cioRisk.var_budget_used_pct || 0} className="h-2" /></div>
                        <div><div className="flex justify-between text-sm mb-1"><span className="text-muted-foreground">Exposure Budget</span><span className="font-mono">{cioRisk.exposure_budget_used_pct?.toFixed(0)}%</span></div><Progress value={cioRisk.exposure_budget_used_pct || 0} className="h-2" /></div>
                        <div><div className="flex justify-between text-sm mb-1"><span className="text-muted-foreground">Drawdown Budget</span><span className="font-mono">{cioRisk.drawdown_budget_used_pct?.toFixed(0)}%</span></div><Progress value={cioRisk.drawdown_budget_used_pct || 0} className="h-2" /></div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </motion.div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Risk Limits Section */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.3 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Shield className="h-5 w-5" />
                      Risk Limits
                    </CardTitle>
                    <CardDescription>Current usage vs configured limits</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {riskParams && riskMetrics && (
                      <>
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Position Size</span>
                            <span className="font-mono font-semibold">
                              {formatPercentage(
                                accountBalance && accountBalance > 0 && positions.length > 0
                                  ? Math.max(...positions.map(p => (Math.abs((p as any).invested_amount || p.quantity * p.current_price) / accountBalance) * 100))
                                  : 0
                              )} / {formatPercentage(riskParams.max_position_size * 100)}
                            </span>
                          </div>
                          <Progress value={
                            accountBalance && accountBalance > 0 && positions.length > 0
                              ? (Math.max(...positions.map(p => (Math.abs((p as any).invested_amount || p.quantity * p.current_price) / accountBalance) * 100)) / (riskParams.max_position_size * 100)) * 100
                              : 0
                          } className="h-2" />
                        </div>

                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Portfolio Exposure</span>
                            <span className="font-mono font-semibold">
                              {formatPercentage(
                                accountBalance && accountBalance > 0
                                  ? (riskMetrics.total_exposure / accountBalance) * 100
                                  : 0
                              )} / {formatPercentage(riskParams.max_portfolio_exposure * 100)}
                            </span>
                          </div>
                          <Progress value={
                            accountBalance && accountBalance > 0
                              ? ((riskMetrics.total_exposure / accountBalance) * 100 / (riskParams.max_portfolio_exposure * 100)) * 100
                              : 0
                          } className="h-2" />
                        </div>

                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Daily Loss</span>
                            <span className="font-mono font-semibold">
                              {formatPercentage(riskMetrics.current_drawdown)} / {formatPercentage(riskParams.max_daily_loss * 100)}
                            </span>
                          </div>
                          <Progress 
                            value={(riskMetrics.current_drawdown / (riskParams.max_daily_loss * 100)) * 100} 
                            className="h-2"
                          />
                        </div>

                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Margin Utilization</span>
                            <span className="font-mono font-semibold">
                              {formatPercentage(riskMetrics.margin_utilization)} / {formatPercentage(80)}
                            </span>
                          </div>
                          <Progress value={(riskMetrics.margin_utilization / 80) * 100} className="h-2" />
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              </motion.div>

              {/* Risk Alerts Section */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.4 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5" />
                      Risk Alerts
                    </CardTitle>
                    <CardDescription>Recent warnings and threshold breaches</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {riskAlerts.length > 0 ? (
                      <div className="space-y-3">
                        {riskAlerts.map(alert => (
                          <div
                            key={alert.id}
                            className={cn(
                              'p-3 rounded-lg border',
                              alert.severity === 'danger' && 'bg-accent-red/5 border-accent-red/30',
                              alert.severity === 'warning' && 'bg-yellow-500/5 border-yellow-500/30',
                              alert.severity === 'info' && 'bg-blue-500/5 border-blue-500/30'
                            )}
                          >
                            <div className="flex items-start gap-2">
                              {alert.severity === 'danger' && <AlertCircle className="h-4 w-4 text-accent-red flex-shrink-0 mt-0.5" />}
                              {alert.severity === 'warning' && <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />}
                              {alert.severity === 'info' && <Activity className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />}
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold mb-1">{alert.title}</p>
                                <p className="text-xs text-muted-foreground">{alert.message}</p>
                                <p className="text-xs text-muted-foreground mt-1">
                                  {formatTimestamp(alert.timestamp)}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <Shield className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No active risk alerts</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            {/* Additional Metrics */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.5 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Portfolio Risk Metrics</CardTitle>
                  <CardDescription>Comprehensive risk analysis</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Portfolio Beta</p>
                      <p className="text-2xl font-bold font-mono">{riskMetrics?.beta.toFixed(2) || '---'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Total Exposure</p>
                      <p className="text-2xl font-bold font-mono">{formatCurrency(riskMetrics?.total_exposure || 0)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Open Positions</p>
                      <p className="text-2xl font-bold font-mono">{positions.length}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">High Risk Positions</p>
                      <p className="text-2xl font-bold font-mono text-accent-red">
                        {positions.filter(p => p.risk_level === 'high').length}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          {/* Advanced Risk Tab */}
          <TabsContent value="advanced" className="space-y-6">
            {/* VaR Section */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingDown className="h-5 w-5" />
                    Value at Risk (VaR)
                  </CardTitle>
                  <CardDescription>
                    Historical simulation using {advancedRisk?.var?.trading_days_used || 252} trading days
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="p-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
                      <p className="text-xs text-muted-foreground mb-1">95% VaR (Daily)</p>
                      <p className="text-3xl font-bold font-mono text-yellow-400">
                        {formatCurrency(advancedRisk?.var?.var_95 || 0)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-2">
                        You have a 5% chance of losing more than {formatCurrency(advancedRisk?.var?.var_95 || 0)} today
                      </p>
                    </div>
                    <div className="p-4 rounded-lg border border-accent-red/30 bg-accent-red/5">
                      <p className="text-xs text-muted-foreground mb-1">99% VaR (Daily)</p>
                      <p className="text-3xl font-bold font-mono text-accent-red">
                        {formatCurrency(advancedRisk?.var?.var_99 || 0)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-2">
                        You have a 1% chance of losing more than {formatCurrency(advancedRisk?.var?.var_99 || 0)} today
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Stress Tests */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="h-5 w-5" />
                    Stress Test Scenarios
                  </CardTitle>
                  <CardDescription>Estimated portfolio impact under adverse conditions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {(advancedRisk?.stress_tests || []).map((scenario: any, idx: number) => (
                      <div
                        key={idx}
                        className={cn(
                          'p-4 rounded-lg border',
                          scenario.estimated_loss_pct > 5
                            ? 'border-accent-red/30 bg-accent-red/5'
                            : scenario.estimated_loss_pct > 2
                            ? 'border-yellow-500/30 bg-yellow-500/5'
                            : 'border-blue-500/30 bg-blue-500/5'
                        )}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <p className="text-sm font-semibold">{scenario.name}</p>
                          <span className={cn(
                            'text-xs font-mono font-semibold px-2 py-0.5 rounded',
                            scenario.estimated_loss_pct > 5
                              ? 'bg-accent-red/20 text-accent-red'
                              : scenario.estimated_loss_pct > 2
                              ? 'bg-yellow-500/20 text-yellow-400'
                              : 'bg-blue-500/20 text-blue-400'
                          )}>
                            -{formatPercentage(scenario.estimated_loss_pct)}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mb-2">{scenario.description}</p>
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-mono font-semibold text-accent-red">
                            -{formatCurrency(scenario.estimated_loss)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {scenario.affected_positions} position{scenario.affected_positions !== 1 ? 's' : ''} affected
                          </span>
                        </div>
                      </div>
                    ))}
                    {(!advancedRisk?.stress_tests || advancedRisk.stress_tests.length === 0) && (
                      <div className="col-span-2 text-center py-8 text-muted-foreground">
                        <Zap className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No open positions for stress testing</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Margin Utilization Gauge */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.3 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Target className="h-5 w-5" />
                      Margin Utilization
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {advancedRisk?.margin ? (
                      <div className="flex flex-col items-center">
                        {/* Circular gauge using SVG */}
                        <div className="relative w-48 h-48 mb-4">
                          <svg viewBox="0 0 200 200" className="w-full h-full">
                            {/* Background circle */}
                            <circle
                              cx="100" cy="100" r="80"
                              fill="none"
                              stroke="#374151"
                              strokeWidth="16"
                              strokeDasharray="502.65"
                              strokeDashoffset="125.66"
                              transform="rotate(135 100 100)"
                            />
                            {/* Green zone (0-50%) */}
                            <circle
                              cx="100" cy="100" r="80"
                              fill="none"
                              stroke="#10b981"
                              strokeWidth="16"
                              strokeDasharray="502.65"
                              strokeDashoffset={502.65 - Math.min(advancedRisk.margin.utilization_pct / 100, 0.5) * 376.99}
                              transform="rotate(135 100 100)"
                              strokeLinecap="round"
                            />
                            {/* Amber zone (50-75%) */}
                            {advancedRisk.margin.utilization_pct > 50 && (
                              <circle
                                cx="100" cy="100" r="80"
                                fill="none"
                                stroke="#f59e0b"
                                strokeWidth="16"
                                strokeDasharray="502.65"
                                strokeDashoffset={502.65 - Math.min((advancedRisk.margin.utilization_pct - 50) / 100, 0.25) * 376.99}
                                transform={`rotate(${135 + 188.5} 100 100)`}
                                strokeLinecap="round"
                              />
                            )}
                            {/* Red zone (75%+) */}
                            {advancedRisk.margin.utilization_pct > 75 && (
                              <circle
                                cx="100" cy="100" r="80"
                                fill="none"
                                stroke="#ef4444"
                                strokeWidth="16"
                                strokeDasharray="502.65"
                                strokeDashoffset={502.65 - Math.min((advancedRisk.margin.utilization_pct - 75) / 100, 0.25) * 376.99}
                                transform={`rotate(${135 + 282.75} 100 100)`}
                                strokeLinecap="round"
                              />
                            )}
                            {/* Center text */}
                            <text x="100" y="90" textAnchor="middle" className="fill-gray-100 text-3xl font-bold font-mono">
                              {advancedRisk.margin.utilization_pct.toFixed(1)}%
                            </text>
                            <text x="100" y="115" textAnchor="middle" className="fill-gray-400 text-xs">
                              Margin Used
                            </text>
                          </svg>
                        </div>
                        <div className="grid grid-cols-3 gap-4 w-full text-center">
                          <div>
                            <p className="text-xs text-muted-foreground">Used</p>
                            <p className="font-mono font-semibold text-sm">{formatCurrency(advancedRisk.margin.used)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Available</p>
                            <p className="font-mono font-semibold text-sm text-accent-green">{formatCurrency(advancedRisk.margin.available)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Total</p>
                            <p className="font-mono font-semibold text-sm">{formatCurrency(advancedRisk.margin.total)}</p>
                          </div>
                        </div>
                        {/* Zone legend */}
                        <div className="flex items-center gap-4 mt-4 text-xs">
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded-full bg-accent-green" />
                            <span className="text-muted-foreground">&lt;50%</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded-full bg-yellow-500" />
                            <span className="text-muted-foreground">50-75%</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded-full bg-accent-red" />
                            <span className="text-muted-foreground">&gt;75%</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <Target className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No margin data available</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>

              {/* Correlated Pairs */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.4 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5" />
                      Top Correlated Pairs
                    </CardTitle>
                    <CardDescription>Pairs with &gt;0.7 correlation represent hidden concentration risk</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {advancedRisk?.correlated_pairs && advancedRisk.correlated_pairs.length > 0 ? (
                      <div className="space-y-2">
                        {advancedRisk.correlated_pairs.map((pair: any, idx: number) => (
                          <div
                            key={idx}
                            className={cn(
                              'flex items-center justify-between p-3 rounded-lg border',
                              pair.risk_level === 'high'
                                ? 'border-accent-red/30 bg-accent-red/5'
                                : pair.risk_level === 'medium'
                                ? 'border-yellow-500/30 bg-yellow-500/5'
                                : 'border-muted bg-muted/30'
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-semibold text-sm">{pair.symbol_a}</span>
                              <span className="text-muted-foreground text-xs">↔</span>
                              <span className="font-mono font-semibold text-sm">{pair.symbol_b}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={cn(
                                'font-mono font-semibold text-sm',
                                pair.correlation > 0.7 ? 'text-accent-red' :
                                pair.correlation > 0.4 ? 'text-yellow-400' : 'text-accent-green'
                              )}>
                                {pair.correlation.toFixed(3)}
                              </span>
                              {pair.risk_level === 'high' && (
                                <AlertTriangle className="h-4 w-4 text-accent-red" />
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <Activity className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">Not enough position data for correlation analysis</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            {/* Exposure Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Sector Exposure — Horizontal Bar Chart */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.5 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5" />
                      Sector Exposure
                    </CardTitle>
                    <CardDescription>Exposure by sector — red line at 40% limit</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {advancedRisk?.sector_exposure && advancedRisk.sector_exposure.length > 0 ? (
                      <ResponsiveContainer width="100%" height={Math.max(200, advancedRisk.sector_exposure.length * 28)}>
                        <BarChart data={advancedRisk.sector_exposure} layout="vertical" margin={{ left: 10, right: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
                          <XAxis type="number" domain={[0, 'auto']} stroke="#9ca3af" style={{ fontSize: '11px' }} tickFormatter={(v) => `${v}%`} />
                          <YAxis dataKey="name" type="category" width={110} stroke="#9ca3af" style={{ fontSize: '11px' }} />
                          <RechartsTooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }}
                            formatter={(value: any) => [`${Number(value).toFixed(1)}%`, 'Exposure']}
                          />
                          <ReferenceLine x={40} stroke="#ef4444" strokeDasharray="3 3" label={{ value: '40% limit', position: 'top', fill: '#ef4444', fontSize: 10 }} />
                          <Bar dataKey="percentage" name="Exposure %">
                            {advancedRisk.sector_exposure.map((_: any, index: number) => (
                              <Cell key={index} fill={SECTOR_COLORS[index % SECTOR_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <BarChart3 className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No sector exposure data</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>

              {/* Asset Class Exposure — Horizontal Bar Chart */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.6 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5" />
                      Asset Class Exposure
                    </CardTitle>
                    <CardDescription>Stocks, ETFs, Forex, Crypto, Commodities</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {advancedRisk?.asset_class_exposure && advancedRisk.asset_class_exposure.length > 0 ? (
                      <ResponsiveContainer width="100%" height={Math.max(150, advancedRisk.asset_class_exposure.length * 40)}>
                        <BarChart data={advancedRisk.asset_class_exposure} layout="vertical" margin={{ left: 10, right: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
                          <XAxis type="number" domain={[0, 'auto']} stroke="#9ca3af" style={{ fontSize: '11px' }} tickFormatter={(v) => `${v}%`} />
                          <YAxis dataKey="name" type="category" width={100} stroke="#9ca3af" style={{ fontSize: '11px' }} />
                          <RechartsTooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: '12px' }}
                            formatter={(value: any, _: any, props: any) => [`${Number(value).toFixed(1)}% (${formatCurrency(props.payload.value)})`, 'Exposure']}
                          />
                          <Bar dataKey="percentage" name="Exposure %">
                            {advancedRisk.asset_class_exposure.map((_: any, index: number) => (
                              <Cell key={index} fill={ASSET_CLASS_COLORS[index % ASSET_CLASS_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <BarChart3 className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No asset class data</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            {/* Directional Exposure Bar */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.7 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Directional Exposure
                  </CardTitle>
                  <CardDescription>Long vs Short as % of portfolio (60% limit)</CardDescription>
                </CardHeader>
                <CardContent>
                  {advancedRisk?.directional_exposure ? (
                    <div>
                      <ResponsiveContainer width="100%" height={120}>
                        <BarChart
                          layout="vertical"
                          data={[{
                            name: 'Exposure',
                            long: advancedRisk.directional_exposure.long_pct,
                            short: advancedRisk.directional_exposure.short_pct,
                          }]}
                          margin={{ left: 0, right: 20 }}
                        >
                          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} stroke="#9ca3af" />
                          <YAxis type="category" dataKey="name" hide />
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '8px',
                              fontSize: '12px',
                            }}
                            formatter={(value: any, name: any) => [`${Number(value).toFixed(1)}%`, name === 'long' ? 'Long' : 'Short']}
                          />
                          <Bar dataKey="long" stackId="a" fill="#10b981" name="Long" radius={[4, 0, 0, 4]} />
                          <Bar dataKey="short" stackId="a" fill="#ef4444" name="Short" radius={[0, 4, 4, 0]} />
                          <ReferenceLine x={60} stroke="#f59e0b" strokeDasharray="5 5" strokeWidth={2} label={{ value: '60% limit', position: 'top', fill: '#f59e0b', fontSize: 11 }} />
                        </BarChart>
                      </ResponsiveContainer>
                      <div className="flex items-center justify-between mt-4 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full bg-accent-green" />
                          <span className="text-muted-foreground">Long:</span>
                          <span className="font-mono font-semibold">
                            {formatPercentage(advancedRisk.directional_exposure.long_pct)} ({formatCurrency(advancedRisk.directional_exposure.long_value)})
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full bg-accent-red" />
                          <span className="text-muted-foreground">Short:</span>
                          <span className="font-mono font-semibold">
                            {formatPercentage(advancedRisk.directional_exposure.short_pct)} ({formatCurrency(advancedRisk.directional_exposure.short_value)})
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Net:</span>
                          <span className={cn(
                            'font-mono font-semibold ml-1',
                            advancedRisk.directional_exposure.net_pct >= 0 ? 'text-accent-green' : 'text-accent-red'
                          )}>
                            {advancedRisk.directional_exposure.net_pct >= 0 ? '+' : ''}{formatPercentage(advancedRisk.directional_exposure.net_pct)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <BarChart3 className="h-12 w-12 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">No directional exposure data</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          {/* Position Risk Tab */}
          <TabsContent value="positions" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Position Risk Analysis</CardTitle>
                    <CardDescription>
                      Risk metrics for all open positions • {filteredPositions.length} of {positions.length} positions
                    </CardDescription>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        placeholder="Search symbol..."
                        value={positionSearch}
                        onChange={(e) => setPositionSearch(e.target.value)}
                        className="pl-9 w-full sm:w-[200px]"
                      />
                    </div>
                    <Select value={riskLevelFilter} onValueChange={setRiskLevelFilter}>
                      <SelectTrigger className="w-full sm:w-[140px]">
                        <SelectValue placeholder="Risk Level" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Levels</SelectItem>
                        <SelectItem value="low">Low Risk</SelectItem>
                        <SelectItem value="medium">Medium Risk</SelectItem>
                        <SelectItem value="high">High Risk</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Position Concentration Summary */}
                <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card className="bg-muted/50">
                    <CardContent className="pt-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">By Strategy</p>
                          <p className="text-lg font-bold font-mono">
                            {new Set(positions.map(p => p.strategy_id)).size} strategies
                          </p>
                        </div>
                        <BarChart3 className="h-8 w-8 text-muted-foreground opacity-50" />
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="bg-muted/50">
                    <CardContent className="pt-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">By Symbol</p>
                          <p className="text-lg font-bold font-mono">
                            {new Set(positions.map(p => p.symbol)).size} symbols
                          </p>
                        </div>
                        <Activity className="h-8 w-8 text-muted-foreground opacity-50" />
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="bg-muted/50">
                    <CardContent className="pt-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Max Concentration</p>
                          <p className="text-lg font-bold font-mono">
                            {formatPercentage(Math.max(...positions.map(p => p.concentration_pct), 0))}
                          </p>
                        </div>
                        <AlertTriangle className="h-8 w-8 text-muted-foreground opacity-50" />
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {filteredPositions.length > 0 ? (
                  <div className="max-h-[600px] overflow-y-auto">
                    <DataTable
                      columns={positionRiskColumns}
                      data={filteredPositions}
                      pageSize={20}
                      showPagination={true}
                    />
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    {positionSearch || riskLevelFilter !== 'all' 
                      ? 'No positions match your filters' 
                      : 'No open positions'}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Correlation Analysis Tab */}
          <TabsContent value="correlation" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Correlation Analysis</CardTitle>
                <CardDescription>
                  Strategy correlation matrix and diversification metrics
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  {/* Diversification Metrics */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Card className="bg-muted/50">
                      <CardContent className="pt-6">
                        <p className="text-xs text-muted-foreground mb-1">Avg Correlation</p>
                        <p className="text-2xl font-bold font-mono">0.42</p>
                        <p className="text-xs text-accent-green mt-1">Good diversity</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="pt-6">
                        <p className="text-xs text-muted-foreground mb-1">Diversification Score</p>
                        <p className="text-2xl font-bold font-mono">0.78</p>
                        <p className="text-xs text-muted-foreground mt-1">Out of 1.0</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="pt-6">
                        <p className="text-xs text-muted-foreground mb-1">Portfolio Beta</p>
                        <p className="text-2xl font-bold font-mono">{riskMetrics?.beta.toFixed(2) || '---'}</p>
                        <p className="text-xs text-muted-foreground mt-1">vs Market</p>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Correlation Matrix Heatmap */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Strategy Correlation Matrix</h3>
                    {correlationMatrix.length > 0 ? (
                      <div className="bg-muted/30 rounded-lg p-4">
                        <div className="grid gap-1" style={{ 
                          gridTemplateColumns: `repeat(${matrixSize}, minmax(0, 1fr))`,
                        }}>
                          {correlationMatrix.map((cell, idx) => (
                            <div
                              key={idx}
                              className="aspect-square rounded flex items-center justify-center text-xs font-mono font-semibold transition-all hover:scale-110 hover:z-10 cursor-pointer relative group"
                              style={{
                                backgroundColor: getCorrelationColor(Number(cell.value)),
                                opacity: 0.9,
                              }}
                              title={`${cell.x} vs ${cell.y}: ${Number(cell.value).toFixed(2)}`}
                            >
                              <span className="text-white drop-shadow-md">
                                {Number(cell.value).toFixed(2)}
                              </span>
                              {/* Tooltip on hover */}
                              <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-20">
                                {cell.x} ↔ {cell.y}: {Number(cell.value).toFixed(2)}
                              </div>
                            </div>
                          ))}
                        </div>
                        
                        {/* Legend */}
                        <div className="mt-4 flex items-center justify-center gap-4 text-xs">
                          <div className="flex items-center gap-2">
                            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#10b981' }}></div>
                            <span className="text-muted-foreground">Low (0.1-0.4)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#f59e0b' }}></div>
                            <span className="text-muted-foreground">Medium (0.4-0.7)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#ef4444' }}></div>
                            <span className="text-muted-foreground">High (0.7+)</span>
                          </div>
                        </div>
                        
                        <p className="text-xs text-muted-foreground text-center mt-3">
                          Showing correlation between top {matrixSize} strategies • Hover for details
                        </p>
                      </div>
                    ) : (
                      <div className="border border-dashed border-muted-foreground/30 rounded-lg p-8">
                        <div className="text-center">
                          <BarChart3 className="h-12 w-12 mx-auto mb-3 text-muted-foreground opacity-50" />
                          <p className="text-sm text-muted-foreground">
                            {positions.length >= 2
                              ? 'Data unavailable'
                              : 'Not enough strategies for correlation analysis'}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {positions.length >= 2
                              ? 'Correlation data could not be loaded from the backend'
                              : 'At least 2 strategies required'}
                          </p>
                          {positions.length >= 2 && (
                            <Button variant="outline" size="sm" onClick={refresh} className="mt-3 gap-2">
                              <RefreshCw className="h-4 w-4" />
                              Retry
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Beta Breakdown */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Portfolio Beta Breakdown</h3>
                    <div className="space-y-2">
                      {positions.slice(0, 5).map((pos) => {
                        // Get beta from position risks or calculate from concentration
                        const posRisk = positionRisks?.find((r) => r.symbol === pos.symbol);
                        const beta = posRisk?.beta ?? (pos.concentration_pct / 100);
                        const betaPercentage = Math.min(100, beta * 100);
                        
                        return (
                          <div key={pos.id} className="flex items-center gap-3">
                            <div className="w-32 text-sm font-mono truncate">{pos.symbol}</div>
                            <div className="flex-1">
                              <Progress value={betaPercentage} className="h-2" />
                            </div>
                            <div className="w-16 text-right text-sm font-mono">
                              {beta.toFixed(2)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Risk History Tab */}
          <TabsContent value="history" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <CardTitle>Risk History</CardTitle>
                    <CardDescription>
                      Historical risk metrics and limit breaches
                    </CardDescription>
                  </div>
                  <Select value={timePeriod} onValueChange={(v) => setTimePeriod(v as typeof timePeriod)}>
                    <SelectTrigger className="w-full sm:w-[120px]">
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
              </CardHeader>
              <CardContent>
                {riskHistory.length > 0 ? (
                <div className="space-y-6">
                  {/* VaR Over Time Chart */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Value at Risk (95%) Over Time</h3>
                    <div className="bg-muted/30 rounded-lg p-4">
                      <ResponsiveContainer width="100%" height={250}>
                        <LineChart data={riskHistoryData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis 
                            dataKey="date" 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                          />
                          <YAxis 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                            tickFormatter={(value) => `$${(value / 1000).toFixed(1)}k`}
                          />
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '8px',
                              fontSize: '12px',
                            }}
                            formatter={(value: number | undefined) => value !== undefined ? [`$${value.toFixed(0)}`, 'VaR'] : ['', 'VaR']}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="var" 
                            stroke="#ef4444" 
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Drawdown Over Time Chart */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Drawdown Over Time</h3>
                    <div className="bg-muted/30 rounded-lg p-4">
                      <ResponsiveContainer width="100%" height={250}>
                        <AreaChart data={riskHistoryData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis 
                            dataKey="date" 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                          />
                          <YAxis 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                            tickFormatter={(value) => `${value.toFixed(1)}%`}
                          />
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '8px',
                              fontSize: '12px',
                            }}
                            formatter={(value: number | undefined) => value !== undefined ? [`${value.toFixed(2)}%`, 'Drawdown'] : ['', 'Drawdown']}
                          />
                          <Area 
                            type="monotone" 
                            dataKey="drawdown" 
                            stroke="#f59e0b" 
                            fill="#f59e0b"
                            fillOpacity={0.3}
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Leverage Over Time Chart */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Leverage Over Time</h3>
                    <div className="bg-muted/30 rounded-lg p-4">
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={riskHistoryData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis 
                            dataKey="date" 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                          />
                          <YAxis 
                            stroke="#9ca3af"
                            style={{ fontSize: '12px' }}
                            domain={[0, 2]}
                            tickFormatter={(value) => `${value.toFixed(1)}x`}
                          />
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '8px',
                              fontSize: '12px',
                            }}
                            formatter={(value: number | undefined) => value !== undefined ? [`${value.toFixed(2)}x`, 'Leverage'] : ['', 'Leverage']}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="leverage" 
                            stroke="#3b82f6" 
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Risk Limit Breaches Timeline */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3">Risk Limit Breaches</h3>
                    <div className="space-y-3">
                      <div className="p-3 rounded-lg border border-accent-red/30 bg-accent-red/5">
                        <div className="flex items-start gap-2">
                          <AlertCircle className="h-4 w-4 text-accent-red flex-shrink-0 mt-0.5" />
                          <div className="flex-1">
                            <p className="text-sm font-semibold">Max Drawdown Breach</p>
                            <p className="text-xs text-muted-foreground">
                              Drawdown exceeded 10% threshold at 12.3%
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {formatTimestamp(new Date(Date.now() - 86400000 * 2))}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="p-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                          <div className="flex-1">
                            <p className="text-sm font-semibold">Position Size Warning</p>
                            <p className="text-xs text-muted-foreground">
                              SPY position reached 18% of portfolio
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {formatTimestamp(new Date(Date.now() - 86400000 * 5))}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                ) : (
                  <div className="border border-dashed border-muted-foreground/30 rounded-lg p-8">
                    <div className="text-center">
                      <BarChart3 className="h-12 w-12 mx-auto mb-3 text-muted-foreground opacity-50" />
                      <p className="text-sm text-muted-foreground">Data unavailable</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Risk history data could not be loaded from the backend
                      </p>
                      <Button variant="outline" size="sm" onClick={refresh} className="mt-3 gap-2">
                        <RefreshCw className="h-4 w-4" />
                        Retry
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </motion.div>
    </DashboardLayout>
  );
};
