"""State restoration from backups with fallback handling."""

import logging
import shutil
from pathlib import Path
from typing import Optional

from src.data.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class StateManager:
    """Manages state restoration from backups."""

    def __init__(
        self,
        backup_manager: BackupManager,
        db_path: str = "alphacent.db",
        config_dir: str = "config"
    ):
        """Initialize state manager.
        
        Args:
            backup_manager: BackupManager instance
            db_path: Path to database file
            config_dir: Path to configuration directory
        """
        self.backup_manager = backup_manager
        self.db_path = Path(db_path)
        self.config_dir = Path(config_dir)
        
        logger.info("State manager initialized")

    def restore_from_backup(
        self,
        backup_path: Optional[Path] = None,
        restore_config: bool = True,
        restore_logs: bool = False
    ) -> bool:
        """Restore state from backup.
        
        Args:
            backup_path: Specific backup to restore from (uses latest if None)
            restore_config: Whether to restore configuration files
            restore_logs: Whether to restore log files
            
        Returns:
            True if restoration successful, False otherwise
        """
        try:
            # Get backup to restore from
            if backup_path is None:
                backup_path = self.backup_manager.get_latest_backup()
                if backup_path is None:
                    logger.error("No backups available for restoration")
                    return False
            
            logger.info(f"Restoring state from backup: {backup_path}")
            
            # Verify backup integrity
            if not self.backup_manager.verify_backup(backup_path):
                logger.error(f"Backup verification failed: {backup_path}")
                # Try fallback to older backup
                return self._try_fallback_restore(restore_config, restore_logs)
            
            # Restore database
            backup_db = backup_path / "alphacent.db"
            if backup_db.exists():
                # Backup current database before overwriting
                if self.db_path.exists():
                    backup_current = self.db_path.with_suffix(".db.backup")
                    shutil.copy2(self.db_path, backup_current)
                    logger.debug(f"Backed up current database to {backup_current}")
                
                shutil.copy2(backup_db, self.db_path)
                logger.info("Database restored successfully")
            else:
                logger.warning("No database found in backup")
            
            # Restore configuration
            if restore_config:
                backup_config = backup_path / "config"
                if backup_config.exists():
                    # Backup current config before overwriting
                    if self.config_dir.exists():
                        backup_current_config = Path(str(self.config_dir) + ".backup")
                        if backup_current_config.exists():
                            shutil.rmtree(backup_current_config)
                        shutil.copytree(self.config_dir, backup_current_config)
                        logger.debug(f"Backed up current config to {backup_current_config}")
                    
                    # Restore config files
                    self.config_dir.mkdir(parents=True, exist_ok=True)
                    for config_file in backup_config.glob("*"):
                        if config_file.is_file():
                            shutil.copy2(config_file, self.config_dir / config_file.name)
                    
                    logger.info("Configuration restored successfully")
                else:
                    logger.warning("No configuration found in backup")
            
            # Restore logs (optional)
            if restore_logs:
                backup_logs = backup_path / "logs"
                if backup_logs.exists():
                    logs_dir = Path("logs")
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    
                    for log_file in backup_logs.glob("*"):
                        if log_file.is_file():
                            shutil.copy2(log_file, logs_dir / log_file.name)
                    
                    logger.info("Logs restored successfully")
            
            logger.info("State restoration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"State restoration failed: {e}")
            # Try fallback to older backup
            return self._try_fallback_restore(restore_config, restore_logs)

    def _try_fallback_restore(
        self,
        restore_config: bool = True,
        restore_logs: bool = False
    ) -> bool:
        """Try to restore from older backups.
        
        Args:
            restore_config: Whether to restore configuration files
            restore_logs: Whether to restore log files
            
        Returns:
            True if fallback restoration successful, False otherwise
        """
        logger.info("Attempting fallback to older backups")
        
        backups = self.backup_manager.list_backups()
        
        # Skip the first (latest) backup since it already failed
        for backup_info in backups[1:]:
            backup_path = Path(backup_info["path"])
            logger.info(f"Trying fallback backup: {backup_path}")
            
            if self.backup_manager.verify_backup(backup_path):
                try:
                    # Recursively call restore with specific backup
                    # Set a flag to prevent infinite recursion
                    return self._restore_without_fallback(
                        backup_path,
                        restore_config,
                        restore_logs
                    )
                except Exception as e:
                    logger.error(f"Fallback restoration failed: {e}")
                    continue
        
        logger.error("All backup restoration attempts failed")
        return False

    def _restore_without_fallback(
        self,
        backup_path: Path,
        restore_config: bool,
        restore_logs: bool
    ) -> bool:
        """Restore from backup without fallback attempts.
        
        Args:
            backup_path: Backup to restore from
            restore_config: Whether to restore configuration files
            restore_logs: Whether to restore log files
            
        Returns:
            True if restoration successful, False otherwise
        """
        try:
            # Restore database
            backup_db = backup_path / "alphacent.db"
            if backup_db.exists():
                shutil.copy2(backup_db, self.db_path)
                logger.info("Database restored from fallback backup")
            
            # Restore configuration
            if restore_config:
                backup_config = backup_path / "config"
                if backup_config.exists():
                    self.config_dir.mkdir(parents=True, exist_ok=True)
                    for config_file in backup_config.glob("*"):
                        if config_file.is_file():
                            shutil.copy2(config_file, self.config_dir / config_file.name)
                    logger.info("Configuration restored from fallback backup")
            
            # Restore logs
            if restore_logs:
                backup_logs = backup_path / "logs"
                if backup_logs.exists():
                    logs_dir = Path("logs")
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    for log_file in backup_logs.glob("*"):
                        if log_file.is_file():
                            shutil.copy2(log_file, logs_dir / log_file.name)
                    logger.info("Logs restored from fallback backup")
            
            return True
            
        except Exception as e:
            logger.error(f"Fallback restoration failed: {e}")
            return False

    def restore_on_startup(
        self,
        restore_config: bool = True,
        restore_logs: bool = False
    ) -> bool:
        """Restore state on application startup.
        
        This method checks if database exists. If not, attempts to restore
        from the latest backup. If all backups fail, starts with default state.
        
        Args:
            restore_config: Whether to restore configuration files
            restore_logs: Whether to restore log files
            
        Returns:
            True if restoration successful or not needed, False if failed
        """
        # Check if database exists
        if self.db_path.exists():
            logger.info("Database exists, no restoration needed")
            return True
        
        logger.info("Database not found, attempting restoration from backup")
        
        # Try to restore from backup
        if self.restore_from_backup(restore_config=restore_config, restore_logs=restore_logs):
            logger.info("State restored from backup on startup")
            return True
        
        # All backups failed, start with default state
        logger.warning("All backup restoration attempts failed, starting with default state")
        return self._initialize_default_state()

    def _initialize_default_state(self) -> bool:
        """Initialize with default state when no backups available.
        
        Returns:
            True if initialization successful
        """
        try:
            logger.info("Initializing default state")
            
            # Create empty database (will be initialized by Database class)
            # Just ensure the directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create default config directory
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info("Default state initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize default state: {e}")
            return False


class StateRestorationError(Exception):
    """State restoration errors."""
    pass
