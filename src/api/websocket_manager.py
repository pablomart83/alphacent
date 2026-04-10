"""
WebSocket manager for real-time updates.

Manages WebSocket connections and broadcasts updates to connected clients.
Validates: Requirements 11.9, 16.11
"""

import json
import logging
from typing import Dict, List, Set
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Validates: Requirements 11.9, 16.11
    """
    
    def __init__(self):
        """Initialize WebSocket manager."""
        # Map of session_id -> WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        logger.info("WebSocketManager initialized")
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """
        Accept WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            session_id: User session ID
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: session {session_id[:8]}...")
        
        # Send welcome message
        await self.send_personal_message(
            session_id,
            {
                "type": "connection",
                "status": "connected",
                "timestamp": datetime.now().isoformat()
            }
        )
    
    def disconnect(self, session_id: str):
        """
        Remove WebSocket connection.
        
        Args:
            session_id: User session ID
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: session {session_id[:8]}...")
    
    async def send_personal_message(self, session_id: str, message: dict):
        """
        Send message to specific connection.
        
        Args:
            session_id: User session ID
            message: Message dictionary to send
        """
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {session_id[:8]}...: {e}")
                self.disconnect(session_id)
    
    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.
        
        Args:
            message: Message dictionary to broadcast
        """
        disconnected = []
        
        for session_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {session_id[:8]}...: {e}")
                disconnected.append(session_id)
        
        # Clean up disconnected clients
        for session_id in disconnected:
            self.disconnect(session_id)
    
    async def broadcast_market_data_update(self, symbol: str, data: dict):
        """
        Broadcast market data update.
        
        Args:
            symbol: Instrument symbol
            data: Market data dictionary
            
        Validates: Requirement 11.9
        """
        message = {
            "type": "market_data",
            "symbol": symbol,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_position_update(self, position: dict):
        """
        Broadcast position update.
        
        Args:
            position: Position dictionary
            
        Validates: Requirement 11.9
        """
        message = {
            "type": "position_update",
            "position": position,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_strategy_performance_update(self, strategy_id: str, performance: dict):
        """
        Broadcast strategy performance update.
        
        Args:
            strategy_id: Strategy ID
            performance: Performance metrics dictionary
            
        Validates: Requirement 11.9
        """
        message = {
            "type": "strategy_performance",
            "strategy_id": strategy_id,
            "performance": performance,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_error_notification(self, error: dict):
        """
        Broadcast error notification.
        
        Args:
            error: Error dictionary with severity, title, message
            
        Validates: Requirement 11.9
        """
        message = {
            "type": "error",
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_system_state_change(self, state: dict):
        """
        Broadcast system state change.
        
        Args:
            state: System state dictionary
            
        Validates: Requirements 11.12, 16.11
        """
        message = {
            "type": "system_state",
            "state": state,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_order_update(self, order: dict):
        """
        Broadcast order status update.
        
        Args:
            order: Order dictionary
        """
        message = {
            "type": "order_update",
            "order": order,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_strategy_update(self, strategy: dict):
        """
        Broadcast strategy update (creation, activation, deactivation, retirement).
        
        Args:
            strategy: Strategy dictionary with id, name, status, and other fields
            
        Validates: Requirement 5.2 (WebSocket broadcasting of strategy updates)
        """
        message = {
            "type": "strategy_update",
            "strategy": strategy,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted strategy update: {strategy.get('id', 'unknown')[:8]}... status={strategy.get('status')}")
    
    async def broadcast_signal_generated(self, signal: dict):
        """
        Broadcast trading signal generation event.
        
        Args:
            signal: Trading signal dictionary with strategy_id, symbol, action, confidence, reasoning
            
        Validates: Requirement 8.7 (Real-time signal feed with reasoning)
        """
        message = {
            "type": "signal_generated",
            "signal": signal,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted signal: {signal.get('symbol')} {signal.get('action')} confidence={signal.get('confidence', 0):.2f}")
    
    async def broadcast_backtest_progress(self, strategy_id: str, progress: dict):
        """
        Broadcast backtest progress update.
        
        Args:
            strategy_id: Strategy ID being backtested
            progress: Progress dictionary with percent_complete, current_date, signals_generated, preliminary_metrics
            
        Validates: Requirement 8.5 (Backtest progress visualization)
        """
        message = {
            "type": "backtest_progress",
            "strategy_id": strategy_id,
            "progress": progress,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.debug(f"Broadcasted backtest progress: {strategy_id[:8]}... {progress.get('percent_complete', 0):.1f}%")
    
    async def broadcast_autonomous_status_update(self, status: dict):
        """
        Broadcast autonomous system status update.
        
        Args:
            status: Autonomous system status dictionary
            
        Validates: Requirement 7.1 (Real-time autonomous status updates)
        """
        message = {
            "channel": "autonomous:status",
            "event": "status_update",
            "data": status,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.debug(f"Broadcasted autonomous status update: enabled={status.get('enabled')}, regime={status.get('market_regime')}")
    
    async def broadcast_autonomous_cycle_event(self, event_type: str, data: dict):
        """
        Broadcast autonomous cycle event.
        
        Args:
            event_type: Event type (cycle_started, cycle_completed, cycle_progress)
            data: Event data dictionary
            
        Validates: Requirement 7.2 (Real-time cycle progress updates)
        """
        message = {
            "channel": "autonomous:cycle",
            "event": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted autonomous cycle event: {event_type}")
    
    async def broadcast_autonomous_strategy_event(self, event_type: str, strategy: dict):
        """
        Broadcast autonomous strategy lifecycle event.
        
        Args:
            event_type: Event type (strategy_proposed, strategy_backtested, strategy_activated, strategy_retired)
            strategy: Strategy data dictionary
            
        Validates: Requirement 7.2 (Real-time strategy lifecycle updates)
        """
        message = {
            "channel": "autonomous:strategies",
            "event": event_type,
            "data": strategy,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted autonomous strategy event: {event_type} for {strategy.get('name', 'unknown')}")
    
    async def broadcast_autonomous_notification(self, notification: dict):
        """
        Broadcast autonomous system notification.
        
        Args:
            notification: Notification dictionary with type, severity, title, message
            
        Validates: Requirement 7.3 (Real-time notifications for autonomous events)
        """
        message = {
            "channel": "autonomous:notifications",
            "event": "notification",
            "data": notification,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted autonomous notification: {notification.get('type')} - {notification.get('title')}")

    async def broadcast_cycle_progress(self, progress: dict):
        """
        Broadcast autonomous cycle progress event.

        Args:
            progress: Progress dictionary with stage, percent_complete, message
        """
        message = {
            "type": "cycle_progress",
            "data": progress,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.debug(f"Broadcasted cycle progress: {progress.get('stage')} {progress.get('percent_complete', 0):.0f}%")

    async def broadcast_fundamental_alert(self, alert: dict):
        """
        Broadcast fundamental alert triggered event.

        Args:
            alert: Alert dictionary with position_id, symbol, reason, details
        """
        message = {
            "type": "fundamental_alert",
            "data": alert,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        logger.info(f"Broadcasted fundamental alert: {alert.get('symbol')} - {alert.get('reason')}")

    
    def get_connection_count(self) -> int:
        """
        Get number of active connections.
        
        Returns:
            Number of active WebSocket connections
        """
        return len(self.active_connections)


# Global WebSocket manager instance
_ws_manager: WebSocketManager = None


def get_websocket_manager() -> WebSocketManager:
    """
    Get or create global WebSocket manager instance.
    
    Returns:
        WebSocketManager instance
    """
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
