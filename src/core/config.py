"""Configuration management with secure credential storage."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from src.models import RiskConfig, TradingMode

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Configuration-related errors."""
    pass


class CredentialManager:
    """Manages secure credential storage with encryption."""

    def __init__(self, key_file: str = "config/.encryption_key"):
        """Initialize credential manager.
        
        Args:
            key_file: Path to encryption key file
        """
        self.key_file = Path(key_file)
        self._key = self._load_or_create_key()
        self._cipher = Fernet(self._key)

    def _load_or_create_key(self) -> bytes:
        """Load existing encryption key or create new one.
        
        Returns:
            Encryption key bytes
        """
        if self.key_file.exists():
            logger.info(f"Loading encryption key from {self.key_file}")
            return self.key_file.read_bytes()
        else:
            logger.info(f"Creating new encryption key at {self.key_file}")
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            # Secure the key file (Unix-like systems)
            try:
                self.key_file.chmod(0o600)
            except Exception as e:
                logger.warning(f"Could not set key file permissions: {e}")
            return key

    def encrypt(self, data: str) -> str:
        """Encrypt string data.
        
        Args:
            data: Plain text string
            
        Returns:
            Encrypted string (base64 encoded)
        """
        encrypted_bytes = self._cipher.encrypt(data.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt string data.
        
        Args:
            encrypted_data: Encrypted string (base64 encoded)
            
        Returns:
            Decrypted plain text string
        """
        decrypted_bytes = self._cipher.decrypt(encrypted_data.encode())
        return decrypted_bytes.decode()


class Configuration:
    """Application configuration manager."""

    def __init__(self, config_dir: str = "config"):
        """Initialize configuration manager.
        
        Args:
            config_dir: Directory for configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.credential_manager = CredentialManager()
        
        # Configuration files
        self.demo_creds_file = self.config_dir / "demo_credentials.json"
        self.live_creds_file = self.config_dir / "live_credentials.json"
        self.risk_config_file = self.config_dir / "risk_config.json"
        self.app_config_file = self.config_dir / "app_config.json"

    def save_credentials(
        self,
        mode: TradingMode,
        public_key: str,
        user_key: str
    ) -> None:
        """Save encrypted API credentials.
        
        Args:
            mode: Trading mode (DEMO or LIVE)
            public_key: eToro API public key
            user_key: eToro API user key
        """
        creds_file = self.demo_creds_file if mode == TradingMode.DEMO else self.live_creds_file
        
        encrypted_creds = {
            "public_key": self.credential_manager.encrypt(public_key),
            "user_key": self.credential_manager.encrypt(user_key),
            "mode": mode.value
        }
        
        creds_file.write_text(json.dumps(encrypted_creds, indent=2))
        logger.info(f"Saved encrypted credentials for {mode.value} mode")

    def load_credentials(self, mode: TradingMode) -> Dict[str, str]:
        """Load and decrypt API credentials.
        
        Args:
            mode: Trading mode (DEMO or LIVE)
            
        Returns:
            Dictionary with 'public_key' and 'user_key'
            
        Raises:
            ConfigurationError: If credentials not found or invalid
        """
        creds_file = self.demo_creds_file if mode == TradingMode.DEMO else self.live_creds_file
        
        if not creds_file.exists():
            raise ConfigurationError(f"Credentials not found for {mode.value} mode")
        
        try:
            encrypted_creds = json.loads(creds_file.read_text())
            return {
                "public_key": self.credential_manager.decrypt(encrypted_creds["public_key"]),
                "user_key": self.credential_manager.decrypt(encrypted_creds["user_key"])
            }
        except Exception as e:
            raise ConfigurationError(f"Failed to load credentials: {e}")

    def save_risk_config(self, mode: TradingMode, risk_config: RiskConfig) -> None:
        """Save risk configuration to database.
        
        Args:
            mode: Trading mode (DEMO or LIVE)
            risk_config: Risk configuration
        """
        try:
            from src.models.database import get_database
            from src.models.orm import RiskConfigORM
            
            db = get_database()
            session = db.get_session()
            
            try:
                # Check if config exists
                existing = session.query(RiskConfigORM).filter(
                    RiskConfigORM.mode == mode
                ).first()
                
                if existing:
                    # Update existing
                    existing.max_position_size_pct = risk_config.max_position_size_pct
                    existing.max_exposure_pct = risk_config.max_exposure_pct
                    existing.max_daily_loss_pct = risk_config.max_daily_loss_pct
                    existing.max_drawdown_pct = risk_config.max_drawdown_pct
                    existing.position_risk_pct = risk_config.position_risk_pct
                    existing.stop_loss_pct = risk_config.stop_loss_pct
                    existing.take_profit_pct = risk_config.take_profit_pct
                else:
                    # Create new
                    new_config = RiskConfigORM(
                        mode=mode,
                        max_position_size_pct=risk_config.max_position_size_pct,
                        max_exposure_pct=risk_config.max_exposure_pct,
                        max_daily_loss_pct=risk_config.max_daily_loss_pct,
                        max_drawdown_pct=risk_config.max_drawdown_pct,
                        position_risk_pct=risk_config.position_risk_pct,
                        stop_loss_pct=risk_config.stop_loss_pct,
                        take_profit_pct=risk_config.take_profit_pct
                    )
                    session.add(new_config)
                
                session.commit()
                logger.info(f"Saved risk configuration to database for {mode.value} mode")
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to save risk config to database: {e}")
            raise
        
        # Also save to file as backup (optional)
        try:
            if self.risk_config_file.exists():
                config = json.loads(self.risk_config_file.read_text())
            else:
                config = {}
            
            config[mode.value] = {
                "max_position_size_pct": risk_config.max_position_size_pct,
                "max_exposure_pct": risk_config.max_exposure_pct,
                "max_daily_loss_pct": risk_config.max_daily_loss_pct,
                "max_drawdown_pct": risk_config.max_drawdown_pct,
                "position_risk_pct": risk_config.position_risk_pct,
                "stop_loss_pct": risk_config.stop_loss_pct,
                "take_profit_pct": risk_config.take_profit_pct
            }
            
            self.risk_config_file.write_text(json.dumps(config, indent=2))
            logger.info(f"Saved risk configuration to file for {mode.value} mode (backup)")
        except Exception as e:
            logger.warning(f"Failed to save risk config to file: {e}")

    def load_risk_config(self, mode: TradingMode) -> RiskConfig:
        """Load risk configuration from database.
        
        Args:
            mode: Trading mode (DEMO or LIVE)
            
        Returns:
            Risk configuration (defaults if not found)
        """
        try:
            from src.models.database import get_database
            from src.models.orm import RiskConfigORM
            
            db = get_database()
            session = db.get_session()
            
            try:
                # Try to load from database first
                risk_config_orm = session.query(RiskConfigORM).filter(
                    RiskConfigORM.mode == mode
                ).first()
                
                if risk_config_orm:
                    logger.info(f"Loaded risk config from database for {mode.value}")
                    return RiskConfig(
                        max_position_size_pct=risk_config_orm.max_position_size_pct,
                        max_exposure_pct=risk_config_orm.max_exposure_pct,
                        max_daily_loss_pct=risk_config_orm.max_daily_loss_pct,
                        max_drawdown_pct=risk_config_orm.max_drawdown_pct,
                        position_risk_pct=risk_config_orm.position_risk_pct,
                        stop_loss_pct=risk_config_orm.stop_loss_pct,
                        take_profit_pct=risk_config_orm.take_profit_pct
                    )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Failed to load risk config from database: {e}")
        
        # Fallback to file-based config
        if not self.risk_config_file.exists():
            logger.info(f"No risk config found, using defaults for {mode.value}")
            return RiskConfig()
        
        try:
            config = json.loads(self.risk_config_file.read_text())
            mode_config = config.get(mode.value, {})
            return RiskConfig(**mode_config) if mode_config else RiskConfig()
        except Exception as e:
            logger.warning(f"Failed to load risk config from file: {e}, using defaults")
            return RiskConfig()

    def save_app_config(self, config: Dict[str, Any]) -> None:
        """Save application configuration.
        
        Args:
            config: Application configuration dictionary
        """
        self.app_config_file.write_text(json.dumps(config, indent=2))
        logger.info("Saved application configuration")

    def load_app_config(self) -> Dict[str, Any]:
        """Load application configuration.
        
        Returns:
            Application configuration dictionary (empty if not found)
        """
        if not self.app_config_file.exists():
            logger.info("No app config found, using defaults")
            return {}
        
        try:
            return json.loads(self.app_config_file.read_text())
        except Exception as e:
            logger.warning(f"Failed to load app config: {e}, using defaults")
            return {}

    def validate_credentials(self, mode: TradingMode) -> bool:
        """Validate that credentials exist for mode.
        
        Args:
            mode: Trading mode (DEMO or LIVE)
            
        Returns:
            True if credentials exist and can be loaded
        """
        try:
            creds = self.load_credentials(mode)
            return bool(creds.get("public_key") and creds.get("user_key"))
        except ConfigurationError:
            return False


# Global configuration instance
_config_instance: Optional[Configuration] = None


def get_config(config_dir: str = "config") -> Configuration:
    """Get or create global configuration instance.
    
    Args:
        config_dir: Directory for configuration files
        
    Returns:
        Configuration instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Configuration(config_dir)
    return _config_instance


def load_risk_config(mode: TradingMode) -> RiskConfig:
    """Load risk configuration from database (standalone helper function).
    
    This is a convenience function that wraps Configuration.load_risk_config()
    for easier importing in other modules.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        
    Returns:
        Risk configuration (defaults if not found)
    """
    config = get_config()
    return config.load_risk_config(mode)
