"""
Middleware for FastAPI application.

Provides authentication and session validation middleware.
"""

import logging
from typing import Callable, Optional

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.auth import AuthenticationManager

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for session-based authentication.
    
    Validates session on each request and adds user info to request state.
    Validates: Requirements 18.3, 18.4
    """
    
    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/auth/login",
        "/auth/status",
        "/config",
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with authentication check.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response from handler or authentication error
        """
        # Debug logging
        logger.info(f"Middleware processing: {request.method} {request.url.path}")
        
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            logger.info("Skipping auth for OPTIONS request")
            return await call_next(request)
        
        # Skip authentication for public paths
        if request.url.path in self.PUBLIC_PATHS or request.url.path.startswith("/docs"):
            logger.info(f"Skipping auth for public path: {request.url.path}")
            return await call_next(request)
        
        # Get auth manager from dependencies
        from src.api.dependencies import get_auth_manager
        try:
            auth_manager = get_auth_manager()
        except HTTPException:
            logger.error("Auth manager not initialized")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Authentication system not ready"},
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                }
            )
        
        # Get session ID from cookie
        session_id = request.cookies.get("session_id")
        
        if not session_id:
            logger.warning(f"No session cookie for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                }
            )
        
        # Validate session
        if not auth_manager.validate_session(session_id):
            logger.warning(f"Invalid session for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Session expired or invalid"},
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                }
            )
        
        # Get username and add to request state
        username = auth_manager.get_session_user(session_id)
        request.state.username = username
        request.state.session_id = session_id
        
        # Process request
        response = await call_next(request)
        
        return response


def get_current_user(request: Request) -> str:
    """
    Get current authenticated user from request.
    
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
    Get session ID from request.
    
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
