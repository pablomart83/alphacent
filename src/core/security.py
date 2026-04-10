"""
Security module for AlphaCent Trading Platform.

Provides rate limiting and security event logging.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Types of security events."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INVALID_INPUT = "invalid_input"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    ACCOUNT_LOCKED = "account_locked"
    PASSWORD_CHANGE = "password_change"


@dataclass
class SecurityEvent:
    """Security event record."""
    event_type: SecurityEventType
    username: Optional[str]
    ip_address: Optional[str]
    timestamp: datetime
    details: str
    severity: str = "INFO"  # INFO, WARNING, CRITICAL


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    max_attempts: int
    window_seconds: int
    lockout_duration_seconds: int = 300  # 5 minutes default


class RateLimiter:
    """
    Rate limiter for authentication endpoints.
    
    Validates: Requirement 18.7, Property 34
    """
    
    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config
        self.attempts: Dict[str, List[float]] = defaultdict(list)
        self.locked_until: Dict[str, float] = {}
        logger.info(
            f"RateLimiter initialized: {config.max_attempts} attempts per "
            f"{config.window_seconds}s, lockout {config.lockout_duration_seconds}s"
        )
    
    def is_rate_limited(self, identifier: str) -> bool:
        """
        Check if identifier is rate limited.
        
        Args:
            identifier: Identifier to check (username, IP address, etc.)
            
        Returns:
            True if rate limited, False otherwise
            
        Validates: Requirement 18.7, Property 34
        """
        now = time.time()
        
        # Check if locked out
        if identifier in self.locked_until:
            if now < self.locked_until[identifier]:
                return True
            else:
                # Lockout expired, remove
                del self.locked_until[identifier]
                self.attempts[identifier] = []
        
        # Clean old attempts outside window
        cutoff = now - self.config.window_seconds
        self.attempts[identifier] = [
            attempt for attempt in self.attempts[identifier]
            if attempt > cutoff
        ]
        
        # Check if exceeded max attempts
        if len(self.attempts[identifier]) >= self.config.max_attempts:
            # Lock out
            self.locked_until[identifier] = now + self.config.lockout_duration_seconds
            logger.warning(
                f"Rate limit exceeded for {identifier}, locked for "
                f"{self.config.lockout_duration_seconds}s"
            )
            return True
        
        return False
    
    def record_attempt(self, identifier: str):
        """
        Record an attempt for rate limiting.
        
        Args:
            identifier: Identifier to record (username, IP address, etc.)
        """
        now = time.time()
        self.attempts[identifier].append(now)
    
    def get_remaining_attempts(self, identifier: str) -> int:
        """
        Get remaining attempts before rate limit.
        
        Args:
            identifier: Identifier to check
            
        Returns:
            Number of remaining attempts
        """
        if self.is_rate_limited(identifier):
            return 0
        
        current_attempts = len(self.attempts[identifier])
        return max(0, self.config.max_attempts - current_attempts)
    
    def get_lockout_remaining(self, identifier: str) -> Optional[int]:
        """
        Get remaining lockout time in seconds.
        
        Args:
            identifier: Identifier to check
            
        Returns:
            Remaining lockout seconds, or None if not locked
        """
        if identifier not in self.locked_until:
            return None
        
        now = time.time()
        remaining = int(self.locked_until[identifier] - now)
        
        if remaining <= 0:
            return None
        
        return remaining
    
    def reset(self, identifier: str):
        """
        Reset rate limit for identifier.
        
        Args:
            identifier: Identifier to reset
        """
        if identifier in self.attempts:
            del self.attempts[identifier]
        if identifier in self.locked_until:
            del self.locked_until[identifier]
        logger.info(f"Rate limit reset for {identifier}")


class SecurityLogger:
    """
    Logs security events for audit and monitoring.
    
    Validates: Requirement 18.8, Property 35
    """
    
    def __init__(self, max_events: int = 10000):
        """
        Initialize security logger.
        
        Args:
            max_events: Maximum events to keep in memory
        """
        self.events: List[SecurityEvent] = []
        self.max_events = max_events
        logger.info(f"SecurityLogger initialized with max {max_events} events")
    
    def log_event(self, event_type: SecurityEventType, username: Optional[str] = None,
                  ip_address: Optional[str] = None, details: str = "",
                  severity: str = "INFO"):
        """
        Log a security event.
        
        Args:
            event_type: Type of security event
            username: Username involved (if applicable)
            ip_address: IP address (if applicable)
            details: Additional details
            severity: Event severity (INFO, WARNING, CRITICAL)
            
        Validates: Requirement 18.8, Property 35
        """
        event = SecurityEvent(
            event_type=event_type,
            username=username,
            ip_address=ip_address,
            timestamp=datetime.now(),
            details=details,
            severity=severity
        )
        
        self.events.append(event)
        
        # Trim old events if exceeding max
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
        
        # Log to standard logger
        log_message = (
            f"Security Event: {event_type.value} | "
            f"User: {username or 'N/A'} | "
            f"IP: {ip_address or 'N/A'} | "
            f"Details: {details}"
        )
        
        if severity == "CRITICAL":
            logger.critical(log_message)
        elif severity == "WARNING":
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def log_login_success(self, username: str, ip_address: Optional[str] = None):
        """
        Log successful login.
        
        Args:
            username: Username
            ip_address: IP address (optional)
            
        Validates: Requirement 18.8
        """
        self.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            username=username,
            ip_address=ip_address,
            details="User logged in successfully",
            severity="INFO"
        )
    
    def log_login_failure(self, username: str, reason: str, ip_address: Optional[str] = None):
        """
        Log failed login attempt.
        
        Args:
            username: Username
            reason: Failure reason
            ip_address: IP address (optional)
            
        Validates: Requirement 18.8
        """
        self.log_event(
            SecurityEventType.LOGIN_FAILURE,
            username=username,
            ip_address=ip_address,
            details=f"Login failed: {reason}",
            severity="WARNING"
        )
    
    def log_logout(self, username: str, ip_address: Optional[str] = None):
        """
        Log user logout.
        
        Args:
            username: Username
            ip_address: IP address (optional)
        """
        self.log_event(
            SecurityEventType.LOGOUT,
            username=username,
            ip_address=ip_address,
            details="User logged out",
            severity="INFO"
        )
    
    def log_session_expired(self, username: str):
        """
        Log session expiration.
        
        Args:
            username: Username
        """
        self.log_event(
            SecurityEventType.SESSION_EXPIRED,
            username=username,
            details="Session expired due to inactivity",
            severity="INFO"
        )
    
    def log_rate_limit_exceeded(self, identifier: str, ip_address: Optional[str] = None):
        """
        Log rate limit exceeded.
        
        Args:
            identifier: Identifier (username or IP)
            ip_address: IP address (optional)
            
        Validates: Requirement 18.7
        """
        self.log_event(
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            username=identifier,
            ip_address=ip_address,
            details="Rate limit exceeded, account temporarily locked",
            severity="WARNING"
        )
    
    def log_suspicious_activity(self, username: Optional[str], details: str,
                               ip_address: Optional[str] = None):
        """
        Log suspicious activity.
        
        Args:
            username: Username (if known)
            details: Activity details
            ip_address: IP address (optional)
            
        Validates: Requirement 18.8
        """
        self.log_event(
            SecurityEventType.SUSPICIOUS_ACTIVITY,
            username=username,
            ip_address=ip_address,
            details=details,
            severity="CRITICAL"
        )
    
    def get_events(self, username: Optional[str] = None, 
                   event_type: Optional[SecurityEventType] = None,
                   since: Optional[datetime] = None,
                   limit: int = 100) -> List[SecurityEvent]:
        """
        Get security events with optional filtering.
        
        Args:
            username: Filter by username (optional)
            event_type: Filter by event type (optional)
            since: Filter events since timestamp (optional)
            limit: Maximum events to return
            
        Returns:
            List of security events
        """
        filtered = self.events
        
        if username:
            filtered = [e for e in filtered if e.username == username]
        
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        
        if since:
            filtered = [e for e in filtered if e.timestamp >= since]
        
        # Return most recent events
        return filtered[-limit:]
    
    def get_failed_login_count(self, username: str, since: Optional[datetime] = None) -> int:
        """
        Get count of failed login attempts.
        
        Args:
            username: Username
            since: Count since timestamp (optional, default last 24 hours)
            
        Returns:
            Number of failed login attempts
        """
        if since is None:
            since = datetime.now() - timedelta(hours=24)
        
        events = self.get_events(
            username=username,
            event_type=SecurityEventType.LOGIN_FAILURE,
            since=since
        )
        
        return len(events)


class SecureAuthenticationManager:
    """
    Authentication manager with rate limiting and security logging.
    
    Combines authentication, rate limiting, and security logging.
    Validates: Requirements 18.1, 18.7, 18.8
    """
    
    def __init__(self, auth_manager, rate_limiter: RateLimiter, 
                 security_logger: SecurityLogger):
        """
        Initialize secure authentication manager.
        
        Args:
            auth_manager: AuthenticationManager instance
            rate_limiter: RateLimiter instance
            security_logger: SecurityLogger instance
        """
        self.auth_manager = auth_manager
        self.rate_limiter = rate_limiter
        self.security_logger = security_logger
        logger.info("SecureAuthenticationManager initialized")
    
    def authenticate(self, username: str, password: str, 
                    ip_address: Optional[str] = None) -> Optional[str]:
        """
        Authenticate user with rate limiting and security logging.
        
        Args:
            username: Username
            password: Password
            ip_address: IP address (optional)
            
        Returns:
            Session ID if successful, None otherwise
            
        Validates: Requirements 18.1, 18.7, 18.8
        """
        # Check rate limit
        if self.rate_limiter.is_rate_limited(username):
            remaining = self.rate_limiter.get_lockout_remaining(username)
            self.security_logger.log_rate_limit_exceeded(username, ip_address)
            logger.warning(
                f"Authentication blocked for {username}: rate limited "
                f"({remaining}s remaining)"
            )
            return None
        
        # Record attempt
        self.rate_limiter.record_attempt(username)
        
        # Attempt authentication
        session_id = self.auth_manager.authenticate(username, password)
        
        if session_id:
            # Success
            self.security_logger.log_login_success(username, ip_address)
            # Reset rate limit on success
            self.rate_limiter.reset(username)
            return session_id
        else:
            # Failure
            self.security_logger.log_login_failure(
                username, "Invalid credentials", ip_address
            )
            return None
    
    def logout(self, session_id: str, ip_address: Optional[str] = None) -> bool:
        """
        Logout user with security logging.
        
        Args:
            session_id: Session ID
            ip_address: IP address (optional)
            
        Returns:
            True if successful, False otherwise
        """
        username = self.auth_manager.get_session_user(session_id)
        success = self.auth_manager.logout(session_id)
        
        if success and username:
            self.security_logger.log_logout(username, ip_address)
        
        return success
