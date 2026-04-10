"""Unit tests for critical error notification system."""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.core.notification_system import (
    Notification,
    NotificationSeverity,
    NotificationSystem,
    get_notification_system,
    send_critical_error
)


@pytest.fixture
def notification_system():
    """Create fresh notification system for each test."""
    return NotificationSystem()


def test_notification_creation():
    """Test notification data structure."""
    notification = Notification(
        severity=NotificationSeverity.CRITICAL,
        title="Test Error",
        message="This is a test error",
        component="test_component",
        suggested_actions=["Action 1", "Action 2"],
        context={"key": "value"}
    )
    
    assert notification.severity == NotificationSeverity.CRITICAL
    assert notification.title == "Test Error"
    assert notification.message == "This is a test error"
    assert notification.component == "test_component"
    assert len(notification.suggested_actions) == 2
    assert notification.context["key"] == "value"
    assert isinstance(notification.timestamp, datetime)


def test_notification_to_dict():
    """Test notification serialization to dictionary."""
    notification = Notification(
        severity=NotificationSeverity.ERROR,
        title="Test",
        message="Test message"
    )
    
    data = notification.to_dict()
    
    assert data["severity"] == "error"
    assert data["title"] == "Test"
    assert data["message"] == "Test message"
    assert "timestamp" in data
    assert isinstance(data["timestamp"], str)


def test_send_notification_with_handler(notification_system):
    """Test sending notification with registered handler."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_notification(
        severity=NotificationSeverity.CRITICAL,
        title="Critical Error",
        message="Something went wrong"
    )
    
    # Handler should be called
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "critical"
    assert call_args["title"] == "Critical Error"


def test_send_notification_without_handler_queues(notification_system):
    """Test notification is queued when no handler registered."""
    notification_system.send_notification(
        severity=NotificationSeverity.ERROR,
        title="Error",
        message="Test error"
    )
    
    # Notification should be queued
    assert not notification_system._notification_queue.empty()


def test_flush_queue_on_handler_registration(notification_system):
    """Test queued notifications are sent when handler registered."""
    # Send notification without handler (will be queued)
    notification_system.send_notification(
        severity=NotificationSeverity.WARNING,
        title="Warning",
        message="Test warning"
    )
    
    assert not notification_system._notification_queue.empty()
    
    # Register handler
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    # Queue should be flushed
    assert notification_system._notification_queue.empty()
    assert handler.call_count == 1


def test_send_critical_error_method(notification_system):
    """Test send_critical_error convenience method."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_critical_error(
        title="Critical Error",
        message="System failure",
        component="system",
        suggested_actions=["Restart system", "Check logs"],
        context={"error_code": 500}
    )
    
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "critical"
    assert call_args["component"] == "system"
    assert len(call_args["suggested_actions"]) == 2
    assert call_args["context"]["error_code"] == 500


def test_send_error_method(notification_system):
    """Test send_error convenience method."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error(
        title="Error",
        message="Operation failed"
    )
    
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "error"


def test_send_warning_method(notification_system):
    """Test send_warning convenience method."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_warning(
        title="Warning",
        message="Low disk space"
    )
    
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "warning"


def test_send_info_method(notification_system):
    """Test send_info convenience method."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_info(
        title="Info",
        message="System started"
    )
    
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "info"


def test_notification_history(notification_system):
    """Test notification history is maintained."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error("Error 1", "Message 1")
    notification_system.send_warning("Warning 1", "Message 2")
    notification_system.send_critical_error("Critical 1", "Message 3")
    
    history = notification_system.get_notification_history()
    
    assert len(history) == 3
    assert history[0].title == "Error 1"
    assert history[1].title == "Warning 1"
    assert history[2].title == "Critical 1"


