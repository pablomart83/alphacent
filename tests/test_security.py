"""
Unit tests for security module (rate limiting and security logging).
"""

import pytest
import time
from datetime import datetime, timedelta
from src.core.security import (
    RateLimiter, RateLimitConfig, SecurityLogger, SecurityEventType,
    SecureAuthenticationManager
)
from src.core.auth import AuthenticationManager


class TestRateLimiter:
    """Test RateLimiter functionality."""
    
    def test_rate_limiter_initialization(self):
        """Test RateLimiter initialization."""
        config = RateLimitConfig(max_attempts=5, window_seconds=60, lockout_duration_seconds=300)
        limiter = RateLimiter(config)
        
        assert limiter.config.max_attempts == 5
        assert limiter.config.window_seconds == 60
        assert limiter.config.lockout_duration_seconds == 300
    
    def test_is_rate_limited_initial(self):
        """Test that new identifier is not rate limited."""
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        
        is_limited = limiter.is_rate_limited("testuser")
        
        assert is_limited is False
    
    def test_record_attempt(self):
        """Test recording attempts."""
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        
        limiter.record_attempt("testuser")
        limiter.record_attempt("testuser")
        
        assert len(limiter.attempts["testuser"]) == 2
    
    def test_rate_limit_enforcement(self):
        """Test that rate limit is enforced after max attempts."""
        config = RateLimitConfig(max_attempts=3, window_seconds=60, lockout_duration_seconds=5)
        limiter = RateLimiter(config)
        
        # Record max attempts
        for _ in range(3):
            limiter.record_attempt("testuser")
        
        # Should be rate limited
        is_limited = limiter.is_rate_limited("testuser")
        
        assert is_limited is True
    
    def test_rate_limit_lockout(self):
        """Test that lockout is applied after exceeding limit."""
        config = RateLimitConfig(max_attempts=2, window_seconds=60, lockout_duration_seconds=5)
        limiter = RateLimiter(config)
        
        # Exceed limit
        limiter.record_attempt("testuser")
        limiter.record_attempt("testuser")
        limiter.is_rate_limited("testuser")  # Trigger lockout
        
        # Should be locked
        assert "testuser" in limiter.locked_until
        assert limiter.is_rate_limited("testuser") is True
    
    def test_rate_limit_window_expiration(self):
        """Test that attempts outside window are not counted."""
        config = RateLimitConfig(max_attempts=2, window_seconds=1)
        limiter = RateLimiter(config)
        
        # Record attempts
        limiter.record_attempt("testuser")
        limiter.record_attempt("testuser")
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should not be rate limited (old attempts expired)
        is_limited = limiter.is_rate_limited("testuser")
        
        assert is_limited is False
    
    def test_get_remaining_attempts(self):
        """Test getting remaining attempts."""
        config = RateLimitConfig(max_attempts=5, window_seconds=60)
        limiter = RateLimiter(config)
        
        assert limiter.get_remaining_attempts("testuser") == 5
        
        limiter.record_attempt("testuser")
        assert limiter.get_remaining_attempts("testuser") == 4
        
        limiter.record_attempt("testuser")
        assert limiter.get_remaining_attempts("testuser") == 3
    
    def test_get_lockout_remaining(self):
        """Test getting remaining lockout time."""
        config = RateLimitConfig(max_attempts=1, window_seconds=60, lockout_duration_seconds=10)
        limiter = RateLimiter(config)
        
        # Not locked initially
        assert limiter.get_lockout_remaining("testuser") is None
        
        # Trigger lockout
        limiter.record_attempt("testuser")
        limiter.is_rate_limited("testuser")
        
        # Should have lockout time remaining
        remaining = limiter.get_lockout_remaining("testuser")
        assert remaining is not None
        assert remaining > 0
        assert remaining <= 10
    
    def test_reset(self):
        """Test resetting rate limit for identifier."""
        config = RateLimitConfig(max_attempts=2, window_seconds=60)
        limiter = RateLimiter(config)
        
        limiter.record_attempt("testuser")
        limiter.record_attempt("testuser")
        
        limiter.reset("testuser")
        
        assert len(limiter.attempts.get("testuser", [])) == 0
        assert "testuser" not in limiter.locked_until


