"""Tests for configuration management."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core import Configuration, ConfigurationError, CredentialManager
from src.models import RiskConfig, TradingMode


def test_credential_manager_encryption():
    """Test credential encryption and decryption."""
    with TemporaryDirectory() as tmpdir:
        key_file = Path(tmpdir) / ".encryption_key"
        manager = CredentialManager(str(key_file))
        
        # Test encryption/decryption
        original = "my_secret_key_12345"
        encrypted = manager.encrypt(original)
        decrypted = manager.decrypt(encrypted)
        
        assert encrypted != original
        assert decrypted == original


def test_credential_manager_key_persistence():
    """Test that encryption key is persisted and reused."""
    with TemporaryDirectory() as tmpdir:
        key_file = Path(tmpdir) / ".encryption_key"
        
        # Create first manager
        manager1 = CredentialManager(str(key_file))
        original = "test_data"
        encrypted = manager1.encrypt(original)
        
        # Create second manager with same key file
        manager2 = CredentialManager(str(key_file))
        decrypted = manager2.decrypt(encrypted)
        
        assert decrypted == original


def test_configuration_save_load_credentials():
    """Test saving and loading encrypted credentials."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Save credentials
        config.save_credentials(
            TradingMode.DEMO,
            "public_key_123",
            "user_key_456"
        )
        
        # Load credentials
        creds = config.load_credentials(TradingMode.DEMO)
        
        assert creds["public_key"] == "public_key_123"
        assert creds["user_key"] == "user_key_456"


def test_configuration_separate_mode_credentials():
    """Test that demo and live credentials are stored separately."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Save demo credentials
        config.save_credentials(
            TradingMode.DEMO,
            "demo_public",
            "demo_user"
        )
        
        # Save live credentials
        config.save_credentials(
            TradingMode.LIVE,
            "live_public",
            "live_user"
        )
        
        # Load and verify
        demo_creds = config.load_credentials(TradingMode.DEMO)
        live_creds = config.load_credentials(TradingMode.LIVE)
        
        assert demo_creds["public_key"] == "demo_public"
        assert live_creds["public_key"] == "live_public"


def test_configuration_missing_credentials():
    """Test error when loading non-existent credentials."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        with pytest.raises(ConfigurationError):
            config.load_credentials(TradingMode.DEMO)


def test_configuration_save_load_risk_config():
    """Test saving and loading risk configuration."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Create custom risk config
        risk_config = RiskConfig(
            max_position_size_pct=0.15,
            max_exposure_pct=0.9,
            max_daily_loss_pct=0.05
        )
        
        # Save
        config.save_risk_config(TradingMode.DEMO, risk_config)
        
        # Load
        loaded = config.load_risk_config(TradingMode.DEMO)
        
        assert loaded.max_position_size_pct == 0.15
        assert loaded.max_exposure_pct == 0.9
        assert loaded.max_daily_loss_pct == 0.05


def test_configuration_risk_config_defaults():
    """Test that default risk config is returned when none exists."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Load without saving
        loaded = config.load_risk_config(TradingMode.DEMO)
        
        # Should return defaults
        assert loaded.max_position_size_pct == 0.1
        assert loaded.max_exposure_pct == 0.8


def test_configuration_validate_credentials():
    """Test credential validation."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Should be invalid initially
        assert not config.validate_credentials(TradingMode.DEMO)
        
        # Save credentials
        config.save_credentials(
            TradingMode.DEMO,
            "public_key",
            "user_key"
        )
        
        # Should be valid now
        assert config.validate_credentials(TradingMode.DEMO)


def test_configuration_app_config():
    """Test saving and loading application configuration."""
    with TemporaryDirectory() as tmpdir:
        config = Configuration(tmpdir)
        
        # Save app config
        app_config = {
            "theme": "dark",
            "refresh_interval": 5,
            "features": ["social_insights", "smart_portfolios"]
        }
        config.save_app_config(app_config)
        
        # Load app config
        loaded = config.load_app_config()
        
        assert loaded["theme"] == "dark"
        assert loaded["refresh_interval"] == 5
        assert "social_insights" in loaded["features"]
