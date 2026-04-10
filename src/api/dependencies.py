"""
FastAPI dependencies for dependency injection.

Provides reusable dependencies for authentication, database, services, etc.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.core.auth import AuthenticationManager, SessionManager
from src.core.config import Configuration, get_config
from src.api.websocket_manager import WebSocketManager, get_websocket_manager
from src.models.database import get_database

logger = logging.getLogger(__name__)


# Global instances (will be initialized in app startup)
_auth_manager: Optional[AuthenticationManager] = None
_session_manager: Optional[SessionManager] = None


def init_dependencies(
    auth_manager: AuthenticationManager,
    session_manager: SessionManager
):
    """
    Initialize global dependency instances.
    
    Should be called during app startup.
    
    Args:
        auth_manager: AuthenticationManager instance
        session_manager: SessionManager instance
    """
    global _auth_manager, _session_manager
    _auth_manager = auth_manager
    _session_manager = session_manager
    logger.info("Dependencies initialized")


def get_auth_manager() -> AuthenticationManager:
    """
    Get AuthenticationManager dependency.
    
    Returns:
        AuthenticationManager instance
        
    Raises:
        HTTPException: If not initialized
    """
    if _auth_manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication manager not initialized"
        )
    return _auth_manager


def get_session_manager() -> SessionManager:
    """
    Get SessionManager dependency.
    
    Returns:
        SessionManager instance
        
    Raises:
        HTTPException: If not initialized
    """
    if _session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session manager not initialized"
        )
    return _session_manager


def get_configuration() -> Configuration:
    """
    Get Configuration dependency.
    
    Returns:
        Configuration instance
    """
    return get_config()


def get_ws_manager() -> WebSocketManager:
    """
    Get WebSocketManager dependency.
    
    Returns:
        WebSocketManager instance
    """
    return get_websocket_manager()


def get_current_user(request: Request) -> str:
    """
    Get current authenticated user from request state.
    
    Args:
        request: FastAPI request
        
    Returns:
        Username of authenticated user
        
    Raises:
        HTTPException: If user not authenticated
    """
    username = getattr(request.state, "username", None)
    
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return username


def get_session_id(request: Request) -> str:
    """
    Get session ID from request state.
    
    Args:
        request: FastAPI request
        
    Returns:
        Session ID
        
    Raises:
        HTTPException: If session not found
    """
    session_id = getattr(request.state, "session_id", None)
    
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session"
        )
    
    return session_id


def get_db_session():
    """
    Get database session for request.
    
    Yields:
        SQLAlchemy session
    """
    db = get_database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
