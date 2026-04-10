/**
 * Autonomous Trading Notification Types
 */

export type AutonomousEventType =
  | 'cycle_started'
  | 'cycle_completed'
  | 'strategies_proposed'
  | 'backtest_completed'
  | 'strategy_activated'
  | 'strategy_retired'
  | 'regime_changed'
  | 'portfolio_rebalanced'
  | 'error_occurred';

export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error';

export interface NotificationAction {
  label: string;
  action: string;
  url?: string;
}

export interface AutonomousNotification {
  id: string;
  type: AutonomousEventType;
  severity: NotificationSeverity;
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  data?: any;
  actionButton?: NotificationAction;
}

export interface NotificationPreferences {
  enabled: boolean;
  soundEnabled: boolean;
  showToasts: boolean;
  severityFilter: NotificationSeverity[];
  eventTypeFilter: AutonomousEventType[];
}

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  enabled: true,
  soundEnabled: false,
  showToasts: true,
  severityFilter: ['info', 'success', 'warning', 'error'],
  eventTypeFilter: [
    'cycle_started',
    'cycle_completed',
    'strategies_proposed',
    'backtest_completed',
    'strategy_activated',
    'strategy_retired',
    'regime_changed',
    'portfolio_rebalanced',
    'error_occurred',
  ],
};

export { DEFAULT_NOTIFICATION_PREFERENCES as default };
