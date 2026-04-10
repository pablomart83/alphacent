"""
WebSocket endpoint for real-time updates.

Provides WebSocket connection for pushing real-time updates to clients.
Validates: Requirements 11.9, 11.12, 16.11
"""

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from src.api.websocket_manager import get_websocket_manager
from src.api.dependencies import get_auth_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time updates.
    
    Clients connect with their session ID and receive real-time updates for:
    - Market data updates
    - Position updates on fills
    - Strategy performance updates
    - Error notifications
    - System state changes
    
    Args:
        websocket: WebSocket connection
        session_id: User session ID for authentication
        
    Validates: Requirements 11.9, 11.12, 16.11
    """
    ws_manager = get_websocket_manager()
    auth_manager = get_auth_manager()
    
    # Validate session
    if not session_id:
        logger.warning("WebSocket connection attempt without session ID")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    if not auth_manager.validate_session(session_id):
        logger.warning(f"WebSocket connection attempt with invalid session: {session_id[:8]}...")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Get username
    username = auth_manager.get_session_user(session_id)
    logger.info(f"WebSocket connection from user: {username}")
    
    # Accept connection
    await ws_manager.connect(websocket, session_id)
    
    try:
        # Keep connection alive and handle incoming messages
        while True:
            # Receive messages from client (mostly for keepalive)
            data = await websocket.receive_text()
            
            # Handle ping/pong for keepalive
            if data == "ping":
                await websocket.send_text("pong")
            
            # Validate session is still active
            if not auth_manager.validate_session(session_id):
                logger.info(f"Session expired for WebSocket: {session_id[:8]}...")
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user {username}")
        ws_manager.disconnect(session_id)
    
    except Exception as e:
        logger.error(f"WebSocket error for user {username}: {e}")
        ws_manager.disconnect(session_id)
