import { type FC, useEffect, useState } from 'react';
import { useNotifications } from '../hooks/useWebSocket';
import type { Notification } from '../types';

/**
 * Toast Notification Component
 * Displays critical and error notifications as floating toasts at the top of the screen
 * Auto-dismisses after a timeout (except for CRITICAL notifications)
 */
export const NotificationToast: FC = () => {
  const { notifications, markAsRead, clearNotification } = useNotifications();
  const [visibleToasts, setVisibleToasts] = useState<Notification[]>([]);

  useEffect(() => {
    // Filter for CRITICAL and ERROR notifications that haven't been read
    const criticalNotifications = notifications.filter(
      (n) => !n.read && (n.severity === 'CRITICAL' || n.severity === 'ERROR')
    );

    // Show only the 3 most recent critical/error notifications
    setVisibleToasts(criticalNotifications.slice(0, 3));
  }, [notifications]);

  // Auto-dismiss ERROR notifications after 10 seconds (CRITICAL stay until manually dismissed)
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    visibleToasts.forEach((toast) => {
      if (toast.severity === 'ERROR') {
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
            rounded-lg shadow-2xl border-2 p-4 animate-slide-in-right
            ${
              toast.severity === 'CRITICAL'
                ? 'bg-red-900/90 border-red-500 backdrop-blur-sm'
                : 'bg-orange-900/90 border-orange-500 backdrop-blur-sm'
            }
          `}
          role="alert"
        >
          <div className="flex items-start gap-3">
            {/* Icon */}
            <div
              className={`
                flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-2xl
                ${
                  toast.severity === 'CRITICAL'
                    ? 'bg-red-500/20 text-red-300'
                    : 'bg-orange-500/20 text-orange-300'
                }
              `}
            >
              {toast.severity === 'CRITICAL' ? '🚨' : '❌'}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-1">
                <h4
                  className={`
                    text-sm font-bold uppercase tracking-wide
                    ${
                      toast.severity === 'CRITICAL'
                        ? 'text-red-200'
                        : 'text-orange-200'
                    }
                  `}
                >
                  {toast.severity === 'CRITICAL' ? 'CRITICAL ERROR' : 'ERROR'}
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
              <h5 className="text-base font-semibold text-white mb-1">
                {toast.title}
              </h5>
              <p className="text-sm text-gray-200 break-words">{toast.message}</p>
              {toast.severity === 'ERROR' && (
                <p className="text-xs text-gray-400 mt-2">
                  Auto-dismissing in 10 seconds...
                </p>
              )}
            </div>
          </div>

          {/* Action Button for Critical Errors */}
          {toast.severity === 'CRITICAL' && (
            <div className="mt-3 pt-3 border-t border-red-500/30">
              <button
                onClick={() => handleDismiss(toast.id)}
                className="w-full px-4 py-2 rounded-lg text-sm font-semibold bg-red-500/20 text-red-200 hover:bg-red-500/30 transition-colors border border-red-500/50"
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
