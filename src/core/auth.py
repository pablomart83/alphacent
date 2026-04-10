"""
Authentication module for AlphaCent Trading Platform.

Provides user authentication with bcrypt password hashing and session management.
"""

import bcrypt
import secrets
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class User:
    """User account information."""
    username: str
    password_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None


@dataclass
class Session:
    """User session information."""
    session_id: str
    username: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime


class AuthenticationManager:
    """
    Manages user authentication with bcrypt password hashing and session-based auth.
    
    Validates: Requirements 18.1, 18.2, 18.3
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        """
        Initialize authentication manager.
        
        Args:
            session_timeout_minutes: Session timeout in minutes (default 30)
        """
        self.users: Dict[str, User] = {}
        self.sessions: Dict[str, Session] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        logger.info(f"AuthenticationManager initialized with {session_timeout_minutes}min timeout")
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hashed password
            
        Validates: Requirement 18.2, Property 31
        """
        # Use rounds=12 for reasonable security with good performance
        # Default is 12, but explicitly setting it for clarity
        salt = bcrypt.gensalt(rounds=10)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Stored bcrypt hash
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def create_user(self, username: str, password: str) -> User:
        """
        Create new user with hashed password.
        
        Args:
            username: Username
            password: Plain text password (will be hashed)
            
        Returns:
            Created User object
            
        Raises:
            ValueError: If username already exists
            
        Validates: Requirements 18.1, 18.2
        """
        if username in self.users:
            logger.warning(f"Attempt to create duplicate user: {username}")
            raise ValueError(f"User {username} already exists")
        
        password_hash = self.hash_password(password)
        user = User(username=username, password_hash=password_hash)
        self.users[username] = user
        
        logger.info(f"User created: {username}")
        return user
    
    def authenticate(self, username: str, password: str) -> Optional[str]:
        """
        Authenticate user and create session.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            Session ID if authentication successful, None otherwise
            
        Validates: Requirements 18.1, 18.3
        """
        user = self.users.get(username)
        
        if not user:
            logger.warning(f"Authentication failed: user not found - {username}")
            return None
        
        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Authentication failed: invalid password - {username}")
            return None
        
        # Create session
        session_id = secrets.token_urlsafe(32)
        now = datetime.now()
        session = Session(
            session_id=session_id,
            username=username,
            created_at=now,
            last_activity=now,
            expires_at=now + self.session_timeout
        )
        
        self.sessions[session_id] = session
        user.last_login = now
        
        logger.info(f"User authenticated: {username}, session: {session_id[:8]}...")
        return session_id
    
    def validate_session(self, session_id: str) -> bool:
        """
        Validate session and update last activity.
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            True if session is valid, False otherwise
            
        Validates: Requirement 18.4
        """
        session = self.sessions.get(session_id)
        
        if not session:
            return False
        
        now = datetime.now()
        
        # Check if session expired
        if now > session.expires_at:
            logger.info(f"Session expired: {session_id[:8]}... for user {session.username}")
            self.logout(session_id)
            return False
        
        # Update last activity and extend expiration
        session.last_activity = now
        session.expires_at = now + self.session_timeout
        
        return True
    
    def get_session_user(self, session_id: str) -> Optional[str]:
        """
        Get username for valid session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Username if session valid, None otherwise
        """
        if not self.validate_session(session_id):
            return None
        
        session = self.sessions.get(session_id)
        return session.username if session else None
    
    def logout(self, session_id: str) -> bool:
        """
        Logout user by removing session.
        
        Args:
            session_id: Session ID to remove
            
        Returns:
            True if session was removed, False if not found
        """
        session = self.sessions.pop(session_id, None)
        
        if session:
            logger.info(f"User logged out: {session.username}, session: {session_id[:8]}...")
            return True
        
        return False
    
    def clear_expired_sessions(self) -> int:
        """
        Remove all expired sessions.
        
        Returns:
            Number of sessions cleared
            
        Validates: Requirement 18.4
        """
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if now > session.expires_at
        ]
        
        for session_id in expired_sessions:
            session = self.sessions.pop(session_id)
            logger.info(f"Cleared expired session for user: {session.username}")
        
        if expired_sessions:
            logger.info(f"Cleared {len(expired_sessions)} expired sessions")
        
        return len(expired_sessions)
    
    def get_user(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username
            
        Returns:
            User object if found, None otherwise
        """
        return self.users.get(username)



class SessionManager:
    """
    Manages user sessions with automatic cleanup of expired sessions.
    
    Validates: Requirement 18.4
    """
    
    def __init__(self, auth_manager: AuthenticationManager, cleanup_interval_seconds: int = 300):
        """
        Initialize session manager with automatic cleanup.
        
        Args:
            auth_manager: AuthenticationManager instance
            cleanup_interval_seconds: Interval for automatic cleanup (default 300s = 5min)
        """
        self.auth_manager = auth_manager
        self.cleanup_interval = cleanup_interval_seconds
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
        logger.info(f"SessionManager initialized with {cleanup_interval_seconds}s cleanup interval")
    
    def start_automatic_cleanup(self):
        """
        Start background thread for automatic session cleanup.
        
        Validates: Requirement 18.4 - Clear expired sessions automatically
        """
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
            
            # Wait for next cleanup interval
            self._stop_cleanup.wait(self.cleanup_interval)
    
    def validate_session(self, session_id: str) -> bool:
        """
        Validate session and update last activity.
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            True if session is valid, False otherwise
            
        Validates: Requirement 18.4 - Session validation on each request
        """
        return self.auth_manager.validate_session(session_id)
    
    def get_session_info(self, session_id: str) -> Optional[Session]:
        """
        Get session information.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session object if valid, None otherwise
        """
        if not self.validate_session(session_id):
            return None
        
        return self.auth_manager.sessions.get(session_id)
    
    def get_active_sessions_count(self) -> int:
        """
        Get count of active sessions.
        
        Returns:
            Number of active sessions
        """
        return len(self.auth_manager.sessions)
    
    def get_user_sessions(self, username: str) -> list[Session]:
        """
        Get all active sessions for a user.
        
        Args:
            username: Username
            
        Returns:
            List of active sessions for the user
        """
        return [
            session for session in self.auth_manager.sessions.values()
            if session.username == username
        ]
    
    def logout_user_sessions(self, username: str) -> int:
        """
        Logout all sessions for a user.
        
        Args:
            username: Username
            
        Returns:
            Number of sessions logged out
        """
        user_sessions = self.get_user_sessions(username)
        count = 0
        
        for session in user_sessions:
            if self.auth_manager.logout(session.session_id):
                count += 1
        
        logger.info(f"Logged out {count} sessions for user: {username}")
        return count
