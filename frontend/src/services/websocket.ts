import type {
  WebSocketMessage,
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

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

type MessageHandler = (data: any) => void;

// Throttle configuration for high-frequency updates
const THROTTLE_CONFIG = {
  market_data: 1000, // 1 second
  autonomous_status: 2000, // 2 seconds
  position_update: 500, // 500ms
  default: 0, // No throttle
};

/**
 * WebSocket Manager for real-time updates
 * Handles connection lifecycle, reconnection, and message routing
 * Supports autonomous trading channels with throttling
 */
class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // Start with 1 second
  private maxReconnectDelay = 30000; // Max 30 seconds
  private reconnectTimer: number | null = null;
  private isIntentionallyClosed = false;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private connectionStateHandlers: Set<(connected: boolean) => void> = new Set();
  
  // Throttling state
  private throttleTimers: Map<string, number> = new Map();
  private lastMessageTime: Map<string, number> = new Map();
  private pendingMessages: Map<string, any> = new Map();

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    this.isIntentionallyClosed = false;
    
    // Get session_id from cookie
    const sessionId = this.getCookie('session_id');
    
    console.log('[WebSocket] Attempting to connect...');
    console.log('[WebSocket] Session ID from cookie:', sessionId ? `${sessionId.substring(0, 8)}...` : 'NOT FOUND');
    console.log('[WebSocket] All cookies:', document.cookie);
    
    if (!sessionId) {
      console.error('[WebSocket] No session ID found in cookies, cannot connect');
      return;
    }

    try {
      const wsUrl = `${WS_BASE_URL}/ws?session_id=${sessionId}`;
      console.log('[WebSocket] Connecting to:', wsUrl.replace(sessionId, sessionId.substring(0, 8) + '...'));
      
      // Include session ID in WebSocket URL
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WebSocket] ✅ Connected successfully');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.notifyConnectionState(true);
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('[WebSocket] Message received:', message.type || message.channel);
          
          // Handle channel-based messages (autonomous events)
          if (message.channel && message.event) {
            // Convert channel:event format to message type
            const messageType = this.convertChannelToType(message.channel, message.event);
            const wsMessage: WebSocketMessage = {
              type: messageType as WebSocketMessage['type'],
              data: message.data || message,
            };
            this.handleMessage(wsMessage);
          } else if (message.type) {
            // Handle standard message format — normalize data field
            // Backend may put payload in .data, .strategy, .signal, etc.
            const wsMessage: WebSocketMessage = {
              type: message.type as WebSocketMessage['type'],
              data: message.data || message.strategy || message.signal || message,
            };
            this.handleMessage(wsMessage);
          } else {
            console.warn('[WebSocket] Unknown message format:', message);
          }
        } catch (error) {
          console.error('[WebSocket] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WebSocket] ❌ Error:', error);
      };

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected. Code:', event.code, 'Reason:', event.reason || 'No reason provided');
        this.notifyConnectionState(false);
        
        if (!this.isIntentionallyClosed) {
          console.log('[WebSocket] Will attempt to reconnect...');
          this.scheduleReconnect();
        }
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create connection:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Get cookie value by name
   */
  private getCookie(name: string): string | null {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop()?.split(';').shift() || null;
    }
    return null;
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.isIntentionallyClosed = true;
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    // Clear all throttle timers
    this.throttleTimers.forEach((timer) => clearTimeout(timer));
    this.throttleTimers.clear();
    this.lastMessageTime.clear();
    this.pendingMessages.clear();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.notifyConnectionState(false);
  }

  /**
   * Schedule reconnection with exponential backoff
   */
  private scheduleReconnect(): void {
    if (this.isIntentionallyClosed) {
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Convert channel-based message to message type
   */
  private convertChannelToType(channel: string, _event: string): string {
    // Map channel:event to message type
    const channelMap: Record<string, string> = {
      'autonomous:status': 'autonomous_status',
      'autonomous:cycle': 'autonomous_cycle',
      'autonomous:strategies': 'autonomous_strategies',
      'autonomous:notifications': 'autonomous_notifications',
    };

    return channelMap[channel] || channel.replace(':', '_');
  }

  /**
   * Handle incoming WebSocket message with throttling
   */
  private handleMessage(message: WebSocketMessage): void {
    // Check if this message type should be throttled
    const throttleDelay = this.getThrottleDelay(message.type);
    
    if (throttleDelay > 0) {
      this.handleThrottledMessage(message, throttleDelay);
    } else {
      this.dispatchMessage(message);
    }
  }

  /**
   * Get throttle delay for a message type
   */
  private getThrottleDelay(type: string): number {
    return THROTTLE_CONFIG[type as keyof typeof THROTTLE_CONFIG] || THROTTLE_CONFIG.default;
  }

  /**
   * Handle throttled message
   */
  private handleThrottledMessage(message: WebSocketMessage, throttleDelay: number): void {
    const now = Date.now();
    const lastTime = this.lastMessageTime.get(message.type) || 0;
    const timeSinceLastMessage = now - lastTime;

    if (timeSinceLastMessage >= throttleDelay) {
      // Enough time has passed, dispatch immediately
      this.dispatchMessage(message);
      this.lastMessageTime.set(message.type, now);
    } else {
      // Store pending message and schedule dispatch
      this.pendingMessages.set(message.type, message);
      
      // Clear existing timer if any
      const existingTimer = this.throttleTimers.get(message.type);
      if (existingTimer) {
        clearTimeout(existingTimer);
      }

      // Schedule dispatch after remaining throttle time
      const remainingTime = throttleDelay - timeSinceLastMessage;
      const timer = window.setTimeout(() => {
        const pendingMessage = this.pendingMessages.get(message.type);
        if (pendingMessage) {
          this.dispatchMessage(pendingMessage);
          this.lastMessageTime.set(message.type, Date.now());
          this.pendingMessages.delete(message.type);
        }
        this.throttleTimers.delete(message.type);
      }, remainingTime);

      this.throttleTimers.set(message.type, timer);
    }
  }

  /**
   * Dispatch message to handlers
   */
  private dispatchMessage(message: WebSocketMessage): void {
    const handlers = this.handlers.get(message.type);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(message.data);
        } catch (error) {
          console.error(`Error in ${message.type} handler:`, error);
        }
      });
    }
  }

  /**
   * Subscribe to a specific message type
   */
  subscribe(type: WebSocketMessage['type'], handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    
    this.handlers.get(type)!.add(handler);

    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(type);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.handlers.delete(type);
        }
      }
    };
  }

  /**
   * Subscribe to market data updates
   */
  onMarketData(handler: (data: MarketData) => void): () => void {
    return this.subscribe('market_data', handler);
  }

  /**
   * Subscribe to position updates
   */
  onPositionUpdate(handler: (data: Position) => void): () => void {
    return this.subscribe('position_update', handler);
  }

  /**
   * Subscribe to order updates
   */
  onOrderUpdate(handler: (data: Order) => void): () => void {
    return this.subscribe('order_update', handler);
  }

  /**
   * Subscribe to strategy updates
   */
  onStrategyUpdate(handler: (data: Strategy) => void): () => void {
    return this.subscribe('strategy_update', handler);
  }

  /**
   * Subscribe to system state changes
   */
  onSystemState(handler: (data: SystemStatus) => void): () => void {
    return this.subscribe('system_state', handler);
  }

  /**
   * Subscribe to notifications
   */
  onNotification(handler: (data: Notification) => void): () => void {
    return this.subscribe('notification', handler);
  }

  /**
   * Subscribe to service status updates
   */
  onServiceStatus(handler: (data: Record<string, DependentService>) => void): () => void {
    return this.subscribe('service_status', handler);
  }

  /**
   * Subscribe to signal generation events
   */
  onSignalGenerated(handler: (data: any) => void): () => void {
    return this.subscribe('signal_generated', handler);
  }

  /**
   * Generic subscription method for any message type
   */
  on(type: string, handler: MessageHandler): () => void {
    return this.subscribe(type as WebSocketMessage['type'], handler);
  }

  /**
   * Subscribe to autonomous status updates
   */
  onAutonomousStatus(handler: (data: AutonomousStatus) => void): () => void {
    return this.subscribe('autonomous_status', handler);
  }

  /**
   * Subscribe to autonomous cycle events
   */
  onAutonomousCycle(handler: (data: { event: string; data: any }) => void): () => void {
    return this.subscribe('autonomous_cycle', handler);
  }

  /**
   * Subscribe to autonomous strategy events
   */
  onAutonomousStrategies(handler: (data: { event: string; data: any }) => void): () => void {
    return this.subscribe('autonomous_strategies', handler);
  }

  /**
   * Subscribe to autonomous notifications
   */
  onAutonomousNotifications(handler: (data: AutonomousNotification) => void): () => void {
    return this.subscribe('autonomous_notifications', handler);
  }

  /**
   * Subscribe to autonomous cycle progress events
   */
  onCycleProgress(handler: (data: any) => void): () => void {
    return this.subscribe('cycle_progress' as WebSocketMessage['type'], handler);
  }

  /**
   * Subscribe to fundamental alert events
   */
  onFundamentalAlert(handler: (data: any) => void): () => void {
    return this.subscribe('fundamental_alert' as WebSocketMessage['type'], handler);
  }

  /**
   * Subscribe to connection state changes
   */
  onConnectionStateChange(handler: (connected: boolean) => void): () => void {
    this.connectionStateHandlers.add(handler);
    
    // Immediately notify of current state
    handler(this.isConnected());

    // Return unsubscribe function
    return () => {
      this.connectionStateHandlers.delete(handler);
    };
  }

  /**
   * Notify all connection state handlers
   */
  private notifyConnectionState(connected: boolean): void {
    this.connectionStateHandlers.forEach((handler) => {
      try {
        handler(connected);
      } catch (error) {
        console.error('Error in connection state handler:', error);
      }
    });
  }

  /**
   * Check if WebSocket is connected
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Get current connection state
   */
  getConnectionState(): 'connecting' | 'open' | 'closing' | 'closed' {
    if (!this.ws) return 'closed';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'open';
      case WebSocket.CLOSING:
        return 'closing';
      case WebSocket.CLOSED:
        return 'closed';
      default:
        return 'closed';
    }
  }

  /**
   * Send a message to the server (if needed for future features)
   */
  send(message: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }
}

// Export singleton instance
export const wsManager = new WebSocketManager();
