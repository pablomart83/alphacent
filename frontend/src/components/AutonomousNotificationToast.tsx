import { type FC, useEffect, useState } from 'react';
import { useAutonomousNotifications } from '../contexts/NotificationContext';
import type { AutonomousNotification } from '../types/notifications';
import { useNavigate } from 'react-router-dom';

/**
 * Autonomous Trading Notification Toast Component
 * Displays autonomous trading notifications as floating toasts
 * Supports action buttons and auto-dismiss
 */
export const AutonomousNotificationToast: FC = () => {
  const { notifications, markAsRead, clearNotification, preferences } =
    useAutonomousNotifications();
  const [visibleToasts, setVisibleToasts] = useState<AutonomousNotification[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    if (!preferences.showToasts) {
      setVisibleToasts([]);
      return;
    }

    // Filter for unread notifications
    const unreadNotifications = notifications.filter((n) => !n.read);

    // Show only the 3 most recent notifications
    setVisibleToasts(unreadNotifications.slice(0, 3));
  }, [notifications, preferences.showToasts]);

  // Auto-dismiss info and success notifications after 10 seconds
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    visibleToasts.forEach((toast) => {
      if (toast.severity === 'info' || toast.severity === 'success') {
        const timer = setTimeout(() => {
          handleDismiss(toast.id);
        }, 10000);
        timers.push(timer);
      }
    });

    return () => {
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, [visibleToasts]);

  const handleDismiss = (id: string) => {
    markAsRead(id);
  };

  const handleClose = (id: string) => {
    clearNotification(id);
  };

  const handleAction = (notification: AutonomousNotification) => {
    if (notification.actionButton?.url) {
      navigate(notification.actionButton.url);
    }
    handleDismiss(notification.id);
  };

  const getIcon = (notification: AutonomousNotification): string => {
    switch (notification.type) {
      case 'cycle_started':
        return '🔄';
      case 'cycle_completed':
        return '✅';
      case 'strategies_proposed':
        return '💡';
      case 'backtest_completed':
        return '📊';
      case 'strategy_activated':
        return '🚀';
      case 'strategy_retired':
        return '📉';
      case 'regime_changed':
        return '🌐';
      case 'portfolio_rebalanced':
        return '⚖️';
      case 'error_occurred':
        return '❌';
      default:
        return 'ℹ️';
    }
  };

  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case 'success':
        return 'bg-green-900/90 border-green-500 text-green-200';
      case 'warning':
        return 'bg-yellow-900/90 border-yellow-500 text-yellow-200';
      case 'error':
        return 'bg-red-900/90 border-red-500 text-red-200';
      case 'info':
      default:
        return 'bg-blue-900/90 border-blue-500 text-blue-200';
    }
  };

  const getIconBgStyles = (severity: string) => {
    switch (severity) {
      case 'success':
        return 'bg-green-500/20 text-green-300';
      case 'warning':
        return 'bg-yellow-500/20 text-yellow-300';
      case 'error':
        return 'bg-red-500/20 text-red-300';
      case 'info':
      default:
        return 'bg-blue-500/20 text-blue-300';
    }
  };

  const filteredToasts = visibleToasts.filter(t => t.title || t.message);
  if (filteredToasts.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-4 right-4 z-50 space-y-3 max-w-md">
      {filteredToasts.map((toast) => (
        <div
          key={toast.id}
          className={`
            rounded-lg shadow-2xl border-2 p-4 animate-slide-in-right backdrop-blur-sm
            ${getSeverityStyles(toast.severity)}
          `}
          role="alert"
        >
          <div className="flex items-start gap-3">
            {/* Icon */}
            <div
              className={`
                flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-2xl
                ${getIconBgStyles(toast.severity)}
              `}
            >
              {getIcon(toast)}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-1">
                <h4 className="text-sm font-bold uppercase tracking-wide">
                  {toast.severity.toUpperCase()}
                </h4>
                <button
                  onClick={() => handleClose(toast.id)}
                  className="text-gray-300 hover:text-white transition-colors"
                  aria-label="Close notification"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
              <h5 className="text-base font-semibold text-white mb-1">{toast.title}</h5>
              <p className="text-sm text-gray-200 break-words">{toast.message}</p>
              {(toast.severity === 'info' || toast.severity === 'success') && (
                <p className="text-xs text-gray-400 mt-2">Auto-dismissing in 10 seconds...</p>
              )}
            </div>
          </div>

          {/* Action Button */}
          {toast.actionButton && (
            <div className="mt-3 pt-3 border-t border-gray-500/30">
              <button
                onClick={() => handleAction(toast)}
                className={`
                  w-full px-4 py-2 rounded-lg text-sm font-semibold transition-colors border
                  ${
                    toast.severity === 'success'
                      ? 'bg-green-500/20 text-green-200 hover:bg-green-500/30 border-green-500/50'
                      : toast.severity === 'warning'
                      ? 'bg-yellow-500/20 text-yellow-200 hover:bg-yellow-500/30 border-yellow-500/50'
                      : toast.severity === 'error'
                      ? 'bg-red-500/20 text-red-200 hover:bg-red-500/30 border-red-500/50'
                      : 'bg-blue-500/20 text-blue-200 hover:bg-blue-500/30 border-blue-500/50'
                  }
                `}
              >
                {toast.actionButton.label}
              </button>
            </div>
          )}

          {/* Acknowledge button for warnings and errors */}
          {(toast.severity === 'warning' || toast.severity === 'error') &&
            !toast.actionButton && (
              <div className="mt-3 pt-3 border-t border-gray-500/30">
                <button
                  onClick={() => handleDismiss(toast.id)}
                  className={`
                    w-full px-4 py-2 rounded-lg text-sm font-semibold transition-colors border
                    ${
                      toast.severity === 'warning'
                        ? 'bg-yellow-500/20 text-yellow-200 hover:bg-yellow-500/30 border-yellow-500/50'
                        : 'bg-red-500/20 text-red-200 hover:bg-red-500/30 border-red-500/50'
                    }
                  `}
                >
                  Acknowledge
                </button>
              </div>
            )}
        </div>
      ))}
    </div>
  );
};
