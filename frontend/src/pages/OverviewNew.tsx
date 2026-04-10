import { type FC, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity, TrendingUp, TrendingDown, DollarSign, BarChart3, AlertCircle,
  Shield, Target, Zap, Clock, Award, ChevronRight, Layers,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { DashboardLayout } from '../components/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { RefreshButton } from '../components/ui/RefreshButton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { classifyError } from '../lib/errors';
import { toast } from 'sonner';
import { useEffect } from 'react';

interface OverviewNewProps {
  onLogout: () => void;
}

interface DashboardData {
  pnl_periods: Array<{ label: string; pnl_absolute: number; pnl_percent: number }>;
  equity_curve: Array<{ date: string; equity: number; benchmark?: number }>;
  drawdown_data: Array<{ date: string; drawdown_pct: number }>;
  sector_exposure: Array<{ sector: string; allocation_pct: number; pnl: number; pnl_pct: number; position_count: number }>;
  market_regime: { current_regime: string; regime_color: string; regime_description: string };
  health_score: { score: number; drawdown_score: number; concentration_score: number; margin_score: number; diversity_score: number };
  quick_stats: { open_positions: number; active_strategies: number; pending_orders: number; todays_trades: number; win_rate_30d: number };
  account_balance: number;
  account_equity: number;
  available_cash: number;
  total_unrealized_pnl: number;
  total_invested: number;
}

const REGIME_LABELS: Record<string, string> = {
  trending_up: '📈 Trending Up',
  trending_down: '📉 Trending Down',
  ranging_high_vol: '🌊 Ranging (High Vol)',
  ranging_low_vol: '😴 Ranging (Low Vol)',
  unknown: '❓ Unknown',
};

const HEALTH_COLORS = ['#ef4444', '#f59e0b', '#eab308', '#84cc16', '#22c55e'];

function getHealthColor(score: number): string {
  if (score >= 80) return HEALTH_COLORS[4];
  if (score >= 60) return HEALTH_COLORS[3];
  if (score >= 40) return HEALTH_COLORS[2];
  if (score >= 20) return HEALTH_COLORS[1];
  return HEALTH_COLORS[0];
}

function getHealthLabel(score: number): string {
  if (score >= 80) return 'Excellent';
  if (score >= 60) return 'Good';
  if (score >= 40) return 'Fair';
  if (score >= 20) return 'Poor';
  return 'Critical';
}

const SECTOR_COLORS = [
  '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
  '#ef4444', '#ec4899', '#6366f1', '#14b8a6', '#f97316',
];

export const OverviewNew: FC<OverviewNewProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();
  const navigate = useNavigate();

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);

  const fetchDashboard = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getDashboardSummary(tradingMode);
      setDashboard(data);
      setLastFetchedAt(new Date());
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch dashboard:', error);
      const classified = classifyError(error, 'dashboard data');
      toast.error(classified.title, { description: classified.message });
      setLoading(false);
    }
  }, [tradingMode]);

  // usePolling replaces the manual useEffect + fetchDashboard pattern
  const { refresh, isRefreshing } = usePolling({
    fetchFn: fetchDashboard,
    intervalMs: 30000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // WebSocket for live updates — call refresh() instead of fetchDashboard() directly
  useEffect(() => {
    const unsub1 = wsManager.onPositionUpdate(() => { if (tradingMode) refresh(); });
    const unsub2 = wsManager.onOrderUpdate(() => { if (tradingMode) refresh(); });
    return () => { unsub1(); unsub2(); };
  }, [tradingMode, refresh]);

  // Health score pie data
  const healthPieData = useMemo(() => {
    if (!dashboard) return [];
    const s = dashboard.health_score;
    return [
      { name: 'Score', value: s.score },
      { name: 'Remaining', value: 100 - s.score },
    ];
  }, [dashboard?.health_score]);

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  const d = dashboard;

  return (
    <DashboardLayout onLogout={onLogout}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto space-y-6 relative"
      >
        <RefreshIndicator visible={isRefreshing && !loading} />
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 font-mono mb-1">
              ◆ Command Centre
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-gray-400 text-sm">
                {tradingMode === 'DEMO' ? '📊 Demo Mode' : '💰 Live Trading'} — Real-time portfolio intelligence
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
          <RefreshButton loading={isRefreshing} label="Refresh" onClick={refresh} />
        </div>

        {/* P&L Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {d?.pnl_periods.map((period, i) => (
            <motion.div
              key={period.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
            >
              <Card className="relative overflow-hidden">
                <CardContent className="pt-5 pb-4">
                  <p className="text-xs text-muted-foreground font-mono mb-1">{period.label}</p>
                  <p className={cn(
                    'text-xl lg:text-2xl font-bold font-mono',
                    period.pnl_absolute >= 0 ? 'text-accent-green' : 'text-accent-red'
                  )}>
                    {period.pnl_absolute >= 0 ? '+' : ''}{formatCurrency(period.pnl_absolute)}
                  </p>
                  <p className={cn(
                    'text-sm font-mono mt-0.5',
                    period.pnl_percent >= 0 ? 'text-accent-green/80' : 'text-accent-red/80'
                  )}>
                    {formatPercentage(period.pnl_percent)}
                    <span className="text-[10px] text-muted-foreground ml-1">(vs equity)</span>
                  </p>
                  <div className={cn(
                    'absolute top-0 right-0 w-1 h-full',
                    period.pnl_absolute >= 0 ? 'bg-accent-green' : 'bg-accent-red'
                  )} />
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Quick Stats Row */}
        {d?.quick_stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              { label: 'Open Positions', value: d.quick_stats.open_positions, icon: Layers, onClick: () => navigate('/portfolio') },
              { label: 'Active Strategies', value: d.quick_stats.active_strategies, icon: Zap, onClick: () => navigate('/strategies') },
              { label: 'Pending Orders', value: d.quick_stats.pending_orders, icon: Clock, onClick: () => navigate('/orders') },
              { label: "Today's Trades", value: d.quick_stats.todays_trades, icon: Target, onClick: () => navigate('/orders') },
              { label: 'Win Rate (30d)', value: `${d.quick_stats.win_rate_30d}%`, icon: Award, onClick: () => navigate('/analytics') },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: 0.2 + i * 0.03 }}
              >
                <Card
                  className="cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={stat.onClick}
                >
                  <CardContent className="pt-4 pb-3 flex items-center gap-3">
                    <stat.icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs text-muted-foreground truncate">{stat.label}</p>
                      <p className="text-lg font-bold font-mono">{stat.value}</p>
                    </div>
                    <ChevronRight className="h-3 w-3 text-muted-foreground ml-auto flex-shrink-0" />
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        )}

        {/* Main Grid: Equity Curve + Right Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Equity Curve + Drawdown */}
          <div className="lg:col-span-2 space-y-6">
            {/* Equity Curve */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <TrendingUp className="h-4 w-4" />
                    Equity Curve
                  </CardTitle>
                  <CardDescription>Account equity over last 90 days</CardDescription>
                </CardHeader>
                <CardContent>
                  {d?.equity_curve && d.equity_curve.length > 0 ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <AreaChart data={d.equity_curve} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                        <defs>
                          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          tickFormatter={(v) => {
                            const d = new Date(v);
                            return `${d.getMonth() + 1}/${d.getDate()}`;
                          }}
                          interval="preserveStartEnd"
                          minTickGap={40}
                        />
                        <YAxis
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                          width={55}
                        />
                        <RechartsTooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                          labelStyle={{ color: '#9ca3af' }}
                          formatter={(value: any) => [formatCurrency(value as number), 'Equity']}
                          labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        />
                        <Area
                          type="monotone"
                          dataKey="equity"
                          stroke="#3b82f6"
                          strokeWidth={2}
                          fill="url(#equityGradient)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[280px] flex items-center justify-center text-muted-foreground text-sm">
                      No equity data available yet
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Drawdown Chart */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.35 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <TrendingDown className="h-4 w-4 text-accent-red" />
                        Drawdown
                      </CardTitle>
                      <CardDescription>
                        Max drawdown: {d?.drawdown_data?.length
                          ? `${Math.min(...d.drawdown_data.map(p => p.drawdown_pct)).toFixed(2)}%`
                          : 'N/A'}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {d?.drawdown_data && d.drawdown_data.length > 0 ? (
                    <ResponsiveContainer width="100%" height={160}>
                      <AreaChart data={d.drawdown_data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                        <defs>
                          <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          tickFormatter={(v) => {
                            const d = new Date(v);
                            return `${d.getMonth() + 1}/${d.getDate()}`;
                          }}
                          interval="preserveStartEnd"
                          minTickGap={40}
                        />
                        <YAxis
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          tickFormatter={(v) => `${v.toFixed(1)}%`}
                          width={45}
                        />
                        <RechartsTooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                          labelStyle={{ color: '#9ca3af' }}
                          formatter={(value: any) => [`${(value as number).toFixed(2)}%`, 'Drawdown']}
                          labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        />
                        <Area
                          type="monotone"
                          dataKey="drawdown_pct"
                          stroke="#ef4444"
                          strokeWidth={1.5}
                          fill="url(#ddGradient)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[160px] flex items-center justify-center text-muted-foreground text-sm">
                      No drawdown data available
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </div>

          {/* Right Panel: Regime + Health + Exposure */}
          <div className="space-y-6">
            {/* Market Regime Indicator */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" />
                    Market Regime
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {d?.market_regime && (
                    <div className="space-y-3">
                      <div
                        className="flex items-center gap-3 p-3 rounded-lg border"
                        style={{ borderColor: d.market_regime.regime_color + '40', backgroundColor: d.market_regime.regime_color + '10' }}
                      >
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: d.market_regime.regime_color }}
                        />
                        <span className="font-mono font-semibold text-sm">
                          {REGIME_LABELS[d.market_regime.current_regime] || d.market_regime.current_regime}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {d.market_regime.regime_description}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Account Health Score */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.35 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Shield className="h-4 w-4" />
                    Account Health
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {d?.health_score && (
                    <div className="space-y-4">
                      {/* Donut Chart */}
                      <div className="flex items-center justify-center">
                        <div className="relative">
                          <PieChart width={140} height={140}>
                            <Pie
                              data={healthPieData}
                              cx={65}
                              cy={65}
                              innerRadius={45}
                              outerRadius={60}
                              startAngle={90}
                              endAngle={-270}
                              dataKey="value"
                              stroke="none"
                            >
                              <Cell fill={getHealthColor(d.health_score.score)} />
                              <Cell fill="#374151" />
                            </Pie>
                          </PieChart>
                          <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-2xl font-bold font-mono" style={{ color: getHealthColor(d.health_score.score) }}>
                              {d.health_score.score}
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {getHealthLabel(d.health_score.score)}
                            </span>
                          </div>
                        </div>
                      </div>
                      {/* Score Breakdown */}
                      <div className="space-y-2">
                        {[
                          { label: 'Drawdown', score: d.health_score.drawdown_score, max: 25 },
                          { label: 'Concentration', score: d.health_score.concentration_score, max: 25 },
                          { label: 'Margin', score: d.health_score.margin_score, max: 25 },
                          { label: 'Diversity', score: d.health_score.diversity_score, max: 25 },
                        ].map((item) => (
                          <div key={item.label} className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground w-24 truncate">{item.label}</span>
                            <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{
                                  width: `${(item.score / item.max) * 100}%`,
                                  backgroundColor: getHealthColor((item.score / item.max) * 100),
                                }}
                              />
                            </div>
                            <span className="text-xs font-mono w-8 text-right">{item.score}/{item.max}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Sector Exposure */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.4 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <BarChart3 className="h-4 w-4" />
                    Sector Exposure
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {d?.sector_exposure && d.sector_exposure.length > 0 ? (
                    <div className="space-y-2">
                      {d.sector_exposure.map((sector, i) => (
                        <div key={sector.sector} className="flex items-center gap-2">
                          <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }}
                          />
                          <span className="text-xs text-muted-foreground flex-1 truncate">{sector.sector}</span>
                          <span className="text-xs font-mono w-10 text-right">{sector.allocation_pct.toFixed(0)}%</span>
                          <span className={cn(
                            'text-xs font-mono w-16 text-right',
                            sector.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
                          )}>
                            {sector.pnl >= 0 ? '+' : ''}{formatCurrency(sector.pnl)}
                          </span>
                        </div>
                      ))}
                      {d.sector_exposure.length === 0 && (
                        <p className="text-xs text-muted-foreground text-center py-4">No open positions</p>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-6 text-muted-foreground text-sm">
                      No exposure data — no open positions
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Account Summary */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.45 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <DollarSign className="h-4 w-4" />
                    Account
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Equity</span>
                      <span className="font-mono font-semibold text-sm">
                        {d ? formatCurrency(d.account_equity) : '---'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Available to Trade</span>
                      <span className="font-mono font-semibold text-sm text-accent-green">
                        {d ? formatCurrency(d.available_cash) : '---'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Invested</span>
                      <span className="font-mono font-semibold text-sm">
                        {d ? formatCurrency(d.total_invested || 0) : '---'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Unrealised P&L</span>
                      <span className={cn(
                        'font-mono font-semibold text-sm',
                        d && (d.total_unrealized_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'
                      )}>
                        {d ? `${(d.total_unrealized_pnl || 0) >= 0 ? '+' : ''}${formatCurrency(d.total_unrealized_pnl || 0)}` : '---'}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Demo Mode Warning */}
            {tradingMode === 'DEMO' && (
              <Card className="border-yellow-500/30 bg-yellow-500/5">
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-semibold text-yellow-400">Demo Mode</p>
                      <p className="text-[10px] text-yellow-400/70">All trades are simulated</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </motion.div>
    </DashboardLayout>
  );
};
