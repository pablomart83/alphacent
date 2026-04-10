import { useEffect, useState, useCallback } from 'react';
import { wsManager } from '../services/websocket';
import type {
  MarketData,
  Position,
  Order,
  Strategy,
  SystemStatus,
  DependentService,
  Notification,
  AutonomousStatus,
} from '../types';
import type { AutonomousNotification } from '../types/notifications';

/**
 * Hook for WebSocket connection state
 */
export function useWebSocketConnection() {
  const [isConnected, setIsConnected] = useState(wsManager.isConnected());

  useEffect(() => {
    const unsubscribe = wsManager.onConnectionStateChange(setIsConnected);
    return unsubscribe;
  }, []);

  return isConnected;
}

/**
 * Hook for market data updates
 */
export function useMarketData(symbol?: string) {
  const [data, setData] = useState<MarketData | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onMarketData((marketData) => {
      if (!symbol || marketData.symbol === symbol) {
        setData(marketData);
      }
    });

    return unsubscribe;
  }, [symbol]);

  return data;
}

/**
 * Hook for position updates
 */
export function usePositionUpdates() {
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    const unsubscribe = wsManager.onPositionUpdate((position) => {
      setPositions((prev) => {
        const index = prev.findIndex((p) => p.id === position.id);
        if (index >= 0) {
          // Update existing position
          const updated = [...prev];
          updated[index] = position;
          return updated;
        } else {
          // Add new position
          return [...prev, position];
        }
      });
    });

    return unsubscribe;
  }, []);

  return positions;
}

/**
 * Hook for order updates
 */
export function useOrderUpdates() {
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    const unsubscribe = wsManager.onOrderUpdate((order) => {
      setOrders((prev) => {
        const index = prev.findIndex((o) => o.id === order.id);
        if (index >= 0) {
          // Update existing order
          const updated = [...prev];
          updated[index] = order;
          return updated;
        } else {
          // Add new order
          return [...prev, order];
        }
      });
    });

    return unsubscribe;
  }, []);

  return orders;
}

/**
 * Hook for strategy updates
 */
export function useStrategyUpdates() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  useEffect(() => {
    const unsubscribe = wsManager.onStrategyUpdate((strategy) => {
      setStrategies((prev) => {
        const index = prev.findIndex((s) => s.id === strategy.id);
        if (index >= 0) {
          // Update existing strategy
          const updated = [...prev];
          updated[index] = strategy;
          return updated;
        } else {
          // Add new strategy
          return [...prev, strategy];
        }
      });
    });

    return unsubscribe;
  }, []);

  return strategies;
}

/**
 * Hook for system status updates
 */
export function useSystemStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onSystemState(setStatus);
    return unsubscribe;
  }, []);

  return status;
}

/**
 * Hook for service status updates
 */
export function useServiceStatus() {
  const [services, setServices] = useState<Record<string, DependentService>>({});

  useEffect(() => {
    const unsubscribe = wsManager.onServiceStatus(setServices);
    return unsubscribe;
  }, []);

  return services;
}

/**
 * Hook for notifications
 */
export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const unsubscribe = wsManager.onNotification((notification) => {
      setNotifications((prev) => [notification, ...prev]);
      if (!notification.read) {
        setUnreadCount((prev) => prev + 1);
      }
    });

    return unsubscribe;
  }, []);

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
  }, []);

  const clearNotification = useCallback((id: string) => {
    setNotifications((prev) => {
      const notification = prev.find((n) => n.id === id);
      if (notification && !notification.read) {
        setUnreadCount((count) => Math.max(0, count - 1));
      }
      return prev.filter((n) => n.id !== id);
    });
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
    setUnreadCount(0);
  }, []);

  return {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  };
}

/**
 * Hook to manage WebSocket lifecycle
 * Automatically connects on mount and disconnects on unmount
 */
export function useWebSocketManager() {
  useEffect(() => {
    wsManager.connect();

    return () => {
      wsManager.disconnect();
    };
  }, []);

  return {
    isConnected: useWebSocketConnection(),
    connectionState: wsManager.getConnectionState(),
  };
}

/**
 * Hook for autonomous status updates
 */
export function useAutonomousStatus() {
  const [status, setStatus] = useState<AutonomousStatus | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onAutonomousStatus(setStatus);
    return unsubscribe;
  }, []);

  return status;
}

/**
 * Hook for autonomous cycle events
 */
export function useAutonomousCycle() {
  const [cycleEvent, setCycleEvent] = useState<{ event: string; data: any } | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onAutonomousCycle((data) => {
      setCycleEvent(data);
    });

    return unsubscribe;
  }, []);

  return cycleEvent;
}

/**
 * Hook for autonomous strategy events
 */
export function useAutonomousStrategies() {
  const [strategyEvent, setStrategyEvent] = useState<{ event: string; data: any } | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onAutonomousStrategies((data) => {
      setStrategyEvent(data);
    });

    return unsubscribe;
  }, []);

  return strategyEvent;
}

/**
 * Hook for autonomous notifications
 */
export function useAutonomousNotifications() {
  const [notifications, setNotifications] = useState<AutonomousNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const unsubscribe = wsManager.onAutonomousNotifications((notification) => {
      setNotifications((prev) => [notification, ...prev]);
      if (!notification.read) {
        setUnreadCount((prev) => prev + 1);
      }
    });

    return unsubscribe;
  }, []);

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
  }, []);

  const clearNotification = useCallback((id: string) => {
    setNotifications((prev) => {
      const notification = prev.find((n) => n.id === id);
      if (notification && !notification.read) {
        setUnreadCount((count) => Math.max(0, count - 1));
      }
      return prev.filter((n) => n.id !== id);
    });
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
    setUnreadCount(0);
  }, []);

  return {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  };
}

/**
 * Combined hook for all autonomous WebSocket updates
 */
export function useAutonomousWebSocket() {
  const status = useAutonomousStatus();
  const cycleEvent = useAutonomousCycle();
  const strategyEvent = useAutonomousStrategies();
  const { notifications, unreadCount, markAsRead, markAllAsRead, clearNotification, clearAll } = useAutonomousNotifications();

  return {
    status,
    cycleEvent,
    strategyEvent,
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  };
}


/**
 * Hook for cycle progress events
 */
export function useCycleProgress() {
  const [progress, setProgress] = useState<{ stage: string; percent_complete: number; message: string } | null>(null);

  useEffect(() => {
    const unsubscribe = wsManager.onCycleProgress((data) => {
      setProgress(data);
    });

    return unsubscribe;
  }, []);

  return progress;
}

/**
 * Hook for fundamental alert events
 */
export function useFundamentalAlerts() {
  const [alerts, setAlerts] = useState<any[]>([]);

  useEffect(() => {
    const unsubscribe = wsManager.onFundamentalAlert((alert) => {
      setAlerts((prev) => [alert, ...prev].slice(0, 50)); // Keep last 50
    });

    return unsubscribe;
  }, []);

  return alerts;
}
