/**
 * Unified service exports
 * Provides centralized access to all API and WebSocket services
 */

export { apiClient } from './api';
export { wsManager } from './websocket';
export { authService } from './auth';

// Re-export types for convenience
export type {
  ApiResponse,
  AccountInfo,
  Position,
  Order,
  Strategy,
  PerformanceMetrics,
  MarketData,
  SystemStatus,
  DependentService,
  ConfigData,
  RiskParams,
  Notification,
  WebSocketMessage,
} from '../types';
