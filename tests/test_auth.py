"""
Unit tests for authentication module.
Tests use an in-memory SQLite database for isolation.
"""

import pytest
import time
from datetime import datetime, timedelta
from src.core.auth import AuthenticationManager, SessionManager, Session, ROLE_PERMISSIONS


@pytest.fixture
def db(tmp_path):
    """Create a minimal test database with just the users table."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.models.orm import Base, UserORM

    db_file = str(tmp_path / "test_auth.db")
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(bind=engine, tables=[UserORM.__table__])
    SessionLocal = sessionmaker(bind=engine)

    class MinimalDB:
        def get_session(self):
            return SessionLocal()
        def close(self):
            engine.dispose()

    yield MinimalDB()


@pytest.fixture
def auth(db):
    """Create an AuthenticationManager connected to test DB."""
    manager = AuthenticationManager()
    manager.set_database(db)
    return manager


@pytest.fixture
def auth(db):
    """Create an AuthenticationManager connected to test DB."""
    manager = AuthenticationManager()
    manager.set_database(db)
    return manager


class TestAuthenticationManager:
    """Test AuthenticationManager functionality."""

    def test_ensure_admin_exists(self, auth):
        """Test default admin creation when no users exist."""
        auth.ensure_admin_exists("testpass")
        users = auth.list_users()
        assert len(users) == 1
        assert users[0]["username"] == "admin"
        assert users[0]["role"] == "admin"

    def test_ensure_admin_exists_idempotent(self, auth):
        """Test that ensure_admin_exists doesn't create duplicates."""
        auth.ensure_admin_exists("testpass")
        auth.ensure_admin_exists("testpass")
        users = auth.list_users()
        assert len(users) == 1

    def test_create_user(self, auth):
        """Test user creation with password hashing."""
        user = auth.create_user("testuser", "TestPass123", role="trader", created_by="admin")
        assert user["username"] == "testuser"
        assert user["role"] == "trader"
        assert user["is_active"] is True
        assert user["created_by"] == "admin"
        assert "password_hash" not in user  # Should not expose hash

    def test_create_duplicate_user(self, auth):
        """Test that duplicate usernames are rejected."""
        auth.create_user("testuser", "TestPass123")
        with pytest.raises(ValueError, match="already exists"):
            auth.create_user("testuser", "AnotherPass456")

    def test_create_user_invalid_role(self, auth):
        """Test that invalid roles are rejected."""
        with pytest.raises(ValueError, match="Invalid role"):
            auth.create_user("testuser", "TestPass123", role="superadmin")

    def test_password_hashing(self, auth):
        """Test that passwords are hashed using bcrypt."""
        password = "SecurePass123"
        hash1 = auth.hash_password(password)
        hash2 = auth.hash_password(password)
        assert hash1 != password
        assert hash1.startswith("$2b$")
        assert hash1 != hash2  # Different salts

    def test_password_verification(self, auth):
        """Test password verification."""
        password = "TestPass123"
        password_hash = auth.hash_password(password)
        assert auth.verify_password(password, password_hash) is True
        assert auth.verify_password("WrongPass", password_hash) is False

    def test_authenticate_success(self, auth):
        """Test successful authentication."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert session_id is not None
        assert session_id in auth.sessions

    def test_authenticate_invalid_user(self, auth):
        """Test authentication with non-existent user."""
        assert auth.authenticate("nonexistent", "TestPass123") is None

    def test_authenticate_invalid_password(self, auth):
        """Test authentication with wrong password."""
        auth.create_user("testuser", "TestPass123")
        assert auth.authenticate("testuser", "WrongPass") is None

    def test_authenticate_inactive_user(self, auth):
        """Test that inactive users cannot authenticate."""
        auth.create_user("testuser", "TestPass123")
        auth.update_user("testuser", is_active=False)
        assert auth.authenticate("testuser", "TestPass123") is None

    def test_session_creation(self, auth):
        """Test that authentication creates valid session with role/permissions."""
        auth.create_user("testuser", "TestPass123", role="trader")
        session_id = auth.authenticate("testuser", "TestPass123")
        session = auth.sessions[session_id]
        assert session.username == "testuser"
        assert session.role == "trader"
        assert "trade" in session.permissions.get("actions", [])
        assert session.expires_at > datetime.now()

    def test_validate_session_valid(self, auth):
        """Test validation of valid session."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert auth.validate_session(session_id) is True

    def test_validate_session_invalid(self, auth):
        """Test validation of invalid session."""
        assert auth.validate_session("invalid_session_id") is False

    def test_validate_session_updates_activity(self, auth):
        """Test that session validation updates last activity."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        original = auth.sessions[session_id].last_activity
        time.sleep(0.05)
        auth.validate_session(session_id)
        assert auth.sessions[session_id].last_activity > original

    def test_session_expiration(self, auth):
        """Test that expired sessions are invalidated."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        auth.sessions[session_id].expires_at = datetime.now() - timedelta(seconds=1)
        assert auth.validate_session(session_id) is False
        assert session_id not in auth.sessions

    def test_get_session_user(self, auth):
        """Test getting username from session."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert auth.get_session_user(session_id) == "testuser"

    def test_get_session_role(self, auth):
        """Test getting role from session."""
        auth.create_user("testuser", "TestPass123", role="admin")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert auth.get_session_role(session_id) == "admin"

    def test_logout(self, auth):
        """Test user logout."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert auth.logout(session_id) is True
        assert session_id not in auth.sessions

    def test_logout_invalid_session(self, auth):
        """Test logout with invalid session."""
        assert auth.logout("invalid_session") is False

    def test_clear_expired_sessions(self, auth):
        """Test clearing expired sessions."""
        auth.create_user("user1", "Pass123")
        auth.create_user("user2", "Pass456")
        s1 = auth.authenticate("user1", "Pass123")
        s2 = auth.authenticate("user2", "Pass456")
        auth.sessions[s1].expires_at = datetime.now() - timedelta(seconds=1)
        auth.sessions[s2].expires_at = datetime.now() - timedelta(seconds=1)
        assert auth.clear_expired_sessions() == 2
        assert len(auth.sessions) == 0

    def test_change_password(self, auth):
        """Test changing own password."""
        auth.create_user("testuser", "OldPass123")
        auth.change_password("testuser", "OldPass123", "NewPass456")
        # Old password should fail
        assert auth.authenticate("testuser", "OldPass123") is None
        # New password should work
        assert auth.authenticate("testuser", "NewPass456") is not None

    def test_change_password_wrong_old(self, auth):
        """Test that wrong old password is rejected."""
        auth.create_user("testuser", "OldPass123")
        with pytest.raises(ValueError, match="incorrect"):
            auth.change_password("testuser", "WrongOld", "NewPass456")

    def test_change_password_too_short(self, auth):
        """Test that short new password is rejected."""
        auth.create_user("testuser", "OldPass123")
        with pytest.raises(ValueError, match="at least 6"):
            auth.change_password("testuser", "OldPass123", "short")

    def test_reset_password(self, auth):
        """Test admin password reset."""
        auth.create_user("testuser", "OldPass123")
        auth.reset_password("testuser", "ResetPass789", admin_username="admin")
        assert auth.authenticate("testuser", "ResetPass789") is not None

    def test_update_user_role(self, auth):
        """Test updating user role."""
        auth.create_user("testuser", "TestPass123", role="viewer")
        result = auth.update_user("testuser", role="trader")
        assert result["role"] == "trader"
        # Permissions should update to trader defaults
        assert "trade" in result["permissions"]["actions"]

    def test_update_user_deactivate_kills_sessions(self, auth):
        """Test that deactivating a user kills their sessions."""
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert session_id in auth.sessions
        auth.update_user("testuser", is_active=False)
        assert session_id not in auth.sessions

    def test_delete_user(self, auth):
        """Test deleting a user."""
        auth.create_user("testuser", "TestPass123")
        auth.delete_user("testuser", admin_username="admin")
        assert auth.get_user("testuser") is None

    def test_delete_self_rejected(self, auth):
        """Test that you cannot delete yourself."""
        auth.create_user("admin", "AdminPass")
        with pytest.raises(ValueError, match="Cannot delete your own"):
            auth.delete_user("admin", admin_username="admin")

    def test_list_users(self, auth):
        """Test listing all users."""
        auth.create_user("user1", "Pass123", role="admin")
        auth.create_user("user2", "Pass456", role="viewer")
        users = auth.list_users()
        assert len(users) == 2
        usernames = [u["username"] for u in users]
        assert "user1" in usernames
        assert "user2" in usernames

    def test_role_permissions(self, auth):
        """Test that role permissions are correctly assigned."""
        roles = auth.get_role_permissions()
        assert "admin" in roles
        assert "trader" in roles
        assert "viewer" in roles
        assert "manage_users" in roles["admin"]["actions"]
        assert "manage_users" not in roles["viewer"]["actions"]
        assert "trade" in roles["trader"]["actions"]


