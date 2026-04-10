"""
Critical error notification system for AlphaCent.

This module provides a notification system that:
- Sends critical errors to Dashboard via WebSocket
- Includes error details and suggested actions
- Supports different notification severities
- Queues notifications when WebSocket unavailable
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from queue import Queue
import threading

from src.core.logging_config import LogComponent, get_logger


logger = get_logger(LogComponent.SYSTEM)


class NotificationSeverity(Enum):
    """Severity levels for notifications."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Notification:
    """Notification data structure."""
    severity: NotificationSeverity
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    component: Optional[str] = None
    suggested_actions: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    notification_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary for JSON serialization."""
        data = asdict(self)
        data['severity'] = self.severity.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


class NotificationSystem:
    """
    Centralized notification system for critical errors and alerts.
    
    Sends notifications to connected Dashboard clients via WebSocket.
    Queues notifications when no clients connected.
    """
    
    def __init__(self, max_queue_size: int = 100):
        """
        Initialize notification system.
        
        Args:
            max_queue_size: Maximum number of queued notifications
        """
        self._websocket_handlers: Set[Callable] = set()
        self._notification_queue: Queue = Queue(maxsize=max_queue_size)
        self._notification_history: List[Notification] = []
        self._max_history_size = 1000
        self._lock = threading.Lock()
        
        logger.info("Notification system initialized", context={"max_queue_size": max_queue_size})
    
    def register_websocket_handler(self, handler: Callable):
        """
        Register a WebSocket handler for sending notifications.
        
        Args:
            handler: Async function that sends notification to WebSocket clients
        """
        with self._lock:
            self._websocket_handlers.add(handler)
            logger.info("WebSocket handler registered", context={"handler_count": len(self._websocket_handlers)})
            
            # Send queued notifications
            self._flush_queue()
    
    def unregister_websocket_handler(self, handler: Callable):
        """
        Unregister a WebSocket handler.
        
        Args:
            handler: Handler to remove
        """
        with self._lock:
            self._websocket_handlers.discard(handler)
            logger.info("WebSocket handler unregistered", context={"handler_count": len(self._websocket_handlers)})
    
    def send_notification(
        self,
        severity: NotificationSeverity,
        title: str,
        message: str,
        component: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send notification to Dashboard.
        
        Args:
            severity: Notification severity level
            title: Short notification title
            message: Detailed notification message
            component: Component that generated the notification
            suggested_actions: List of suggested actions for user
            context: Additional context information
        """
        notification = Notification(
            severity=severity,
            title=title,
            message=message,
            component=component,
            suggested_actions=suggested_actions or [],
            context=context or {},
            notification_id=self._generate_notification_id()
        )
        
        # Add to history
        self._add_to_history(notification)
        
        # Log notification
        log_context = {
            "severity": severity.value,
            "title": title,
            "component": component
        }
        
        if severity == NotificationSeverity.CRITICAL:
            logger.critical(f"Critical notification: {title} - {message}", context=log_context)
        elif severity == NotificationSeverity.ERROR:
            logger.error(f"Error notification: {title} - {message}", context=log_context)
        elif severity == NotificationSeverity.WARNING:
            logger.warning(f"Warning notification: {title} - {message}", context=log_context)
        else:
            logger.info(f"Info notification: {title} - {message}", context=log_context)
        
        # Send to WebSocket handlers or queue
        with self._lock:
            if self._websocket_handlers:
                self._send_to_handlers(notification)
            else:
                self._queue_notification(notification)
    
    def send_critical_error(
        self,
        title: str,
        message: str,
        component: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send critical error notification.
        
        Args:
            title: Short error title
            message: Detailed error message
            component: Component that generated the error
            suggested_actions: List of suggested actions for user
            context: Additional context information
        """
        self.send_notification(
            severity=NotificationSeverity.CRITICAL,
            title=title,
            message=message,
            component=component,
            suggested_actions=suggested_actions,
            context=context
        )
    
    def send_error(
        self,
        title: str,
        message: str,
        component: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send error notification.
        
        Args:
            title: Short error title
            message: Detailed error message
            component: Component that generated the error
            suggested_actions: List of suggested actions for user
            context: Additional context information
        """
        self.send_notification(
            severity=NotificationSeverity.ERROR,
            title=title,
            message=message,
            component=component,
            suggested_actions=suggested_actions,
            context=context
        )
    
    def send_warning(
        self,
        title: str,
        message: str,
        component: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send warning notification.
        
        Args:
            title: Short warning title
            message: Detailed warning message
            component: Component that generated the warning
            suggested_actions: List of suggested actions for user
            context: Additional context information
        """
        self.send_notification(
            severity=NotificationSeverity.WARNING,
            title=title,
            message=message,
            component=component,
            suggested_actions=suggested_actions,
            context=context
        )
    
    def send_info(
        self,
        title: str,
        message: str,
        component: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send info notification.
        
        Args:
            title: Short info title
            message: Detailed info message
            component: Component that generated the info
            context: Additional context information
        """
        self.send_notification(
            severity=NotificationSeverity.INFO,
            title=title,
            message=message,
            component=component,
            context=context
        )
    
    def get_notification_history(
        self,
        severity: Optional[NotificationSeverity] = None,
        limit: int = 100
    ) -> List[Notification]:
        """
        Get notification history.
        
        Args:
            severity: Filter by severity (None for all)
            limit: Maximum number of notifications to return
            
        Returns:
            List of notifications
        """
        with self._lock:
            notifications = self._notification_history
            
            if severity:
                notifications = [n for n in notifications if n.severity == severity]
            
            return notifications[-limit:]
    
    def clear_history(self):
        """Clear notification history."""
        with self._lock:
            self._notification_history.clear()
            logger.info("Notification history cleared")
    
    def _send_to_handlers(self, notification: Notification):
        """Send notification to all registered handlers."""
        notification_data = notification.to_dict()
        
        for handler in self._websocket_handlers:
            try:
                # Call handler (should be async)
                handler(notification_data)
            except Exception as e:
                logger.error(
                    f"Error sending notification to handler: {e}",
                    context={"notification_id": notification.notification_id},
                    exc_info=True
                )
    
    def _queue_notification(self, notification: Notification):
        """Queue notification when no handlers available."""
        try:
            self._notification_queue.put_nowait(notification)
            logger.warning(
                "Notification queued (no WebSocket handlers)",
                context={"notification_id": notification.notification_id}
            )
        except Exception as e:
            logger.error(
                f"Failed to queue notification: {e}",
                context={"notification_id": notification.notification_id}
            )
    
    def _flush_queue(self):
        """Send all queued notifications to handlers."""
        count = 0
        while not self._notification_queue.empty():
            try:
                notification = self._notification_queue.get_nowait()
                self._send_to_handlers(notification)
                count += 1
            except Exception as e:
                logger.error(f"Error flushing notification queue: {e}", exc_info=True)
                break
        
        if count > 0:
            logger.info(f"Flushed {count} queued notifications")
    
    def _add_to_history(self, notification: Notification):
        """Add notification to history."""
        with self._lock:
            self._notification_history.append(notification)
            
            # Trim history if too large
            if len(self._notification_history) > self._max_history_size:
                self._notification_history = self._notification_history[-self._max_history_size:]
    
    def _generate_notification_id(self) -> str:
        """Generate unique notification ID."""
        import uuid
        return str(uuid.uuid4())


# Global notification system instance
_notification_system: Optional[NotificationSystem] = None


def get_notification_system() -> NotificationSystem:
    """
    Get global notification system instance.
    
    Returns:
        NotificationSystem instance
    """
    global _notification_system
    if _notification_system is None:
        _notification_system = NotificationSystem()
    return _notification_system


def send_critical_error(
    title: str,
    message: str,
    component: Optional[str] = None,
    suggested_actions: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None
):
    """
    Convenience function to send critical error notification.
    
    Args:
        title: Short error title
        message: Detailed error message
        component: Component that generated the error
        suggested_actions: List of suggested actions for user
        context: Additional context information
    """
    get_notification_system().send_critical_error(
        title=title,
        message=message,
        component=component,
        suggested_actions=suggested_actions,
        context=context
    )
