import { type FC, useState, useEffect, useCallback } from 'react';
import { useNotifications } from '../hooks/useWebSocket';
import { apiClient } from '../services/api';
import type { Notification } from '../types';

interface AlertHistoryItem {
  id: number;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  metadata: any;
  read: boolean;
  acknowledged: boolean;
  link_page: string | null;
  created_at: string;
}

/**
 * Notifications Component
 * Displays system notifications from WebSocket + persistent alerts from AlertHistory DB.
 * Supports notification history, filtering by severity, browser push for critical alerts.
 */
export const Notifications: FC = () => {
  const {
    notifications: wsNotifications,
    unreadCount: wsUnreadCount,
    markAsRead: wsMarkAsRead,
    markAllAsRead: wsMarkAllAsRead,
    clearNotification: wsClearNotification,
    clearAll: wsClearAll,
  } = useNotifications();

  const [isExpanded, setIsExpanded] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [alertHistory, setAlertHistory] = useState<AlertHistoryItem[]>([]);
  const [alertUnreadCount, setAlertUnreadCount] = useState(0);

  // Fetch alert history from backend
  const fetchAlertHistory = useCallback(async () => {
    try {
      const result = await apiClient.getAlertHistory(50);
      if (result?.alerts) {
        setAlertHistory(result.alerts);
        setAlertUnreadCount(result.unread_count || 0);
      }
    } catch {
      // Silently fail — alerts are supplementary
    }
  }, []);

  // Fetch on mount and when panel opens
  useEffect(() => {
    fetchAlertHistory();
    const interval = setInterval(fetchAlertHistory, 60000); // Refresh every 60s
    return () => clearInterval(interval);
  }, [fetchAlertHistory]);

  useEffect(() => {
    if (isExpanded) fetchAlertHistory();
  }, [isExpanded, fetchAlertHistory]);

  // Merge WS notifications + DB alert history into a unified list
  const mergedNotifications: Array<{
    id: string;
    source: 'ws' | 'db';
    severity: string;
    title: string;
    message: string;
    timestamp: string;
    read: boolean;
    acknowledged: boolean;
    linkPage?: string | null;
    dbId?: number;
  }> = [
    ...wsNotifications.map((n: Notification) => ({
      id: n.id,
      source: 'ws' as const,
      severity: n.severity,
      title: n.title,
      message: n.message,
      timestamp: n.timestamp,
      read: n.read,
      acknowledged: false,
      linkPage: null,
    })),
    ...alertHistory.map((a) => ({
      id: `db-${a.id}`,
      source: 'db' as const,
      severity: a.severity === 'critical' ? 'CRITICAL' : a.severity === 'warning' ? 'WARNING' : 'INFO',
      title: a.title,
      message: a.message,
      timestamp: a.created_at,
      read: a.read,
      acknowledged: a.acknowledged,
      linkPage: a.link_page,
      dbId: a.id,
    })),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  const totalUnread = wsUnreadCount + alertUnreadCount;

  // Filter by severity
  const filteredNotifications =
    filterSeverity === 'ALL'
      ? mergedNotifications
      : mergedNotifications.filter((n) => n.severity === filterSeverity);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return 'text-red-500 bg-red-500/10 border-red-500/30';
      case 'ERROR': return 'text-orange-500 bg-orange-500/10 border-orange-500/30';
      case 'WARNING': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30';
      case 'INFO': return 'text-blue-500 bg-blue-500/10 border-blue-500/30';
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/30';
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return '🚨';
      case 'ERROR': return '❌';
      case 'WARNING': return '⚠️';
      case 'INFO': return 'ℹ️';
      default: return '📢';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const handleNotificationClick = async (notification: typeof mergedNotifications[0]) => {
    if (!notification.read) {
      if (notification.source === 'ws') {
        wsMarkAsRead(notification.id);
      } else if (notification.dbId) {
        try {
          await apiClient.markAlertRead(notification.dbId);
          setAlertHistory(prev => prev.map(a => a.id === notification.dbId ? { ...a, read: true } : a));
          setAlertUnreadCount(prev => Math.max(0, prev - 1));
        } catch { /* ignore */ }
      }
    }
    // Navigate if link_page is set
    if (notification.linkPage) {
      window.location.hash = notification.linkPage;
    }
  };

  const handleAcknowledge = async (notification: typeof mergedNotifications[0]) => {
    if (notification.dbId) {
      try {
        await apiClient.acknowledgeAlert(notification.dbId);
        setAlertHistory(prev => prev.map(a => a.id === notification.dbId ? { ...a, acknowledged: true, read: true } : a));
        setAlertUnreadCount(prev => Math.max(0, prev - 1));
      } catch { /* ignore */ }
    }
  };

  const handleMarkAllRead = async () => {
    wsMarkAllAsRead();
    try {
      await apiClient.markAllAlertsRead();
      setAlertHistory(prev => prev.map(a => ({ ...a, read: true })));
      setAlertUnreadCount(0);
    } catch { /* ignore */ }
  };

  const handleClearAll = async () => {
    wsClearAll();
    try {
      await apiClient.clearAlertHistory();
      setAlertHistory([]);
      setAlertUnreadCount(0);
    } catch { /* ignore */ }
  };

  const handleClearNotification = (notification: typeof mergedNotifications[0]) => {
    if (notification.source === 'ws') {
      wsClearNotification(notification.id);
    }
    // DB alerts persist — user can clear all via button
  };

  return (
    <div className="relative">
      {/* Notification Bell Button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="relative p-2 rounded-lg hover:bg-gray-800 transition-colors"
        aria-label="Notifications"
      >
        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {totalUnread > 0 && (
          <span className="absolute top-0 right-0 inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-white transform translate-x-1/2 -translate-y-1/2 bg-red-600 rounded-full">
            {totalUnread > 99 ? '99+' : totalUnread}
          </span>
        )}
      </button>

      {/* Notification Panel */}
      {isExpanded && (
        <div
          className="absolute right-0 mt-2 w-96 rounded-lg shadow-xl z-50"
          style={{ backgroundColor: 'var(--color-card-bg)', border: '1px solid var(--color-border)' }}
        >
          {/* Header */}
          <div className="p-4 border-b border-gray-800">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-100 font-mono">Notifications</h3>
              <div className="flex items-center gap-2">
                {totalUnread > 0 && (
                  <button onClick={handleMarkAllRead} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                    Mark all read
                  </button>
                )}
                {mergedNotifications.length > 0 && (
                  <button onClick={handleClearAll} className="text-xs text-red-400 hover:text-red-300 transition-colors">
                    Clear all
                  </button>
                )}
              </div>
            </div>
            {/* Severity Filter */}
            <div className="flex gap-2">
              {['ALL', 'CRITICAL', 'WARNING', 'INFO'].map((severity) => (
                <button
                  key={severity}
                  onClick={() => setFilterSeverity(severity)}
                  className={`px-3 py-1 text-xs rounded transition-colors ${
                    filterSeverity === severity
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                  }`}
                >
                  {severity}
                </button>
              ))}
            </div>
          </div>

          {/* Notification List */}
          <div className="max-h-96 overflow-y-auto">
            {filteredNotifications.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                <svg className="w-12 h-12 mx-auto mb-3 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p className="text-sm">No notifications</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-800">
                {filteredNotifications.map((notification) => (
                  <div
                    key={notification.id}
                    onClick={() => handleNotificationClick(notification)}
                    className={`p-4 cursor-pointer transition-colors ${
                      !notification.read ? 'bg-blue-500/5 hover:bg-blue-500/10' : 'hover:bg-gray-800/50'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-lg border ${getSeverityColor(notification.severity)}`}>
                        {getSeverityIcon(notification.severity)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <h4 className={`text-sm font-semibold ${
                            notification.severity === 'CRITICAL' ? 'text-red-400'
                              : notification.severity === 'WARNING' ? 'text-yellow-400'
                              : 'text-gray-200'
                          }`}>
                            {notification.title}
                          </h4>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleClearNotification(notification); }}
                            className="text-gray-500 hover:text-gray-300 transition-colors"
                            aria-label="Clear notification"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                        <p className="text-sm text-gray-400 mb-2 break-words">{notification.message}</p>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">{formatTimestamp(notification.timestamp)}</span>
                          {!notification.read && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-500/20 text-blue-400">New</span>
                          )}
                          {notification.severity === 'CRITICAL' && !notification.acknowledged && notification.source === 'db' && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleAcknowledge(notification); }}
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                            >
                              Acknowledge
                            </button>
                          )}
                          {notification.linkPage && (
                            <span className="text-xs text-blue-400">→ View</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