class TestSessionManager:
    """Test SessionManager functionality."""

    def test_session_manager_initialization(self, auth):
        session_mgr = SessionManager(auth, cleanup_interval_seconds=60)
        assert session_mgr.auth_manager == auth
        assert session_mgr.cleanup_interval == 60

    def test_validate_session(self, auth):
        session_mgr = SessionManager(auth)
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        assert session_mgr.validate_session(session_id) is True

    def test_get_session_info(self, auth):
        session_mgr = SessionManager(auth)
        auth.create_user("testuser", "TestPass123")
        session_id = auth.authenticate("testuser", "TestPass123")
        info = session_mgr.get_session_info(session_id)
        assert info is not None
        assert info.username == "testuser"

    def test_get_active_sessions_count(self, auth):
        session_mgr = SessionManager(auth)
        auth.create_user("user1", "Pass123")
        auth.create_user("user2", "Pass456")
        auth.authenticate("user1", "Pass123")
        auth.authenticate("user2", "Pass456")
        assert session_mgr.get_active_sessions_count() == 2

    def test_logout_user_sessions(self, auth):
        session_mgr = SessionManager(auth)
        auth.create_user("testuser", "Pass123")
        auth.authenticate("testuser", "Pass123")
        auth.authenticate("testuser", "Pass123")
        count = session_mgr.logout_user_sessions("testuser")
        assert count == 2
        assert len(auth.sessions) == 0

    def test_automatic_cleanup_start_stop(self, auth):
        session_mgr = SessionManager(auth, cleanup_interval_seconds=1)
        session_mgr.start_automatic_cleanup()
        assert session_mgr._cleanup_thread is not None
        assert session_mgr._cleanup_thread.is_alive()
        session_mgr.stop_automatic_cleanup()
        assert not session_mgr._cleanup_thread.is_alive()
