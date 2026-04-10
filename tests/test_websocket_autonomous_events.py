"""
Test WebSocket event handlers for autonomous trading system.

Validates: Requirements 7.1, 7.2, 7.3
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.websocket_manager import WebSocketManager
from src.models.enums import StrategyStatus


@pytest.fixture
def ws_manager():
    """Create WebSocketManager instance."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestAutonomousStatusChannel:
    """Test autonomous:status channel events."""
    
    @pytest.mark.asyncio
    async def test_broadcast_autonomous_status_update(self, ws_manager, mock_websocket):
        """
        Test broadcasting autonomous status update.
        
        Validates: Requirement 7.1 (Real-time autonomous status updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast status update
        status = {
            "enabled": True,
            "market_regime": "TRENDING_UP",
            "last_run_time": datetime.now().isoformat(),
            "active_strategies_count": 5
        }
        
        await ws_manager.broadcast_autonomous_status_update(status)
        
        # Verify message was sent
        assert mock_websocket.send_json.call_count >= 2  # Welcome + status update
        
        # Get the status update call (last call)
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:status"
        assert message["event"] == "status_update"
        assert message["data"] == status
        assert "timestamp" in message


class TestAutonomousCycleChannel:
    """Test autonomous:cycle channel events."""
    
    @pytest.mark.asyncio
    async def test_broadcast_cycle_started(self, ws_manager, mock_websocket):
        """
        Test broadcasting cycle started event.
        
        Validates: Requirement 7.2 (Real-time cycle progress updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast cycle started
        data = {
            "cycle_id": "cycle_abc123",
            "estimated_duration": 2700,
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_cycle_event("cycle_started", data)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:cycle"
        assert message["event"] == "cycle_started"
        assert message["data"]["cycle_id"] == "cycle_abc123"
        assert message["data"]["estimated_duration"] == 2700
    
    @pytest.mark.asyncio
    async def test_broadcast_cycle_completed(self, ws_manager, mock_websocket):
        """
        Test broadcasting cycle completed event.
        
        Validates: Requirement 7.2 (Real-time cycle progress updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast cycle completed
        data = {
            "cycle_id": "cycle_abc123",
            "duration_seconds": 2450,
            "proposals_generated": 5,
            "proposals_backtested": 5,
            "strategies_activated": 2,
            "strategies_retired": 1,
            "errors_count": 0
        }
        
        await ws_manager.broadcast_autonomous_cycle_event("cycle_completed", data)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:cycle"
        assert message["event"] == "cycle_completed"
        assert message["data"]["strategies_activated"] == 2
        assert message["data"]["strategies_retired"] == 1


class TestAutonomousStrategiesChannel:
    """Test autonomous:strategies channel events."""
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_proposed(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy proposed event.
        
        Validates: Requirement 7.2 (Real-time strategy lifecycle updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast strategy proposed
        strategy = {
            "id": "strat_123",
            "name": "RSI Mean Reversion",
            "symbols": ["SPY", "QQQ"],
            "status": StrategyStatus.PROPOSED.value,
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_strategy_event("strategy_proposed", strategy)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:strategies"
        assert message["event"] == "strategy_proposed"
        assert message["data"]["name"] == "RSI Mean Reversion"
        assert message["data"]["status"] == StrategyStatus.PROPOSED.value
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_backtested(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy backtested event.
        
        Validates: Requirement 7.2 (Real-time strategy lifecycle updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast strategy backtested
        strategy = {
            "id": "strat_123",
            "name": "RSI Mean Reversion",
            "symbols": ["SPY", "QQQ"],
            "status": StrategyStatus.BACKTESTED.value,
            "backtest_results": {
                "sharpe_ratio": 1.85,
                "total_return": 0.243,
                "max_drawdown": 0.082,
                "win_rate": 0.625,
                "total_trades": 45
            },
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_strategy_event("strategy_backtested", strategy)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:strategies"
        assert message["event"] == "strategy_backtested"
        assert message["data"]["backtest_results"]["sharpe_ratio"] == 1.85
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_activated(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy activated event.
        
        Validates: Requirement 7.2 (Real-time strategy lifecycle updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast strategy activated
        strategy = {
            "id": "strat_123",
            "name": "RSI Mean Reversion",
            "symbols": ["SPY", "QQQ"],
            "status": StrategyStatus.DEMO.value,
            "backtest_results": {
                "sharpe_ratio": 1.85,
                "total_return": 0.243,
                "max_drawdown": 0.082,
                "win_rate": 0.625
            },
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_strategy_event("strategy_activated", strategy)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:strategies"
        assert message["event"] == "strategy_activated"
        assert message["data"]["status"] == StrategyStatus.DEMO.value
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_retired(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy retired event.
        
        Validates: Requirement 7.2 (Real-time strategy lifecycle updates)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast strategy retired
        strategy = {
            "id": "strat_123",
            "name": "RSI Mean Reversion",
            "symbols": ["SPY", "QQQ"],
            "status": StrategyStatus.RETIRED.value,
            "retirement_reason": "Sharpe ratio below threshold (0.42 < 0.5)",
            "final_metrics": {
                "sharpe_ratio": 0.42,
                "total_return": -0.082,
                "max_drawdown": 0.18
            },
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_strategy_event("strategy_retired", strategy)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:strategies"
        assert message["event"] == "strategy_retired"
        assert message["data"]["retirement_reason"] == "Sharpe ratio below threshold (0.42 < 0.5)"


class TestAutonomousNotificationsChannel:
    """Test autonomous:notifications channel events."""
    
    @pytest.mark.asyncio
    async def test_broadcast_cycle_started_notification(self, ws_manager, mock_websocket):
        """
        Test broadcasting cycle started notification.
        
        Validates: Requirement 7.3 (Real-time notifications for autonomous events)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast notification
        notification = {
            "type": "cycle_started",
            "severity": "info",
            "title": "Autonomous Cycle Started",
            "message": "Strategy proposal and evaluation cycle has begun",
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_notification(notification)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:notifications"
        assert message["event"] == "notification"
        assert message["data"]["type"] == "cycle_started"
        assert message["data"]["severity"] == "info"
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_activated_notification(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy activated notification.
        
        Validates: Requirement 7.3 (Real-time notifications for autonomous events)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast notification
        notification = {
            "type": "strategy_activated",
            "severity": "success",
            "title": "Strategy Activated",
            "message": "RSI Mean Reversion activated with Sharpe 1.85",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "strategy_id": "strat_123",
                "strategy_name": "RSI Mean Reversion"
            }
        }
        
        await ws_manager.broadcast_autonomous_notification(notification)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:notifications"
        assert message["event"] == "notification"
        assert message["data"]["type"] == "strategy_activated"
        assert message["data"]["severity"] == "success"
        assert "strategy_id" in message["data"]["data"]
    
    @pytest.mark.asyncio
    async def test_broadcast_strategy_retired_notification(self, ws_manager, mock_websocket):
        """
        Test broadcasting strategy retired notification.
        
        Validates: Requirement 7.3 (Real-time notifications for autonomous events)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast notification
        notification = {
            "type": "strategy_retired",
            "severity": "warning",
            "title": "Strategy Retired",
            "message": "RSI Mean Reversion retired: Sharpe ratio below threshold",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "strategy_id": "strat_123",
                "strategy_name": "RSI Mean Reversion",
                "reason": "Sharpe ratio below threshold (0.42 < 0.5)"
            }
        }
        
        await ws_manager.broadcast_autonomous_notification(notification)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:notifications"
        assert message["event"] == "notification"
        assert message["data"]["type"] == "strategy_retired"
        assert message["data"]["severity"] == "warning"
    
    @pytest.mark.asyncio
    async def test_broadcast_cycle_error_notification(self, ws_manager, mock_websocket):
        """
        Test broadcasting cycle error notification.
        
        Validates: Requirement 7.3 (Real-time notifications for autonomous events)
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Broadcast notification
        notification = {
            "type": "cycle_error",
            "severity": "error",
            "title": "Autonomous Cycle Error",
            "message": "Fatal error in cycle: Database connection failed",
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_notification(notification)
        
        # Verify message was sent
        last_call = mock_websocket.send_json.call_args_list[-1]
        message = last_call[0][0]
        
        assert message["channel"] == "autonomous:notifications"
        assert message["event"] == "notification"
        assert message["data"]["type"] == "cycle_error"
        assert message["data"]["severity"] == "error"


class TestMultipleClients:
    """Test broadcasting to multiple connected clients."""
    
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, ws_manager):
        """
        Test that events are broadcast to all connected clients.
        
        Validates: Requirements 7.1, 7.2, 7.3
        """
        # Connect multiple clients
        clients = []
        for i in range(3):
            ws = AsyncMock()
            ws.send_json = AsyncMock()
            session_id = f"session_{i}"
            await ws_manager.connect(ws, session_id)
            clients.append(ws)
        
        # Broadcast a notification
        notification = {
            "type": "cycle_started",
            "severity": "info",
            "title": "Test",
            "message": "Test message",
            "timestamp": datetime.now().isoformat()
        }
        
        await ws_manager.broadcast_autonomous_notification(notification)
        
        # Verify all clients received the message
        for ws in clients:
            assert ws.send_json.call_count >= 2  # Welcome + notification
            last_call = ws.send_json.call_args_list[-1]
            message = last_call[0][0]
            assert message["channel"] == "autonomous:notifications"
            assert message["data"]["type"] == "cycle_started"


class TestEventStructure:
    """Test that event messages have correct structure."""
    
    @pytest.mark.asyncio
    async def test_event_has_required_fields(self, ws_manager, mock_websocket):
        """
        Test that all events have required fields: channel, event, data, timestamp.
        
        Validates: Requirements 7.1, 7.2, 7.3
        """
        # Connect a client
        session_id = "test_session_123"
        await ws_manager.connect(mock_websocket, session_id)
        
        # Test status update
        await ws_manager.broadcast_autonomous_status_update({"enabled": True})
        message = mock_websocket.send_json.call_args_list[-1][0][0]
        assert "channel" in message
        assert "event" in message
        assert "data" in message
        assert "timestamp" in message
        
        # Test cycle event
        await ws_manager.broadcast_autonomous_cycle_event("cycle_started", {"cycle_id": "123"})
        message = mock_websocket.send_json.call_args_list[-1][0][0]
        assert "channel" in message
        assert "event" in message
        assert "data" in message
        assert "timestamp" in message
        
        # Test strategy event
        await ws_manager.broadcast_autonomous_strategy_event("strategy_proposed", {"id": "123"})
        message = mock_websocket.send_json.call_args_list[-1][0][0]
        assert "channel" in message
        assert "event" in message
        assert "data" in message
        assert "timestamp" in message
        
        # Test notification
        await ws_manager.broadcast_autonomous_notification({"type": "test", "severity": "info"})
        message = mock_websocket.send_json.call_args_list[-1][0][0]
        assert "channel" in message
        assert "event" in message
        assert "data" in message
        assert "timestamp" in message
