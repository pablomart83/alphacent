"""
Authentication endpoints for AlphaCent Trading Platform.

Provides user login, logout, and session validation endpoints.
Validates: Requirements 18.1, 18.3
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.core.auth import AuthenticationManager
from src.api.dependencies import get_auth_manager, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response model."""
    success: bool
    message: str
    username: Optional[str] = None


class LogoutResponse(BaseModel):
    """Logout response model."""
    success: bool
    message: str


class SessionStatusResponse(BaseModel):
    """Session status response model."""
    authenticated: bool
    username: Optional[str] = None


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """
    User login endpoint.
    
    Creates a new session and sets session cookie.
    
    Args:
        request: Login credentials
        response: FastAPI response (for setting cookie)
        auth_manager: Authentication manager dependency
        
    Returns:
        Login response with success status
        
    Validates: Requirements 18.1, 18.3
    """
    logger.info(f"Login attempt for user: {request.username}")
    
    # Authenticate user
    session_id = auth_manager.authenticate(request.username, request.password)
    
    if not session_id:
        logger.warning(f"Login failed for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Set session cookie (httponly=False so JavaScript can read it for WebSocket)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=False,  # Allow JavaScript to read for WebSocket connection
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=30 * 60  # 30 minutes
    )
    
    logger.info(f"Login successful for user: {request.username}")
    
    return LoginResponse(
        success=True,
        message="Login successful",
        username=request.username
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    username: str = Depends(get_current_user),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """
    User logout endpoint.
    
    Removes session and clears session cookie.
    
    Args:
        response: FastAPI response (for clearing cookie)
        username: Current authenticated user
        auth_manager: Authentication manager dependency
        
    Returns:
        Logout response with success status
        
    Validates: Requirement 18.3
    """
    logger.info(f"Logout request for user: {username}")
    
    # Get session ID from request (set by middleware)
    # Note: In a real implementation, we'd get this from request.state
    # For now, we'll find the session by username
    sessions = [
        sid for sid, session in auth_manager.sessions.items()
        if session.username == username
    ]
    
    # Logout all user sessions
    for session_id in sessions:
        auth_manager.logout(session_id)
    
    # Clear session cookie
    response.delete_cookie(key="session_id")
    
    logger.info(f"Logout successful for user: {username}")
    
    return LogoutResponse(
        success=True,
        message="Logout successful"
    )


@router.get("/status", response_model=SessionStatusResponse)
async def session_status(
    request: Request,
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """
    Session validation endpoint.
    
    Checks if current session is valid without requiring authentication.
    Returns authenticated status and username if logged in.
    
    Args:
        request: FastAPI request
        auth_manager: Authentication manager
        
    Returns:
        Session status with username if authenticated
        
    Validates: Requirement 18.3
    """
    # Check if user is authenticated by validating session cookie
    session_id = request.cookies.get("session_id")
    
    if session_id and auth_manager.validate_session(session_id):
        username = auth_manager.get_session_user(session_id)
        return SessionStatusResponse(
            authenticated=True,
            username=username
        )
    
    return SessionStatusResponse(
        authenticated=False,
        username=None
    )