class TestSecurityLogger:
    """Test SecurityLogger functionality."""
    
    def test_security_logger_initialization(self):
        """Test SecurityLogger initialization."""
        logger = SecurityLogger(max_events=100)
        
        assert logger.max_events == 100
        assert len(logger.events) == 0
    
    def test_log_event(self):
        """Test logging a security event."""
        logger = SecurityLogger()
        
        logger.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            username="testuser",
            ip_address="192.168.1.1",
            details="Test login",
            severity="INFO"
        )
        
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == SecurityEventType.LOGIN_SUCCESS
        assert event.username == "testuser"
        assert event.ip_address == "192.168.1.1"
        assert event.details == "Test login"
        assert event.severity == "INFO"
    
    def test_log_login_success(self):
        """Test logging successful login."""
        logger = SecurityLogger()
        
        logger.log_login_success("testuser", "192.168.1.1")
        
        assert len(logger.events) == 1
        assert logger.events[0].event_type == SecurityEventType.LOGIN_SUCCESS
    
    def test_log_login_failure(self):
        """Test logging failed login."""
        logger = SecurityLogger()
        
        logger.log_login_failure("testuser", "Invalid password", "192.168.1.1")
        
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == SecurityEventType.LOGIN_FAILURE
        assert event.severity == "WARNING"
    
    def test_log_rate_limit_exceeded(self):
        """Test logging rate limit exceeded."""
        logger = SecurityLogger()
        
        logger.log_rate_limit_exceeded("testuser", "192.168.1.1")
        
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED
        assert event.severity == "WARNING"
    
    def test_log_suspicious_activity(self):
        """Test logging suspicious activity."""
        logger = SecurityLogger()
        
        logger.log_suspicious_activity("testuser", "Multiple failed logins", "192.168.1.1")
        
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY
        assert event.severity == "CRITICAL"
    
    def test_max_events_limit(self):
        """Test that old events are removed when exceeding max."""
        logger = SecurityLogger(max_events=5)
        
        # Log more than max events
        for i in range(10):
            logger.log_event(SecurityEventType.LOGIN_SUCCESS, username=f"user{i}")
        
        # Should only keep last 5
        assert len(logger.events) == 5
        assert logger.events[0].username == "user5"
        assert logger.events[-1].username == "user9"
    
    def test_get_events_no_filter(self):
        """Test getting all events."""
        logger = SecurityLogger()
        
        logger.log_login_success("user1")
        logger.log_login_failure("user2", "Invalid password")
        
        events = logger.get_events()
        
        assert len(events) == 2
    
    def test_get_events_filter_by_username(self):
        """Test filtering events by username."""
        logger = SecurityLogger()
        
        logger.log_login_success("user1")
        logger.log_login_success("user2")
        logger.log_login_failure("user1", "Invalid password")
        
        events = logger.get_events(username="user1")
        
        assert len(events) == 2
        assert all(e.username == "user1" for e in events)
    
    def test_get_events_filter_by_type(self):
        """Test filtering events by type."""
        logger = SecurityLogger()
        
        logger.log_login_success("user1")
        logger.log_login_failure("user1", "Invalid password")
        logger.log_logout("user1")
        
        events = logger.get_events(event_type=SecurityEventType.LOGIN_FAILURE)
        
        assert len(events) == 1
        assert events[0].event_type == SecurityEventType.LOGIN_FAILURE
    
    def test_get_events_filter_by_time(self):
        """Test filtering events by time."""
        logger = SecurityLogger()
        
        logger.log_login_success("user1")
        
        # Get events since 1 hour ago
        since = datetime.now() - timedelta(hours=1)
        events = logger.get_events(since=since)
        
        assert len(events) == 1
    
    def test_get_failed_login_count(self):
        """Test getting failed login count."""
        logger = SecurityLogger()
        
        logger.log_login_failure("user1", "Invalid password")
        logger.log_login_failure("user1", "Invalid password")
        logger.log_login_success("user1")
        
        count = logger.get_failed_login_count("user1")
        
        assert count == 2


class TestSecureAuthenticationManager:
    """Test SecureAuthenticationManager functionality."""
    
    def test_secure_auth_initialization(self):
        """Test SecureAuthenticationManager initialization."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        assert secure_auth.auth_manager == auth
        assert secure_auth.rate_limiter == limiter
        assert secure_auth.security_logger == sec_logger
    
    def test_authenticate_success_with_logging(self):
        """Test successful authentication with security logging."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        auth.create_user("testuser", "TestPass123")
        session_id = secure_auth.authenticate("testuser", "TestPass123", "192.168.1.1")
        
        assert session_id is not None
        # Check security log
        events = sec_logger.get_events(event_type=SecurityEventType.LOGIN_SUCCESS)
        assert len(events) == 1
        assert events[0].username == "testuser"
    
    def test_authenticate_failure_with_logging(self):
        """Test failed authentication with security logging."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        auth.create_user("testuser", "TestPass123")
        session_id = secure_auth.authenticate("testuser", "WrongPass", "192.168.1.1")
        
        assert session_id is None
        # Check security log
        events = sec_logger.get_events(event_type=SecurityEventType.LOGIN_FAILURE)
        assert len(events) == 1
    
    def test_authenticate_rate_limited(self):
        """Test authentication blocked by rate limit."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=2, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        auth.create_user("testuser", "TestPass123")
        
        # Exceed rate limit
        secure_auth.authenticate("testuser", "WrongPass")
        secure_auth.authenticate("testuser", "WrongPass")
        
        # Should be blocked
        session_id = secure_auth.authenticate("testuser", "TestPass123")
        
        assert session_id is None
        # Check rate limit log
        events = sec_logger.get_events(event_type=SecurityEventType.RATE_LIMIT_EXCEEDED)
        assert len(events) == 1
    
    def test_authenticate_resets_rate_limit_on_success(self):
        """Test that successful auth resets rate limit."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        auth.create_user("testuser", "TestPass123")
        
        # Failed attempts
        secure_auth.authenticate("testuser", "WrongPass")
        secure_auth.authenticate("testuser", "WrongPass")
        
        # Successful auth should reset
        session_id = secure_auth.authenticate("testuser", "TestPass123")
        
        assert session_id is not None
        assert limiter.get_remaining_attempts("testuser") == 3
    
    def test_logout_with_logging(self):
        """Test logout with security logging."""
        auth = AuthenticationManager()
        config = RateLimitConfig(max_attempts=3, window_seconds=60)
        limiter = RateLimiter(config)
        sec_logger = SecurityLogger()
        secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)
        
        auth.create_user("testuser", "TestPass123")
        session_id = secure_auth.authenticate("testuser", "TestPass123")
        
        success = secure_auth.logout(session_id, "192.168.1.1")
        
        assert success is True
        # Check security log
        events = sec_logger.get_events(event_type=SecurityEventType.LOGOUT)
        assert len(events) == 1
