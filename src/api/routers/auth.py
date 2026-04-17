"""
Authentication and user management endpoints for AlphaCent Trading Platform.

Provides login, logout, session validation, password change, and user CRUD.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.core.auth import AuthenticationManager, ROLE_PERMISSIONS
from src.api.dependencies import get_auth_manager, get_current_user, require_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# --- Request/Response Models ---

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

class LoginResponse(BaseModel):
    success: bool
    message: str
    username: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[dict] = None

class LogoutResponse(BaseModel):
    success: bool
    message: str

class SessionStatusResponse(BaseModel):
    authenticated: bool
    username: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[dict] = None

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)
    role: str = Field(default="viewer")

class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    permissions: Optional[dict] = None
    is_active: Optional[bool] = None

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


# --- Auth Endpoints ---

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """User login — creates session and sets cookie."""
    logger.info(f"Login attempt for user: {request.username}")

    session_id = auth_manager.authenticate(request.username, request.password)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=8 * 60 * 60,  # 8 hours
    )

    session = auth_manager.sessions.get(session_id)
    logger.info(f"Login successful for user: {request.username}")

    return LoginResponse(
        success=True,
        message="Login successful",
        username=request.username,
        role=session.role if session else None,
        permissions=session.permissions if session else None,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    username: str = Depends(get_current_user),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """User logout — removes session and clears cookie."""
    sessions = [sid for sid, s in auth_manager.sessions.items() if s.username == username]
    for session_id in sessions:
        auth_manager.logout(session_id)

    response.delete_cookie(key="session_id")
    logger.info(f"Logout successful for user: {username}")
    return LogoutResponse(success=True, message="Logout successful")


@router.get("/status", response_model=SessionStatusResponse)
async def session_status(
    request: Request,
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Check if current session is valid. Returns role and permissions."""
    session_id = request.cookies.get("session_id")

    if session_id and auth_manager.validate_session(session_id):
        session = auth_manager.sessions.get(session_id)
        if session:
            return SessionStatusResponse(
                authenticated=True,
                username=session.username,
                role=session.role,
                permissions=session.permissions,
            )

    return SessionStatusResponse(authenticated=False)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    username: str = Depends(get_current_user),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Change own password. Requires current password."""
    try:
        auth_manager.change_password(username, request.old_password, request.new_password)
        return {"success": True, "message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/me")
async def get_current_user_info(
    request: Request,
    username: str = Depends(get_current_user),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Get current user's profile info."""
    user = auth_manager.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# --- User Management Endpoints (admin only) ---

@router.get("/users")
async def list_users(
    username: str = Depends(require_action("manage_users")),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """List all users. Admin only."""
    return {"users": auth_manager.list_users()}


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    username: str = Depends(require_action("manage_users")),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Create a new user. Admin only."""
    try:
        user = auth_manager.create_user(
            username=request.username,
            password=request.password,
            role=request.role,
            created_by=username,
        )
        return {"success": True, "message": f"User '{request.username}' created", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/users/{target_username}")
async def update_user(
    target_username: str,
    request: UpdateUserRequest,
    username: str = Depends(require_action("manage_users")),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Update user role/permissions/active status. Admin only."""
    try:
        user = auth_manager.update_user(
            username=target_username,
            role=request.role,
            permissions=request.permissions,
            is_active=request.is_active,
            admin_username=username,
        )
        return {"success": True, "message": f"User '{target_username}' updated", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/users/{target_username}")
async def delete_user(
    target_username: str,
    username: str = Depends(require_action("manage_users")),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Delete a user. Admin only. Cannot delete yourself."""
    try:
        auth_manager.delete_user(target_username, admin_username=username)
        return {"success": True, "message": f"User '{target_username}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/users/{target_username}/reset-password")
async def reset_user_password(
    target_username: str,
    request: ResetPasswordRequest,
    username: str = Depends(require_action("manage_users")),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Reset another user's password. Admin only."""
    try:
        auth_manager.reset_password(target_username, request.new_password, admin_username=username)
        return {"success": True, "message": f"Password reset for '{target_username}'"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/roles")
async def get_roles(
    username: str = Depends(get_current_user),
    auth_manager: AuthenticationManager = Depends(get_auth_manager)
):
    """Get available roles and their default permissions."""
    return {"roles": auth_manager.get_role_permissions()}