def test_notification_history_filter_by_severity(notification_system):
    """Test filtering notification history by severity."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error("Error 1", "Message 1")
    notification_system.send_warning("Warning 1", "Message 2")
    notification_system.send_critical_error("Critical 1", "Message 3")
    notification_system.send_error("Error 2", "Message 4")
    
    critical_history = notification_system.get_notification_history(
        severity=NotificationSeverity.CRITICAL
    )
    
    assert len(critical_history) == 1
    assert critical_history[0].title == "Critical 1"
    
    error_history = notification_system.get_notification_history(
        severity=NotificationSeverity.ERROR
    )
    
    assert len(error_history) == 2


def test_notification_history_limit(notification_system):
    """Test notification history respects limit."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    for i in range(10):
        notification_system.send_info(f"Info {i}", f"Message {i}")
    
    history = notification_system.get_notification_history(limit=5)
    
    assert len(history) == 5
    assert history[-1].title == "Info 9"


def test_clear_history(notification_system):
    """Test clearing notification history."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error("Error", "Message")
    notification_system.send_warning("Warning", "Message")
    
    assert len(notification_system.get_notification_history()) == 2
    
    notification_system.clear_history()
    
    assert len(notification_system.get_notification_history()) == 0


def test_multiple_handlers(notification_system):
    """Test notification sent to multiple handlers."""
    handler1 = Mock()
    handler2 = Mock()
    
    notification_system.register_websocket_handler(handler1)
    notification_system.register_websocket_handler(handler2)
    
    notification_system.send_critical_error("Error", "Message")
    
    assert handler1.call_count == 1
    assert handler2.call_count == 1


def test_unregister_handler(notification_system):
    """Test unregistering handler."""
    handler = Mock()
    
    notification_system.register_websocket_handler(handler)
    notification_system.send_info("Info 1", "Message 1")
    
    assert handler.call_count == 1
    
    notification_system.unregister_websocket_handler(handler)
    notification_system.send_info("Info 2", "Message 2")
    
    # Handler should not be called again
    assert handler.call_count == 1


def test_handler_error_does_not_crash_system(notification_system):
    """Test that handler errors don't crash notification system."""
    def failing_handler(data):
        raise Exception("Handler error")
    
    notification_system.register_websocket_handler(failing_handler)
    
    # Should not raise exception
    notification_system.send_critical_error("Error", "Message")
    
    # Notification should still be in history
    history = notification_system.get_notification_history()
    assert len(history) == 1


def test_notification_id_generated(notification_system):
    """Test notification ID is generated."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error("Error", "Message")
    
    call_args = handler.call_args[0][0]
    assert "notification_id" in call_args
    assert call_args["notification_id"] is not None


def test_get_global_notification_system():
    """Test getting global notification system instance."""
    system1 = get_notification_system()
    system2 = get_notification_system()
    
    # Should return same instance
    assert system1 is system2


def test_send_critical_error_convenience_function():
    """Test global send_critical_error convenience function."""
    system = get_notification_system()
    handler = Mock()
    system.register_websocket_handler(handler)
    
    send_critical_error(
        title="Critical Error",
        message="System failure",
        component="test"
    )
    
    assert handler.call_count == 1
    call_args = handler.call_args[0][0]
    assert call_args["severity"] == "critical"
    assert call_args["title"] == "Critical Error"


def test_suggested_actions_included(notification_system):
    """Test suggested actions are included in notification."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_critical_error(
        title="API Error",
        message="eToro API connection failed",
        suggested_actions=[
            "Check internet connection",
            "Verify API credentials",
            "Check eToro service status"
        ]
    )
    
    call_args = handler.call_args[0][0]
    assert len(call_args["suggested_actions"]) == 3
    assert "Check internet connection" in call_args["suggested_actions"]


def test_context_included(notification_system):
    """Test context information is included in notification."""
    handler = Mock()
    notification_system.register_websocket_handler(handler)
    
    notification_system.send_error(
        title="Order Failed",
        message="Order submission failed",
        context={
            "order_id": "12345",
            "symbol": "AAPL",
            "error_code": "RATE_LIMIT"
        }
    )
    
    call_args = handler.call_args[0][0]
    assert call_args["context"]["order_id"] == "12345"
    assert call_args["context"]["symbol"] == "AAPL"
    assert call_args["context"]["error_code"] == "RATE_LIMIT"
