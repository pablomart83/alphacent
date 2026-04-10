"""
Unit tests for authentication module.
"""

import pytest
from datetime import datetime, timedelta
from src.core.auth import AuthenticationManager, SessionManager, User, Session


class TestAuthenticationManager:
    """Test AuthenticationManager functionality."""
    
    def test_create_user(self):
        """Test user creation with password hashing."""
        auth = AuthenticationManager()
        user = auth.create_user("testuser", "TestPass123")
        
        assert user.username == "testuser"
        assert user.password_hash != "TestPass123"  # Password should be hashed
        assert len(user.password_hash) > 0
        assert user.created_at is not None
    
    def test_create_duplicate_user(self):
        """Test that duplicate usernames are rejected."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        
        with pytest.raises(ValueError, match="already exists"):
            auth.create_user("testuser", "AnotherPass456")
    
    def test_password_hashing(self):
        """Test that passwords are hashed using bcrypt."""
        auth = AuthenticationManager()
        password = "SecurePass123"
        password_hash = auth.hash_password(password)
        
        # Hash should be different from password
        assert password_hash != password
        # Hash should start with bcrypt prefix
        assert password_hash.startswith("$2b$")
        # Hashing same password twice should produce different hashes (due to salt)
        password_hash2 = auth.hash_password(password)
        assert password_hash != password_hash2
    
    def test_password_verification(self):
        """Test password verification."""
        auth = AuthenticationManager()
        password = "TestPass123"
        password_hash = auth.hash_password(password)
        
        # Correct password should verify
        assert auth.verify_password(password, password_hash) is True
        # Incorrect password should not verify
        assert auth.verify_password("WrongPass", password_hash) is False
    
    def test_authenticate_success(self):
        """Test successful authentication."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        
        session_id = auth.authenticate("testuser", "TestPass123")
        
        assert session_id is not None
        assert len(session_id) > 0
        assert session_id in auth.sessions
    
    def test_authenticate_invalid_user(self):
        """Test authentication with non-existent user."""
        auth = AuthenticationManager()
        
        session_id = auth.authenticate("nonexistent", "TestPass123")
        
        assert session_id is None
    
    def test_authenticate_invalid_password(self):
        """Test authentication with wrong password."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        
        session_id = auth.authenticate("testuser", "WrongPass")
        
        assert session_id is None
    
    def test_session_creation(self):
        """Test that authentication creates valid session."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        
        session_id = auth.authenticate("testuser", "TestPass123")
        session = auth.sessions[session_id]
        
        assert session.username == "testuser"
        assert session.session_id == session_id
        assert session.created_at is not None
        assert session.last_activity is not None
        assert session.expires_at > datetime.now()
    
    def test_validate_session_valid(self):
        """Test validation of valid session."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        is_valid = auth.validate_session(session_id)
        
        assert is_valid is True
    
    def test_validate_session_invalid(self):
        """Test validation of invalid session."""
        auth = AuthenticationManager()
        
        is_valid = auth.validate_session("invalid_session_id")
        
        assert is_valid is False
    
    def test_validate_session_updates_activity(self):
        """Test that session validation updates last activity."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        original_activity = auth.sessions[session_id].last_activity
        
        # Wait a moment and validate
        import time
        time.sleep(0.1)
        auth.validate_session(session_id)
        
        new_activity = auth.sessions[session_id].last_activity
        assert new_activity > original_activity
    
    def test_session_expiration(self):
        """Test that expired sessions are invalidated."""
        auth = AuthenticationManager(session_timeout_minutes=0)  # Immediate expiration
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        # Manually expire session
        auth.sessions[session_id].expires_at = datetime.now() - timedelta(seconds=1)
        
        is_valid = auth.validate_session(session_id)
        
        assert is_valid is False
        assert session_id not in auth.sessions  # Should be removed
    
    def test_get_session_user(self):
        """Test getting username from session."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        username = auth.get_session_user(session_id)
        
        assert username == "testuser"
    
    def test_logout(self):
        """Test user logout."""
        auth = AuthenticationManager()
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        success = auth.logout(session_id)
        
        assert success is True
        assert session_id not in auth.sessions
    
    def test_logout_invalid_session(self):
        """Test logout with invalid session."""
        auth = AuthenticationManager()
        
        success = auth.logout("invalid_session")
        
        assert success is False
    
    def test_clear_expired_sessions(self):
        """Test clearing expired sessions."""
        auth = AuthenticationManager(session_timeout_minutes=0)
        auth.create_user("user1", "Pass123")
        auth.create_user("user2", "Pass456")
        
        session1 = auth.authenticate("user1", "Pass123")
        session2 = auth.authenticate("user2", "Pass456")
        
        # Expire both sessions
        auth.sessions[session1].expires_at = datetime.now() - timedelta(seconds=1)
        auth.sessions[session2].expires_at = datetime.now() - timedelta(seconds=1)
        
        cleared = auth.clear_expired_sessions()
        
        assert cleared == 2
        assert len(auth.sessions) == 0


class TestSessionManager:
    """Test SessionManager functionality."""
    
    def test_session_manager_initialization(self):
        """Test SessionManager initialization."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth, cleanup_interval_seconds=60)
        
        assert session_mgr.auth_manager == auth
        assert session_mgr.cleanup_interval == 60
    
    def test_validate_session(self):
        """Test session validation through SessionManager."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth)
        
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        is_valid = session_mgr.validate_session(session_id)
        
        assert is_valid is True
    
    def test_get_session_info(self):
        """Test getting session information."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth)
        
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        
        session_info = session_mgr.get_session_info(session_id)
        
        assert session_info is not None
        assert session_info.username == "testuser"
    
    def test_get_active_sessions_count(self):
        """Test getting active session count."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth)
        
        auth.create_user("user1", "Pass123")
        auth.create_user("user2", "Pass456")
        
        auth.authenticate("user1", "Pass123")
        auth.authenticate("user2", "Pass456")
        
        count = session_mgr.get_active_sessions_count()
        
        assert count == 2
    
    def test_get_user_sessions(self):
        """Test getting sessions for specific user."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth)
        
        auth.create_user("testuser", "Pass123")
        
        session1 = auth.authenticate("testuser", "Pass123")
        session2 = auth.authenticate("testuser", "Pass123")
        
        user_sessions = session_mgr.get_user_sessions("testuser")
        
        assert len(user_sessions) == 2
        assert all(s.username == "testuser" for s in user_sessions)
    
    def test_logout_user_sessions(self):
        """Test logging out all sessions for a user."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth)
        
        auth.create_user("testuser", "Pass123")
        
        auth.authenticate("testuser", "Pass123")
        auth.authenticate("testuser", "Pass123")
        
        count = session_mgr.logout_user_sessions("testuser")
        
        assert count == 2
        assert len(auth.sessions) == 0
    
    def test_automatic_cleanup_start_stop(self):
        """Test starting and stopping automatic cleanup."""
        auth = AuthenticationManager()
        session_mgr = SessionManager(auth, cleanup_interval_seconds=1)
        
        session_mgr.start_automatic_cleanup()
        assert session_mgr._cleanup_thread is not None
        assert session_mgr._cleanup_thread.is_alive()
        
        session_mgr.stop_automatic_cleanup()
        assert not session_mgr._cleanup_thread.is_alive()
