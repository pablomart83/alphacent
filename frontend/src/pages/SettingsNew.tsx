import { type FC, useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { motion } from 'framer-motion';
import { 
  Settings as SettingsIcon, Shield, Bell, Key, Activity,
  Save, RotateCcw, Eye, EyeOff, CheckCircle, RefreshCw,
  AlertTriangle, Info, Target, Keyboard, Users,
  UserPlus, Trash2, RotateCw
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { SectionLabel } from '../components/ui/SectionLabel';
import { Button } from '../components/ui/Button';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { Input } from '../components/ui/Input';
import { Label } from '../components/ui/Label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Switch } from '../components/ui/switch';
import { Checkbox } from '../components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { authService } from '../services/auth';
import { formatDate, formatDateTime } from '../lib/date-utils';
import { TradingMode, type ApiUsageStats } from '../types';
import { cn } from '../lib/utils';
import { toast } from 'sonner';
import { KEYBOARD_SHORTCUTS } from '../hooks/useKeyboardShortcuts';

interface SettingsNewProps {
  onLogout: () => void;
}

// Validation schemas
const apiConfigSchema = z.object({
  publicKey: z.string().min(1, 'Public key is required'),
  userKey: z.string().min(1, 'User key is required'),
});

const riskLimitsSchema = z.object({
  max_position_size_pct: z.number().min(0).max(100),
  max_exposure_pct: z.number().min(0).max(100),
  max_daily_loss_pct: z.number().min(0).max(100),
  max_drawdown_pct: z.number().min(0).max(100),
  position_risk_pct: z.number().min(0).max(100),
  stop_loss_pct: z.number().min(0).max(100),
  take_profit_pct: z.number().min(0).max(100),
});

const autonomousConfigSchema = z.object({
  // ─── Core ──────────────────────────────────────────────────────────
  enabled: z.boolean(),
  proposal_count: z.number().min(10).max(500),
  max_active_strategies: z.number().min(5).max(500),
  min_active_strategies: z.number().min(3).max(25),
  watchlist_size: z.number().min(1).max(20),
  backtested_ttl_cycles: z.number().min(6).max(200),
  signal_generation_interval: z.number().min(300).max(3600),
  dynamic_symbol_additions: z.number().min(0).max(50),

  // ─── Activation — Sharpe / WR / DD ────────────────────────────────
  min_sharpe: z.number().min(0).max(3.0),
  min_sharpe_crypto: z.number().min(0).max(3.0),
  min_sharpe_commodity: z.number().min(0).max(3.0),
  max_drawdown: z.number().min(5).max(50),
  min_win_rate: z.number().min(20).max(80),
  min_win_rate_crypto: z.number().min(15).max(70),
  min_win_rate_commodity: z.number().min(20).max(70),

  // ─── Activation — Min Trades ──────────────────────────────────────
  min_trades: z.number().min(1).max(50),
  min_trades_dsl: z.number().min(1).max(50),
  min_trades_dsl_4h: z.number().min(1).max(50),
  min_trades_dsl_1h: z.number().min(1).max(100),
  min_trades_alpha_edge: z.number().min(1).max(50),
  min_trades_crypto_1d: z.number().min(1).max(50),
  min_trades_crypto_4h: z.number().min(1).max(50),
  min_trades_crypto_1h: z.number().min(1).max(100),
  min_trades_commodity: z.number().min(1).max(50),

  // ─── Activation — Min Return Per Trade (percentages) ──────────────
  min_rpt_stock: z.number().min(0).max(20),
  min_rpt_stock_4h: z.number().min(0).max(20),
  min_rpt_stock_1h: z.number().min(0).max(10),
  min_rpt_etf: z.number().min(0).max(20),
  min_rpt_etf_4h: z.number().min(0).max(20),
  min_rpt_etf_1h: z.number().min(0).max(10),
  min_rpt_forex: z.number().min(0).max(10),
  min_rpt_forex_1h: z.number().min(0).max(5),
  min_rpt_crypto: z.number().min(0).max(30),
  min_rpt_crypto_1d: z.number().min(0).max(30),
  min_rpt_crypto_4h: z.number().min(0).max(30),
  min_rpt_crypto_1h: z.number().min(0).max(20),
  min_rpt_index: z.number().min(0).max(20),
  min_rpt_index_1h: z.number().min(0).max(10),
  min_rpt_commodity: z.number().min(0).max(20),
  min_rpt_commodity_4h: z.number().min(0).max(20),

  // ─── Retirement ─────────────────────────────────────────────────────
  retirement_max_sharpe: z.number().min(-1.0).max(2.0),
  retirement_max_drawdown: z.number().min(5).max(50),
  retirement_min_win_rate: z.number().min(15).max(60),
  retirement_min_trades_for_evaluation: z.number().min(3).max(100),
  retirement_min_live_trades: z.number().min(1).max(50),
  retirement_rolling_window_days: z.number().min(7).max(365),
  retirement_consecutive_failures: z.number().min(1).max(10),
  retirement_probation_days: z.number().min(1).max(365),

  // ─── Walk-Forward ──────────────────────────────────────────────────
  wf_train_days: z.number().min(30).max(1460),
  wf_test_days: z.number().min(30).max(1460),

  // Direction-aware thresholds (5 regimes × long/short × 3 metrics + default)
  da_default_min_return: z.number().min(-0.2).max(0.2),
  da_default_min_sharpe: z.number().min(-0.5).max(2.0),
  da_default_min_win_rate: z.number().min(0.2).max(0.8),
  da_ranging_long_min_return: z.number().min(-0.2).max(0.2),
  da_ranging_long_min_sharpe: z.number().min(-0.5).max(2.0),
  da_ranging_long_min_win_rate: z.number().min(0.2).max(0.8),
  da_ranging_short_min_return: z.number().min(-0.2).max(0.2),
  da_ranging_short_min_sharpe: z.number().min(-0.5).max(2.0),
  da_ranging_short_min_win_rate: z.number().min(0.2).max(0.8),
  da_trending_up_long_min_return: z.number().min(-0.2).max(0.2),
  da_trending_up_long_min_sharpe: z.number().min(-0.5).max(2.0),
  da_trending_up_long_min_win_rate: z.number().min(0.2).max(0.8),
  da_trending_up_short_min_return: z.number().min(-0.2).max(0.2),
  da_trending_up_short_min_sharpe: z.number().min(-0.5).max(2.0),
  da_trending_up_short_min_win_rate: z.number().min(0.2).max(0.8),
  da_trending_down_long_min_return: z.number().min(-0.2).max(0.2),
  da_trending_down_long_min_sharpe: z.number().min(-0.5).max(2.0),
  da_trending_down_long_min_win_rate: z.number().min(0.2).max(0.8),
  da_trending_down_short_min_return: z.number().min(-0.2).max(0.2),
  da_trending_down_short_min_sharpe: z.number().min(-0.5).max(2.0),
  da_trending_down_short_min_win_rate: z.number().min(0.2).max(0.8),
  da_high_vol_long_min_return: z.number().min(-0.2).max(0.2),
  da_high_vol_long_min_sharpe: z.number().min(-0.5).max(2.0),
  da_high_vol_long_min_win_rate: z.number().min(0.2).max(0.8),
  da_high_vol_short_min_return: z.number().min(-0.2).max(0.2),
  da_high_vol_short_min_sharpe: z.number().min(-0.5).max(2.0),
  da_high_vol_short_min_win_rate: z.number().min(0.2).max(0.8),

  // ─── Adaptive Risk ──────────────────────────────────────────────────
  adaptive_risk_enabled: z.boolean(),
  adaptive_min_sl_pct: z.number().min(0.5).max(20),
  adaptive_max_sl_pct: z.number().min(1).max(30),
  adaptive_min_tp_pct: z.number().min(1).max(30),
  adaptive_max_tp_pct: z.number().min(2).max(50),
  adaptive_min_rr_ratio: z.number().min(0.5).max(5),

  // ─── Performance Feedback ──────────────────────────────────────────
  feedback_lookback_days: z.number().min(7).max(365),
  feedback_min_trades: z.number().min(1).max(50),
  feedback_max_weight: z.number().min(1.0).max(3.0),
  feedback_min_weight: z.number().min(0.1).max(1.0),
  feedback_weight_decay_per_day: z.number().min(0).max(0.1),

  // ─── Directional Balance + Quotas ──────────────────────────────────
  directional_balance_enabled: z.boolean(),
  directional_min_long_pct: z.number().min(0).max(100),
  directional_max_long_pct: z.number().min(0).max(100),
  directional_min_short_pct: z.number().min(0).max(100),
  directional_max_short_pct: z.number().min(0).max(100),
  // Per-regime quotas
  dq_enabled: z.boolean(),
  dq_adjacent_regime_reserve_pct: z.number().min(0).max(100),
  dq_ranging_long: z.number().min(0).max(100),
  dq_ranging_short: z.number().min(0).max(100),
  dq_ranging_low_vol_long: z.number().min(0).max(100),
  dq_ranging_low_vol_short: z.number().min(0).max(100),
  dq_trending_up_long: z.number().min(0).max(100),
  dq_trending_up_short: z.number().min(0).max(100),
  dq_trending_up_weak_long: z.number().min(0).max(100),
  dq_trending_up_weak_short: z.number().min(0).max(100),
  dq_trending_up_strong_long: z.number().min(0).max(100),
  dq_trending_up_strong_short: z.number().min(0).max(100),
  dq_trending_down_long: z.number().min(0).max(100),
  dq_trending_down_short: z.number().min(0).max(100),
  dq_trending_down_weak_long: z.number().min(0).max(100),
  dq_trending_down_weak_short: z.number().min(0).max(100),
  dq_high_volatility_long: z.number().min(0).max(100),
  dq_high_volatility_short: z.number().min(0).max(100),

  // ─── Portfolio balance / sector caps ───────────────────────────────
  max_long_exposure_pct: z.number().min(10).max(100),
  max_short_exposure_pct: z.number().min(10).max(100),
  max_sector_exposure_pct: z.number().min(10).max(100),
});

const positionManagementSchema = z.object({
  trailing_stop_enabled: z.boolean(),
  trailing_stop_activation_pct: z.number().min(0).max(100),
  trailing_stop_distance_pct: z.number().min(0).max(100),
  partial_exit_enabled: z.boolean(),
  partial_exit_levels: z.array(z.object({
    profit_pct: z.number().min(0).max(100),
    exit_pct: z.number().min(0).max(100),
  })),
  correlation_adjustment_enabled: z.boolean(),
  correlation_threshold: z.number().min(0).max(1),
  correlation_reduction_factor: z.number().min(0).max(1),
  regime_based_sizing_enabled: z.boolean(),
  regime_multipliers: z.object({
    high_volatility: z.number().min(0).max(2),
    low_volatility: z.number().min(0).max(2),
    trending: z.number().min(0).max(2),
    ranging: z.number().min(0).max(2),
  }),
  cancel_stale_orders: z.boolean(),
  stale_order_hours: z.number().min(1).max(168),
});

const alphaEdgeSchema = z.object({
  fundamental_filters_enabled: z.boolean(),
  fundamental_min_checks_passed: z.number().min(1).max(5),
  fundamental_checks: z.object({
    profitable: z.boolean(),
    growing: z.boolean(),
    reasonable_valuation: z.boolean(),
    no_dilution: z.boolean(),
    insider_buying: z.boolean(),
  }),
  ml_filter_enabled: z.boolean(),
  ml_min_confidence: z.number().min(50).max(95),
  ml_retrain_frequency_days: z.number().min(1).max(90),
  max_active_strategies: z.number().min(5).max(20),
  min_conviction_score: z.number().min(50).max(90),
  min_holding_period_days: z.number().min(1).max(30),
  max_trades_per_strategy_per_month: z.number().min(1).max(10),
  earnings_momentum_enabled: z.boolean(),
  sector_rotation_enabled: z.boolean(),
  quality_mean_reversion_enabled: z.boolean(),
});

type ApiConfigFormData = z.infer<typeof apiConfigSchema>;
type RiskLimitsFormData = z.infer<typeof riskLimitsSchema>;
type AutonomousConfigFormData = z.infer<typeof autonomousConfigSchema>;
type PositionManagementFormData = z.infer<typeof positionManagementSchema>;
type AlphaEdgeFormData = z.infer<typeof alphaEdgeSchema>;

export const SettingsNew: FC<SettingsNewProps> = ({ onLogout }) => {
  const { tradingMode: contextTradingMode, setTradingMode: setContextTradingMode } = useTradingMode();
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; message: string } | null>(null);
  const [checkingConnection, setCheckingConnection] = useState(false);
  const [showTradingModeDialog, setShowTradingModeDialog] = useState(false);
  const [pendingTradingMode, setPendingTradingMode] = useState<TradingMode | null>(null);
  const [apiUsage, setApiUsage] = useState<ApiUsageStats | null>(null);
  // Read-only audit view of yaml fields that aren't editable from the UI
  // (cost model, validation rules, symbol counts, data source status).
  // Populated by the /config/autonomous GET response.
  const [autonomousAdvanced, setAutonomousAdvanced] = useState<any>(null);
  
  // Alert configuration state
  const [alertConfig, setAlertConfig] = useState({
    pnl_loss_enabled: false,
    pnl_loss_threshold: 1000,
    pnl_gain_enabled: false,
    pnl_gain_threshold: 5000,
    drawdown_enabled: true,
    drawdown_threshold: 10,
    position_loss_enabled: true,
    position_loss_threshold: 5,
    margin_enabled: false,
    margin_threshold: 80,
    cycle_complete_enabled: true,
    strategy_retired_enabled: true,
    browser_push_enabled: false,
  });
  const [alertConfigLoading, setAlertConfigLoading] = useState(false);

  // User management state
  const [userList, setUserList] = useState<any[]>([]);
  const [userListLoading, setUserListLoading] = useState(false);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('viewer');
  const [createUserLoading, setCreateUserLoading] = useState(false);
  const [changePasswordOld, setChangePasswordOld] = useState('');
  const [changePasswordNew, setChangePasswordNew] = useState('');
  const [changePasswordConfirm, setChangePasswordConfirm] = useState('');
  const [changePasswordLoading, setChangePasswordLoading] = useState(false);
  const [resetPasswordUser, setResetPasswordUser] = useState<string | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState('');
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<string | null>(null);
  const isAdmin = authService.isAdmin();

  // API Config Form
  const apiForm = useForm<ApiConfigFormData>({
    resolver: zodResolver(apiConfigSchema),
    defaultValues: {
      publicKey: '',
      userKey: '',
    },
  });

  // Risk Limits Form
  const riskForm = useForm<RiskLimitsFormData>({
    resolver: zodResolver(riskLimitsSchema),
    defaultValues: {
      max_position_size_pct: 10,
      max_exposure_pct: 50,
      max_daily_loss_pct: 5,
      max_drawdown_pct: 15,
      position_risk_pct: 2,
      stop_loss_pct: 2,
      take_profit_pct: 4,
    },
  });

  // Autonomous Config Form
  const autonomousForm = useForm<AutonomousConfigFormData>({
    resolver: zodResolver(autonomousConfigSchema),
    defaultValues: {
      // Core
      enabled: true,
      proposal_count: 200,
      max_active_strategies: 200,
      min_active_strategies: 10,
      watchlist_size: 5,
      backtested_ttl_cycles: 168,
      signal_generation_interval: 1800,
      dynamic_symbol_additions: 0,
      // Activation — Sharpe / WR / DD
      min_sharpe: 1.0,
      min_sharpe_crypto: 0.3,
      min_sharpe_commodity: 0.5,
      max_drawdown: 25,
      min_win_rate: 45,
      min_win_rate_crypto: 30,
      min_win_rate_commodity: 35,
      // Min Trades
      min_trades: 2,
      min_trades_dsl: 8,
      min_trades_dsl_4h: 8,
      min_trades_dsl_1h: 15,
      min_trades_alpha_edge: 8,
      min_trades_crypto_1d: 4,
      min_trades_crypto_4h: 4,
      min_trades_crypto_1h: 15,
      min_trades_commodity: 6,
      // Min RPT
      min_rpt_stock: 0.15,
      min_rpt_stock_4h: 0.08,
      min_rpt_stock_1h: 0.03,
      min_rpt_etf: 0.1,
      min_rpt_etf_4h: 0.05,
      min_rpt_etf_1h: 0.02,
      min_rpt_forex: 0.05,
      min_rpt_forex_1h: 0.01,
      min_rpt_crypto: 5.0,
      min_rpt_crypto_1d: 3.0,
      min_rpt_crypto_4h: 3.0,
      min_rpt_crypto_1h: 3.0,
      min_rpt_index: 0.1,
      min_rpt_index_1h: 0.02,
      min_rpt_commodity: 0.15,
      min_rpt_commodity_4h: 0.08,
      // Retirement
      retirement_max_sharpe: 0.0,
      retirement_max_drawdown: 31,
      retirement_min_win_rate: 28,
      retirement_min_trades_for_evaluation: 10,
      retirement_min_live_trades: 5,
      retirement_rolling_window_days: 60,
      retirement_consecutive_failures: 3,
      retirement_probation_days: 30,
      // Walk-forward
      wf_train_days: 365,
      wf_test_days: 180,
      // Direction-aware defaults
      da_default_min_return: 0,
      da_default_min_sharpe: 0.3,
      da_default_min_win_rate: 0.45,
      da_ranging_long_min_return: -0.02,
      da_ranging_long_min_sharpe: 0.15,
      da_ranging_long_min_win_rate: 0.4,
      da_ranging_short_min_return: 0,
      da_ranging_short_min_sharpe: 0.3,
      da_ranging_short_min_win_rate: 0.45,
      da_trending_up_long_min_return: 0,
      da_trending_up_long_min_sharpe: 0.3,
      da_trending_up_long_min_win_rate: 0.45,
      da_trending_up_short_min_return: -0.02,
      da_trending_up_short_min_sharpe: 0.15,
      da_trending_up_short_min_win_rate: 0.4,
      da_trending_down_long_min_return: -0.02,
      da_trending_down_long_min_sharpe: 0.15,
      da_trending_down_long_min_win_rate: 0.4,
      da_trending_down_short_min_return: 0,
      da_trending_down_short_min_sharpe: 0.3,
      da_trending_down_short_min_win_rate: 0.45,
      da_high_vol_long_min_return: -0.01,
      da_high_vol_long_min_sharpe: 0.2,
      da_high_vol_long_min_win_rate: 0.42,
      da_high_vol_short_min_return: -0.01,
      da_high_vol_short_min_sharpe: 0.2,
      da_high_vol_short_min_win_rate: 0.42,
      // Adaptive risk
      adaptive_risk_enabled: true,
      adaptive_min_sl_pct: 2.0,
      adaptive_max_sl_pct: 8.0,
      adaptive_min_tp_pct: 4.0,
      adaptive_max_tp_pct: 20.0,
      adaptive_min_rr_ratio: 1.5,
      // Performance feedback
      feedback_lookback_days: 60,
      feedback_min_trades: 5,
      feedback_max_weight: 1.5,
      feedback_min_weight: 0.4,
      feedback_weight_decay_per_day: 0.01,
      // Directional balance + quotas
      directional_balance_enabled: true,
      directional_min_long_pct: 30,
      directional_max_long_pct: 70,
      directional_min_short_pct: 20,
      directional_max_short_pct: 50,
      dq_enabled: true,
      dq_adjacent_regime_reserve_pct: 20,
      dq_ranging_long: 70,
      dq_ranging_short: 0,
      dq_ranging_low_vol_long: 75,
      dq_ranging_low_vol_short: 0,
      dq_trending_up_long: 80,
      dq_trending_up_short: 5,
      dq_trending_up_weak_long: 75,
      dq_trending_up_weak_short: 8,
      dq_trending_up_strong_long: 85,
      dq_trending_up_strong_short: 3,
      dq_trending_down_long: 20,
      dq_trending_down_short: 50,
      dq_trending_down_weak_long: 30,
      dq_trending_down_weak_short: 30,
      dq_high_volatility_long: 30,
      dq_high_volatility_short: 10,
      // Portfolio balance
      max_long_exposure_pct: 65,
      max_short_exposure_pct: 60,
      max_sector_exposure_pct: 40,
    },
  });

  // Position Management Form
  const positionManagementForm = useForm<PositionManagementFormData>({
    resolver: zodResolver(positionManagementSchema),
    defaultValues: {
      trailing_stop_enabled: true,
      trailing_stop_activation_pct: 5,
      trailing_stop_distance_pct: 3,
      partial_exit_enabled: true,
      partial_exit_levels: [
        { profit_pct: 5, exit_pct: 50 },
        { profit_pct: 10, exit_pct: 25 },
      ],
      correlation_adjustment_enabled: true,
      correlation_threshold: 0.7,
      correlation_reduction_factor: 0.5,
      regime_based_sizing_enabled: false,
      regime_multipliers: {
        high_volatility: 0.5,
        low_volatility: 1.0,
        trending: 1.2,
        ranging: 0.8,
      },
      cancel_stale_orders: true,
      stale_order_hours: 24,
    },
  });

  // Alpha Edge Form
  const alphaEdgeForm = useForm<AlphaEdgeFormData>({
    resolver: zodResolver(alphaEdgeSchema),
    defaultValues: {
      fundamental_filters_enabled: true,
      fundamental_min_checks_passed: 4,
      fundamental_checks: {
        profitable: true,
        growing: true,
        reasonable_valuation: true,
        no_dilution: true,
        insider_buying: true,
      },
      ml_filter_enabled: true,
      ml_min_confidence: 70,
      ml_retrain_frequency_days: 30,
      max_active_strategies: 10,
      min_conviction_score: 70,
      min_holding_period_days: 7,
      max_trades_per_strategy_per_month: 4,
      earnings_momentum_enabled: false,
      sector_rotation_enabled: false,
      quality_mean_reversion_enabled: false,
    },
  });

  // Load configuration on mount
  useEffect(() => {
    loadConfiguration();
  }, []);

  const loadConfiguration = async () => {
    try {
      setLoading(true);
      
      const [
        _appConfig,
        riskConfig,
        alphaEdgeSettings,
        autonomousConfig,
        apiUsageData,
        alertConfigData,
      ] = await Promise.all([
        apiClient.getAppConfig().catch(err => { console.error('Failed to load app config:', err); return null; }),
        contextTradingMode ? apiClient.getRiskConfig(contextTradingMode).catch(err => { console.error('Failed to load risk config:', err); return null; }) as Promise<any> : Promise.resolve(null),
        apiClient.getAlphaEdgeSettings().catch(err => { console.error('Failed to load Alpha Edge settings:', err); return null; }),
        apiClient.getAutonomousConfig().catch(err => { console.error('Failed to load autonomous config:', err); return null; }),
        apiClient.getAlphaEdgeApiUsage().catch(err => { console.error('Failed to load API usage:', err); return null; }),
        apiClient.getAlertConfig().catch(() => null),
      ]);

      if (riskConfig) {
        riskForm.reset({
          max_position_size_pct: (riskConfig.max_position_size_pct || 0.1) * 100,
          max_exposure_pct: (riskConfig.max_exposure_pct || 0.5) * 100,
          max_daily_loss_pct: (riskConfig.max_daily_loss_pct || 0.05) * 100,
          max_drawdown_pct: (riskConfig.max_drawdown_pct || 0.15) * 100,
          position_risk_pct: (riskConfig.position_risk_pct || 0.02) * 100,
          stop_loss_pct: (riskConfig.stop_loss_pct || 0.02) * 100,
          take_profit_pct: (riskConfig.take_profit_pct || 0.04) * 100,
        });
        
        positionManagementForm.reset({
          trailing_stop_enabled: riskConfig.trailing_stop_enabled ?? true,
          trailing_stop_activation_pct: (riskConfig.trailing_stop_activation_pct ?? 0.05) * 100,
          trailing_stop_distance_pct: (riskConfig.trailing_stop_distance_pct ?? 0.03) * 100,
          partial_exit_enabled: riskConfig.partial_exit_enabled ?? true,
          partial_exit_levels: riskConfig.partial_exit_levels?.map((level: { profit_pct: number; exit_pct: number }) => ({
            profit_pct: level.profit_pct * 100,
            exit_pct: level.exit_pct * 100,
          })) ?? [
            { profit_pct: 5, exit_pct: 50 },
            { profit_pct: 10, exit_pct: 25 },
          ],
          correlation_adjustment_enabled: riskConfig.correlation_adjustment_enabled ?? true,
          correlation_threshold: riskConfig.correlation_threshold ?? 0.7,
          correlation_reduction_factor: riskConfig.correlation_reduction_factor ?? 0.5,
          regime_based_sizing_enabled: riskConfig.regime_based_sizing_enabled ?? false,
          regime_multipliers: riskConfig.regime_multipliers ?? {
            high_volatility: 0.5,
            low_volatility: 1.0,
            trending: 1.2,
            ranging: 0.8,
          },
          cancel_stale_orders: riskConfig.cancel_stale_orders ?? true,
          stale_order_hours: riskConfig.stale_order_hours ?? 24,
        });
      }

      if (autonomousConfig) {
        // Helper to safely map nested direction-aware and quota blocks
        const da = autonomousConfig.direction_aware_thresholds || {};
        const daDefault = da.default || {};
        const daRanging = da.ranging || {};
        const daTrendingUp = da.trending_up || {};
        const daTrendingDown = da.trending_down || {};
        const daHighVol = da.high_vol || {};
        const dq = autonomousConfig.directional_quotas || {};
        const num = (v: any, def: number) => typeof v === 'number' ? v : def;

        autonomousForm.reset({
          // Core
          enabled: autonomousConfig.enabled ?? true,
          proposal_count: num(autonomousConfig.proposal_count, 200),
          max_active_strategies: num(autonomousConfig.max_active_strategies, 200),
          min_active_strategies: num(autonomousConfig.min_active_strategies, 10),
          watchlist_size: num(autonomousConfig.watchlist_size, 5),
          backtested_ttl_cycles: num(autonomousConfig.backtested_ttl_cycles, 168),
          signal_generation_interval: num(autonomousConfig.signal_generation_interval, 1800),
          dynamic_symbol_additions: num(autonomousConfig.dynamic_symbol_additions, 0),
          // Activation — Sharpe / WR / DD
          min_sharpe: num(autonomousConfig.min_sharpe, 1.0),
          min_sharpe_crypto: num(autonomousConfig.min_sharpe_crypto, 0.3),
          min_sharpe_commodity: num(autonomousConfig.min_sharpe_commodity, 0.5),
          max_drawdown: num(autonomousConfig.max_drawdown, 25),
          min_win_rate: num(autonomousConfig.min_win_rate, 45),
          min_win_rate_crypto: num(autonomousConfig.min_win_rate_crypto, 30),
          min_win_rate_commodity: num(autonomousConfig.min_win_rate_commodity, 35),
          // Min Trades
          min_trades: num(autonomousConfig.min_trades, 2),
          min_trades_dsl: num(autonomousConfig.min_trades_dsl, 8),
          min_trades_dsl_4h: num(autonomousConfig.min_trades_dsl_4h, 8),
          min_trades_dsl_1h: num(autonomousConfig.min_trades_dsl_1h, 15),
          min_trades_alpha_edge: num(autonomousConfig.min_trades_alpha_edge, 8),
          min_trades_crypto_1d: num(autonomousConfig.min_trades_crypto_1d, 4),
          min_trades_crypto_4h: num(autonomousConfig.min_trades_crypto_4h, 4),
          min_trades_crypto_1h: num(autonomousConfig.min_trades_crypto_1h, 15),
          min_trades_commodity: num(autonomousConfig.min_trades_commodity, 6),
          // Min RPT (already as percentage from API)
          min_rpt_stock: num(autonomousConfig.min_rpt_stock, 0.15),
          min_rpt_stock_4h: num(autonomousConfig.min_rpt_stock_4h, 0.08),
          min_rpt_stock_1h: num(autonomousConfig.min_rpt_stock_1h, 0.03),
          min_rpt_etf: num(autonomousConfig.min_rpt_etf, 0.1),
          min_rpt_etf_4h: num(autonomousConfig.min_rpt_etf_4h, 0.05),
          min_rpt_etf_1h: num(autonomousConfig.min_rpt_etf_1h, 0.02),
          min_rpt_forex: num(autonomousConfig.min_rpt_forex, 0.05),
          min_rpt_forex_1h: num(autonomousConfig.min_rpt_forex_1h, 0.01),
          min_rpt_crypto: num(autonomousConfig.min_rpt_crypto, 5.0),
          min_rpt_crypto_1d: num(autonomousConfig.min_rpt_crypto_1d, 3.0),
          min_rpt_crypto_4h: num(autonomousConfig.min_rpt_crypto_4h, 3.0),
          min_rpt_crypto_1h: num(autonomousConfig.min_rpt_crypto_1h, 3.0),
          min_rpt_index: num(autonomousConfig.min_rpt_index, 0.1),
          min_rpt_index_1h: num(autonomousConfig.min_rpt_index_1h, 0.02),
          min_rpt_commodity: num(autonomousConfig.min_rpt_commodity, 0.15),
          min_rpt_commodity_4h: num(autonomousConfig.min_rpt_commodity_4h, 0.08),
          // Retirement
          retirement_max_sharpe: num(autonomousConfig.retirement_max_sharpe, 0),
          retirement_max_drawdown: num(autonomousConfig.retirement_max_drawdown, 31),
          retirement_min_win_rate: num(autonomousConfig.retirement_min_win_rate, 28),
          retirement_min_trades_for_evaluation: num(autonomousConfig.retirement_min_trades_for_evaluation, 10),
          retirement_min_live_trades: num(autonomousConfig.retirement_min_live_trades, 5),
          retirement_rolling_window_days: num(autonomousConfig.retirement_rolling_window_days, 60),
          retirement_consecutive_failures: num(autonomousConfig.retirement_consecutive_failures, 3),
          retirement_probation_days: num(autonomousConfig.retirement_probation_days, 30),
          // Walk-forward
          wf_train_days: num(autonomousConfig.wf_train_days, 365),
          wf_test_days: num(autonomousConfig.wf_test_days, 180),
          // Direction-aware defaults (yaml stores decimals; keep as-is for the form since these are typically tiny)
          da_default_min_return: num(daDefault.min_return, 0),
          da_default_min_sharpe: num(daDefault.min_sharpe, 0.3),
          da_default_min_win_rate: num(daDefault.min_win_rate, 0.45),
          da_ranging_long_min_return: num(daRanging.long?.min_return, -0.02),
          da_ranging_long_min_sharpe: num(daRanging.long?.min_sharpe, 0.15),
          da_ranging_long_min_win_rate: num(daRanging.long?.min_win_rate, 0.4),
          da_ranging_short_min_return: num(daRanging.short?.min_return, 0),
          da_ranging_short_min_sharpe: num(daRanging.short?.min_sharpe, 0.3),
          da_ranging_short_min_win_rate: num(daRanging.short?.min_win_rate, 0.45),
          da_trending_up_long_min_return: num(daTrendingUp.long?.min_return, 0),
          da_trending_up_long_min_sharpe: num(daTrendingUp.long?.min_sharpe, 0.3),
          da_trending_up_long_min_win_rate: num(daTrendingUp.long?.min_win_rate, 0.45),
          da_trending_up_short_min_return: num(daTrendingUp.short?.min_return, -0.02),
          da_trending_up_short_min_sharpe: num(daTrendingUp.short?.min_sharpe, 0.15),
          da_trending_up_short_min_win_rate: num(daTrendingUp.short?.min_win_rate, 0.4),
          da_trending_down_long_min_return: num(daTrendingDown.long?.min_return, -0.02),
          da_trending_down_long_min_sharpe: num(daTrendingDown.long?.min_sharpe, 0.15),
          da_trending_down_long_min_win_rate: num(daTrendingDown.long?.min_win_rate, 0.4),
          da_trending_down_short_min_return: num(daTrendingDown.short?.min_return, 0),
          da_trending_down_short_min_sharpe: num(daTrendingDown.short?.min_sharpe, 0.3),
          da_trending_down_short_min_win_rate: num(daTrendingDown.short?.min_win_rate, 0.45),
          da_high_vol_long_min_return: num(daHighVol.long?.min_return, -0.01),
          da_high_vol_long_min_sharpe: num(daHighVol.long?.min_sharpe, 0.2),
          da_high_vol_long_min_win_rate: num(daHighVol.long?.min_win_rate, 0.42),
          da_high_vol_short_min_return: num(daHighVol.short?.min_return, -0.01),
          da_high_vol_short_min_sharpe: num(daHighVol.short?.min_sharpe, 0.2),
          da_high_vol_short_min_win_rate: num(daHighVol.short?.min_win_rate, 0.42),
          // Adaptive risk
          adaptive_risk_enabled: autonomousConfig.adaptive_risk_enabled ?? true,
          adaptive_min_sl_pct: num(autonomousConfig.adaptive_min_sl_pct, 2),
          adaptive_max_sl_pct: num(autonomousConfig.adaptive_max_sl_pct, 8),
          adaptive_min_tp_pct: num(autonomousConfig.adaptive_min_tp_pct, 4),
          adaptive_max_tp_pct: num(autonomousConfig.adaptive_max_tp_pct, 20),
          adaptive_min_rr_ratio: num(autonomousConfig.adaptive_min_rr_ratio, 1.5),
          // Performance feedback
          feedback_lookback_days: num(autonomousConfig.feedback_lookback_days, 60),
          feedback_min_trades: num(autonomousConfig.feedback_min_trades, 5),
          feedback_max_weight: num(autonomousConfig.feedback_max_weight, 1.5),
          feedback_min_weight: num(autonomousConfig.feedback_min_weight, 0.4),
          feedback_weight_decay_per_day: num(autonomousConfig.feedback_weight_decay_per_day, 0.01),
          // Directional balance + quotas
          directional_balance_enabled: autonomousConfig.directional_balance_enabled ?? true,
          directional_min_long_pct: num(autonomousConfig.directional_min_long_pct, 30),
          directional_max_long_pct: num(autonomousConfig.directional_max_long_pct, 70),
          directional_min_short_pct: num(autonomousConfig.directional_min_short_pct, 20),
          directional_max_short_pct: num(autonomousConfig.directional_max_short_pct, 50),
          dq_enabled: dq.enabled ?? true,
          dq_adjacent_regime_reserve_pct: num(dq.adjacent_regime_reserve_pct, 20),
          dq_ranging_long: num(dq.ranging?.min_long_pct, 70),
          dq_ranging_short: num(dq.ranging?.min_short_pct, 0),
          dq_ranging_low_vol_long: num(dq.ranging_low_vol?.min_long_pct, 75),
          dq_ranging_low_vol_short: num(dq.ranging_low_vol?.min_short_pct, 0),
          dq_trending_up_long: num(dq.trending_up?.min_long_pct, 80),
          dq_trending_up_short: num(dq.trending_up?.min_short_pct, 5),
          dq_trending_up_weak_long: num(dq.trending_up_weak?.min_long_pct, 75),
          dq_trending_up_weak_short: num(dq.trending_up_weak?.min_short_pct, 8),
          dq_trending_up_strong_long: num(dq.trending_up_strong?.min_long_pct, 85),
          dq_trending_up_strong_short: num(dq.trending_up_strong?.min_short_pct, 3),
          dq_trending_down_long: num(dq.trending_down?.min_long_pct, 20),
          dq_trending_down_short: num(dq.trending_down?.min_short_pct, 50),
          dq_trending_down_weak_long: num(dq.trending_down_weak?.min_long_pct, 30),
          dq_trending_down_weak_short: num(dq.trending_down_weak?.min_short_pct, 30),
          dq_high_volatility_long: num(dq.high_volatility?.min_long_pct, 30),
          dq_high_volatility_short: num(dq.high_volatility?.min_short_pct, 10),
          // Portfolio balance
          max_long_exposure_pct: num(autonomousConfig.max_long_exposure_pct, 65),
          max_short_exposure_pct: num(autonomousConfig.max_short_exposure_pct, 60),
          max_sector_exposure_pct: num(autonomousConfig.max_sector_exposure_pct, 40),
        });

        // Keep the advanced_readonly block on a separate state for display
        setAutonomousAdvanced(autonomousConfig.advanced_readonly || null);
      }

      if (alphaEdgeSettings) {
        alphaEdgeForm.reset({
          fundamental_filters_enabled: alphaEdgeSettings.fundamental_filters_enabled,
          fundamental_min_checks_passed: alphaEdgeSettings.fundamental_min_checks_passed,
          fundamental_checks: alphaEdgeSettings.fundamental_checks,
          ml_filter_enabled: alphaEdgeSettings.ml_filter_enabled,
          ml_min_confidence: alphaEdgeSettings.ml_min_confidence * 100,
          ml_retrain_frequency_days: alphaEdgeSettings.ml_retrain_frequency_days,
          max_active_strategies: alphaEdgeSettings.max_active_strategies,
          min_conviction_score: alphaEdgeSettings.min_conviction_score,
          min_holding_period_days: alphaEdgeSettings.min_holding_period_days,
          max_trades_per_strategy_per_month: alphaEdgeSettings.max_trades_per_strategy_per_month,
          earnings_momentum_enabled: alphaEdgeSettings.earnings_momentum_enabled,
          sector_rotation_enabled: alphaEdgeSettings.sector_rotation_enabled,
          quality_mean_reversion_enabled: alphaEdgeSettings.quality_mean_reversion_enabled,
        });
      }

      if (apiUsageData) {
        setApiUsage(apiUsageData);
      }

      if (alertConfigData) {
        setAlertConfig(prev => ({ ...prev, ...alertConfigData }));
      }
      
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to load configuration:', error);
      toast.error('Failed to load configuration');
    } finally {
      setLoading(false);
      if (contextTradingMode) {
        checkConnection(contextTradingMode);
      }
    }
  };

  const checkConnection = async (mode: TradingMode) => {
    if (!mode) return;
    
    try {
      setCheckingConnection(true);
      const status = await apiClient.getConnectionStatus(mode);
      setConnectionStatus(status);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to check connection';
      setConnectionStatus({ 
        connected: false, 
        message: errorMessage.includes('No credentials') 
          ? 'No credentials configured' 
          : 'Credentials saved but connection test failed'
      });
    } finally {
      setCheckingConnection(false);
    }
  };

  const onApiConfigSubmit = async (data: ApiConfigFormData) => {
    if (!contextTradingMode) {
      toast.error('Trading mode not set');
      return;
    }

    try {
      await apiClient.setCredentials({
        public_key: data.publicKey,
        user_key: data.userKey,
        mode: contextTradingMode,
      });
      
      toast.success('API credentials saved successfully');
      apiForm.reset({ publicKey: '', userKey: '' });
      setShowKeys(false);
      await loadConfiguration();
    } catch (error) {
      console.error('Failed to save credentials:', error);
      toast.error('Failed to save API credentials');
    }
  };

  const onRiskLimitsSubmit = async (data: RiskLimitsFormData) => {
    if (!contextTradingMode) {
      toast.error('Trading mode not set');
      return;
    }

    try {
      const payload = {
        mode: contextTradingMode,
        max_position_size_pct: data.max_position_size_pct / 100,
        max_exposure_pct: data.max_exposure_pct / 100,
        max_daily_loss_pct: data.max_daily_loss_pct / 100,
        max_drawdown_pct: data.max_drawdown_pct / 100,
        position_risk_pct: data.position_risk_pct / 100,
        stop_loss_pct: data.stop_loss_pct / 100,
        take_profit_pct: data.take_profit_pct / 100,
      };

      await apiClient.updateRiskConfig(payload as any);
      
      toast.success('Risk parameters saved successfully');
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to save risk parameters:', error);
      toast.error('Failed to save risk parameters');
    }
  };

  const onAutonomousConfigSubmit = async (formData: AutonomousConfigFormData) => {
    try {
      // Flatten top-level scalar fields, but rebuild the nested structures
      // the backend expects for direction_aware_thresholds and
      // directional_quotas (both are BaseModels on the backend side).
      const payload: any = {
        // Core
        enabled: formData.enabled,
        proposal_count: formData.proposal_count,
        max_active_strategies: formData.max_active_strategies,
        min_active_strategies: formData.min_active_strategies,
        watchlist_size: formData.watchlist_size,
        backtested_ttl_cycles: formData.backtested_ttl_cycles,
        signal_generation_interval: formData.signal_generation_interval,
        dynamic_symbol_additions: formData.dynamic_symbol_additions,
        // Activation — Sharpe / WR / DD
        min_sharpe: formData.min_sharpe,
        min_sharpe_crypto: formData.min_sharpe_crypto,
        min_sharpe_commodity: formData.min_sharpe_commodity,
        max_drawdown: formData.max_drawdown,
        min_win_rate: formData.min_win_rate,
        min_win_rate_crypto: formData.min_win_rate_crypto,
        min_win_rate_commodity: formData.min_win_rate_commodity,
        // Min Trades
        min_trades: formData.min_trades,
        min_trades_dsl: formData.min_trades_dsl,
        min_trades_dsl_4h: formData.min_trades_dsl_4h,
        min_trades_dsl_1h: formData.min_trades_dsl_1h,
        min_trades_alpha_edge: formData.min_trades_alpha_edge,
        min_trades_crypto_1d: formData.min_trades_crypto_1d,
        min_trades_crypto_4h: formData.min_trades_crypto_4h,
        min_trades_crypto_1h: formData.min_trades_crypto_1h,
        min_trades_commodity: formData.min_trades_commodity,
        // Min RPT
        min_rpt_stock: formData.min_rpt_stock,
        min_rpt_stock_4h: formData.min_rpt_stock_4h,
        min_rpt_stock_1h: formData.min_rpt_stock_1h,
        min_rpt_etf: formData.min_rpt_etf,
        min_rpt_etf_4h: formData.min_rpt_etf_4h,
        min_rpt_etf_1h: formData.min_rpt_etf_1h,
        min_rpt_forex: formData.min_rpt_forex,
        min_rpt_forex_1h: formData.min_rpt_forex_1h,
        min_rpt_crypto: formData.min_rpt_crypto,
        min_rpt_crypto_1d: formData.min_rpt_crypto_1d,
        min_rpt_crypto_4h: formData.min_rpt_crypto_4h,
        min_rpt_crypto_1h: formData.min_rpt_crypto_1h,
        min_rpt_index: formData.min_rpt_index,
        min_rpt_index_1h: formData.min_rpt_index_1h,
        min_rpt_commodity: formData.min_rpt_commodity,
        min_rpt_commodity_4h: formData.min_rpt_commodity_4h,
        // Retirement
        retirement_max_sharpe: formData.retirement_max_sharpe,
        retirement_max_drawdown: formData.retirement_max_drawdown,
        retirement_min_win_rate: formData.retirement_min_win_rate,
        retirement_min_trades_for_evaluation: formData.retirement_min_trades_for_evaluation,
        retirement_min_live_trades: formData.retirement_min_live_trades,
        retirement_rolling_window_days: formData.retirement_rolling_window_days,
        retirement_consecutive_failures: formData.retirement_consecutive_failures,
        retirement_probation_days: formData.retirement_probation_days,
        // Walk-forward
        wf_train_days: formData.wf_train_days,
        wf_test_days: formData.wf_test_days,
        // Direction-aware (nested)
        direction_aware_thresholds: {
          default: {
            min_return: formData.da_default_min_return,
            min_sharpe: formData.da_default_min_sharpe,
            min_win_rate: formData.da_default_min_win_rate,
          },
          ranging: {
            long: {
              min_return: formData.da_ranging_long_min_return,
              min_sharpe: formData.da_ranging_long_min_sharpe,
              min_win_rate: formData.da_ranging_long_min_win_rate,
            },
            short: {
              min_return: formData.da_ranging_short_min_return,
              min_sharpe: formData.da_ranging_short_min_sharpe,
              min_win_rate: formData.da_ranging_short_min_win_rate,
            },
          },
          trending_up: {
            long: {
              min_return: formData.da_trending_up_long_min_return,
              min_sharpe: formData.da_trending_up_long_min_sharpe,
              min_win_rate: formData.da_trending_up_long_min_win_rate,
            },
            short: {
              min_return: formData.da_trending_up_short_min_return,
              min_sharpe: formData.da_trending_up_short_min_sharpe,
              min_win_rate: formData.da_trending_up_short_min_win_rate,
            },
          },
          trending_down: {
            long: {
              min_return: formData.da_trending_down_long_min_return,
              min_sharpe: formData.da_trending_down_long_min_sharpe,
              min_win_rate: formData.da_trending_down_long_min_win_rate,
            },
            short: {
              min_return: formData.da_trending_down_short_min_return,
              min_sharpe: formData.da_trending_down_short_min_sharpe,
              min_win_rate: formData.da_trending_down_short_min_win_rate,
            },
          },
          high_vol: {
            long: {
              min_return: formData.da_high_vol_long_min_return,
              min_sharpe: formData.da_high_vol_long_min_sharpe,
              min_win_rate: formData.da_high_vol_long_min_win_rate,
            },
            short: {
              min_return: formData.da_high_vol_short_min_return,
              min_sharpe: formData.da_high_vol_short_min_sharpe,
              min_win_rate: formData.da_high_vol_short_min_win_rate,
            },
          },
        },
        // Adaptive risk
        adaptive_risk_enabled: formData.adaptive_risk_enabled,
        adaptive_min_sl_pct: formData.adaptive_min_sl_pct,
        adaptive_max_sl_pct: formData.adaptive_max_sl_pct,
        adaptive_min_tp_pct: formData.adaptive_min_tp_pct,
        adaptive_max_tp_pct: formData.adaptive_max_tp_pct,
        adaptive_min_rr_ratio: formData.adaptive_min_rr_ratio,
        // Performance feedback
        feedback_lookback_days: formData.feedback_lookback_days,
        feedback_min_trades: formData.feedback_min_trades,
        feedback_max_weight: formData.feedback_max_weight,
        feedback_min_weight: formData.feedback_min_weight,
        feedback_weight_decay_per_day: formData.feedback_weight_decay_per_day,
        // Directional balance + quotas (nested for quotas)
        directional_balance_enabled: formData.directional_balance_enabled,
        directional_min_long_pct: formData.directional_min_long_pct,
        directional_max_long_pct: formData.directional_max_long_pct,
        directional_min_short_pct: formData.directional_min_short_pct,
        directional_max_short_pct: formData.directional_max_short_pct,
        directional_quotas: {
          enabled: formData.dq_enabled,
          adjacent_regime_reserve_pct: formData.dq_adjacent_regime_reserve_pct,
          ranging: { min_long_pct: formData.dq_ranging_long, min_short_pct: formData.dq_ranging_short },
          ranging_low_vol: { min_long_pct: formData.dq_ranging_low_vol_long, min_short_pct: formData.dq_ranging_low_vol_short },
          trending_up: { min_long_pct: formData.dq_trending_up_long, min_short_pct: formData.dq_trending_up_short },
          trending_up_weak: { min_long_pct: formData.dq_trending_up_weak_long, min_short_pct: formData.dq_trending_up_weak_short },
          trending_up_strong: { min_long_pct: formData.dq_trending_up_strong_long, min_short_pct: formData.dq_trending_up_strong_short },
          trending_down: { min_long_pct: formData.dq_trending_down_long, min_short_pct: formData.dq_trending_down_short },
          trending_down_weak: { min_long_pct: formData.dq_trending_down_weak_long, min_short_pct: formData.dq_trending_down_weak_short },
          high_volatility: { min_long_pct: formData.dq_high_volatility_long, min_short_pct: formData.dq_high_volatility_short },
        },
        // Portfolio balance
        max_long_exposure_pct: formData.max_long_exposure_pct,
        max_short_exposure_pct: formData.max_short_exposure_pct,
        max_sector_exposure_pct: formData.max_sector_exposure_pct,
      };
      await apiClient.updateAutonomousConfig(payload);
      toast.success('Autonomous configuration saved successfully');
      setLastUpdated(new Date());
      // Refresh to re-read yaml (writes may normalize some values)
      await loadConfiguration();
    } catch (error) {
      console.error('Failed to save autonomous configuration:', error);
      toast.error('Failed to save autonomous configuration');
    }
  };

  const onPositionManagementSubmit = async (formData: PositionManagementFormData) => {
    if (!contextTradingMode) {
      toast.error('Trading mode not set');
      return;
    }

    try {
      const currentRiskConfig: any = await apiClient.getRiskConfig(contextTradingMode);
      
      const payload = {
        mode: contextTradingMode,
        max_position_size_pct: currentRiskConfig.max_position_size_pct,
        max_exposure_pct: currentRiskConfig.max_exposure_pct,
        max_daily_loss_pct: currentRiskConfig.max_daily_loss_pct,
        max_drawdown_pct: currentRiskConfig.max_drawdown_pct,
        position_risk_pct: currentRiskConfig.position_risk_pct,
        stop_loss_pct: currentRiskConfig.stop_loss_pct,
        take_profit_pct: currentRiskConfig.take_profit_pct,
        trailing_stop_enabled: formData.trailing_stop_enabled,
        trailing_stop_activation_pct: formData.trailing_stop_activation_pct / 100,
        trailing_stop_distance_pct: formData.trailing_stop_distance_pct / 100,
        partial_exit_enabled: formData.partial_exit_enabled,
        partial_exit_levels: formData.partial_exit_levels.map(level => ({
          profit_pct: level.profit_pct / 100,
          exit_pct: level.exit_pct / 100,
        })),
        correlation_adjustment_enabled: formData.correlation_adjustment_enabled,
        correlation_threshold: formData.correlation_threshold,
        correlation_reduction_factor: formData.correlation_reduction_factor,
        regime_based_sizing_enabled: formData.regime_based_sizing_enabled,
        regime_multipliers: formData.regime_multipliers,
        cancel_stale_orders: formData.cancel_stale_orders,
        stale_order_hours: formData.stale_order_hours,
      };

      await apiClient.updateRiskConfig(payload as any);
      
      toast.success('Position management settings saved successfully');
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to save position management settings:', error);
      toast.error('Failed to save position management settings');
    }
  };

  const onAlphaEdgeSubmit = async (formData: AlphaEdgeFormData) => {
    try {
      await apiClient.updateAlphaEdgeSettings({
        fundamental_filters_enabled: formData.fundamental_filters_enabled,
        fundamental_min_checks_passed: formData.fundamental_min_checks_passed,
        fundamental_checks: formData.fundamental_checks,
        ml_filter_enabled: formData.ml_filter_enabled,
        ml_min_confidence: formData.ml_min_confidence / 100,
        ml_retrain_frequency_days: formData.ml_retrain_frequency_days,
        max_active_strategies: formData.max_active_strategies,
        min_conviction_score: formData.min_conviction_score,
        min_holding_period_days: formData.min_holding_period_days,
        max_trades_per_strategy_per_month: formData.max_trades_per_strategy_per_month,
        earnings_momentum_enabled: formData.earnings_momentum_enabled,
        sector_rotation_enabled: formData.sector_rotation_enabled,
        quality_mean_reversion_enabled: formData.quality_mean_reversion_enabled,
      });
      
      toast.success('Alpha Edge settings saved successfully');
      setLastUpdated(new Date());
      
      try {
        const usage = await apiClient.getAlphaEdgeApiUsage();
        setApiUsage(usage);
      } catch (error) {
        console.error('Failed to reload API usage:', error);
      }
    } catch (error) {
      console.error('Failed to save Alpha Edge settings:', error);
      toast.error('Failed to save Alpha Edge settings');
    }
  };

  const handleTradingModeChange = (newMode: TradingMode) => {
    setPendingTradingMode(newMode);
    setShowTradingModeDialog(true);
  };

  const confirmTradingModeChange = async () => {
    if (!pendingTradingMode) return;

    try {
      await apiClient.updateAppConfig({ trading_mode: pendingTradingMode });
      setContextTradingMode(pendingTradingMode);
      toast.success(`Switched to ${pendingTradingMode} mode`);
      
      await checkConnection(pendingTradingMode);
      setShowTradingModeDialog(false);
      setPendingTradingMode(null);
    } catch (error) {
      console.error('Failed to change trading mode:', error);
      toast.error('Failed to change trading mode');
    }
  };

  const saveAlertConfig = async () => {
    setAlertConfigLoading(true);
    try {
      await apiClient.updateAlertConfig(alertConfig);
      toast.success('Alert configuration saved');
    } catch (e) {
      toast.error('Failed to save alert configuration');
    } finally {
      setAlertConfigLoading(false);
    }
  };

  const requestPushPermission = async () => {
    if (!('Notification' in window)) {
      toast.error('Browser notifications not supported');
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      setAlertConfig(prev => ({ ...prev, browser_push_enabled: true }));
      toast.success('Browser notifications enabled');
    } else {
      toast.error('Browser notification permission denied');
    }
  };

  const loadUsers = async () => {
    if (!isAdmin) return;
    setUserListLoading(true);
    try {
      const users = await apiClient.listUsers();
      setUserList(users);
    } catch {
      // Non-admin users will get 403 — that's fine
    } finally {
      setUserListLoading(false);
    }
  };

  const handleCreateUser = async () => {
    if (!newUsername || !newPassword) {
      toast.error('Username and password are required');
      return;
    }
    setCreateUserLoading(true);
    try {
      await apiClient.createUser(newUsername, newPassword, newRole);
      toast.success(`User '${newUsername}' created`);
      setNewUsername('');
      setNewPassword('');
      setNewRole('viewer');
      setShowCreateUser(false);
      await loadUsers();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setCreateUserLoading(false);
    }
  };

  const handleChangePassword = async () => {
    if (changePasswordNew !== changePasswordConfirm) {
      toast.error('New passwords do not match');
      return;
    }
    if (changePasswordNew.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    setChangePasswordLoading(true);
    try {
      await apiClient.changePassword(changePasswordOld, changePasswordNew);
      toast.success('Password changed successfully');
      setChangePasswordOld('');
      setChangePasswordNew('');
      setChangePasswordConfirm('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to change password');
    } finally {
      setChangePasswordLoading(false);
    }
  };

  const handleResetPassword = async (targetUser: string) => {
    if (resetPasswordValue.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    try {
      await apiClient.resetUserPassword(targetUser, resetPasswordValue);
      toast.success(`Password reset for '${targetUser}'`);
      setResetPasswordUser(null);
      setResetPasswordValue('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to reset password');
    }
  };

  const handleDeleteUser = async (targetUser: string) => {
    try {
      await apiClient.deleteUser(targetUser);
      toast.success(`User '${targetUser}' deleted`);
      setDeleteConfirmUser(null);
      await loadUsers();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to delete user');
    }
  };

  const handleToggleActive = async (targetUser: string, currentActive: boolean) => {
    try {
      await apiClient.updateUser(targetUser, { is_active: !currentActive });
      toast.success(`User '${targetUser}' ${!currentActive ? 'activated' : 'deactivated'}`);
      await loadUsers();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to update user');
    }
  };

  const handleRoleChange = async (targetUser: string, newRoleValue: string) => {
    try {
      await apiClient.updateUser(targetUser, { role: newRoleValue });
      toast.success(`Role updated for '${targetUser}'`);
      await loadUsers();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to update role');
    }
  };

  if (loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Settings" description="Configure trading mode, API credentials, risk parameters, and preferences" compact={true}>
          <div className="flex items-center justify-center h-64">
            <div className="text-gray-400 font-mono">Loading configuration...</div>
          </div>
        </PageTemplate>
      </DashboardLayout>
    );
  }

  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastUpdated} />
      <button onClick={loadConfiguration} disabled={loading} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Refresh">
        <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
      </button>
    </div>
  );

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Settings"
        description="Configure trading mode, API credentials, risk parameters, and preferences"
        compact={true}
      >
      <div className="p-2 sm:p-3 lg:p-4 max-w-[1800px] mx-auto">

        {/* Tabs */}
        <Tabs defaultValue="trading-mode" className="space-y-2">
          <div className="flex items-center gap-2">
            <TabsList className="flex-1 overflow-x-auto">
            <TabsTrigger value="trading-mode" className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              <span className="hidden sm:inline">Trading Mode</span>
            </TabsTrigger>
            <TabsTrigger value="api" className="flex items-center gap-2">
              <Key className="h-4 w-4" />
              <span className="hidden sm:inline">API Config</span>
            </TabsTrigger>
            <TabsTrigger value="risk" className="flex items-center gap-2">
              <Shield className="h-4 w-4" />
              <span className="hidden sm:inline">Risk Limits</span>
            </TabsTrigger>
            <TabsTrigger value="position-management" className="flex items-center gap-2">
              <Target className="h-4 w-4" />
              <span className="hidden sm:inline">Position Mgmt</span>
            </TabsTrigger>
            <TabsTrigger value="autonomous" className="flex items-center gap-2">
              <SettingsIcon className="h-4 w-4" />
              <span className="hidden sm:inline">Autonomous</span>
            </TabsTrigger>
            <TabsTrigger value="alpha-edge" className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              <span className="hidden sm:inline">Alpha Edge</span>
            </TabsTrigger>
            <TabsTrigger value="notifications" className="flex items-center gap-2">
              <Bell className="h-4 w-4" />
              <span className="hidden sm:inline">Alerts</span>
            </TabsTrigger>
            <TabsTrigger value="users" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              <span className="hidden sm:inline">Users</span>
            </TabsTrigger>
            <TabsTrigger value="shortcuts" className="flex items-center gap-2">
              <Keyboard className="h-4 w-4" />
              <span className="hidden sm:inline">Shortcuts</span>
            </TabsTrigger>
          </TabsList>
            {headerActions}
          </div>

          {/* Trading Mode Tab */}
          <TabsContent value="trading-mode" className="space-y-4">
            <SectionLabel>Trading Mode</SectionLabel>
            <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Demo Mode */}
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleTradingModeChange(TradingMode.DEMO)}
                    disabled={contextTradingMode === TradingMode.DEMO}
                    className={cn(
                      "p-6 rounded-lg border-2 transition-all text-left",
                      contextTradingMode === TradingMode.DEMO
                        ? "border-yellow-500 bg-yellow-900/20"
                        : "border-gray-700 hover:border-gray-600 bg-dark-surface"
                    )}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-12 h-12 rounded-full flex items-center justify-center",
                          contextTradingMode === TradingMode.DEMO
                            ? "bg-yellow-500/20"
                            : "bg-gray-700"
                        )}>
                          <Activity className={cn(
                            "h-6 w-6",
                            contextTradingMode === TradingMode.DEMO
                              ? "text-yellow-500"
                              : "text-gray-400"
                          )} />
                        </div>
                        <div>
                          <h3 className="text-[12px] font-semibold text-gray-100">Demo Mode</h3>
                          <p className="text-xs text-gray-400">Paper trading with simulated funds</p>
                        </div>
                      </div>
                      {contextTradingMode === TradingMode.DEMO && (
                        <span className="px-3 py-1 bg-yellow-500 text-dark-bg rounded-full text-xs font-bold">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <div className="space-y-2 text-[11px] text-gray-400">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        <span>No real money at risk</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        <span>Test strategies safely</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        <span>Simulated market conditions</span>
                      </div>
                    </div>
                  </motion.button>

                  {/* Live Mode */}
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleTradingModeChange(TradingMode.LIVE)}
                    disabled={contextTradingMode === TradingMode.LIVE}
                    className={cn(
                      "p-6 rounded-lg border-2 transition-all text-left",
                      contextTradingMode === TradingMode.LIVE
                        ? "border-red-500 bg-red-900/20"
                        : "border-gray-700 hover:border-gray-600 bg-dark-surface"
                    )}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-12 h-12 rounded-full flex items-center justify-center",
                          contextTradingMode === TradingMode.LIVE
                            ? "bg-red-500/20"
                            : "bg-gray-700"
                        )}>
                          <AlertTriangle className={cn(
                            "h-6 w-6",
                            contextTradingMode === TradingMode.LIVE
                              ? "text-red-500"
                              : "text-gray-400"
                          )} />
                        </div>
                        <div>
                          <h3 className="text-[12px] font-semibold text-gray-100">Live Mode</h3>
                          <p className="text-xs text-gray-400">Real trading with actual funds</p>
                        </div>
                      </div>
                      {contextTradingMode === TradingMode.LIVE && (
                        <span className="px-3 py-1 bg-red-500 text-white rounded-full text-xs font-bold">
                          LIVE
                        </span>
                      )}
                    </div>
                    <div className="space-y-2 text-[11px] text-gray-400">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                        <span>Real money at risk</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                        <span>Actual market execution</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                        <span>Requires proper risk management</span>
                      </div>
                    </div>
                  </motion.button>
                </div>

                {/* Current Mode Warning */}
                {contextTradingMode === TradingMode.DEMO && (
                  <div className="p-4 bg-yellow-900/20 border border-yellow-700 rounded-lg flex items-start gap-3">
                    <Info className="h-5 w-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-yellow-400 font-semibold text-[11px] mb-1">Demo Mode Active</div>
                      <div className="text-xs text-gray-400">
                        All trades are simulated. No real money is at risk. Use this mode to test strategies safely.
                      </div>
                    </div>
                  </div>
                )}

                {contextTradingMode === TradingMode.LIVE && (
                  <div className="p-4 bg-red-900/20 border border-red-700 rounded-lg flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-red-400 font-semibold text-[11px] mb-1">Live Mode Active</div>
                      <div className="text-xs text-gray-400">
                        Trading with real money. All orders will be executed on your live eToro account. Ensure risk parameters are properly configured.
                      </div>
                    </div>
                  </div>
                )}
            </div>
          </TabsContent>

          {/* API Configuration Tab */}
          <TabsContent value="api" className="space-y-4">
            <SectionLabel>API Configuration</SectionLabel>
            <p className="text-xs text-gray-500 mb-2">Configure your eToro API credentials for {contextTradingMode} mode</p>
                <form onSubmit={apiForm.handleSubmit(onApiConfigSubmit)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="publicKey" className="text-[11px]">eToro Public Key</Label>
                    <div className="relative">
                      <Input
                        id="publicKey"
                        type={showKeys ? 'text' : 'password'}
                        placeholder="Enter your eToro public key"
                        {...apiForm.register('publicKey')}
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKeys(!showKeys)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
                      >
                        {showKeys ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    {apiForm.formState.errors.publicKey && (
                      <p className="text-xs text-red-500">{apiForm.formState.errors.publicKey.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="userKey" className="text-[11px]">eToro User Key</Label>
                    <Input
                      id="userKey"
                      type={showKeys ? 'text' : 'password'}
                      placeholder="Enter your eToro user key"
                      {...apiForm.register('userKey')}
                    />
                    {apiForm.formState.errors.userKey && (
                      <p className="text-xs text-red-500">{apiForm.formState.errors.userKey.message}</p>
                    )}
                  </div>

                  {/* Connection Status */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[11px] text-gray-400">Credentials Status:</span>
                      <div className="flex items-center gap-2">
                        {checkingConnection ? (
                          <span className="text-[11px] text-gray-400">Checking...</span>
                        ) : connectionStatus ? (
                          <>
                            <span className={cn(
                              "w-2 h-2 rounded-full",
                              connectionStatus.connected 
                                ? 'bg-green-500' 
                                : connectionStatus.message.includes('No credentials') 
                                ? 'bg-red-500' 
                                : 'bg-green-500'
                            )} />
                            <span className={cn(
                              "text-[11px]",
                              connectionStatus.connected 
                                ? 'text-green-400' 
                                : connectionStatus.message.includes('No credentials') 
                                ? 'text-red-400' 
                                : 'text-green-400'
                            )}>
                              {connectionStatus.connected 
                                ? 'Connected & Verified' 
                                : connectionStatus.message.includes('No credentials') 
                                ? 'Not Configured' 
                                : 'Configured'}
                            </span>
                          </>
                        ) : (
                          <span className="text-[11px] text-gray-500">Unknown</span>
                        )}
                      </div>
                    </div>
                    {connectionStatus && (
                      <p className="text-xs text-gray-500">{connectionStatus.message}</p>
                    )}
                  </div>

                  <div className="flex gap-3">
                    <Button type="submit" disabled={apiForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {apiForm.formState.isSubmitting ? 'Saving...' : 'Save Credentials'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => apiForm.reset()}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>

                  <div className="text-xs text-gray-500 space-y-1 pt-2">
                    <p>• Get your API keys from eToro's developer portal</p>
                    <p>• Keys are encrypted before storage</p>
                    <p>• Separate keys for Demo and Live modes</p>
                    <p>• Input fields are always empty for security (saved keys are never displayed)</p>
                  </div>
                </form>
          </TabsContent>

          {/* Risk Limits Tab */}
          <TabsContent value="risk" className="space-y-4">
            <SectionLabel>Risk Limits</SectionLabel>
                <form onSubmit={riskForm.handleSubmit(onRiskLimitsSubmit)} className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <Label htmlFor="max_position_size_pct" className="text-[11px]">Max Position Size (%)</Label>
                      <Input
                        id="max_position_size_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('max_position_size_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Maximum size of a single position as % of portfolio</p>
                      {riskForm.formState.errors.max_position_size_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.max_position_size_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_exposure_pct" className="text-[11px]">Max Portfolio Exposure (%)</Label>
                      <Input
                        id="max_exposure_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('max_exposure_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Maximum total exposure across all positions</p>
                      {riskForm.formState.errors.max_exposure_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.max_exposure_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_daily_loss_pct" className="text-[11px]">Max Daily Loss (%)</Label>
                      <Input
                        id="max_daily_loss_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('max_daily_loss_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Circuit breaker activates at this loss threshold</p>
                      {riskForm.formState.errors.max_daily_loss_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.max_daily_loss_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_drawdown_pct" className="text-[11px]">Max Drawdown (%)</Label>
                      <Input
                        id="max_drawdown_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('max_drawdown_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Maximum acceptable drawdown</p>
                      {riskForm.formState.errors.max_drawdown_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.max_drawdown_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="position_risk_pct" className="text-[11px]">Risk Per Trade (%)</Label>
                      <Input
                        id="position_risk_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('position_risk_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Maximum risk per individual trade</p>
                      {riskForm.formState.errors.position_risk_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.position_risk_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="stop_loss_pct" className="text-[11px]">Stop Loss (%)</Label>
                      <Input
                        id="stop_loss_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('stop_loss_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Default stop loss percentage</p>
                      {riskForm.formState.errors.stop_loss_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.stop_loss_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="take_profit_pct" className="text-[11px]">Take Profit (%)</Label>
                      <Input
                        id="take_profit_pct"
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        {...riskForm.register('take_profit_pct', { valueAsNumber: true })}
                      />
                      <p className="text-xs text-gray-500">Default take profit percentage</p>
                      {riskForm.formState.errors.take_profit_pct && (
                        <p className="text-xs text-red-500">{riskForm.formState.errors.take_profit_pct.message}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button type="submit" disabled={riskForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {riskForm.formState.isSubmitting ? 'Saving...' : 'Save Risk Limits'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => riskForm.reset()}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>
                </form>
          </TabsContent>

          {/* Position Management Tab */}
          <TabsContent value="position-management" className="space-y-4">
            <SectionLabel>Position Management</SectionLabel>
                <form onSubmit={positionManagementForm.handleSubmit(onPositionManagementSubmit)} className="space-y-8">
                  
                  {/* Trailing Stops Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="trailing-stop-enabled" className="text-[11px]">Enable Trailing Stops</Label>
                        <p className="text-xs text-gray-500">Automatically move stop-loss up as positions become profitable</p>
                      </div>
                      <Switch
                        id="trailing-stop-enabled"
                        checked={positionManagementForm.watch('trailing_stop_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('trailing_stop_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('trailing_stop_enabled') && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pl-4">
                        <div className="space-y-2">
                          <Label htmlFor="trailing_stop_activation_pct" className="text-[11px]">Activation Profit (%)</Label>
                          <Input
                            id="trailing_stop_activation_pct"
                            type="number"
                            step="0.1"
                            min="0"
                            max="100"
                            {...positionManagementForm.register('trailing_stop_activation_pct', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Start trailing after this profit level (e.g., 5% = activate at 5% profit)</p>
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="trailing_stop_distance_pct" className="text-[11px]">Trailing Distance (%)</Label>
                          <Input
                            id="trailing_stop_distance_pct"
                            type="number"
                            step="0.1"
                            min="0"
                            max="100"
                            {...positionManagementForm.register('trailing_stop_distance_pct', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Distance below current price (e.g., 3% = trail 3% below peak)</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Partial Exits Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="partial-exit-enabled" className="text-[11px]">Enable Partial Exits</Label>
                        <p className="text-xs text-gray-500">Take profits incrementally at predefined levels</p>
                      </div>
                      <Switch
                        id="partial-exit-enabled"
                        checked={positionManagementForm.watch('partial_exit_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('partial_exit_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('partial_exit_enabled') && (
                      <div className="space-y-3 pl-4">
                        <Label className="text-[11px] font-semibold text-gray-300">Exit Levels</Label>
                        {positionManagementForm.watch('partial_exit_levels').map((_, index) => (
                          <div key={index} className="grid grid-cols-2 gap-4 p-3 bg-dark-bg border border-dark-border rounded">
                            <div className="space-y-2">
                              <Label htmlFor={`partial_exit_levels.${index}.profit_pct`} className="text-[11px]">Profit Level (%)</Label>
                              <Input
                                id={`partial_exit_levels.${index}.profit_pct`}
                                type="number"
                                step="0.1"
                                min="0"
                                max="100"
                                {...positionManagementForm.register(`partial_exit_levels.${index}.profit_pct`, { valueAsNumber: true })}
                              />
                            </div>
                            <div className="space-y-2">
                              <Label htmlFor={`partial_exit_levels.${index}.exit_pct`} className="text-[11px]">Exit Size (%)</Label>
                              <Input
                                id={`partial_exit_levels.${index}.exit_pct`}
                                type="number"
                                step="0.1"
                                min="0"
                                max="100"
                                {...positionManagementForm.register(`partial_exit_levels.${index}.exit_pct`, { valueAsNumber: true })}
                              />
                            </div>
                          </div>
                        ))}
                        <p className="text-xs text-gray-500">Example: At 5% profit, exit 50% of position; at 10% profit, exit 25% more</p>
                      </div>
                    )}
                  </div>

                  {/* Correlation Adjustment Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="correlation-adjustment-enabled" className="text-[11px]">Enable Correlation Adjustment</Label>
                        <p className="text-xs text-gray-500">Reduce position sizes for correlated assets to maintain diversification</p>
                      </div>
                      <Switch
                        id="correlation-adjustment-enabled"
                        checked={positionManagementForm.watch('correlation_adjustment_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('correlation_adjustment_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('correlation_adjustment_enabled') && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pl-4">
                        <div className="space-y-2">
                          <Label htmlFor="correlation_threshold" className="text-[11px]">Correlation Threshold</Label>
                          <Input
                            id="correlation_threshold"
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            {...positionManagementForm.register('correlation_threshold', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Trigger adjustment when correlation exceeds this (0.7 = 70% correlation)</p>
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="correlation_reduction_factor" className="text-[11px]">Reduction Factor</Label>
                          <Input
                            id="correlation_reduction_factor"
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            {...positionManagementForm.register('correlation_reduction_factor', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Size reduction multiplier (0.5 = reduce by 50% of correlation)</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Regime-Based Sizing Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="regime-based-sizing-enabled" className="text-[11px]">Enable Regime-Based Sizing</Label>
                        <p className="text-xs text-gray-500">Adjust position sizes based on market volatility and regime (advanced)</p>
                      </div>
                      <Switch
                        id="regime-based-sizing-enabled"
                        checked={positionManagementForm.watch('regime_based_sizing_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('regime_based_sizing_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('regime_based_sizing_enabled') && (
                      <div className="space-y-3 pl-4">
                        <Label className="text-[11px] font-semibold text-gray-300">Regime Multipliers</Label>
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label htmlFor="regime_multipliers.high_volatility" className="text-[11px]">High Volatility</Label>
                            <Input
                              id="regime_multipliers.high_volatility"
                              type="number"
                              step="0.1"
                              min="0"
                              max="2"
                              {...positionManagementForm.register('regime_multipliers.high_volatility', { valueAsNumber: true })}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="regime_multipliers.low_volatility" className="text-[11px]">Low Volatility</Label>
                            <Input
                              id="regime_multipliers.low_volatility"
                              type="number"
                              step="0.1"
                              min="0"
                              max="2"
                              {...positionManagementForm.register('regime_multipliers.low_volatility', { valueAsNumber: true })}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="regime_multipliers.trending" className="text-[11px]">Trending Market</Label>
                            <Input
                              id="regime_multipliers.trending"
                              type="number"
                              step="0.1"
                              min="0"
                              max="2"
                              {...positionManagementForm.register('regime_multipliers.trending', { valueAsNumber: true })}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="regime_multipliers.ranging" className="text-[11px]">Ranging Market</Label>
                            <Input
                              id="regime_multipliers.ranging"
                              type="number"
                              step="0.1"
                              min="0"
                              max="2"
                              {...positionManagementForm.register('regime_multipliers.ranging', { valueAsNumber: true })}
                            />
                          </div>
                        </div>
                        <p className="text-xs text-gray-500">Multipliers adjust base position size (1.0 = normal, 0.5 = half size, 1.5 = 50% larger)</p>
                      </div>
                    )}
                  </div>

                  {/* Order Management Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="cancel-stale-orders" className="text-[11px]">Cancel Stale Orders</Label>
                        <p className="text-xs text-gray-500">Automatically cancel pending orders that haven't filled</p>
                      </div>
                      <Switch
                        id="cancel-stale-orders"
                        checked={positionManagementForm.watch('cancel_stale_orders')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('cancel_stale_orders', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('cancel_stale_orders') && (
                      <div className="pl-4">
                        <div className="space-y-2">
                          <Label htmlFor="stale_order_hours" className="text-[11px]">Stale Order Timeout (hours)</Label>
                          <Input
                            id="stale_order_hours"
                            type="number"
                            step="1"
                            min="1"
                            max="168"
                            {...positionManagementForm.register('stale_order_hours', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Cancel orders older than this many hours (24 = 1 day, 168 = 1 week)</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Warning Box */}
                  <div className="p-4 bg-yellow-900/20 border border-yellow-700 rounded-lg flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-yellow-400 font-semibold text-[11px] mb-1">Advanced Features</div>
                      <div className="text-xs text-gray-400">
                        These settings directly impact trading behavior. Test thoroughly in DEMO mode before enabling in LIVE mode. 
                        Regime-based sizing is an advanced feature - only enable after understanding your strategy's regime sensitivity.
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button type="submit" disabled={positionManagementForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {positionManagementForm.formState.isSubmitting ? 'Saving...' : 'Save Position Management Settings'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => positionManagementForm.reset()}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>
                </form>
          </TabsContent>

          {/* Autonomous Configuration Tab */}
          <TabsContent value="autonomous" className="space-y-4">
            <SectionLabel>Autonomous Trading Configuration</SectionLabel>
            <p className="text-xs text-gray-500 mb-3">
              Every editable parameter from <code className="text-[10px] bg-dark-bg px-1 rounded">config/autonomous_trading.yaml</code>.
              Changes take effect on the next cycle (proposer re-reads yaml fresh each cycle).
              Toggling <em>Enable Autonomous System</em> or changing schedule requires a service restart.
            </p>
                <form onSubmit={autonomousForm.handleSubmit(onAutonomousConfigSubmit)} className="space-y-6">
                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 1 — Core: enable, proposals, limits, scheduling         */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="autonomous-enabled" className="text-[11px]">Enable Autonomous System</Label>
                        <p className="text-xs text-gray-500">Master switch — when off, proposer / WF / activation all stand down (service restart required)</p>
                      </div>
                      <Switch
                        id="autonomous-enabled"
                        checked={autonomousForm.watch('enabled')}
                        onCheckedChange={(checked) => autonomousForm.setValue('enabled', checked)}
                      />
                    </div>

                    <h3 className="text-[11px] font-semibold text-gray-300 pt-2 border-t border-dark-border">Strategy Generation</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="proposal_count" className="text-[11px]">Proposal Count</Label>
                        <Input id="proposal_count" type="number" min="10" max="500" {...autonomousForm.register('proposal_count', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Proposals per cycle (10-500)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="watchlist_size" className="text-[11px]">Watchlist Size</Label>
                        <Input id="watchlist_size" type="number" min="1" max="20" {...autonomousForm.register('watchlist_size', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Symbols per template watchlist (1-20)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="dynamic_symbol_additions" className="text-[11px]">Dynamic Symbol Additions</Label>
                        <Input id="dynamic_symbol_additions" type="number" min="0" max="50" {...autonomousForm.register('dynamic_symbol_additions', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Extra symbols added at signal-gen time (0-50)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="signal_generation_interval" className="text-[11px]">Signal Interval (minutes)</Label>
                        <Input id="signal_generation_interval" type="number" min="5" max="60"
                          value={Math.round(autonomousForm.watch('signal_generation_interval') / 60)}
                          onChange={(e) => autonomousForm.setValue('signal_generation_interval', Number(e.target.value) * 60)} />
                        <p className="text-xs text-gray-500">Signal-gen cadence (5-60 min)</p>
                      </div>
                    </div>

                    <h3 className="text-[11px] font-semibold text-gray-300 pt-2 border-t border-dark-border">Active-Book Limits</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="max_active_strategies" className="text-[11px]">Max Active Strategies</Label>
                        <Input id="max_active_strategies" type="number" min="5" max="500" {...autonomousForm.register('max_active_strategies', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Cap on simultaneously-running strategies (5-500)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_active_strategies" className="text-[11px]">Min Active Strategies</Label>
                        <Input id="min_active_strategies" type="number" min="3" max="25" {...autonomousForm.register('min_active_strategies', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Floor below which the proposer self-boosts (3-25)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="backtested_ttl_cycles" className="text-[11px]">Backtested TTL (cycles)</Label>
                        <Input id="backtested_ttl_cycles" type="number" min="6" max="200" {...autonomousForm.register('backtested_ttl_cycles', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Retire BACKTESTED strategies after N signal cycles without a trade (default 168 ≈ 1 week)</p>
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 2 — Activation thresholds: Sharpe / Win Rate / DD      */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Activation Thresholds — Sharpe / Win Rate / Drawdown</h3>
                    <p className="text-xs text-gray-500">Minimum quality bar for a WF-validated strategy to be activated to DEMO. Separate gates for crypto (heavy-tail) and commodity (low-frequency) asset classes.</p>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="min_sharpe" className="text-[11px]">Min Sharpe — Equity</Label>
                        <Input id="min_sharpe" type="number" step="0.1" min="0" max="3.0" {...autonomousForm.register('min_sharpe', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Stocks, ETFs, forex, indices (0-3.0)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_sharpe_crypto" className="text-[11px]">Min Sharpe — Crypto</Label>
                        <Input id="min_sharpe_crypto" type="number" step="0.1" min="0" max="3.0" {...autonomousForm.register('min_sharpe_crypto', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Heavy-tail calibration (0-3.0)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_sharpe_commodity" className="text-[11px]">Min Sharpe — Commodity</Label>
                        <Input id="min_sharpe_commodity" type="number" step="0.1" min="0" max="3.0" {...autonomousForm.register('min_sharpe_commodity', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Low-frequency calibration (0-3.0)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="max_drawdown" className="text-[11px]">Max Drawdown (%)</Label>
                        <Input id="max_drawdown" type="number" step="1" min="5" max="50" {...autonomousForm.register('max_drawdown', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Reject if test DD exceeds this (5-50%)</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_win_rate" className="text-[11px]">Min Win Rate — Equity (%)</Label>
                        <Input id="min_win_rate" type="number" step="1" min="20" max="80" {...autonomousForm.register('min_win_rate', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Soft floor — expectancy gate overrides when n≥15 trades</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_win_rate_crypto" className="text-[11px]">Min Win Rate — Crypto (%)</Label>
                        <Input id="min_win_rate_crypto" type="number" step="1" min="15" max="70" {...autonomousForm.register('min_win_rate_crypto', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Lower floor for trend-follower profiles</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_win_rate_commodity" className="text-[11px]">Min Win Rate — Commodity (%)</Label>
                        <Input id="min_win_rate_commodity" type="number" step="1" min="20" max="70" {...autonomousForm.register('min_win_rate_commodity', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Low-frequency floor (20-70%)</p>
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 3 — Min Trades per asset class × interval              */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Min Trades (Statistical Significance)</h3>
                    <p className="text-xs text-gray-500">Minimum number of test-window trades required to accept WF results. Higher intervals need fewer trades (longer holding period).</p>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                      <div className="space-y-2">
                        <Label htmlFor="min_trades" className="text-[11px]">Min Trades (base)</Label>
                        <Input id="min_trades" type="number" min="1" max="50" {...autonomousForm.register('min_trades', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_dsl" className="text-[11px]">DSL daily</Label>
                        <Input id="min_trades_dsl" type="number" min="1" max="50" {...autonomousForm.register('min_trades_dsl', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_dsl_4h" className="text-[11px]">DSL 4H</Label>
                        <Input id="min_trades_dsl_4h" type="number" min="1" max="50" {...autonomousForm.register('min_trades_dsl_4h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_dsl_1h" className="text-[11px]">DSL 1H</Label>
                        <Input id="min_trades_dsl_1h" type="number" min="1" max="100" {...autonomousForm.register('min_trades_dsl_1h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_alpha_edge" className="text-[11px]">Alpha Edge</Label>
                        <Input id="min_trades_alpha_edge" type="number" min="1" max="50" {...autonomousForm.register('min_trades_alpha_edge', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_crypto_1d" className="text-[11px]">Crypto daily</Label>
                        <Input id="min_trades_crypto_1d" type="number" min="1" max="50" {...autonomousForm.register('min_trades_crypto_1d', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_crypto_4h" className="text-[11px]">Crypto 4H</Label>
                        <Input id="min_trades_crypto_4h" type="number" min="1" max="50" {...autonomousForm.register('min_trades_crypto_4h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_crypto_1h" className="text-[11px]">Crypto 1H</Label>
                        <Input id="min_trades_crypto_1h" type="number" min="1" max="100" {...autonomousForm.register('min_trades_crypto_1h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_commodity" className="text-[11px]">Commodity</Label>
                        <Input id="min_trades_commodity" type="number" min="1" max="50" {...autonomousForm.register('min_trades_commodity', { valueAsNumber: true })} />
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 4 — Min Return Per Trade (RPT) floors                   */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Min Return Per Trade (%) — Per-Position Basis</h3>
                    <p className="text-xs text-gray-500">Minimum net return per trade (post-cost). Gated by the activation RPT check in <code>portfolio_manager.evaluate_for_activation</code>. Values are per-position (e.g. crypto_1d = 3% means each trade must make ≥3% on the capital deployed).</p>
                    <h4 className="text-[11px] text-gray-400 font-medium">Equity</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Stock daily</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_stock', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Stock 4H</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_stock_4h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Stock 1H</Label>
                        <Input type="number" step="0.01" min="0" max="10" {...autonomousForm.register('min_rpt_stock_1h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">ETF daily</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_etf', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">ETF 4H</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_etf_4h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">ETF 1H</Label>
                        <Input type="number" step="0.01" min="0" max="10" {...autonomousForm.register('min_rpt_etf_1h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Index daily</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_index', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Index 1H</Label>
                        <Input type="number" step="0.01" min="0" max="10" {...autonomousForm.register('min_rpt_index_1h', { valueAsNumber: true })} />
                      </div>
                    </div>
                    <h4 className="text-[11px] text-gray-400 font-medium pt-2 border-t border-dark-border/50">Forex</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Forex daily</Label>
                        <Input type="number" step="0.01" min="0" max="10" {...autonomousForm.register('min_rpt_forex', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Forex 1H</Label>
                        <Input type="number" step="0.005" min="0" max="5" {...autonomousForm.register('min_rpt_forex_1h', { valueAsNumber: true })} />
                      </div>
                    </div>
                    <h4 className="text-[11px] text-gray-400 font-medium pt-2 border-t border-dark-border/50">Crypto (2.2-3% round-trip cost on eToro)</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Crypto fallback</Label>
                        <Input type="number" step="0.1" min="0" max="30" {...autonomousForm.register('min_rpt_crypto', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Crypto daily</Label>
                        <Input type="number" step="0.1" min="0" max="30" {...autonomousForm.register('min_rpt_crypto_1d', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Crypto 4H</Label>
                        <Input type="number" step="0.1" min="0" max="30" {...autonomousForm.register('min_rpt_crypto_4h', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Crypto 1H</Label>
                        <Input type="number" step="0.1" min="0" max="20" {...autonomousForm.register('min_rpt_crypto_1h', { valueAsNumber: true })} />
                      </div>
                    </div>
                    <h4 className="text-[11px] text-gray-400 font-medium pt-2 border-t border-dark-border/50">Commodity</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Commodity daily</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_commodity', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Commodity 4H</Label>
                        <Input type="number" step="0.01" min="0" max="20" {...autonomousForm.register('min_rpt_commodity_4h', { valueAsNumber: true })} />
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 5 — Retirement                                          */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Retirement Thresholds + Logic</h3>
                    <p className="text-xs text-gray-500">Conditions under which a live DEMO strategy is retired. `min_live_trades` gates evaluation so strategies aren't killed before statistical significance.</p>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Retire if Sharpe &lt;</Label>
                        <Input type="number" step="0.1" min="-1.0" max="2.0" {...autonomousForm.register('retirement_max_sharpe', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Live Sharpe floor (-1.0 to 2.0)</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Retire if DD &gt; (%)</Label>
                        <Input type="number" step="1" min="5" max="50" {...autonomousForm.register('retirement_max_drawdown', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Max tolerated live DD</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Retire if WR &lt; (%)</Label>
                        <Input type="number" step="1" min="15" max="60" {...autonomousForm.register('retirement_min_win_rate', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Live win rate floor</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Trades for Eval</Label>
                        <Input type="number" min="3" max="100" {...autonomousForm.register('retirement_min_trades_for_evaluation', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Statistical minimum before retirement check</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Live Trades</Label>
                        <Input type="number" min="1" max="50" {...autonomousForm.register('retirement_min_live_trades', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Filled trades required before retirement eligible</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Rolling Window (days)</Label>
                        <Input type="number" min="7" max="365" {...autonomousForm.register('retirement_rolling_window_days', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Lookback for rolling retirement metrics</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Consecutive Failures</Label>
                        <Input type="number" min="1" max="10" {...autonomousForm.register('retirement_consecutive_failures', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Failures in a row to trigger retirement</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Probation (days)</Label>
                        <Input type="number" min="1" max="365" {...autonomousForm.register('retirement_probation_days', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Grace period after activation before retirement kicks in</p>
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 6 — Walk-Forward + Direction-Aware thresholds          */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Walk-Forward & Direction-Aware Thresholds</h3>
                    <p className="text-xs text-gray-500">Per-regime × per-direction relaxation so uptrend shorts and ranging longs aren't systematically rejected. Values are raw (not percentages) to match yaml convention.</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-[11px]">WF Train Days</Label>
                        <Input type="number" min="30" max="1460" {...autonomousForm.register('wf_train_days', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Training window length (30-1460 days)</p>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">WF Test Days</Label>
                        <Input type="number" min="30" max="1460" {...autonomousForm.register('wf_test_days', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Out-of-sample test window (30-1460 days)</p>
                      </div>
                    </div>

                    {/* Direction-aware — default */}
                    <div className="pt-3 border-t border-dark-border">
                      <h4 className="text-[11px] text-gray-400 font-medium mb-2">Default (used when no regime match)</h4>
                      <div className="grid grid-cols-3 gap-3">
                        <div className="space-y-1">
                          <Label className="text-[10px]">Min Return</Label>
                          <Input type="number" step="0.01" {...autonomousForm.register('da_default_min_return', { valueAsNumber: true })} />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px]">Min Sharpe</Label>
                          <Input type="number" step="0.05" {...autonomousForm.register('da_default_min_sharpe', { valueAsNumber: true })} />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px]">Min WR</Label>
                          <Input type="number" step="0.01" {...autonomousForm.register('da_default_min_win_rate', { valueAsNumber: true })} />
                        </div>
                      </div>
                    </div>

                    {/* Direction-aware — per-regime grid */}
                    {[
                      { key: 'ranging', label: 'Ranging' },
                      { key: 'trending_up', label: 'Trending Up' },
                      { key: 'trending_down', label: 'Trending Down' },
                      { key: 'high_vol', label: 'High Volatility' },
                    ].map(({ key, label }) => (
                      <div key={key} className="pt-3 border-t border-dark-border">
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">{label}</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {['long', 'short'].map((dir) => (
                            <div key={dir} className="space-y-2 p-2 bg-dark-bg/50 rounded border border-dark-border/50">
                              <p className="text-[10px] uppercase text-gray-500 font-semibold">{dir}</p>
                              <div className="grid grid-cols-3 gap-2">
                                <div className="space-y-1">
                                  <Label className="text-[10px]">Return</Label>
                                  <Input type="number" step="0.01" {...autonomousForm.register(`da_${key}_${dir}_min_return` as any, { valueAsNumber: true })} />
                                </div>
                                <div className="space-y-1">
                                  <Label className="text-[10px]">Sharpe</Label>
                                  <Input type="number" step="0.05" {...autonomousForm.register(`da_${key}_${dir}_min_sharpe` as any, { valueAsNumber: true })} />
                                </div>
                                <div className="space-y-1">
                                  <Label className="text-[10px]">WR</Label>
                                  <Input type="number" step="0.01" {...autonomousForm.register(`da_${key}_${dir}_min_win_rate` as any, { valueAsNumber: true })} />
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 7 — Adaptive Risk (SL/TP bounds)                        */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-[11px]">Enable Adaptive Risk</Label>
                        <p className="text-xs text-gray-500">Clamps strategy SL/TP into sensible bounds at proposal time</p>
                      </div>
                      <Switch
                        checked={autonomousForm.watch('adaptive_risk_enabled')}
                        onCheckedChange={(checked) => autonomousForm.setValue('adaptive_risk_enabled', checked)}
                      />
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min SL (%)</Label>
                        <Input type="number" step="0.5" min="0.5" max="20" {...autonomousForm.register('adaptive_min_sl_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max SL (%)</Label>
                        <Input type="number" step="0.5" min="1" max="30" {...autonomousForm.register('adaptive_max_sl_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min TP (%)</Label>
                        <Input type="number" step="0.5" min="1" max="30" {...autonomousForm.register('adaptive_min_tp_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max TP (%)</Label>
                        <Input type="number" step="0.5" min="2" max="50" {...autonomousForm.register('adaptive_max_tp_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min R:R Ratio</Label>
                        <Input type="number" step="0.1" min="0.5" max="5" {...autonomousForm.register('adaptive_min_rr_ratio', { valueAsNumber: true })} />
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 8 — Performance Feedback                                */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Performance Feedback Loop</h3>
                    <p className="text-xs text-gray-500">How past-trade performance weights future proposals. Recency-decayed so stale losses don't permanently lock out a symbol.</p>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Lookback (days)</Label>
                        <Input type="number" min="7" max="365" {...autonomousForm.register('feedback_lookback_days', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Trades</Label>
                        <Input type="number" min="1" max="50" {...autonomousForm.register('feedback_min_trades', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Weight</Label>
                        <Input type="number" step="0.1" min="1.0" max="3.0" {...autonomousForm.register('feedback_max_weight', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Weight</Label>
                        <Input type="number" step="0.05" min="0.1" max="1.0" {...autonomousForm.register('feedback_min_weight', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Decay/day</Label>
                        <Input type="number" step="0.005" min="0" max="0.1" {...autonomousForm.register('feedback_weight_decay_per_day', { valueAsNumber: true })} />
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 9 — Directional Balance + Per-Regime Quotas            */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-[11px]">Enable Directional Balance</Label>
                        <p className="text-xs text-gray-500">Caps overall portfolio long/short exposure</p>
                      </div>
                      <Switch
                        checked={autonomousForm.watch('directional_balance_enabled')}
                        onCheckedChange={(checked) => autonomousForm.setValue('directional_balance_enabled', checked)}
                      />
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Long (%)</Label>
                        <Input type="number" min="0" max="100" {...autonomousForm.register('directional_min_long_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Long (%)</Label>
                        <Input type="number" min="0" max="100" {...autonomousForm.register('directional_max_long_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Min Short (%)</Label>
                        <Input type="number" min="0" max="100" {...autonomousForm.register('directional_min_short_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Short (%)</Label>
                        <Input type="number" min="0" max="100" {...autonomousForm.register('directional_max_short_pct', { valueAsNumber: true })} />
                      </div>
                    </div>

                    <div className="pt-3 border-t border-dark-border">
                      <div className="flex items-center justify-between mb-3">
                        <div className="space-y-0.5">
                          <Label className="text-[11px]">Per-Regime Directional Quotas</Label>
                          <p className="text-xs text-gray-500">Minimum long/short % allocation by market regime</p>
                        </div>
                        <Switch
                          checked={autonomousForm.watch('dq_enabled')}
                          onCheckedChange={(checked) => autonomousForm.setValue('dq_enabled', checked)}
                        />
                      </div>
                      <div className="space-y-2 mb-3">
                        <Label className="text-[11px]">Adjacent Regime Reserve (%)</Label>
                        <Input type="number" step="1" min="0" max="100" {...autonomousForm.register('dq_adjacent_regime_reserve_pct', { valueAsNumber: true })} />
                        <p className="text-xs text-gray-500">Slack when regime is at boundary (prevents whipsaw allocations)</p>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {[
                          { key: 'ranging', label: 'Ranging' },
                          { key: 'ranging_low_vol', label: 'Ranging (low vol)' },
                          { key: 'trending_up', label: 'Trending Up' },
                          { key: 'trending_up_weak', label: 'Trending Up (weak)' },
                          { key: 'trending_up_strong', label: 'Trending Up (strong)' },
                          { key: 'trending_down', label: 'Trending Down' },
                          { key: 'trending_down_weak', label: 'Trending Down (weak)' },
                          { key: 'high_volatility', label: 'High Volatility' },
                        ].map(({ key, label }) => (
                          <div key={key} className="p-2 bg-dark-bg/50 rounded border border-dark-border/50">
                            <p className="text-[10px] uppercase text-gray-500 font-semibold mb-2">{label}</p>
                            <div className="grid grid-cols-2 gap-2">
                              <div className="space-y-1">
                                <Label className="text-[10px]">Min Long (%)</Label>
                                <Input type="number" step="1" min="0" max="100" {...autonomousForm.register(`dq_${key}_long` as any, { valueAsNumber: true })} />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px]">Min Short (%)</Label>
                                <Input type="number" step="1" min="0" max="100" {...autonomousForm.register(`dq_${key}_short` as any, { valueAsNumber: true })} />
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* ══════════════════════════════════════════════════════════ */}
                  {/* CARD 10 — Portfolio Caps                                     */}
                  {/* ══════════════════════════════════════════════════════════ */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Portfolio Exposure Caps</h3>
                    <p className="text-xs text-gray-500">Upper bounds on long/short and sector exposure.</p>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Long Exposure (%)</Label>
                        <Input type="number" min="10" max="100" {...autonomousForm.register('max_long_exposure_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Short Exposure (%)</Label>
                        <Input type="number" min="10" max="100" {...autonomousForm.register('max_short_exposure_pct', { valueAsNumber: true })} />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-[11px]">Max Sector Exposure (%)</Label>
                        <Input type="number" min="10" max="100" {...autonomousForm.register('max_sector_exposure_pct', { valueAsNumber: true })} />
                      </div>
                    </div>
                  </div>

                  {/* Save / Reset */}
                  <div className="flex gap-3">
                    <Button type="submit" disabled={autonomousForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {autonomousForm.formState.isSubmitting ? 'Saving...' : 'Save Configuration'}
                    </Button>
                    <Button type="button" variant="outline" onClick={() => autonomousForm.reset()}>
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>
                </form>

                {/* ══════════════════════════════════════════════════════════ */}
                {/* READ-ONLY — Advanced / System (Category 3)                   */}
                {/* ══════════════════════════════════════════════════════════ */}
                {autonomousAdvanced && (
                  <div className="mt-8 p-4 bg-dark-bg/60 border border-dark-border rounded-lg space-y-3">
                    <div className="flex items-start gap-2">
                      <Info className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <h3 className="text-[11px] font-semibold text-gray-300">Advanced / System (read-only)</h3>
                        <p className="text-xs text-gray-500">These values are managed directly in <code className="text-[10px] bg-dark-bg px-1 rounded">config/autonomous_trading.yaml</code> by ops and reflect the actual broker cost model, validation rules, symbol universe, and data source status. Editing them from this UI is intentionally disabled because changes affect backtest correctness and historical comparability.</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-dark-border">
                      <div>
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">Transaction Costs — Per Asset Class (%)</h4>
                        <div className="space-y-1 text-[11px] font-mono">
                          {(['stock','etf','forex','crypto','index','commodity'] as const).map(ac => {
                            const c = autonomousAdvanced[`transaction_costs_${ac}`] || {};
                            const rt = ((c.commission_percent || 0) + (c.spread_percent || 0) + (c.slippage_percent || 0)) * 2 * 100;
                            return (
                              <div key={ac} className="grid grid-cols-5 gap-1 text-gray-400">
                                <span className="text-gray-300 capitalize">{ac}</span>
                                <span>c: {((c.commission_percent || 0) * 100).toFixed(3)}%</span>
                                <span>s: {((c.spread_percent || 0) * 100).toFixed(3)}%</span>
                                <span>sl: {((c.slippage_percent || 0) * 100).toFixed(3)}%</span>
                                <span className="text-gray-200">rt: {rt.toFixed(2)}%</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div>
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">Transaction Costs — Per Symbol Overrides</h4>
                        <div className="space-y-1 text-[11px] font-mono">
                          {Object.entries(autonomousAdvanced.transaction_costs_per_symbol || {}).map(([sym, c]: [string, any]) => {
                            const rt = ((c.commission_percent || 0) + (c.spread_percent || 0) + (c.slippage_percent || 0)) * 2 * 100;
                            return (
                              <div key={sym} className="grid grid-cols-5 gap-1 text-gray-400">
                                <span className="text-gray-300">{sym}</span>
                                <span>c: {((c.commission_percent || 0) * 100).toFixed(3)}%</span>
                                <span>s: {((c.spread_percent || 0) * 100).toFixed(3)}%</span>
                                <span>sl: {((c.slippage_percent || 0) * 100).toFixed(3)}%</span>
                                <span className="text-gray-200">rt: {rt.toFixed(2)}%</span>
                              </div>
                            );
                          })}
                          {Object.keys(autonomousAdvanced.transaction_costs_per_symbol || {}).length === 0 && (
                            <span className="text-gray-500">(none)</span>
                          )}
                        </div>
                      </div>

                      <div>
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">Asset-Class Defaults (SL / TP / Hold)</h4>
                        <div className="space-y-1 text-[11px] font-mono">
                          {Object.entries(autonomousAdvanced.asset_class_parameters || {}).map(([ac, p]: [string, any]) => (
                            <div key={ac} className="grid grid-cols-4 gap-1 text-gray-400">
                              <span className="text-gray-300 capitalize">{ac}</span>
                              <span>SL: {((p.stop_loss_pct || 0) * 100).toFixed(1)}%</span>
                              <span>TP: {((p.take_profit_pct || 0) * 100).toFixed(1)}%</span>
                              <span>hold: {p.holding_period_days_min}-{p.holding_period_days_max}d</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div>
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">Symbol Universe</h4>
                        <div className="space-y-1 text-[11px] font-mono">
                          {Object.entries(autonomousAdvanced.symbol_counts || {}).map(([cls, n]: [string, any]) => (
                            <div key={cls} className="grid grid-cols-2 gap-1 text-gray-400">
                              <span className="text-gray-300 capitalize">{cls}</span>
                              <span>{n} symbols</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="md:col-span-2">
                        <h4 className="text-[11px] text-gray-400 font-medium mb-2">Data Sources</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
                          {Object.entries(autonomousAdvanced.data_sources || {}).map(([name, ds]: [string, any]) => (
                            <div key={name} className={cn("p-1.5 rounded border", ds.enabled ? "border-green-900/50 bg-green-900/10" : "border-gray-800 bg-gray-900/30")}>
                              <span className="text-gray-300">{name}</span>{' '}
                              <span className={ds.enabled ? "text-green-400" : "text-gray-500"}>
                                {ds.enabled ? 'ON' : 'OFF'}
                              </span>
                              {ds.cache_duration && (
                                <span className="text-gray-500"> · {Math.round((ds.cache_duration || 0) / 3600)}h cache</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
          </TabsContent>

          {/* Alpha Edge Tab */}
          <TabsContent value="alpha-edge" className="space-y-4">
            <SectionLabel>Alpha Edge Settings</SectionLabel>
                <form onSubmit={alphaEdgeForm.handleSubmit(onAlphaEdgeSubmit)} className="space-y-8">
                  
                  {/* Fundamental Filters Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="fundamental-filters-enabled" className="text-[11px]">Enable Fundamental Filtering</Label>
                        <p className="text-xs text-gray-500">Filter stocks based on fundamental criteria before trading</p>
                      </div>
                      <Switch
                        id="fundamental-filters-enabled"
                        checked={alphaEdgeForm.watch('fundamental_filters_enabled')}
                        onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_filters_enabled', checked)}
                      />
                    </div>

                    {alphaEdgeForm.watch('fundamental_filters_enabled') && (
                      <div className="space-y-4 pl-4">
                        <div className="space-y-2">
                          <Label htmlFor="fundamental_min_checks_passed" className="text-[11px]">Minimum Checks Required</Label>
                          <Input
                            id="fundamental_min_checks_passed"
                            type="number"
                            min="1"
                            max="5"
                            {...alphaEdgeForm.register('fundamental_min_checks_passed', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Number of fundamental checks that must pass (out of 5)</p>
                        </div>

                        <div className="space-y-3">
                          <Label className="text-[11px] font-semibold text-gray-300">Individual Checks</Label>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-profitable" className="text-[11px]">Profitable (EPS &gt; 0)</Label>
                                <p className="text-xs text-gray-500">Company must be profitable</p>
                              </div>
                              <Checkbox
                                id="check-profitable"
                                checked={alphaEdgeForm.watch('fundamental_checks.profitable')}
                                onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_checks.profitable', checked as boolean)}
                              />
                            </div>

                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-growing" className="text-[11px]">Growing Revenue</Label>
                                <p className="text-xs text-gray-500">Revenue growth &gt; 0%</p>
                              </div>
                              <Checkbox
                                id="check-growing"
                                checked={alphaEdgeForm.watch('fundamental_checks.growing')}
                                onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_checks.growing', checked as boolean)}
                              />
                            </div>

                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-valuation" className="text-[11px]">Reasonable Valuation</Label>
                                <p className="text-xs text-gray-500">P/E ratio within acceptable range</p>
                              </div>
                              <Checkbox
                                id="check-valuation"
                                checked={alphaEdgeForm.watch('fundamental_checks.reasonable_valuation')}
                                onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_checks.reasonable_valuation', checked as boolean)}
                              />
                            </div>

                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-dilution" className="text-[11px]">No Excessive Dilution</Label>
                                <p className="text-xs text-gray-500">Share count change &lt; 10%</p>
                              </div>
                              <Checkbox
                                id="check-dilution"
                                checked={alphaEdgeForm.watch('fundamental_checks.no_dilution')}
                                onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_checks.no_dilution', checked as boolean)}
                              />
                            </div>

                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-insider" className="text-[11px]">Insider Buying</Label>
                                <p className="text-xs text-gray-500">Net insider buying &gt; 0</p>
                              </div>
                              <Checkbox
                                id="check-insider"
                                checked={alphaEdgeForm.watch('fundamental_checks.insider_buying')}
                                onCheckedChange={(checked) => alphaEdgeForm.setValue('fundamental_checks.insider_buying', checked as boolean)}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* ML Filter Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="ml-filter-enabled" className="text-[11px]">Enable ML Signal Filtering</Label>
                        <p className="text-xs text-gray-500">Use machine learning to filter trading signals</p>
                      </div>
                      <Switch
                        id="ml-filter-enabled"
                        checked={alphaEdgeForm.watch('ml_filter_enabled')}
                        onCheckedChange={(checked) => alphaEdgeForm.setValue('ml_filter_enabled', checked)}
                      />
                    </div>

                    {alphaEdgeForm.watch('ml_filter_enabled') && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pl-4">
                        <div className="space-y-2">
                          <Label htmlFor="ml_min_confidence" className="text-[11px]">Minimum Confidence (%)</Label>
                          <Input
                            id="ml_min_confidence"
                            type="number"
                            step="1"
                            min="50"
                            max="95"
                            {...alphaEdgeForm.register('ml_min_confidence', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">Only trade signals with ML confidence above this threshold</p>
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="ml_retrain_frequency_days" className="text-[11px]">Retrain Frequency (days)</Label>
                          <Input
                            id="ml_retrain_frequency_days"
                            type="number"
                            step="1"
                            min="1"
                            max="90"
                            {...alphaEdgeForm.register('ml_retrain_frequency_days', { valueAsNumber: true })}
                          />
                          <p className="text-xs text-gray-500">How often to retrain the ML model with new data</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Trading Frequency Section */}
                  <div className="space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Trading Frequency Controls</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="max_active_strategies" className="text-[11px]">Max Active Strategies</Label>
                        <Input
                          id="max_active_strategies"
                          type="number"
                          min="5"
                          max="20"
                          {...alphaEdgeForm.register('max_active_strategies', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Maximum number of active strategies (5-20)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_conviction_score" className="text-[11px]">Min Conviction Score</Label>
                        <Input
                          id="min_conviction_score"
                          type="number"
                          min="50"
                          max="90"
                          {...alphaEdgeForm.register('min_conviction_score', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum conviction score to generate signals (50-90)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_holding_period_days" className="text-[11px]">Min Holding Period (days)</Label>
                        <Input
                          id="min_holding_period_days"
                          type="number"
                          min="1"
                          max="30"
                          {...alphaEdgeForm.register('min_holding_period_days', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum days to hold a position</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="max_trades_per_strategy_per_month" className="text-[11px]">Max Trades/Strategy/Month</Label>
                        <Input
                          id="max_trades_per_strategy_per_month"
                          type="number"
                          min="1"
                          max="10"
                          {...alphaEdgeForm.register('max_trades_per_strategy_per_month', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Maximum trades per strategy per month</p>
                      </div>
                    </div>
                  </div>

                  {/* Strategy Templates Section */}
                  <div className="space-y-4">
                    <h3 className="text-[11px] font-semibold text-gray-300">Alpha Edge Strategy Templates</h3>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="earnings-momentum-enabled" className="text-[11px]">Earnings Momentum</Label>
                          <p className="text-xs text-gray-500">Trade small-cap stocks with positive earnings surprises</p>
                        </div>
                        <Switch
                          id="earnings-momentum-enabled"
                          checked={alphaEdgeForm.watch('earnings_momentum_enabled')}
                          onCheckedChange={(checked) => alphaEdgeForm.setValue('earnings_momentum_enabled', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="sector-rotation-enabled" className="text-[11px]">Sector Rotation</Label>
                          <p className="text-xs text-gray-500">Rotate into sectors that outperform in current market regime</p>
                        </div>
                        <Switch
                          id="sector-rotation-enabled"
                          checked={alphaEdgeForm.watch('sector_rotation_enabled')}
                          onCheckedChange={(checked) => alphaEdgeForm.setValue('sector_rotation_enabled', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="quality-mean-reversion-enabled" className="text-[11px]">Quality Mean Reversion</Label>
                          <p className="text-xs text-gray-500">Buy high-quality stocks when temporarily oversold</p>
                        </div>
                        <Switch
                          id="quality-mean-reversion-enabled"
                          checked={alphaEdgeForm.watch('quality_mean_reversion_enabled')}
                          onCheckedChange={(checked) => alphaEdgeForm.setValue('quality_mean_reversion_enabled', checked)}
                        />
                      </div>
                    </div>
                  </div>

                  {/* API Usage Monitoring */}
                  {apiUsage && (
                    <div className="space-y-4">
                      <h3 className="text-[11px] font-semibold text-gray-300">API Usage Monitoring</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* FMP Usage */}
                        <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <Label className="text-[11px]">Financial Modeling Prep</Label>
                            <span className="text-xs text-gray-500">
                              {apiUsage.fmp_usage.calls_today} / {apiUsage.fmp_usage.limit}
                            </span>
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-2">
                            <div
                              className={cn(
                                "h-2 rounded-full transition-all",
                                apiUsage.fmp_usage.percentage >= 80 ? "bg-red-500" :
                                apiUsage.fmp_usage.percentage >= 60 ? "bg-yellow-500" :
                                "bg-green-500"
                              )}
                              style={{ width: `${Math.min(apiUsage.fmp_usage.percentage, 100)}%` }}
                            />
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            {apiUsage.fmp_usage.remaining} calls remaining ({apiUsage.fmp_usage.percentage.toFixed(1)}% used)
                          </p>
                        </div>

                        {/* Alpha Vantage Usage */}
                        <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <Label className="text-[11px]">Alpha Vantage</Label>
                            <span className="text-xs text-gray-500">
                              {apiUsage.alpha_vantage_usage.calls_today} / {apiUsage.alpha_vantage_usage.limit}
                            </span>
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-2">
                            <div
                              className={cn(
                                "h-2 rounded-full transition-all",
                                apiUsage.alpha_vantage_usage.percentage >= 80 ? "bg-red-500" :
                                apiUsage.alpha_vantage_usage.percentage >= 60 ? "bg-yellow-500" :
                                "bg-green-500"
                              )}
                              style={{ width: `${Math.min(apiUsage.alpha_vantage_usage.percentage, 100)}%` }}
                            />
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            {apiUsage.alpha_vantage_usage.remaining} calls remaining ({apiUsage.alpha_vantage_usage.percentage.toFixed(1)}% used)
                          </p>
                        </div>
                      </div>

                      {/* Cache Stats */}
                      <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <Label className="text-[11px] mb-2 block">Cache Statistics</Label>
                        <div className="grid grid-cols-2 gap-4 text-[12px]">
                          <div>
                            <span className="text-gray-500">Cache Size:</span>
                            <span className="ml-2 text-gray-300">{apiUsage.cache_stats?.size} entries</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Hit Rate:</span>
                            <span className="ml-2 text-gray-300">{apiUsage.cache_stats?.hit_rate.toFixed(1)}%</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Info Box */}
                  <div className="p-4 bg-blue-900/20 border border-blue-700 rounded-lg flex items-start gap-3">
                    <Info className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-blue-400 font-semibold text-[11px] mb-1">Alpha Edge Features</div>
                      <div className="text-xs text-gray-400">
                        These settings control advanced alpha generation features including fundamental analysis, 
                        machine learning signal filtering, and specialized strategy templates. Test thoroughly in 
                        DEMO mode before enabling in LIVE mode.
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button type="submit" disabled={alphaEdgeForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {alphaEdgeForm.formState.isSubmitting ? 'Saving...' : 'Save Alpha Edge Settings'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => alphaEdgeForm.reset()}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>
                </form>
          </TabsContent>

          {/* Alerts & Notifications Tab */}
          <TabsContent value="notifications" className="space-y-6">
            {/* Alert Thresholds */}
            <SectionLabel>Alert Thresholds</SectionLabel>
            <div className="space-y-4">
                {/* P&L Loss Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[11px] text-red-400">Daily P&L Loss</Label>
                    <p className="text-xs text-gray-500">Alert when daily P&L drops below threshold</p>
                    {alertConfig.pnl_loss_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-[11px] text-gray-400">-$</span>
                        <Input
                          type="number"
                          value={alertConfig.pnl_loss_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, pnl_loss_threshold: Number(e.target.value) }))}
                          className="w-32 h-8 text-[12px]"
                          min={0}
                        />
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.pnl_loss_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, pnl_loss_enabled: checked }))}
                  />
                </div>

                {/* P&L Gain Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[11px] text-green-400">Daily P&L Gain</Label>
                    <p className="text-xs text-gray-500">Alert when daily P&L exceeds threshold</p>
                    {alertConfig.pnl_gain_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-[11px] text-gray-400">+$</span>
                        <Input
                          type="number"
                          value={alertConfig.pnl_gain_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, pnl_gain_threshold: Number(e.target.value) }))}
                          className="w-32 h-8 text-[12px]"
                          min={0}
                        />
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.pnl_gain_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, pnl_gain_enabled: checked }))}
                  />
                </div>

                {/* Drawdown Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[11px] text-amber-400">Drawdown</Label>
                    <p className="text-xs text-gray-500">Alert when drawdown exceeds threshold</p>
                    {alertConfig.drawdown_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.drawdown_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, drawdown_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-[12px]"
                          min={0}
                          max={100}
                        />
                        <span className="text-[11px] text-gray-400">%</span>
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.drawdown_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, drawdown_enabled: checked }))}
                  />
                </div>

                {/* Position Loss Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[11px] text-orange-400">Position Loss</Label>
                    <p className="text-xs text-gray-500">Alert when any position loses more than threshold</p>
                    {alertConfig.position_loss_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.position_loss_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, position_loss_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-[12px]"
                          min={0}
                          max={100}
                        />
                        <span className="text-[11px] text-gray-400">%</span>
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.position_loss_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, position_loss_enabled: checked }))}
                  />
                </div>

                {/* Margin Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[11px] text-purple-400">Margin Utilization</Label>
                    <p className="text-xs text-gray-500">Alert when margin utilization exceeds threshold</p>
                    {alertConfig.margin_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.margin_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, margin_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-[12px]"
                          min={0}
                          max={100}
                        />
                        <span className="text-[11px] text-gray-400">%</span>
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.margin_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, margin_enabled: checked }))}
                  />
                </div>
            </div>

            {/* Event Alerts */}
            <SectionLabel>Event Alerts</SectionLabel>
            <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-[11px]">Autonomous Cycle Complete</Label>
                    <p className="text-xs text-gray-500">Alert when an autonomous cycle finishes</p>
                  </div>
                  <Switch
                    checked={alertConfig.cycle_complete_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, cycle_complete_enabled: checked }))}
                  />
                </div>
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-[11px]">Strategy Retired</Label>
                    <p className="text-xs text-gray-500">Alert when a strategy is retired</p>
                  </div>
                  <Switch
                    checked={alertConfig.strategy_retired_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, strategy_retired_enabled: checked }))}
                  />
                </div>
            </div>

            {/* Delivery Settings */}
            <SectionLabel>Delivery Settings</SectionLabel>
            <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-[11px]">In-App Notifications</Label>
                    <p className="text-xs text-gray-500">Toast + persistent alert in notification panel (always on)</p>
                  </div>
                  <span className="text-xs text-green-400 bg-green-500/10 px-2 py-1 rounded">Always On</span>
                </div>
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-[11px]">Browser Push Notifications</Label>
                    <p className="text-xs text-gray-500">Get notified even when the tab is not focused (critical alerts only)</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {!alertConfig.browser_push_enabled && (
                      <Button variant="outline" size="sm" onClick={requestPushPermission}>
                        Enable
                      </Button>
                    )}
                    <Switch
                      checked={alertConfig.browser_push_enabled}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          requestPushPermission();
                        } else {
                          setAlertConfig(prev => ({ ...prev, browser_push_enabled: false }));
                        }
                      }}
                    />
                  </div>
                </div>

                <div className="pt-4">
                  <Button onClick={saveAlertConfig} disabled={alertConfigLoading} className="w-full">
                    <Save className="h-4 w-4 mr-2" />
                    {alertConfigLoading ? 'Saving...' : 'Save Alert Configuration'}
                  </Button>
                </div>
            </div>
          </TabsContent>

          {/* Users & Security Tab */}
          <TabsContent value="users" className="space-y-6">
            {/* Change Password — available to all users */}
            <SectionLabel>Change Password</SectionLabel>
            <div className="space-y-4 max-w-md">
                <div className="space-y-2">
                  <Label htmlFor="old-password" className="text-[11px]">Current Password</Label>
                  <Input
                    id="old-password"
                    type="password"
                    value={changePasswordOld}
                    onChange={(e) => setChangePasswordOld(e.target.value)}
                    placeholder="Enter current password"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-password" className="text-[11px]">New Password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={changePasswordNew}
                    onChange={(e) => setChangePasswordNew(e.target.value)}
                    placeholder="Min 6 characters"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password" className="text-[11px]">Confirm New Password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={changePasswordConfirm}
                    onChange={(e) => setChangePasswordConfirm(e.target.value)}
                    placeholder="Repeat new password"
                  />
                </div>
                <Button
                  onClick={handleChangePassword}
                  disabled={changePasswordLoading || !changePasswordOld || !changePasswordNew || !changePasswordConfirm}
                >
                  {changePasswordLoading ? 'Changing...' : 'Change Password'}
                </Button>
            </div>

            {/* User Management — admin only */}
            {isAdmin && (
              <div>
                <SectionLabel actions={
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={loadUsers} disabled={userListLoading}>
                      <RotateCw className={cn("h-4 w-4 mr-1", userListLoading && "animate-spin")} />
                      Refresh
                    </Button>
                    <Button size="sm" onClick={() => setShowCreateUser(true)}>
                      <UserPlus className="h-4 w-4 mr-1" />
                      New User
                    </Button>
                  </div>
                }>User Management</SectionLabel>

                  {/* Role legend */}
                  <div className="flex gap-4 mb-4 text-xs text-gray-400">
                    <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />Admin — full access, user management</span>
                    <span><span className="inline-block w-2 h-2 rounded-full bg-yellow-500 mr-1" />Trader — trade, manage strategies</span>
                    <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />Viewer — read-only dashboard access</span>
                  </div>

                  {/* Create user form */}
                  {showCreateUser && (
                    <div className="mb-4 p-4 border border-gray-700 rounded-lg bg-dark-surface space-y-3">
                      <h4 className="text-[11px] font-medium text-gray-200">Create New User</h4>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <Label htmlFor="create-username" className="text-xs">Username</Label>
                          <Input
                            id="create-username"
                            value={newUsername}
                            onChange={(e) => setNewUsername(e.target.value)}
                            placeholder="username"
                          />
                        </div>
                        <div>
                          <Label htmlFor="create-password" className="text-xs">Password</Label>
                          <Input
                            id="create-password"
                            type="password"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            placeholder="min 6 chars"
                          />
                        </div>
                        <div>
                          <Label htmlFor="create-role" className="text-xs">Role</Label>
                          <select
                            id="create-role"
                            value={newRole}
                            onChange={(e) => setNewRole(e.target.value)}
                            className="w-full h-10 rounded-md border border-gray-700 bg-dark-bg px-3 text-[12px] text-gray-200"
                          >
                            <option value="admin">Admin</option>
                            <option value="trader">Trader</option>
                            <option value="viewer">Viewer</option>
                          </select>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={handleCreateUser} disabled={createUserLoading}>
                          {createUserLoading ? 'Creating...' : 'Create'}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => { setShowCreateUser(false); setNewUsername(''); setNewPassword(''); }}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* User list */}
                  {userList.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p className="text-[11px]">Click Refresh to load users</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[12px]">
                        <thead>
                          <tr className="border-b border-gray-700 text-gray-400">
                            <th className="text-left py-2 px-3 text-xs">Username</th>
                            <th className="text-left py-2 px-3 text-xs">Role</th>
                            <th className="text-left py-2 px-3 text-xs">Status</th>
                            <th className="text-left py-2 px-3 text-xs">Created</th>
                            <th className="text-left py-2 px-3 text-xs">Last Login</th>
                            <th className="text-right py-2 px-3 text-xs">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {userList.map((user) => (
                            <tr key={user.username} className="border-b border-gray-800 hover:bg-gray-800/50">
                              <td className="py-2 px-3 font-medium text-gray-200">
                                {user.username}
                                {user.username === authService.getUsername() && (
                                  <span className="ml-2 text-xs text-blue-400">(you)</span>
                                )}
                              </td>
                              <td className="py-2 px-3">
                                {user.username === authService.getUsername() ? (
                                  <span className={cn(
                                    "px-2 py-0.5 rounded text-xs font-medium",
                                    user.role === 'admin' ? 'bg-red-900/30 text-red-400' :
                                    user.role === 'trader' ? 'bg-yellow-900/30 text-yellow-400' :
                                    'bg-blue-900/30 text-blue-400'
                                  )}>
                                    {user.role}
                                  </span>
                                ) : (
                                  <select
                                    value={user.role}
                                    onChange={(e) => handleRoleChange(user.username, e.target.value)}
                                    className={cn(
                                      "px-2 py-0.5 rounded text-xs font-medium border-0 cursor-pointer",
                                      user.role === 'admin' ? 'bg-red-900/30 text-red-400' :
                                      user.role === 'trader' ? 'bg-yellow-900/30 text-yellow-400' :
                                      'bg-blue-900/30 text-blue-400'
                                    )}
                                  >
                                    <option value="admin">admin</option>
                                    <option value="trader">trader</option>
                                    <option value="viewer">viewer</option>
                                  </select>
                                )}
                              </td>
                              <td className="py-2 px-3">
                                <button
                                  onClick={() => user.username !== authService.getUsername() && handleToggleActive(user.username, user.is_active)}
                                  disabled={user.username === authService.getUsername()}
                                  className={cn(
                                    "px-2 py-0.5 rounded text-xs font-medium",
                                    user.is_active ? 'bg-green-900/30 text-green-400' : 'bg-gray-700 text-gray-400',
                                    user.username !== authService.getUsername() && 'cursor-pointer hover:opacity-80'
                                  )}
                                >
                                  {user.is_active ? 'Active' : 'Disabled'}
                                </button>
                              </td>
                              <td className="py-2 px-3 text-gray-400 text-xs">
                                {user.created_at ? formatDate(user.created_at) : '—'}
                              </td>
                              <td className="py-2 px-3 text-gray-400 text-xs">
                                {user.last_login ? formatDateTime(user.last_login) : 'Never'}
                              </td>
                              <td className="py-2 px-3 text-right">
                                {user.username !== authService.getUsername() && (
                                  <div className="flex items-center justify-end gap-1">
                                    {resetPasswordUser === user.username ? (
                                      <div className="flex items-center gap-1">
                                        <Input
                                          type="password"
                                          value={resetPasswordValue}
                                          onChange={(e) => setResetPasswordValue(e.target.value)}
                                          placeholder="new password"
                                          className="h-7 w-32 text-xs"
                                        />
                                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleResetPassword(user.username)}>
                                          Set
                                        </Button>
                                        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setResetPasswordUser(null); setResetPasswordValue(''); }}>
                                          ✕
                                        </Button>
                                      </div>
                                    ) : deleteConfirmUser === user.username ? (
                                      <div className="flex items-center gap-1">
                                        <span className="text-xs text-red-400">Delete?</span>
                                        <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={() => handleDeleteUser(user.username)}>
                                          Yes
                                        </Button>
                                        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setDeleteConfirmUser(null)}>
                                          No
                                        </Button>
                                      </div>
                                    ) : (
                                      <>
                                        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setResetPasswordUser(user.username)} title="Reset password">
                                          <Key className="h-3 w-3" />
                                        </Button>
                                        <Button size="sm" variant="ghost" className="h-7 text-xs text-red-400 hover:text-red-300" onClick={() => setDeleteConfirmUser(user.username)} title="Delete user">
                                          <Trash2 className="h-3 w-3" />
                                        </Button>
                                      </>
                                    )}
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
              </div>
            )}

            {!isAdmin && (
              <div className="py-8 text-center text-gray-500">
                <Shield className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-[11px]">User management is only available to administrators.</p>
                <p className="text-xs mt-1">Your role: <span className="text-gray-300">{authService.getRole()}</span></p>
              </div>
            )}
          </TabsContent>

          {/* Keyboard Shortcuts Tab */}
          <TabsContent value="shortcuts" className="space-y-4">
            <SectionLabel>Keyboard Shortcuts</SectionLabel>
            <p className="text-xs text-gray-500 mb-2">
              Use keyboard shortcuts to navigate faster. Shortcuts are disabled while typing in input fields.
              Press <kbd className="px-1.5 py-0.5 rounded text-xs font-mono bg-gray-800 border border-gray-700 mx-1">?</kbd> anywhere to toggle this reference.
            </p>
                <div className="space-y-6">
                  {(['navigation', 'actions', 'general'] as const).map((category) => {
                    const items = KEYBOARD_SHORTCUTS.filter((s) => s.category === category);
                    if (items.length === 0) return null;
                    const categoryLabels = { navigation: 'Navigation', actions: 'Actions', general: 'General' };
                    return (
                      <div key={category}>
                        <h3 className="text-[11px] font-semibold text-gray-300 uppercase tracking-wider mb-3">
                          {categoryLabels[category]}
                        </h3>
                        <div className="space-y-2">
                          {items.map((shortcut) => (
                            <div
                              key={shortcut.key}
                              className="flex items-center justify-between py-2 px-3 rounded-lg bg-dark-bg/50"
                            >
                              <span className="text-[12px] text-gray-300">{shortcut.description}</span>
                              <kbd className="px-2.5 py-1 rounded text-xs font-mono bg-gray-800 border border-gray-700 text-gray-400">
                                {shortcut.label}
                              </kbd>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Trading Mode Confirmation Dialog */}
      <Dialog open={showTradingModeDialog} onOpenChange={setShowTradingModeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Trading Mode Change</DialogTitle>
            <DialogDescription>
              {pendingTradingMode === TradingMode.LIVE ? (
                <div className="space-y-3 pt-2">
                  <div className="flex items-start gap-3 p-3 bg-red-900/20 border border-red-700 rounded">
                    <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-gray-300">
                      <p className="font-semibold text-red-400 mb-1">Warning: Switching to Live Mode</p>
                      <p>You are about to switch to live trading mode. All orders will be executed with real money on your eToro account.</p>
                    </div>
                  </div>
                  <ul className="text-sm text-gray-400 space-y-1 list-disc list-inside">
                    <li>Ensure your API credentials are correct</li>
                    <li>Verify your risk parameters are properly configured</li>
                    <li>Start with small position sizes</li>
                    <li>Monitor your account closely</li>
                  </ul>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div className="flex items-start gap-3 p-3 bg-yellow-900/20 border border-yellow-700 rounded">
                    <Info className="h-5 w-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-gray-300">
                      <p className="font-semibold text-yellow-400 mb-1">Switching to Demo Mode</p>
                      <p>You are about to switch to demo trading mode. All trades will be simulated with paper money.</p>
                    </div>
                  </div>
                </div>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTradingModeDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={confirmTradingModeChange}
              className={cn(
                pendingTradingMode === TradingMode.LIVE && "bg-red-600 hover:bg-red-700"
              )}
            >
              Confirm Change
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </PageTemplate>
    </DashboardLayout>
  );
};
