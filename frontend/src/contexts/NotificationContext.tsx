import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
  type FC,
} from 'react';
import { wsManager } from '../services/websocket';
import {
  type AutonomousNotification,
  type NotificationPreferences,
  DEFAULT_NOTIFICATION_PREFERENCES,
} from '../types/notifications';

interface NotificationContextType {
  notifications: AutonomousNotification[];
  unreadCount: number;
  preferences: NotificationPreferences;
  addNotification: (notification: AutonomousNotification) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearNotification: (id: string) => void;
  clearAll: () => void;
  updatePreferences: (preferences: Partial<NotificationPreferences>) => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

const STORAGE_KEY = 'autonomous_notifications';
const PREFERENCES_KEY = 'notification_preferences';
const MAX_NOTIFICATIONS = 100;

interface NotificationProviderProps {
  children: ReactNode;
}

export const NotificationProvider: FC<NotificationProviderProps> = ({ children }) => {
  const [notifications, setNotifications] = useState<AutonomousNotification[]>(() => {
    // Load notifications from localStorage on mount
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (error) {
      console.error('Failed to load notifications from storage:', error);
      return [];
    }
  });

  const [preferences, setPreferences] = useState<NotificationPreferences>(() => {
    // Load preferences from localStorage on mount
    try {
      const stored = localStorage.getItem(PREFERENCES_KEY);
      return stored ? JSON.parse(stored) : DEFAULT_NOTIFICATION_PREFERENCES;
    } catch (error) {
      console.error('Failed to load notification preferences:', error);
      return DEFAULT_NOTIFICATION_PREFERENCES;
    }
  });

  const [unreadCount, setUnreadCount] = useState(() => {
    return notifications.filter((n) => !n.read).length;
  });

  // Persist notifications to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(notifications));
    } catch (error) {
      console.error('Failed to save notifications to storage:', error);
    }
  }, [notifications]);

  // Persist preferences to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
    } catch (error) {
      console.error('Failed to save notification preferences:', error);
    }
  }, [preferences]);

  // Update unread count
  useEffect(() => {
    setUnreadCount(notifications.filter((n) => !n.read).length);
  }, [notifications]);

  // Play notification sound
  const playNotificationSound = useCallback(() => {
    if (preferences.soundEnabled) {
      try {
        // Create a simple beep sound using Web Audio API
        const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.value = 800;
        oscillator.type = 'sine';

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
      } catch (error) {
        console.error('Failed to play notification sound:', error);
      }
    }
  }, [preferences.soundEnabled]);

  // Add notification
  const addNotification = useCallback(
    (notification: AutonomousNotification) => {
      // Check if notification should be filtered
      if (!preferences.enabled) return;
      if (!preferences.severityFilter.includes(notification.severity)) return;
      if (!preferences.eventTypeFilter.includes(notification.type)) return;

      setNotifications((prev) => {
        // Prevent duplicates
        if (prev.some((n) => n.id === notification.id)) {
          return prev;
        }

        // Add new notification and limit to MAX_NOTIFICATIONS
        const updated = [notification, ...prev].slice(0, MAX_NOTIFICATIONS);
        return updated;
      });

      // Play sound for new notifications
      playNotificationSound();
    },
    [preferences, playNotificationSound]
  );

  // Mark notification as read
  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  // Mark all notifications as read
  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  // Clear notification
  const clearNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  // Clear all notifications
  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  // Update preferences
  const updatePreferences = useCallback((newPreferences: Partial<NotificationPreferences>) => {
    setPreferences((prev) => ({ ...prev, ...newPreferences }));
  }, []);

  // Subscribe to WebSocket autonomous notifications
  useEffect(() => {
    const unsubscribe = wsManager.on('autonomous_notifications', (data: any) => {
      // Transform WebSocket data to AutonomousNotification
      const notification: AutonomousNotification = {
        id: data.id || `notif-${Date.now()}-${Math.random()}`,
        type: data.type,
        severity: data.severity,
        title: data.title,
        message: data.message,
        timestamp: data.timestamp || new Date().toISOString(),
        read: false,
        data: data.data,
        actionButton: data.actionButton,
      };

      addNotification(notification);
    });

    return unsubscribe;
  }, [addNotification]);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        preferences,
        addNotification,
        markAsRead,
        markAllAsRead,
        clearNotification,
        clearAll,
        updatePreferences,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
};

export const useAutonomousNotifications = (): NotificationContextType => {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error('useAutonomousNotifications must be used within a NotificationProvider');
  }
  return context;
};
