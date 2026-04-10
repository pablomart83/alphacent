/**
 * Unified hooks exports
 */

export { useAuth } from './useAuth';
export { useApi, useApiMutation } from './useApi';
export {
  useWebSocketConnection,
  useMarketData,
  usePositionUpdates,
  useOrderUpdates,
  useStrategyUpdates,
  useSystemStatus,
  useServiceStatus,
  useNotifications,
  useWebSocketManager,
} from './useWebSocket';
export { useRetry } from './useRetry';
export { useThrottle, useThrottledValue } from './useThrottle';
export { useUpdateFlash, useFlashClasses } from './useUpdateFlash';
export { usePolling } from './usePolling';
export type { UsePollingOptions, UsePollingReturn } from './usePolling';
