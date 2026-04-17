import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  ApiResponse,
  AccountInfo,
  Position,
  Order,
  Strategy,
  PerformanceMetrics,
  MarketData,
  SystemStatus,
  SessionSummary,
  DependentService,
  ConfigData,
  RiskParams,
  TradingMode,
  OrderType,
  OrderSide,
  AutonomousStatus,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * API Client for backend communication
 * Handles REST API calls with authentication token management
 */
class ApiClient {
  private client: AxiosInstance;
  private maxRetries: number = 3;
  private retryDelay: number = 1000; // 1 second

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      withCredentials: true,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 60000, // 60 second timeout (SQLite can be slow under write contention)
    });

    // Add request interceptor - no need to add auth token since we use session cookies
    this.client.interceptors.request.use(
      (config) => {
        // Session authentication is handled via cookies (withCredentials: true)
        // No need to add Authorization header
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ApiResponse<any>>) => {
        if (error.response?.status === 401) {
          // Unauthorized - clear username and redirect to login
          localStorage.removeItem('username');
          // Only redirect if not already on login page
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
  }

  /**
   * Retry wrapper for API calls with exponential backoff
   */
  private async withRetry<T>(
    fn: () => Promise<T>,
    retries: number = this.maxRetries
  ): Promise<T> {
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (error: any) {
        // Don't retry on client errors (4xx) except 429 (rate limit)
        if (error.response?.status && error.response.status >= 400 && error.response.status < 500) {
          if (error.response.status !== 429) {
            throw error;
          }
        }
        
        // Don't retry on last attempt
        if (i === retries - 1) {
          throw error;
        }
        
        // Exponential backoff
        const delay = this.retryDelay * Math.pow(2, i);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    throw new Error('Max retries exceeded');
  }

  private handleResponse<T>(response: { data: ApiResponse<T> | T }): T {
    // Check if response is wrapped in ApiResponse format
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      const apiResponse = response.data as ApiResponse<T>;
      if (apiResponse.error) {
        throw new Error(apiResponse.error);
      }
      if (!apiResponse.data) {
        throw new Error('Invalid response from server');
      }
      return apiResponse.data;
    }
    
    // Response is direct data (not wrapped)
    return response.data as T;
  }

  private extractArrayFromResponse<T>(response: { data: any }, key: string): T[] {
    const data = this.handleResponse<any>(response);
    
    // If data has the key (e.g., 'orders', 'positions'), extract it
    if (data && typeof data === 'object' && key in data) {
      const value = data[key];
      // Ensure it's an array
      if (Array.isArray(value)) {
        return value as T[];
      }
      // If it's an object with numeric keys, convert to array
      if (typeof value === 'object' && value !== null) {
        return Object.values(value) as T[];
      }
    }
    
    // If data is already an array, return it
    if (Array.isArray(data)) {
      return data as T[];
    }
    
    // If data is an object with numeric keys, convert to array
    if (typeof data === 'object' && data !== null) {
      const keys = Object.keys(data);
      if (keys.length > 0 && keys.every(k => !isNaN(Number(k)))) {
        return Object.values(data) as T[];
      }
    }
    
    // Fallback: return empty array
    console.warn(`Could not extract array from response for key: ${key}`, data);
    return [];
  }

  // ============================================================================
  // Account Endpoints
  // ============================================================================

  async getAccountInfo(mode: TradingMode): Promise<AccountInfo> {
    return this.withRetry(async () => {
      const response = await this.client.get<ApiResponse<AccountInfo>>(
        `/account?mode=${mode}`
      );
      return this.handleResponse(response);
    });
  }

  async getPositions(mode: TradingMode): Promise<Position[]> {
    return this.withRetry(async () => {
      const response = await this.client.get<ApiResponse<Position[]>>(
        `/account/positions?mode=${mode}`
      );
      return this.extractArrayFromResponse<Position>(response, 'positions');
    });
  }

  async getClosedPositions(mode: TradingMode, limit: number = 100): Promise<Position[]> {
    return this.withRetry(async () => {
      const response = await this.client.get<ApiResponse<Position[]>>(
        `/account/positions/closed?mode=${mode}&limit=${limit}`
      );
      return this.extractArrayFromResponse<Position>(response, 'positions');
    });
  }

  async getPosition(positionId: string, mode: TradingMode): Promise<Position> {
    const response = await this.client.get<ApiResponse<Position>>(
      `/account/positions/${positionId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async closePosition(positionId: string, mode: TradingMode): Promise<{ success: boolean; message: string; order?: Order }> {
    const response = await this.client.delete<ApiResponse<{ success: boolean; message: string; order?: Order }>>(
      `/account/positions/${positionId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async modifyStopLoss(positionId: string, stopPrice: number, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      `/account/positions/${positionId}/stop-loss?mode=${mode}`,
      { stop_price: stopPrice }
    );
    return this.handleResponse(response);
  }

  async modifyTakeProfit(positionId: string, targetPrice: number, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      `/account/positions/${positionId}/take-profit?mode=${mode}`,
      { target_price: targetPrice }
    );
    return this.handleResponse(response);
  }

  async getPendingClosures(mode: TradingMode): Promise<Position[]> {
    const response = await this.client.get<ApiResponse<Position[]>>(
      `/account/positions/pending-closures?mode=${mode}`
    );
    return this.extractArrayFromResponse<Position>(response, 'positions');
  }

  async approvePositionClosure(positionId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/account/positions/${positionId}/approve-closure?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async approveBulkClosures(positionIds: string[], mode: TradingMode): Promise<{ success: boolean; message: string; success_count: number; fail_count: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; success_count: number; fail_count: number }>>(
      `/account/positions/approve-closures-bulk?mode=${mode}`,
      { position_ids: positionIds }
    );
    return this.handleResponse(response);
  }

  async dismissPositionClosure(positionId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/account/positions/${positionId}/dismiss-closure?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async syncPositions(mode: TradingMode): Promise<{ success: boolean; message: string; synced_count: number; new_count: number; closed_count: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; synced_count: number; new_count: number; closed_count: number }>>(
      `/account/positions/sync?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async closePositions(positionIds: string[], mode: TradingMode): Promise<{ success: boolean; message: string; success_count: number; fail_count: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; success_count: number; fail_count: number }>>(
      `/account/positions/close?mode=${mode}`,
      { position_ids: positionIds }
    );
    return this.handleResponse(response);
  }

  async closeAllPositions(mode: TradingMode): Promise<{ success: boolean; message: string; success_count: number; fail_count: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; success_count: number; fail_count: number }>>(
      `/account/positions/close-all?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Fundamental Alerts Endpoints (Task 11.10.3)
  // ============================================================================

  async getFundamentalAlerts(mode: TradingMode): Promise<{ alerts: any[]; count: number }> {
    const response = await this.client.get<ApiResponse<{ alerts: any[]; count: number }>>(
      `/account/positions/fundamental-alerts?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async dismissFundamentalAlert(positionId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/account/positions/${positionId}/dismiss-alert?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async triggerFundamentalCheck(mode: TradingMode): Promise<{ success: boolean; message: string; checked: number; flagged: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; checked: number; flagged: number }>>(
      `/account/fundamental-check/trigger?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Order Endpoints
  // ============================================================================

  async getOrders(mode: TradingMode, limit: number = 200): Promise<Order[]> {
    const response = await this.client.get<ApiResponse<Order[]>>(
      `/orders?mode=${mode}&limit=${limit}`
    );
    return this.extractArrayFromResponse<Order>(response, 'orders');
  }

  async getOrder(orderId: string, mode: TradingMode): Promise<Order> {
    const response = await this.client.get<ApiResponse<Order>>(
      `/orders/${orderId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async placeOrder(params: {
    strategy_id?: string;
    symbol: string;
    side: OrderSide;
    order_type: OrderType;
    quantity: number;
    price?: number;
    stop_price?: number;
    mode: TradingMode;
  }): Promise<Order> {
    const response = await this.client.post<ApiResponse<Order>>(
      `/orders?mode=${params.mode}`,
      {
        strategy_id: params.strategy_id || 'manual_order',
        symbol: params.symbol,
        side: params.side,
        order_type: params.order_type,
        quantity: params.quantity,
        price: params.price,
        stop_price: params.stop_price
      }
    );
    return this.handleResponse(response);
  }

  async cancelOrder(orderId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.delete<ApiResponse<{ success: boolean; message: string }>>(
      `/orders/${orderId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async deleteOrderPermanent(orderId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.delete<ApiResponse<{ success: boolean; message: string }>>(
      `/orders/${orderId}/permanent?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async closeFilledOrderPosition(orderId: string, mode: TradingMode): Promise<{ success: boolean; message: string; position_closed: boolean }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; position_closed: boolean }>>(
      `/orders/${orderId}/close-position?mode=${mode}`
    );
    return this.handleResponse(response);
  }


  async bulkDeleteOrders(orderIds: string[], mode: TradingMode): Promise<{ success_count: number; fail_count: number; deleted_order_ids: string[]; failed_order_ids: string[] }> {
    const response = await this.client.post<ApiResponse<{ success_count: number; fail_count: number; deleted_order_ids: string[]; failed_order_ids: string[] }>>(
      `/orders/bulk-delete?mode=${mode}`,
      { order_ids: orderIds }
    );
    return this.handleResponse(response);
  }

  async syncOrders(mode: TradingMode): Promise<{ success: boolean; message: string; checked: number; filled: number; cancelled: number; failed: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; checked: number; filled: number; cancelled: number; failed: number }>>(
      `/orders/sync?mode=${mode}`
    );
    return this.handleResponse(response);
  }


  // ============================================================================
  // Signal Activity Endpoints
  // ============================================================================

  async getRecentSignals(mode: TradingMode, limit: number = 100): Promise<{
    signals: Array<{
      id: number;
      signal_id: string;
      strategy_id: string;
      symbol: string;
      side: string;
      signal_type: string;
      decision: string;
      rejection_reason: string | null;
      created_at: string;
      metadata: Record<string, any> | null;
    }>;
    summary: {
      total: number;
      accepted: number;
      rejected: number;
      acceptance_rate: number;
      rejection_reasons: Array<{ reason: string; count: number; percentage: number }>;
    };
  }> {
    const response = await this.client.get<ApiResponse<any>>(
      `/signals/recent?mode=${mode}&limit=${limit}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Strategy Endpoints
  // ============================================================================

  async getStrategies(mode: TradingMode, includeRetired: boolean = false): Promise<Strategy[]> {
    const response = await this.client.get<ApiResponse<Strategy[]>>(
      `/strategies?mode=${mode}&include_retired=${includeRetired}`
    );
    return this.extractArrayFromResponse<Strategy>(response, 'strategies');
  }

  async getStrategy(strategyId: string, mode: TradingMode): Promise<Strategy> {
    const response = await this.client.get<ApiResponse<Strategy>>(
      `/strategies/${strategyId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async createStrategy(params: {
    name: string;
    description: string;
    prompt: string;
    mode: TradingMode;
  }): Promise<Strategy> {
    const response = await this.client.post<ApiResponse<Strategy>>('/strategies', params);
    return this.handleResponse(response);
  }

  async updateStrategy(
    strategyId: string,
    params: {
      name?: string;
      description?: string;
      rules?: string;
      symbols?: string[];
      allocation_percent?: number;
      mode: TradingMode;
    }
  ): Promise<Strategy> {
    const response = await this.client.put<ApiResponse<Strategy>>(
      `/strategies/${strategyId}`,
      params
    );
    return this.handleResponse(response);
  }

  async retireStrategy(strategyId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.delete<ApiResponse<{ success: boolean; message: string }>>(
      `/strategies/${strategyId}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async permanentlyDeleteStrategy(strategyId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.delete<ApiResponse<{ success: boolean; message: string }>>(
      `/strategies/${strategyId}/permanent?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async activateStrategy(strategyId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/strategies/${strategyId}/activate?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async deactivateStrategy(strategyId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/strategies/${strategyId}/deactivate?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getStrategyPerformance(strategyId: string, mode: TradingMode): Promise<PerformanceMetrics> {
    const response = await this.client.get<ApiResponse<PerformanceMetrics>>(
      `/strategies/${strategyId}/performance?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async generateStrategy(params: {
    prompt: string;
    constraints?: {
      symbols?: string[];
      timeframe?: string;
      risk_tolerance?: string;
    };
  }): Promise<Strategy> {
    const response = await this.client.post<ApiResponse<Strategy>>(
      '/strategies/generate',
      {
        prompt: params.prompt,
        constraints: params.constraints || {}
      }
    );
    return this.handleResponse(response);
  }

  async backtestStrategy(
    strategyId: string,
    params?: {
      start_date?: string;
      end_date?: string;
    }
  ): Promise<{
    strategy_id: string;
    total_return: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    total_trades: number;
    backtest_period: {
      start: string;
      end: string;
    };
    message: string;
  }> {
    const response = await this.client.post<ApiResponse<any>>(
      `/strategies/${strategyId}/backtest`,
      params || {}
    );
    return this.handleResponse(response);
  }

  async bootstrapStrategies(params?: {
    strategy_types?: string[];
    auto_activate?: boolean;
    min_sharpe?: number;
  }): Promise<{
    strategies: Strategy[];
    summary: {
      total_generated: number;
      total_activated: number;
      avg_sharpe: number;
    };
  }> {
    const response = await this.client.post<ApiResponse<any>>(
      '/strategies/bootstrap',
      params || {}
    );
    return this.handleResponse(response);
  }

  async updateAllocation(
    strategyId: string,
    allocationPercent: number
  ): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      `/strategies/${strategyId}/allocation`,
      { allocation_percent: allocationPercent }
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Market Data Endpoints
  // ============================================================================

  async getQuote(symbol: string, mode: TradingMode = 'DEMO'): Promise<MarketData> {
    const response = await this.client.get<ApiResponse<MarketData>>(
      `/market-data/${symbol}?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getHistoricalData(params: {
    symbol: string;
    start_date: string;
    end_date: string;
    interval?: string;
    mode?: TradingMode;
  }): Promise<any[]> {
    const mode = params.mode || 'DEMO';
    const response = await this.client.get<ApiResponse<any[]>>(
      `/market-data/${params.symbol}/historical?mode=${mode}`,
      { 
        params: {
          start: params.start_date,
          end: params.end_date,
          interval: params.interval
        }
      }
    );
    return this.extractArrayFromResponse<any>(response, 'data');
  }

  // ============================================================================
  // System Control Endpoints
  // ============================================================================

  async getSystemStatus(): Promise<SystemStatus> {
    const response = await this.client.get<ApiResponse<SystemStatus>>(
      '/control/system/status'
    );
    return this.handleResponse(response);
  }

  async getSessionHistory(limit: number = 5): Promise<SessionSummary[]> {
    const response = await this.client.get<ApiResponse<SessionSummary[]>>(
      `/control/system/sessions?limit=${limit}`
    );
    return this.extractArrayFromResponse<SessionSummary>(response, 'sessions');
  }

  async startAutonomousTrading(confirmation: boolean): Promise<{ state: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ state: string; message: string }>>(
      '/control/system/start',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  async pauseAutonomousTrading(confirmation: boolean): Promise<{ state: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ state: string; message: string }>>(
      '/control/system/pause',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  async stopAutonomousTrading(confirmation: boolean): Promise<{ state: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ state: string; message: string }>>(
      '/control/system/stop',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  async resumeAutonomousTrading(confirmation: boolean): Promise<{ state: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ state: string; message: string }>>(
      '/control/system/resume',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  async resetFromEmergencyHalt(confirmation: boolean, acknowledgeRisks: boolean): Promise<{ state: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ state: string; message: string }>>(
      '/control/system/reset',
      { confirmation, acknowledge_risks: acknowledgeRisks }
    );
    return this.handleResponse(response);
  }

  async activateKillSwitch(confirmation: boolean, reason: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      '/control/kill-switch',
      { confirmation, reason }
    );
    return this.handleResponse(response);
  }

  async resetCircuitBreaker(confirmation: boolean): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      '/control/circuit-breaker/reset',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  async manualRebalance(confirmation: boolean): Promise<{ success: boolean; message: string; orders: Order[] }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; orders: Order[] }>>(
      '/control/rebalance',
      { confirmation }
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Service Management Endpoints
  // ============================================================================

  async getServicesStatus(): Promise<Record<string, DependentService>> {
    const response = await this.client.get<ApiResponse<Record<string, DependentService>>>(
      '/control/services'
    );
    return this.handleResponse(response);
  }

  async getServiceHealth(serviceName: string): Promise<DependentService> {
    const response = await this.client.get<ApiResponse<DependentService>>(
      `/control/services/${serviceName}/health`
    );
    return this.handleResponse(response);
  }

  async startService(serviceName: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/control/services/${serviceName}/start`
    );
    return this.handleResponse(response);
  }

  async stopService(serviceName: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      `/control/services/${serviceName}/stop`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Configuration Endpoints
  // ============================================================================

  async setCredentials(params: {
    public_key: string;
    user_key: string;
    mode: TradingMode;
  }): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>(
      '/config/credentials',
      params
    );
    return this.handleResponse(response);
  }

  async getConnectionStatus(mode: TradingMode): Promise<{ connected: boolean; message: string }> {
    const response = await this.client.get<ApiResponse<{ connected: boolean; message: string }>>(
      `/config/connection-status?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getRiskConfig(mode: TradingMode): Promise<RiskParams> {
    const response = await this.client.get<ApiResponse<RiskParams>>(
      `/config/risk?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async updateRiskConfig(params: RiskParams & { mode: TradingMode }): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      '/config/risk',
      params
    );
    return this.handleResponse(response);
  }

  async getAppConfig(): Promise<ConfigData> {
    const response = await this.client.get<ApiResponse<ConfigData>>('/config');
    return this.handleResponse(response);
  }

  async updateAppConfig(params: Partial<ConfigData>): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      '/config',
      params
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Alpha Edge Settings Endpoints
  // ============================================================================

  async getAlphaEdgeSettings(): Promise<{
    fundamental_filters_enabled: boolean;
    fundamental_min_checks_passed: number;
    fundamental_checks: Record<string, boolean>;
    ml_filter_enabled: boolean;
    ml_min_confidence: number;
    ml_retrain_frequency_days: number;
    max_active_strategies: number;
    min_conviction_score: number;
    min_holding_period_days: number;
    max_trades_per_strategy_per_month: number;
    earnings_momentum_enabled: boolean;
    sector_rotation_enabled: boolean;
    quality_mean_reversion_enabled: boolean;
  }> {
    const response = await this.client.get<ApiResponse<any>>('/config/alpha-edge');
    return this.handleResponse(response);
  }

  async updateAlphaEdgeSettings(params: {
    fundamental_filters_enabled?: boolean;
    fundamental_min_checks_passed?: number;
    fundamental_checks?: Record<string, boolean>;
    ml_filter_enabled?: boolean;
    ml_min_confidence?: number;
    ml_retrain_frequency_days?: number;
    max_active_strategies?: number;
    min_conviction_score?: number;
    min_holding_period_days?: number;
    max_trades_per_strategy_per_month?: number;
    earnings_momentum_enabled?: boolean;
    sector_rotation_enabled?: boolean;
    quality_mean_reversion_enabled?: boolean;
  }): Promise<{ success: boolean; message: string }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string }>>(
      '/config/alpha-edge',
      params
    );
    return this.handleResponse(response);
  }

  async getAlphaEdgeApiUsage(): Promise<{
    fmp_usage: {
      calls_today: number;
      limit: number;
      percentage: number;
      remaining: number;
    };
    alpha_vantage_usage: {
      calls_today: number;
      limit: number;
      percentage: number;
      remaining: number;
    };
    cache_stats: {
      size: number;
      hit_rate: number;
    };
  }> {
    const response = await this.client.get<ApiResponse<any>>('/config/alpha-edge/api-usage');
    return this.handleResponse(response);
  }

  // ============================================================================
  // Autonomous Trading Endpoints
  // ============================================================================

  async getAutonomousStatus(): Promise<AutonomousStatus> {
    const response = await this.client.get<ApiResponse<AutonomousStatus>>(
      '/strategies/autonomous/status'
    );
    return this.handleResponse(response);
  }

  async triggerAutonomousCycle(force: boolean = false, filters?: { asset_classes?: string[]; intervals?: string[]; strategy_types?: string[] }): Promise<{ success: boolean; message: string; cycle_id?: string; estimated_duration?: number }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string; cycle_id?: string; estimated_duration?: number }>>(
      '/strategies/autonomous/trigger',
      { force, ...filters }
    );
    return this.handleResponse(response);
  }

  async getAutonomousConfig(): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>('/config/autonomous');
    return this.handleResponse(response);
  }

  async updateAutonomousConfig(config: any): Promise<any> {
    const response = await this.client.put<ApiResponse<any>>('/config/autonomous', config);
    return this.handleResponse(response);
  }

  // Schedule endpoints
  async getAutonomousSchedule(): Promise<{
    success: boolean;
    schedule: { enabled: boolean; frequency: string; day_of_week: string; hour: number; minute: number };
    next_run: string | null;
    last_run: string | null;
    message: string;
  }> {
    const response = await this.client.get<ApiResponse<any>>('/control/autonomous/schedule');
    return this.handleResponse(response);
  }

  async updateAutonomousSchedule(schedule: {
    enabled: boolean;
    frequency: string;
    day_of_week: string;
    hour: number;
    minute: number;
  }): Promise<{
    success: boolean;
    schedule: { enabled: boolean; frequency: string; day_of_week: string; hour: number; minute: number };
    next_run: string | null;
    message: string;
  }> {
    const response = await this.client.post<ApiResponse<any>>('/control/autonomous/schedule', schedule);
    return this.handleResponse(response);
  }

  async getAutonomousCycles(limit: number = 20): Promise<{ success: boolean; data: any[] }> {
    const response = await this.client.get<ApiResponse<any>>(`/control/autonomous/cycles?limit=${limit}`);
    return this.handleResponse(response);
  }

  async deleteAutonomousCycles(cycleIds: string[]): Promise<{ success: boolean; deleted: number }> {
    const response = await this.client.post<ApiResponse<any>>(
      '/control/autonomous/cycles/delete',
      { cycle_ids: cycleIds }
    );
    return this.handleResponse(response);
  }

  async clearBlacklists(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<any>>('/control/autonomous/clear-blacklists');
    return this.handleResponse(response);
  }

  async deleteClosedPositions(positionIds: string[], mode: TradingMode): Promise<{ success: boolean; deleted: number }> {
    const response = await this.client.post<ApiResponse<any>>(
      `/account/positions/delete-closed?mode=${mode}`,
      { position_ids: positionIds }
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Dashboard Summary Endpoint
  // ============================================================================

  async getDashboardSummary(mode: TradingMode): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/account/dashboard/summary?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Performance Dashboard Endpoints
  // ============================================================================

  async getPerformanceMetrics(period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `?period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/performance/metrics${params}`
    );
    return this.handleResponse(response);
  }

  async getPortfolioComposition(): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      '/performance/portfolio'
    );
    return this.handleResponse(response);
  }

  async getHistoryAnalytics(period?: '1D' | '1W' | '1M' | '3M'): Promise<any> {
    const params = period ? `?period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/performance/history${params}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Risk Management Endpoints
  // ============================================================================

  async getRiskMetrics(mode: TradingMode): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/risk/metrics?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getRiskHistory(mode: TradingMode, period?: '1D' | '1W' | '1M' | '3M'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/risk/history?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getRiskLimits(mode: TradingMode): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/risk/limits?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async updateRiskLimits(mode: TradingMode, limits: any): Promise<{ success: boolean; message: string; limits: any }> {
    const response = await this.client.put<ApiResponse<{ success: boolean; message: string; limits: any }>>(
      `/risk/limits?mode=${mode}`,
      limits
    );
    return this.handleResponse(response);
  }

  async getRiskAlerts(mode: TradingMode): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/risk/alerts?mode=${mode}`
    );
    return this.extractArrayFromResponse<any>(response, 'alerts');
  }

  async getPositionRisks(mode: TradingMode): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/risk/positions?mode=${mode}`
    );
    return this.extractArrayFromResponse<any>(response, 'positions');
  }

  async getCorrelationMatrix(mode: TradingMode, period?: '1D' | '1W' | '1M' | '3M'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/correlation-matrix?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getAdvancedRisk(mode: TradingMode): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/risk/advanced?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Analytics Endpoints
  // ============================================================================

  async getStrategyAttribution(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any[]> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any[]>>(
      `/analytics/strategy-attribution?mode=${mode}${params}`
    );
    return this.extractArrayFromResponse<any>(response, 'attributions');
  }

  async getTradeAnalytics(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/trade-analytics?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getRegimeAnalysis(mode: TradingMode): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/analytics/regime-analysis?mode=${mode}`
    );
    return this.extractArrayFromResponse<any>(response, 'regimes');
  }

  async getComprehensiveRegimeAnalysis(): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/regime-comprehensive`
    );
    return this.handleResponse(response);
  }

  async getPerformanceAnalytics(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/performance?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Alpha Edge Analytics Endpoints
  // ============================================================================

  async getFundamentalFilterStats(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/alpha-edge/fundamental-stats?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getMLFilterStats(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/alpha-edge/ml-stats?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getConvictionDistribution(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/alpha-edge/conviction-distribution?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getTemplatePerformance(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any[]> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any[]>>(
      `/analytics/alpha-edge/template-performance?mode=${mode}${params}`
    );
    return this.extractArrayFromResponse<any>(response, 'templates');
  }

  // Template Manager
  async getStrategyTemplates(regime?: string): Promise<any> {
    const params = regime ? `?market_regime=${regime}` : '';
    const response = await this.client.get(`/strategies/templates${params}`);
    return response.data;
  }

  async toggleTemplate(templateName: string, enabled: boolean): Promise<any> {
    const response = await this.client.put(
      `/strategies/templates/${encodeURIComponent(templateName)}/toggle`,
      { enabled }
    );
    return response.data;
  }

  async bulkToggleTemplates(templates: Record<string, boolean>): Promise<any> {
    const response = await this.client.put(
      `/strategies/templates/bulk-toggle`,
      { templates }
    );
    return response.data;
  }

  // Symbol Stats
  async getSymbolStats(): Promise<any> {
    const response = await this.client.get('/strategies/symbols');
    return response.data;
  }

  async getTransactionCostSavings(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/alpha-edge/transaction-cost-savings?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getPerformanceStats(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/performance-stats?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // CIO Dashboard Endpoints (Institutional-Grade)
  // ============================================================================

  async getCIODashboard(mode: TradingMode, period?: '1M' | '3M' | '6M' | '1Y' | 'ALL'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/cio-dashboard?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  async getCIORisk(mode: TradingMode): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/risk/cio-risk?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Trade Journal Endpoints
  // ============================================================================

  async getTradeJournal(filters?: {
    strategy_id?: string;
    symbol?: string;
    start_date?: string;
    end_date?: string;
    closed_only?: boolean;
  }): Promise<any> {
    const params = new URLSearchParams();
    if (filters?.strategy_id) params.append('strategy_id', filters.strategy_id);
    if (filters?.symbol) params.append('symbol', filters.symbol);
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    if (filters?.closed_only !== undefined) params.append('closed_only', String(filters.closed_only));
    
    const queryString = params.toString();
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/trade-journal${queryString ? `?${queryString}` : ''}`
    );
    return this.handleResponse(response);
  }

  async getTradeJournalAnalytics(filters?: {
    strategy_id?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<any> {
    const params = new URLSearchParams();
    if (filters?.strategy_id) params.append('strategy_id', filters.strategy_id);
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    
    const queryString = params.toString();
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/trade-journal/analytics${queryString ? `?${queryString}` : ''}`
    );
    return this.handleResponse(response);
  }

  async getTradeJournalPatterns(filters?: {
    start_date?: string;
    end_date?: string;
  }): Promise<any> {
    const params = new URLSearchParams();
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    
    const queryString = params.toString();
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/trade-journal/patterns${queryString ? `?${queryString}` : ''}`
    );
    return this.handleResponse(response);
  }

  async exportTradeJournal(filters?: {
    start_date?: string;
    end_date?: string;
  }): Promise<Blob> {
    const params = new URLSearchParams();
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    
    const queryString = params.toString();
    const response = await this.client.get(
      `/analytics/trade-journal/export${queryString ? `?${queryString}` : ''}`,
      { responseType: 'blob' }
    );
    return response.data;
  }

  // ============================================================================
  // Order Execution Quality Endpoints
  // ============================================================================

  async getExecutionQuality(mode: TradingMode, period?: '1D' | '1W' | '1M' | '3M'): Promise<any> {
    const params = period ? `&period=${period}` : '';
    const response = await this.client.get<ApiResponse<any>>(
      `/orders/execution-quality?mode=${mode}${params}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Alert Configuration & History Endpoints (Task 11.10.16)
  // ============================================================================

  async getAlertConfig(): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>('/alerts/config');
    return this.handleResponse(response);
  }

  async updateAlertConfig(config: any): Promise<any> {
    const response = await this.client.put<ApiResponse<any>>('/alerts/config', config);
    return this.handleResponse(response);
  }

  async getAlertHistory(limit = 50, unreadOnly = false, severity?: string): Promise<any> {
    const params = new URLSearchParams({ limit: String(limit), unread_only: String(unreadOnly) });
    if (severity) params.set('severity', severity);
    const response = await this.client.get<ApiResponse<any>>(`/alerts/history?${params}`);
    return this.handleResponse(response);
  }

  async markAlertRead(alertId: number): Promise<any> {
    const response = await this.client.post<ApiResponse<any>>(`/alerts/history/${alertId}/read`);
    return this.handleResponse(response);
  }

  async markAllAlertsRead(): Promise<any> {
    const response = await this.client.post<ApiResponse<any>>('/alerts/history/read-all');
    return this.handleResponse(response);
  }

  async acknowledgeAlert(alertId: number): Promise<any> {
    const response = await this.client.post<ApiResponse<any>>(`/alerts/history/${alertId}/acknowledge`);
    return this.handleResponse(response);
  }

  async clearAlertHistory(): Promise<any> {
    const response = await this.client.delete<ApiResponse<any>>('/alerts/history');
    return this.handleResponse(response);
  }

  // Data Management
  async getDataSyncStatus(): Promise<{
    last_sync_at: string | null;
    last_sync_success: boolean;
    last_sync_duration_s: number | null;
    last_sync_stats: Record<string, unknown> | null;
    sync_running: boolean;
    sync_interval_s: number;
    db_stats: Record<string, unknown> | null;
  }> {
    const response = await this.client.get<ApiResponse<any>>('/data/sync/status');
    return this.handleResponse(response);
  }

  async triggerDataSync(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>('/data/sync/trigger');
    return this.handleResponse(response);
  }

  async triggerQuickUpdate(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>('/data/quick-update/trigger');
    return this.handleResponse(response);
  }

  async getFmpCacheStatus(): Promise<{
    running: boolean;
    current: number;
    total: number;
    fetched: number;
    cached: number;
    failed: number;
    started_at: number | null;
    completed_at: number | null;
    elapsed_s: number | null;
    total_symbols: number;
    fresh_count: number;
    coverage_pct: number;
    last_warm_at: string | null;
    error: string | null;
  }> {
    const response = await this.client.get<ApiResponse<any>>('/data/fmp-cache/status');
    return this.handleResponse(response);
  }

  async triggerFmpCacheWarm(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<ApiResponse<{ success: boolean; message: string }>>('/data/fmp-cache/trigger');
    return this.handleResponse(response);
  }

  async getMonitoringStatus(): Promise<Record<string, any>> {
    const response = await this.client.get<ApiResponse<any>>('/data/monitoring/status');
    return this.handleResponse(response);
  }

  // --- User Management ---

  async changePassword(oldPassword: string, newPassword: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return response.data;
  }

  async getCurrentUser(): Promise<any> {
    const response = await this.client.get('/auth/me');
    return response.data;
  }

  async listUsers(): Promise<any[]> {
    const response = await this.client.get('/auth/users');
    return response.data.users;
  }

  async createUser(username: string, password: string, role: string): Promise<any> {
    const response = await this.client.post('/auth/users', { username, password, role });
    return response.data;
  }

  async updateUser(username: string, updates: { role?: string; permissions?: any; is_active?: boolean }): Promise<any> {
    const response = await this.client.put(`/auth/users/${username}`, updates);
    return response.data;
  }

  async deleteUser(username: string): Promise<any> {
    const response = await this.client.delete(`/auth/users/${username}`);
    return response.data;
  }

  async resetUserPassword(username: string, newPassword: string): Promise<any> {
    const response = await this.client.post(`/auth/users/${username}/reset-password`, {
      new_password: newPassword,
    });
    return response.data;
  }

  async getRoles(): Promise<Record<string, any>> {
    const response = await this.client.get('/auth/roles');
    return response.data.roles;
  }

  // ============================================================================
  // Analytics Endpoints
  // ============================================================================

  // ============================================================================
  // Advanced Analytics Endpoints (Rolling Stats, Attribution, Tear Sheet, TCA)
  // ============================================================================

  async getRollingStatistics(mode: TradingMode, period: string, window: number): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/rolling-statistics?mode=${mode}&period=${period}&window=${window}`
    );
    return this.handleResponse(response);
  }

  async getPerformanceAttribution(mode: TradingMode, period: string, groupBy: 'sector' | 'asset_class'): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/performance-attribution?mode=${mode}&period=${period}&group_by=${groupBy}`
    );
    return this.handleResponse(response);
  }

  async getTearSheetData(mode: TradingMode, period: string): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/tear-sheet?mode=${mode}&period=${period}`
    );
    return this.handleResponse(response);
  }

  async getTCAData(mode: TradingMode, period: string): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/analytics/tca?mode=${mode}&period=${period}`
    );
    return this.handleResponse(response);
  }

  async getSpyBenchmark(period?: string): Promise<Array<{ date: string; close: number }>> {
    const params = period ? `?period=${period}` : '';
    const response = await this.client.get<ApiResponse<Array<{ date: string; close: number }>>>(
      `/analytics/spy-benchmark${params}`
    );
    return this.extractArrayFromResponse<{ date: string; close: number }>(response, 'data');
  }

  // ============================================================================
  // Template Rankings (Task 9.1)
  // ============================================================================

  async getTemplateRankings(mode: TradingMode): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/strategies/template-rankings?mode=${mode}`
    );
    return this.extractArrayFromResponse<any>(response, 'rankings');
  }

  // ============================================================================
  // Blacklisted Combos
  // ============================================================================

  async getBlacklistedCombos(): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/strategies/blacklisted-combos`
    );
    return this.extractArrayFromResponse<any>(response, 'entries');
  }

  // ============================================================================
  // Idle Demotions
  // ============================================================================

  async getIdleDemotions(): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>(
      `/strategies/idle-demotions`
    );
    return this.extractArrayFromResponse<any>(response, 'entries');
  }

  // ============================================================================
  // Walk-Forward Analytics (Task 9.4)
  // ============================================================================

  async getWalkForwardAnalytics(mode: TradingMode, period: string): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/strategies/autonomous/walk-forward-analytics?mode=${mode}&period=${period}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Position Detail (Task 9.5)
  // ============================================================================

  async getPositionDetail(symbol: string, mode: TradingMode, interval: string = '1d'): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(
      `/account/positions/${encodeURIComponent(symbol)}/detail?mode=${mode}&interval=${interval}`
    );
    return this.handleResponse(response);
  }

  // ============================================================================
  // Data Quality (Task 11.1)
  // ============================================================================

  async getDataQuality(): Promise<any[]> {
    const response = await this.client.get<ApiResponse<any[]>>('/data/quality');
    return this.extractArrayFromResponse<any>(response, 'entries');
  }

  // ============================================================================
  // System Health (Task 11.2)
  // ============================================================================

  async getSystemHealth(): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>('/control/system-health');
    return this.handleResponse(response);
  }

  // ============================================================================
  // Audit Log (Task 11.3)
  // ============================================================================

  async getAuditLog(filters?: {
    event_types?: string[];
    symbol?: string;
    strategy_name?: string;
    severity?: string;
    start_date?: string;
    end_date?: string;
    search?: string;
    offset?: number;
    limit?: number;
  }): Promise<any> {
    const params = new URLSearchParams();
    if (filters?.event_types?.length) params.append('event_types', filters.event_types.join(','));
    if (filters?.symbol) params.append('symbol', filters.symbol);
    if (filters?.strategy_name) params.append('strategy_name', filters.strategy_name);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    if (filters?.search) params.append('search', filters.search);
    if (filters?.offset !== undefined) params.append('offset', String(filters.offset));
    if (filters?.limit !== undefined) params.append('limit', String(filters.limit));
    const qs = params.toString();
    const response = await this.client.get<ApiResponse<any>>(`/audit/log${qs ? `?${qs}` : ''}`);
    return this.handleResponse(response);
  }

  async getTradeLifecycle(tradeId: string): Promise<any> {
    const response = await this.client.get<ApiResponse<any>>(`/audit/trade-lifecycle/${encodeURIComponent(tradeId)}`);
    return this.handleResponse(response);
  }

  async exportAuditLog(filters?: {
    event_types?: string[];
    symbol?: string;
    severity?: string;
    start_date?: string;
    end_date?: string;
    search?: string;
  }): Promise<Blob> {
    const params = new URLSearchParams();
    if (filters?.event_types?.length) params.append('event_types', filters.event_types.join(','));
    if (filters?.symbol) params.append('symbol', filters.symbol);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);
    if (filters?.search) params.append('search', filters.search);
    const qs = params.toString();
    const response = await this.client.get(`/audit/export${qs ? `?${qs}` : ''}`, { responseType: 'blob' });
    return response.data;
  }

  // ============================================================================
  // Widget Data Endpoints (Phase 2 — Task 17.2)
  // ============================================================================

  async getTopMovers(mode: TradingMode): Promise<{ gainers: any[]; losers: any[] }> {
    const response = await this.client.get<ApiResponse<{ gainers: any[]; losers: any[] }>>(
      `/dashboard/top-movers?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getStrategyAlerts(mode: TradingMode): Promise<{ alerts: any[] }> {
    const response = await this.client.get<ApiResponse<{ alerts: any[] }>>(
      `/dashboard/strategy-alerts?mode=${mode}`
    );
    return this.handleResponse(response);
  }

  async getDashboardRecentSignals(mode: TradingMode, limit: number = 5): Promise<{ signals: any[]; total: number }> {
    const response = await this.client.get<ApiResponse<{ signals: any[]; total: number }>>(
      `/dashboard/recent-signals?mode=${mode}&limit=${limit}`
    );
    return this.handleResponse(response);
  }

  // Generic HTTP methods for endpoints not yet in the typed API
  async get(path: string): Promise<any> {
    const response = await this.client.get(path);
    return response.data;
  }

  async post(path: string, data?: any): Promise<any> {
    const response = await this.client.post(path, data);
    return response.data;
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
