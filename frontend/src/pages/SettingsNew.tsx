import { type FC, useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { motion } from 'framer-motion';
import { 
  Settings as SettingsIcon, Shield, Bell, Key, Activity,
  Save, RotateCcw, Eye, EyeOff, CheckCircle, RefreshCw,
  AlertTriangle, Info, Target, TrendingUp, Keyboard, Users,
  UserPlus, Trash2, RotateCw, Lock
} from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
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
  enabled: z.boolean(),
  proposal_count: z.number().min(10).max(500),
  max_active_strategies: z.number().min(5).max(500),
  min_active_strategies: z.number().min(3).max(25),
  watchlist_size: z.number().min(1).max(20),
  backtested_ttl_cycles: z.number().min(6).max(200),
  signal_generation_interval: z.number().min(300).max(3600),
  dynamic_symbol_additions: z.number().min(0).max(50),
  // Activation thresholds
  min_sharpe: z.number().min(0).max(3.0),
  min_sharpe_crypto: z.number().min(0).max(3.0),
  max_drawdown: z.number().min(5).max(50),
  min_win_rate: z.number().min(30).max(80),
  min_win_rate_crypto: z.number().min(20).max(70),
  min_trades: z.number().min(1).max(50),
  min_trades_alpha_edge: z.number().min(1).max(50),
  min_trades_dsl: z.number().min(1).max(50),
  // Retirement thresholds
  retirement_max_sharpe: z.number().min(0).max(2.0),
  retirement_max_drawdown: z.number().min(5).max(50),
  retirement_min_win_rate: z.number().min(20).max(60),
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
      enabled: true,
      proposal_count: 100,
      max_active_strategies: 25,
      min_active_strategies: 10,
      watchlist_size: 10,
      backtested_ttl_cycles: 48,
      signal_generation_interval: 1800,
      dynamic_symbol_additions: 10,
      min_sharpe: 1.0,
      min_sharpe_crypto: 0.4,
      max_drawdown: 12,
      min_win_rate: 50,
      min_win_rate_crypto: 38,
      min_trades: 5,
      min_trades_alpha_edge: 5,
      min_trades_dsl: 10,
      retirement_max_sharpe: 0.5,
      retirement_max_drawdown: 15,
      retirement_min_win_rate: 40,
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
      
      // Fire ALL config requests in parallel instead of sequentially
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

      // Apply risk config
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

      // Apply autonomous config
      if (autonomousConfig) {
        autonomousForm.reset({
          enabled: autonomousConfig.enabled,
          proposal_count: autonomousConfig.proposal_count,
          max_active_strategies: autonomousConfig.max_active_strategies,
          min_active_strategies: autonomousConfig.min_active_strategies,
          watchlist_size: autonomousConfig.watchlist_size,
          backtested_ttl_cycles: autonomousConfig.backtested_ttl_cycles ?? 48,
          signal_generation_interval: autonomousConfig.signal_generation_interval,
          dynamic_symbol_additions: autonomousConfig.dynamic_symbol_additions,
          min_sharpe: autonomousConfig.min_sharpe,
          min_sharpe_crypto: autonomousConfig.min_sharpe_crypto,
          max_drawdown: autonomousConfig.max_drawdown,
          min_win_rate: autonomousConfig.min_win_rate,
          min_win_rate_crypto: autonomousConfig.min_win_rate_crypto ?? 38,
          min_trades: autonomousConfig.min_trades,
          min_trades_alpha_edge: autonomousConfig.min_trades_alpha_edge ?? 5,
          min_trades_dsl: autonomousConfig.min_trades_dsl ?? 10,
          retirement_max_sharpe: autonomousConfig.retirement_max_sharpe,
          retirement_max_drawdown: autonomousConfig.retirement_max_drawdown,
          retirement_min_win_rate: autonomousConfig.retirement_min_win_rate,
        });
      }

      // Apply alpha edge settings
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

      // Apply API usage
      if (apiUsageData) {
        setApiUsage(apiUsageData);
      }

      // Apply alert config
      if (alertConfigData) {
        setAlertConfig(prev => ({ ...prev, ...alertConfigData }));
      }
      
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to load configuration:', error);
      toast.error('Failed to load configuration');
    } finally {
      setLoading(false);
      // Check connection status in background — don't block page render
      // This hits eToro's live API and can take 3-5+ seconds
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
      // Convert percentages to decimals for backend
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
      await apiClient.updateAutonomousConfig(formData);
      toast.success('Autonomous configuration saved successfully');
      setLastUpdated(new Date());
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
      // Get current risk config to preserve existing values
      const currentRiskConfig: any = await apiClient.getRiskConfig(contextTradingMode);
      
      // Convert percentages to decimals for backend
      const payload = {
        mode: contextTradingMode,
        // Include existing risk limit fields (required)
        max_position_size_pct: currentRiskConfig.max_position_size_pct,
        max_exposure_pct: currentRiskConfig.max_exposure_pct,
        max_daily_loss_pct: currentRiskConfig.max_daily_loss_pct,
        max_drawdown_pct: currentRiskConfig.max_drawdown_pct,
        position_risk_pct: currentRiskConfig.position_risk_pct,
        stop_loss_pct: currentRiskConfig.stop_loss_pct,
        take_profit_pct: currentRiskConfig.take_profit_pct,
        // Add position management fields
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
        ml_min_confidence: formData.ml_min_confidence / 100, // Convert to decimal
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
      
      // Reload API usage
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

  // Save alert config to backend
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

  // Request browser push notification permission
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

  // User management functions
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
          <TabsContent value="trading-mode" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-blue-500" />
                  Trading Mode
                </CardTitle>
                <CardDescription>
                  Switch between demo (paper trading) and live (real money) trading modes
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
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
                          <h3 className="text-lg font-semibold text-gray-100">Demo Mode</h3>
                          <p className="text-sm text-gray-400">Paper trading with simulated funds</p>
                        </div>
                      </div>
                      {contextTradingMode === TradingMode.DEMO && (
                        <span className="px-3 py-1 bg-yellow-500 text-dark-bg rounded-full text-xs font-bold">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <div className="space-y-2 text-sm text-gray-400">
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
                          <h3 className="text-lg font-semibold text-gray-100">Live Mode</h3>
                          <p className="text-sm text-gray-400">Real trading with actual funds</p>
                        </div>
                      </div>
                      {contextTradingMode === TradingMode.LIVE && (
                        <span className="px-3 py-1 bg-red-500 text-white rounded-full text-xs font-bold">
                          LIVE
                        </span>
                      )}
                    </div>
                    <div className="space-y-2 text-sm text-gray-400">
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
                      <div className="text-yellow-400 font-semibold mb-1">Demo Mode Active</div>
                      <div className="text-sm text-gray-400">
                        All trades are simulated. No real money is at risk. Use this mode to test strategies safely.
                      </div>
                    </div>
                  </div>
                )}

                {contextTradingMode === TradingMode.LIVE && (
                  <div className="p-4 bg-red-900/20 border border-red-700 rounded-lg flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-red-400 font-semibold mb-1">Live Mode Active</div>
                      <div className="text-sm text-gray-400">
                        Trading with real money. All orders will be executed on your live eToro account. Ensure risk parameters are properly configured.
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* API Configuration Tab */}
          <TabsContent value="api" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Key className="h-5 w-5 text-blue-500" />
                  API Configuration
                </CardTitle>
                <CardDescription>
                  Configure your eToro API credentials for {contextTradingMode} mode
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={apiForm.handleSubmit(onApiConfigSubmit)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="publicKey">eToro Public Key</Label>
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
                      <p className="text-sm text-red-500">{apiForm.formState.errors.publicKey.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="userKey">eToro User Key</Label>
                    <Input
                      id="userKey"
                      type={showKeys ? 'text' : 'password'}
                      placeholder="Enter your eToro user key"
                      {...apiForm.register('userKey')}
                    />
                    {apiForm.formState.errors.userKey && (
                      <p className="text-sm text-red-500">{apiForm.formState.errors.userKey.message}</p>
                    )}
                  </div>

                  {/* Connection Status */}
                  <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-400">Credentials Status:</span>
                      <div className="flex items-center gap-2">
                        {checkingConnection ? (
                          <span className="text-sm text-gray-400">Checking...</span>
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
                              "text-sm",
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
                          <span className="text-sm text-gray-500">Unknown</span>
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
              </CardContent>
            </Card>
          </TabsContent>

          {/* Risk Limits Tab */}
          <TabsContent value="risk" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-blue-500" />
                  Risk Limits
                </CardTitle>
                <CardDescription>
                  Configure risk management parameters to protect your capital
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={riskForm.handleSubmit(onRiskLimitsSubmit)} className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <Label htmlFor="max_position_size_pct">Max Position Size (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.max_position_size_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_exposure_pct">Max Portfolio Exposure (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.max_exposure_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_daily_loss_pct">Max Daily Loss (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.max_daily_loss_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_drawdown_pct">Max Drawdown (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.max_drawdown_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="position_risk_pct">Risk Per Trade (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.position_risk_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="stop_loss_pct">Stop Loss (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.stop_loss_pct.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="take_profit_pct">Take Profit (%)</Label>
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
                        <p className="text-sm text-red-500">{riskForm.formState.errors.take_profit_pct.message}</p>
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
              </CardContent>
            </Card>
          </TabsContent>

          {/* Position Management Tab */}
          <TabsContent value="position-management" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-5 w-5 text-blue-500" />
                  Position Management
                </CardTitle>
                <CardDescription>
                  Configure advanced position management features including trailing stops, partial exits, and dynamic sizing
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={positionManagementForm.handleSubmit(onPositionManagementSubmit)} className="space-y-8">
                  
                  {/* Trailing Stops Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="trailing-stop-enabled" className="text-base">Enable Trailing Stops</Label>
                        <p className="text-sm text-gray-500">Automatically move stop-loss up as positions become profitable</p>
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
                          <Label htmlFor="trailing_stop_activation_pct">Activation Profit (%)</Label>
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
                          <Label htmlFor="trailing_stop_distance_pct">Trailing Distance (%)</Label>
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
                        <Label htmlFor="partial-exit-enabled" className="text-base">Enable Partial Exits</Label>
                        <p className="text-sm text-gray-500">Take profits incrementally at predefined levels</p>
                      </div>
                      <Switch
                        id="partial-exit-enabled"
                        checked={positionManagementForm.watch('partial_exit_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('partial_exit_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('partial_exit_enabled') && (
                      <div className="space-y-3 pl-4">
                        <Label className="text-sm font-semibold text-gray-300">Exit Levels</Label>
                        {positionManagementForm.watch('partial_exit_levels').map((_, index) => (
                          <div key={index} className="grid grid-cols-2 gap-4 p-3 bg-dark-bg border border-dark-border rounded">
                            <div className="space-y-2">
                              <Label htmlFor={`partial_exit_levels.${index}.profit_pct`}>Profit Level (%)</Label>
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
                              <Label htmlFor={`partial_exit_levels.${index}.exit_pct`}>Exit Size (%)</Label>
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
                        <Label htmlFor="correlation-adjustment-enabled" className="text-base">Enable Correlation Adjustment</Label>
                        <p className="text-sm text-gray-500">Reduce position sizes for correlated assets to maintain diversification</p>
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
                          <Label htmlFor="correlation_threshold">Correlation Threshold</Label>
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
                          <Label htmlFor="correlation_reduction_factor">Reduction Factor</Label>
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
                        <Label htmlFor="regime-based-sizing-enabled" className="text-base">Enable Regime-Based Sizing</Label>
                        <p className="text-sm text-gray-500">Adjust position sizes based on market volatility and regime (advanced)</p>
                      </div>
                      <Switch
                        id="regime-based-sizing-enabled"
                        checked={positionManagementForm.watch('regime_based_sizing_enabled')}
                        onCheckedChange={(checked) => positionManagementForm.setValue('regime_based_sizing_enabled', checked)}
                      />
                    </div>

                    {positionManagementForm.watch('regime_based_sizing_enabled') && (
                      <div className="space-y-3 pl-4">
                        <Label className="text-sm font-semibold text-gray-300">Regime Multipliers</Label>
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label htmlFor="regime_multipliers.high_volatility">High Volatility</Label>
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
                            <Label htmlFor="regime_multipliers.low_volatility">Low Volatility</Label>
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
                            <Label htmlFor="regime_multipliers.trending">Trending Market</Label>
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
                            <Label htmlFor="regime_multipliers.ranging">Ranging Market</Label>
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
                        <Label htmlFor="cancel-stale-orders" className="text-base">Cancel Stale Orders</Label>
                        <p className="text-sm text-gray-500">Automatically cancel pending orders that haven't filled</p>
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
                          <Label htmlFor="stale_order_hours">Stale Order Timeout (hours)</Label>
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
                      <div className="text-yellow-400 font-semibold mb-1">Advanced Features</div>
                      <div className="text-sm text-gray-400">
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
              </CardContent>
            </Card>
          </TabsContent>

          {/* Autonomous Configuration Tab */}
          <TabsContent value="autonomous" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <SettingsIcon className="h-5 w-5 text-blue-500" />
                  Autonomous Trading Configuration
                </CardTitle>
                <CardDescription>
                  Configure autonomous strategy generation and management
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={autonomousForm.handleSubmit(onAutonomousConfigSubmit)} className="space-y-6">
                  {/* Enable/Disable */}
                  <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                    <div className="space-y-0.5">
                      <Label htmlFor="autonomous-enabled" className="text-base">Enable Autonomous System</Label>
                      <p className="text-sm text-gray-500">Allow the system to autonomously propose and manage strategies</p>
                    </div>
                    <Switch
                      id="autonomous-enabled"
                      checked={autonomousForm.watch('enabled')}
                      onCheckedChange={(checked) => autonomousForm.setValue('enabled', checked)}
                    />
                  </div>

                  {/* Strategy Generation */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-gray-300">Strategy Generation</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="proposal_count">Proposal Count</Label>
                        <Input
                          id="proposal_count"
                          type="number"
                          min="10"
                          max="500"
                          {...autonomousForm.register('proposal_count', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Number of strategy proposals per cycle (10-500)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="watchlist_size">Watchlist Size</Label>
                        <Input
                          id="watchlist_size"
                          type="number"
                          min="1"
                          max="20"
                          {...autonomousForm.register('watchlist_size', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Number of symbols to watch (1-20)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="dynamic_symbol_additions">Dynamic Symbol Additions</Label>
                        <Input
                          id="dynamic_symbol_additions"
                          type="number"
                          min="0"
                          max="50"
                          {...autonomousForm.register('dynamic_symbol_additions', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Extra symbols added dynamically per strategy during signal generation (0-50)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="signal_generation_interval">Signal Interval (minutes)</Label>
                        <Input
                          id="signal_generation_interval"
                          type="number"
                          min="5"
                          max="60"
                          value={Math.round(autonomousForm.watch('signal_generation_interval') / 60)}
                          onChange={(e) => autonomousForm.setValue('signal_generation_interval', Number(e.target.value) * 60)}
                        />
                        <p className="text-xs text-gray-500">Time between signal generation runs (5-60 min)</p>
                      </div>
                    </div>
                  </div>

                  {/* Strategy Limits */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-gray-300">Strategy Limits</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="max_active_strategies">Max Active Strategies</Label>
                        <Input
                          id="max_active_strategies"
                          type="number"
                          min="5"
                          max="500"
                          {...autonomousForm.register('max_active_strategies', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Maximum strategies to run simultaneously (5-500)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_active_strategies">Min Active Strategies</Label>
                        <Input
                          id="min_active_strategies"
                          type="number"
                          min="3"
                          max="25"
                          {...autonomousForm.register('min_active_strategies', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum strategies to maintain (3-25)</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="backtested_ttl_cycles">Backtested Strategy TTL (signal cycles)</Label>
                        <Input
                          id="backtested_ttl_cycles"
                          type="number"
                          min="6"
                          max="200"
                          {...autonomousForm.register('backtested_ttl_cycles', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Retire BACKTESTED strategies after N signal cycles without a trade (6-200, default 48 ≈ 24h)</p>
                      </div>
                    </div>
                  </div>

                  {/* Activation Thresholds */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-gray-300">Activation Thresholds</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="min_sharpe">Min Sharpe Ratio (Stocks/ETFs)</Label>
                        <Input
                          id="min_sharpe"
                          type="number"
                          step="0.1"
                          min="0"
                          max="3.0"
                          {...autonomousForm.register('min_sharpe', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum Sharpe for stocks, ETFs, forex, indices, commodities (0-3.0)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_sharpe_crypto">Min Sharpe Ratio (Crypto)</Label>
                        <Input
                          id="min_sharpe_crypto"
                          type="number"
                          step="0.1"
                          min="0"
                          max="3.0"
                          {...autonomousForm.register('min_sharpe_crypto', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum Sharpe for crypto strategies (0-3.0)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="max_drawdown">Max Drawdown (%)</Label>
                        <Input
                          id="max_drawdown"
                          type="number"
                          step="1"
                          min="5"
                          max="50"
                          {...autonomousForm.register('max_drawdown', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Maximum acceptable drawdown (5-50%)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_win_rate">Min Win Rate (%)</Label>
                        <Input
                          id="min_win_rate"
                          type="number"
                          step="1"
                          min="30"
                          max="80"
                          {...autonomousForm.register('min_win_rate', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum win rate for stocks/ETFs (30-80%)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_win_rate_crypto">Min Win Rate Crypto (%)</Label>
                        <Input
                          id="min_win_rate_crypto"
                          type="number"
                          step="1"
                          min="20"
                          max="70"
                          {...autonomousForm.register('min_win_rate_crypto', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Minimum win rate for crypto strategies (20-70%)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="min_trades_dsl">Min Trades (DSL)</Label>
                        <Input
                          id="min_trades_dsl"
                          type="number"
                          min="1"
                          max="50"
                          {...autonomousForm.register('min_trades_dsl', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Min trades for technical strategies</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="min_trades_alpha_edge">Min Trades (Alpha Edge)</Label>
                        <Input
                          id="min_trades_alpha_edge"
                          type="number"
                          min="1"
                          max="50"
                          {...autonomousForm.register('min_trades_alpha_edge', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Min trades for fundamental strategies</p>
                      </div>
                    </div>
                  </div>

                  {/* Retirement Thresholds */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-gray-300">Retirement Thresholds</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="retirement_max_sharpe">Max Sharpe (Retire Below)</Label>
                        <Input
                          id="retirement_max_sharpe"
                          type="number"
                          step="0.1"
                          min="0"
                          max="2.0"
                          {...autonomousForm.register('retirement_max_sharpe', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Retire if Sharpe falls below this (0-2.0)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="retirement_max_drawdown">Max Drawdown (Retire Above) (%)</Label>
                        <Input
                          id="retirement_max_drawdown"
                          type="number"
                          step="1"
                          min="5"
                          max="50"
                          {...autonomousForm.register('retirement_max_drawdown', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Retire if drawdown exceeds this (5-50%)</p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="retirement_min_win_rate">Min Win Rate (Retire Below) (%)</Label>
                        <Input
                          id="retirement_min_win_rate"
                          type="number"
                          step="1"
                          min="20"
                          max="60"
                          {...autonomousForm.register('retirement_min_win_rate', { valueAsNumber: true })}
                        />
                        <p className="text-xs text-gray-500">Retire if win rate falls below this (20-60%)</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button type="submit" disabled={autonomousForm.formState.isSubmitting} className="flex-1">
                      <Save className="h-4 w-4 mr-2" />
                      {autonomousForm.formState.isSubmitting ? 'Saving...' : 'Save Configuration'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => autonomousForm.reset()}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alpha Edge Tab */}
          <TabsContent value="alpha-edge" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-blue-500" />
                  Alpha Edge Settings
                </CardTitle>
                <CardDescription>
                  Configure fundamental filters, ML signal filtering, and advanced strategy templates
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={alphaEdgeForm.handleSubmit(onAlphaEdgeSubmit)} className="space-y-8">
                  
                  {/* Fundamental Filters Section */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                      <div className="space-y-0.5">
                        <Label htmlFor="fundamental-filters-enabled" className="text-base">Enable Fundamental Filtering</Label>
                        <p className="text-sm text-gray-500">Filter stocks based on fundamental criteria before trading</p>
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
                          <Label htmlFor="fundamental_min_checks_passed">Minimum Checks Required</Label>
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
                          <Label className="text-sm font-semibold text-gray-300">Individual Checks</Label>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between p-3 bg-dark-bg border border-dark-border rounded">
                              <div>
                                <Label htmlFor="check-profitable" className="text-sm">Profitable (EPS &gt; 0)</Label>
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
                                <Label htmlFor="check-growing" className="text-sm">Growing Revenue</Label>
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
                                <Label htmlFor="check-valuation" className="text-sm">Reasonable Valuation</Label>
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
                                <Label htmlFor="check-dilution" className="text-sm">No Excessive Dilution</Label>
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
                                <Label htmlFor="check-insider" className="text-sm">Insider Buying</Label>
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
                        <Label htmlFor="ml-filter-enabled" className="text-base">Enable ML Signal Filtering</Label>
                        <p className="text-sm text-gray-500">Use machine learning to filter trading signals</p>
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
                          <Label htmlFor="ml_min_confidence">Minimum Confidence (%)</Label>
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
                          <Label htmlFor="ml_retrain_frequency_days">Retrain Frequency (days)</Label>
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
                    <h3 className="text-sm font-semibold text-gray-300">Trading Frequency Controls</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="max_active_strategies">Max Active Strategies</Label>
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
                        <Label htmlFor="min_conviction_score">Min Conviction Score</Label>
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
                        <Label htmlFor="min_holding_period_days">Min Holding Period (days)</Label>
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
                        <Label htmlFor="max_trades_per_strategy_per_month">Max Trades/Strategy/Month</Label>
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
                    <h3 className="text-sm font-semibold text-gray-300">Alpha Edge Strategy Templates</h3>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="earnings-momentum-enabled" className="text-base">Earnings Momentum</Label>
                          <p className="text-sm text-gray-500">Trade small-cap stocks with positive earnings surprises</p>
                        </div>
                        <Switch
                          id="earnings-momentum-enabled"
                          checked={alphaEdgeForm.watch('earnings_momentum_enabled')}
                          onCheckedChange={(checked) => alphaEdgeForm.setValue('earnings_momentum_enabled', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="sector-rotation-enabled" className="text-base">Sector Rotation</Label>
                          <p className="text-sm text-gray-500">Rotate into sectors that outperform in current market regime</p>
                        </div>
                        <Switch
                          id="sector-rotation-enabled"
                          checked={alphaEdgeForm.watch('sector_rotation_enabled')}
                          onCheckedChange={(checked) => alphaEdgeForm.setValue('sector_rotation_enabled', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                        <div className="space-y-0.5">
                          <Label htmlFor="quality-mean-reversion-enabled" className="text-base">Quality Mean Reversion</Label>
                          <p className="text-sm text-gray-500">Buy high-quality stocks when temporarily oversold</p>
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
                      <h3 className="text-sm font-semibold text-gray-300">API Usage Monitoring</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* FMP Usage */}
                        <div className="p-4 bg-dark-bg border border-dark-border rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <Label className="text-sm">Financial Modeling Prep</Label>
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
                            <Label className="text-sm">Alpha Vantage</Label>
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
                        <Label className="text-sm mb-2 block">Cache Statistics</Label>
                        <div className="grid grid-cols-2 gap-4 text-sm">
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
                      <div className="text-blue-400 font-semibold mb-1">Alpha Edge Features</div>
                      <div className="text-sm text-gray-400">
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
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alerts & Notifications Tab */}
          <TabsContent value="notifications" className="space-y-6">
            {/* Alert Thresholds */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-500" />
                  Alert Thresholds
                </CardTitle>
                <CardDescription>
                  Configure when you want to be alerted about portfolio events
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* P&L Loss Alert */}
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-base text-red-400">Daily P&L Loss</Label>
                    <p className="text-sm text-gray-500">Alert when daily P&L drops below threshold</p>
                    {alertConfig.pnl_loss_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-sm text-gray-400">-$</span>
                        <Input
                          type="number"
                          value={alertConfig.pnl_loss_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, pnl_loss_threshold: Number(e.target.value) }))}
                          className="w-32 h-8 text-sm"
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
                    <Label className="text-base text-green-400">Daily P&L Gain</Label>
                    <p className="text-sm text-gray-500">Alert when daily P&L exceeds threshold</p>
                    {alertConfig.pnl_gain_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-sm text-gray-400">+$</span>
                        <Input
                          type="number"
                          value={alertConfig.pnl_gain_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, pnl_gain_threshold: Number(e.target.value) }))}
                          className="w-32 h-8 text-sm"
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
                    <Label className="text-base text-amber-400">Drawdown</Label>
                    <p className="text-sm text-gray-500">Alert when drawdown exceeds threshold</p>
                    {alertConfig.drawdown_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.drawdown_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, drawdown_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-sm"
                          min={0}
                          max={100}
                        />
                        <span className="text-sm text-gray-400">%</span>
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
                    <Label className="text-base text-orange-400">Position Loss</Label>
                    <p className="text-sm text-gray-500">Alert when any position loses more than threshold</p>
                    {alertConfig.position_loss_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.position_loss_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, position_loss_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-sm"
                          min={0}
                          max={100}
                        />
                        <span className="text-sm text-gray-400">%</span>
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
                    <Label className="text-base text-purple-400">Margin Utilization</Label>
                    <p className="text-sm text-gray-500">Alert when margin utilization exceeds threshold</p>
                    {alertConfig.margin_enabled && (
                      <div className="flex items-center gap-2 mt-2">
                        <Input
                          type="number"
                          value={alertConfig.margin_threshold}
                          onChange={(e) => setAlertConfig(prev => ({ ...prev, margin_threshold: Number(e.target.value) }))}
                          className="w-24 h-8 text-sm"
                          min={0}
                          max={100}
                        />
                        <span className="text-sm text-gray-400">%</span>
                      </div>
                    )}
                  </div>
                  <Switch
                    checked={alertConfig.margin_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, margin_enabled: checked }))}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Event Alerts */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="h-5 w-5 text-blue-500" />
                  Event Alerts
                </CardTitle>
                <CardDescription>
                  Alerts for system events (always-on events cannot be disabled)
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-base">Autonomous Cycle Complete</Label>
                    <p className="text-sm text-gray-500">Alert when an autonomous cycle finishes</p>
                  </div>
                  <Switch
                    checked={alertConfig.cycle_complete_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, cycle_complete_enabled: checked }))}
                  />
                </div>
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-base">Strategy Retired</Label>
                    <p className="text-sm text-gray-500">Alert when a strategy is retired</p>
                  </div>
                  <Switch
                    checked={alertConfig.strategy_retired_enabled}
                    onCheckedChange={(checked) => setAlertConfig(prev => ({ ...prev, strategy_retired_enabled: checked }))}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Delivery Settings */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5 text-cyan-500" />
                  Delivery Settings
                </CardTitle>
                <CardDescription>
                  How alerts are delivered to you
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-base">In-App Notifications</Label>
                    <p className="text-sm text-gray-500">Toast + persistent alert in notification panel (always on)</p>
                  </div>
                  <span className="text-xs text-green-400 bg-green-500/10 px-2 py-1 rounded">Always On</span>
                </div>
                <div className="flex items-center justify-between p-4 bg-dark-bg border border-dark-border rounded-lg">
                  <div className="space-y-0.5">
                    <Label className="text-base">Browser Push Notifications</Label>
                    <p className="text-sm text-gray-500">Get notified even when the tab is not focused (critical alerts only)</p>
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
              </CardContent>
            </Card>
          </TabsContent>

          {/* Users & Security Tab */}
          <TabsContent value="users" className="space-y-6">
            {/* Change Password — available to all users */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lock className="h-5 w-5 text-blue-500" />
                  Change Password
                </CardTitle>
                <CardDescription>Update your account password</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 max-w-md">
                <div className="space-y-2">
                  <Label htmlFor="old-password">Current Password</Label>
                  <Input
                    id="old-password"
                    type="password"
                    value={changePasswordOld}
                    onChange={(e) => setChangePasswordOld(e.target.value)}
                    placeholder="Enter current password"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-password">New Password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={changePasswordNew}
                    onChange={(e) => setChangePasswordNew(e.target.value)}
                    placeholder="Min 6 characters"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm New Password</Label>
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
              </CardContent>
            </Card>

            {/* User Management — admin only */}
            {isAdmin && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Users className="h-5 w-5 text-blue-500" />
                        User Management
                      </CardTitle>
                      <CardDescription>Create, edit, and manage user accounts and roles</CardDescription>
                    </div>
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
                  </div>
                </CardHeader>
                <CardContent>
                  {/* Role legend */}
                  <div className="flex gap-4 mb-4 text-xs text-gray-400">
                    <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />Admin — full access, user management</span>
                    <span><span className="inline-block w-2 h-2 rounded-full bg-yellow-500 mr-1" />Trader — trade, manage strategies</span>
                    <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />Viewer — read-only dashboard access</span>
                  </div>

                  {/* Create user form */}
                  {showCreateUser && (
                    <div className="mb-4 p-4 border border-gray-700 rounded-lg bg-dark-surface space-y-3">
                      <h4 className="text-sm font-medium text-gray-200">Create New User</h4>
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
                            className="w-full h-10 rounded-md border border-gray-700 bg-dark-bg px-3 text-sm text-gray-200"
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
                      <p>Click Refresh to load users</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-gray-400">
                            <th className="text-left py-2 px-3">Username</th>
                            <th className="text-left py-2 px-3">Role</th>
                            <th className="text-left py-2 px-3">Status</th>
                            <th className="text-left py-2 px-3">Created</th>
                            <th className="text-left py-2 px-3">Last Login</th>
                            <th className="text-right py-2 px-3">Actions</th>
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
                </CardContent>
              </Card>
            )}

            {!isAdmin && (
              <Card>
                <CardContent className="py-8 text-center text-gray-500">
                  <Shield className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p>User management is only available to administrators.</p>
                  <p className="text-xs mt-1">Your role: <span className="text-gray-300">{authService.getRole()}</span></p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Keyboard Shortcuts Tab */}
          <TabsContent value="shortcuts" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Keyboard className="h-5 w-5 text-blue-500" />
                  Keyboard Shortcuts
                </CardTitle>
                <CardDescription>
                  Use keyboard shortcuts to navigate faster. Shortcuts are disabled while typing in input fields.
                  Press <kbd className="px-1.5 py-0.5 rounded text-xs font-mono bg-gray-800 border border-gray-700 mx-1">?</kbd> anywhere to toggle this reference.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  {(['navigation', 'actions', 'general'] as const).map((category) => {
                    const items = KEYBOARD_SHORTCUTS.filter((s) => s.category === category);
                    if (items.length === 0) return null;
                    const categoryLabels = { navigation: 'Navigation', actions: 'Actions', general: 'General' };
                    return (
                      <div key={category}>
                        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
                          {categoryLabels[category]}
                        </h3>
                        <div className="space-y-2">
                          {items.map((shortcut) => (
                            <div
                              key={shortcut.key}
                              className="flex items-center justify-between py-2 px-3 rounded-lg bg-dark-bg/50"
                            >
                              <span className="text-sm text-gray-300">{shortcut.description}</span>
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
              </CardContent>
            </Card>
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
