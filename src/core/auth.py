"""
Authentication module for AlphaCent Trading Platform.

DB-backed user management with bcrypt password hashing and in-memory session management.
Users persist across restarts. Sessions are ephemeral (in-memory).
"""

import bcrypt
import secrets
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default role permissions — defines what each role can access
ROLE_PERMISSIONS = {
    "admin": {
        "pages": ["overview", "portfolio", "orders", "strategies", "autonomous",
                  "risk", "analytics", "data", "watchlist", "settings"],
        "actions": ["trade", "configure", "manage_users", "manage_strategies",
                    "run_autonomous", "modify_risk", "close_positions", "view_all"],
    },
    "trader": {
        "pages": ["overview", "portfolio", "orders", "strategies", "autonomous",
                  "risk", "analytics", "data", "watchlist", "settings"],
        "actions": ["trade", "close_positions", "manage_strategies", "view_all"],
    },
    "viewer": {
        "pages": ["overview", "portfolio", "orders", "strategies", "risk", "analytics"],
        "actions": ["view_all"],
    },
}


@dataclass
class Session:
    """User session information."""
    session_id: str
    username: str
    role: str
    permissions: dict
    created_at: datetime
    last_activity: datetime
    expires_at: datetime


class AuthenticationManager:
    """
    DB-backed user authentication with bcrypt hashing and in-memory sessions.
    """

    def __init__(self, session_timeout_minutes: int = 30):
        self.sessions: Dict[str, Session] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self._db = None
        logger.info(f"AuthenticationManager initialized with {session_timeout_minutes}min timeout")

    def set_database(self, db):
        """Set database reference for DB-backed user management."""
        self._db = db
        logger.info("AuthenticationManager connected to database")

    def _get_db_session(self):
        """Get a DB session. Returns None if DB not available."""
        if self._db:
            return self._db.get_session()
        return None

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt(rounds=10)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against bcrypt hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    def ensure_admin_exists(self, default_password: str = "admin123"):
        """Create default admin user if no users exist in DB. Called at startup."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            logger.warning("No DB available — cannot ensure admin exists")
            return
        try:
            user_count = db_session.query(UserORM).count()
            if user_count == 0:
                admin = UserORM(
                    username="admin",
                    password_hash=self.hash_password(default_password),
                    role="admin",
                    permissions=ROLE_PERMISSIONS["admin"],
                    is_active=True,
                    created_at=datetime.now(),
                    created_by="system",
                )
                db_session.add(admin)
                db_session.commit()
                logger.info("Created default admin user")
            else:
                logger.info(f"Found {user_count} existing users in DB")
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error ensuring admin exists: {e}")
        finally:
            db_session.close()

    def create_user(self, username: str, password: str, role: str = "viewer",
                    permissions: dict = None, created_by: str = None) -> dict:
        """Create a new user in the database."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            raise RuntimeError("Database not available")
        try:
            existing = db_session.query(UserORM).filter(UserORM.username == username).first()
            if existing:
                raise ValueError(f"User '{username}' already exists")

            if role not in ROLE_PERMISSIONS:
                raise ValueError(f"Invalid role: {role}. Must be one of: {list(ROLE_PERMISSIONS.keys())}")

            # Use role defaults if no custom permissions provided
            user_permissions = permissions if permissions else ROLE_PERMISSIONS[role]

            user = UserORM(
                username=username,
                password_hash=self.hash_password(password),
                role=role,
                permissions=user_permissions,
                is_active=True,
                created_at=datetime.now(),
                created_by=created_by,
            )
            db_session.add(user)
            db_session.commit()
            logger.info(f"User created: {username} (role={role}) by {created_by}")
            return user.to_dict()
        except (ValueError, RuntimeError):
            db_session.rollback()
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error creating user: {e}")
            raise
        finally:
            db_session.close()

    def authenticate(self, username: str, password: str) -> Optional[str]:
        """Authenticate user against DB and create in-memory session."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            logger.error("Database not available for authentication")
            return None
        try:
            user = db_session.query(UserORM).filter(
                UserORM.username == username,
                UserORM.is_active == True
            ).first()

            if not user:
                logger.warning(f"Authentication failed: user not found or inactive - {username}")
                return None

            if not self.verify_password(password, user.password_hash):
                logger.warning(f"Authentication failed: invalid password - {username}")
                return None

            # Update last_login
            user.last_login = datetime.now()
            db_session.commit()

            # Create in-memory session with role/permissions
            session_id = secrets.token_urlsafe(32)
            now = datetime.now()
            session = Session(
                session_id=session_id,
                username=username,
                role=user.role,
                permissions=user.permissions or ROLE_PERMISSIONS.get(user.role, {}),
                created_at=now,
                last_activity=now,
                expires_at=now + self.session_timeout,
            )
            self.sessions[session_id] = session

            logger.info(f"User authenticated: {username} (role={user.role}), session: {session_id[:8]}...")
            return session_id
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
        finally:
            db_session.close()

    def validate_session(self, session_id: str) -> bool:
        """Validate session and update last activity."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        now = datetime.now()
        if now > session.expires_at:
            logger.info(f"Session expired: {session_id[:8]}... for user {session.username}")
            self.logout(session_id)
            return False

        session.last_activity = now
        session.expires_at = now + self.session_timeout
        return True

    def get_session_user(self, session_id: str) -> Optional[str]:
        """Get username for valid session."""
        if not self.validate_session(session_id):
            return None
        session = self.sessions.get(session_id)
        return session.username if session else None

    def get_session_role(self, session_id: str) -> Optional[str]:
        """Get role for valid session."""
        session = self.sessions.get(session_id)
        return session.role if session else None

    def get_session_permissions(self, session_id: str) -> dict:
        """Get permissions for valid session."""
        session = self.sessions.get(session_id)
        return session.permissions if session else {}

    def logout(self, session_id: str) -> bool:
        """Logout user by removing session."""
        session = self.sessions.pop(session_id, None)
        if session:
            logger.info(f"User logged out: {session.username}, session: {session_id[:8]}...")
            return True
        return False

    def clear_expired_sessions(self) -> int:
        """Remove all expired sessions."""
        now = datetime.now()
        expired = [sid for sid, s in self.sessions.items() if now > s.expires_at]
        for sid in expired:
            s = self.sessions.pop(sid)
            logger.info(f"Cleared expired session for user: {s.username}")
        if expired:
            logger.info(f"Cleared {len(expired)} expired sessions")
        return len(expired)

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change user password. Requires old password verification."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            raise RuntimeError("Database not available")
        try:
            user = db_session.query(UserORM).filter(UserORM.username == username).first()
            if not user:
                raise ValueError("User not found")
            if not self.verify_password(old_password, user.password_hash):
                raise ValueError("Current password is incorrect")
            if len(new_password) < 6:
                raise ValueError("New password must be at least 6 characters")

            user.password_hash = self.hash_password(new_password)
            db_session.commit()
            logger.info(f"Password changed for user: {username}")
            return True
        except (ValueError, RuntimeError):
            db_session.rollback()
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error changing password: {e}")
            raise
        finally:
            db_session.close()

    def reset_password(self, username: str, new_password: str, admin_username: str) -> bool:
        """Admin reset of user password (no old password required)."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            raise RuntimeError("Database not available")
        try:
            user = db_session.query(UserORM).filter(UserORM.username == username).first()
            if not user:
                raise ValueError("User not found")
            if len(new_password) < 6:
                raise ValueError("New password must be at least 6 characters")

            user.password_hash = self.hash_password(new_password)
            db_session.commit()
            logger.info(f"Password reset for user: {username} by admin: {admin_username}")
            return True
        except (ValueError, RuntimeError):
            db_session.rollback()
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error resetting password: {e}")
            raise
        finally:
            db_session.close()

    def update_user(self, username: str, role: str = None, permissions: dict = None,
                    is_active: bool = None, admin_username: str = None) -> dict:
        """Update user role/permissions/active status."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            raise RuntimeError("Database not available")
        try:
            user = db_session.query(UserORM).filter(UserORM.username == username).first()
            if not user:
                raise ValueError("User not found")

            if role is not None:
                if role not in ROLE_PERMISSIONS:
                    raise ValueError(f"Invalid role: {role}")
                user.role = role
                # Update permissions to role defaults unless custom permissions also provided
                if permissions is None:
                    user.permissions = ROLE_PERMISSIONS[role]

            if permissions is not None:
                user.permissions = permissions

            if is_active is not None:
                user.is_active = is_active
                # If deactivating, kill their sessions
                if not is_active:
                    self._kill_user_sessions(username)

            db_session.commit()
            logger.info(f"User updated: {username} by {admin_username}")
            return user.to_dict()
        except (ValueError, RuntimeError):
            db_session.rollback()
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error updating user: {e}")
            raise
        finally:
            db_session.close()

    def delete_user(self, username: str, admin_username: str) -> bool:
        """Delete a user. Cannot delete yourself."""
        from src.models.orm import UserORM
        if username == admin_username:
            raise ValueError("Cannot delete your own account")
        db_session = self._get_db_session()
        if not db_session:
            raise RuntimeError("Database not available")
        try:
            user = db_session.query(UserORM).filter(UserORM.username == username).first()
            if not user:
                raise ValueError("User not found")

            # Kill their sessions first
            self._kill_user_sessions(username)

            db_session.delete(user)
            db_session.commit()
            logger.info(f"User deleted: {username} by {admin_username}")
            return True
        except (ValueError, RuntimeError):
            db_session.rollback()
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error deleting user: {e}")
            raise
        finally:
            db_session.close()

    def list_users(self) -> List[dict]:
        """List all users (without password hashes)."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            return []
        try:
            users = db_session.query(UserORM).order_by(UserORM.created_at).all()
            return [u.to_dict() for u in users]
        finally:
            db_session.close()

    def get_user(self, username: str) -> Optional[dict]:
        """Get user by username."""
        from src.models.orm import UserORM
        db_session = self._get_db_session()
        if not db_session:
            return None
        try:
            user = db_session.query(UserORM).filter(UserORM.username == username).first()
            return user.to_dict() if user else None
        finally:
            db_session.close()

    def get_role_permissions(self) -> dict:
        """Return the default role permission definitions."""
        return ROLE_PERMISSIONS

    def _kill_user_sessions(self, username: str):
        """Remove all sessions for a user."""
        to_remove = [sid for sid, s in self.sessions.items() if s.username == username]
        for sid in to_remove:
            self.sessions.pop(sid, None)
        if to_remove:
            logger.info(f"Killed {len(to_remove)} sessions for user: {username}")


class SessionManager:
    """Manages user sessions with automatic cleanup of expired sessions."""

    def __init__(self, auth_manager: AuthenticationManager, cleanup_interval_seconds: int = 300):
        self.auth_manager = auth_manager
        self.cleanup_interval = cleanup_interval_seconds
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
        logger.info(f"SessionManager initialized with {cleanup_interval_seconds}s cleanup interval")

    def start_automatic_cleanup(self):
        """Start background thread for automatic session cleanup."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("Automatic cleanup already running")
            return
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info("Automatic session cleanup started")

    def stop_automatic_cleanup(self):
        """Stop background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._stop_cleanup.set()
            self._cleanup_thread.join(timeout=5)
            logger.info("Automatic session cleanup stopped")

    def _cleanup_loop(self):
        """Background loop for cleaning expired sessions."""
        while not self._stop_cleanup.is_set():
            try:
                cleared = self.auth_manager.clear_expired_sessions()
                if cleared > 0:
                    logger.info(f"Automatic cleanup: removed {cleared} expired sessions")
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
            self._stop_cleanup.wait(self.cleanup_interval)

    def validate_session(self, session_id: str) -> bool:
        return self.auth_manager.validate_session(session_id)

    def get_session_info(self, session_id: str) -> Optional[Session]:
        if not self.validate_session(session_id):
            return None
        return self.auth_manager.sessions.get(session_id)

    def get_active_sessions_count(self) -> int:
        return len(self.auth_manager.sessions)

    def get_user_sessions(self, username: str) -> list[Session]:
        return [s for s in self.auth_manager.sessions.values() if s.username == username]

    def logout_user_sessions(self, username: str) -> int:
        user_sessions = self.get_user_sessions(username)
        count = 0
        for session in user_sessions:
            if self.auth_manager.logout(session.session_id):
                count += 1
        logger.info(f"Logged out {count} sessions for user: {username}")
        return count
