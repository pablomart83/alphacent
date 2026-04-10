"""Automatic backup system for critical data with rotation."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models import Strategy, RiskConfig, TradingMode

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages automatic backups of critical data with rotation."""

    def __init__(
        self,
        backup_dir: str = "backups",
        max_backups: int = 10
    ):
        """Initialize backup manager.
        
        Args:
            backup_dir: Directory for backups
            max_backups: Maximum number of backups to keep
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups
        
        logger.info(f"Backup manager initialized at {self.backup_dir}")

    def create_backup(
        self,
        db_path: str = "alphacent.db",
        config_dir: str = "config",
        logs_dir: Optional[str] = None,
        include_logs: bool = False
    ) -> Path:
        """Create backup of critical data.
        
        Args:
            db_path: Path to database file
            config_dir: Path to configuration directory
            logs_dir: Path to logs directory (optional, auto-detected if not provided)
            include_logs: Whether to include log files
            
        Returns:
            Path to created backup directory
            
        Raises:
            BackupError: If backup creation fails
        """
        try:
            # Create timestamped backup directory with microseconds for uniqueness
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_path = self.backup_dir / f"backup_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Creating backup at {backup_path}")
            
            # Backup database
            db_file = Path(db_path)
            if db_file.exists():
                shutil.copy2(db_file, backup_path / "alphacent.db")
                logger.debug("Backed up database")
            else:
                logger.warning(f"Database file not found: {db_path}")
            
            # Backup configuration
            config_path = Path(config_dir)
            if config_path.exists():
                backup_config_dir = backup_path / "config"
                backup_config_dir.mkdir(exist_ok=True)
                
                # Copy all config files
                for config_file in config_path.glob("*"):
                    if config_file.is_file():
                        shutil.copy2(config_file, backup_config_dir / config_file.name)
                
                logger.debug("Backed up configuration")
            else:
                logger.warning(f"Config directory not found: {config_dir}")
            
            # Optionally backup logs
            if include_logs:
                # Use provided logs_dir or try to auto-detect
                if logs_dir:
                    logs_path = Path(logs_dir)
                else:
                    logs_path = Path("logs")
                    # Check in data directory if logs not in current dir
                    if not logs_path.exists():
                        # Try relative to config_dir parent
                        alt_logs_path = Path(config_dir).parent / "logs"
                        if alt_logs_path.exists():
                            logs_path = alt_logs_path
                
                if logs_path.exists():
                    backup_logs_dir = backup_path / "logs"
                    shutil.copytree(logs_path, backup_logs_dir, dirs_exist_ok=True)
                    logger.debug("Backed up logs")
                else:
                    logger.warning("Logs directory not found")
            
            # Create backup metadata
            metadata = {
                "timestamp": timestamp,
                "created_at": datetime.now().isoformat(),
                "db_path": db_path,
                "config_dir": config_dir,
                "logs_dir": logs_dir,
                "include_logs": include_logs
            }
            
            metadata_file = backup_path / "backup_metadata.json"
            metadata_file.write_text(json.dumps(metadata, indent=2))
            
            logger.info(f"Backup created successfully at {backup_path}")
            
            # Cleanup old backups
            self._cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise BackupError(f"Backup creation failed: {e}")

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups.
        
        Returns:
            List of backup information dictionaries
        """
        backups = []
        
        for backup_path in sorted(self.backup_dir.glob("backup_*"), reverse=True):
            if not backup_path.is_dir():
                continue
            
            metadata_file = backup_path / "backup_metadata.json"
            if metadata_file.exists():
                try:
                    metadata = json.loads(metadata_file.read_text())
                    metadata["path"] = str(backup_path)
                    backups.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to read backup metadata: {e}")
            else:
                # Create basic metadata from directory name
                backups.append({
                    "path": str(backup_path),
                    "timestamp": backup_path.name.replace("backup_", ""),
                    "created_at": datetime.fromtimestamp(
                        backup_path.stat().st_mtime
                    ).isoformat()
                })
        
        return backups

    def get_latest_backup(self) -> Optional[Path]:
        """Get path to most recent backup.
        
        Returns:
            Path to latest backup directory, or None if no backups exist
        """
        backups = list(sorted(self.backup_dir.glob("backup_*"), reverse=True))
        return backups[0] if backups else None

    def delete_backup(self, backup_path: Path) -> None:
        """Delete a specific backup.
        
        Args:
            backup_path: Path to backup directory to delete
        """
        try:
            if backup_path.exists() and backup_path.is_dir():
                shutil.rmtree(backup_path)
                logger.info(f"Deleted backup: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_path}: {e}")

    def _cleanup_old_backups(self) -> None:
        """Remove old backups beyond max_backups limit."""
        backups = sorted(
            self.backup_dir.glob("backup_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove old backups
        for backup in backups[self.max_backups:]:
            self.delete_backup(backup)
            logger.info(f"Removed old backup: {backup}")

    def verify_backup(self, backup_path: Path) -> bool:
        """Verify backup integrity.
        
        Args:
            backup_path: Path to backup directory
            
        Returns:
            True if backup is valid, False otherwise
        """
        try:
            # Check backup directory exists
            if not backup_path.exists() or not backup_path.is_dir():
                logger.error(f"Backup directory not found: {backup_path}")
                return False
            
            # Check for database file
            db_file = backup_path / "alphacent.db"
            if not db_file.exists():
                logger.error(f"Database file missing in backup: {backup_path}")
                return False
            
            # Check for config directory
            config_dir = backup_path / "config"
            if not config_dir.exists():
                logger.warning(f"Config directory missing in backup: {backup_path}")
                # Not critical, continue
            
            # Check metadata
            metadata_file = backup_path / "backup_metadata.json"
            if metadata_file.exists():
                try:
                    json.loads(metadata_file.read_text())
                except json.JSONDecodeError:
                    logger.error(f"Invalid metadata in backup: {backup_path}")
                    return False
            
            logger.info(f"Backup verification passed: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False


class BackupError(Exception):
    """Backup-related errors."""
    pass


class BackupScheduler:
    """Schedules automatic backups at regular intervals."""

    def __init__(
        self,
        backup_manager: BackupManager,
        interval_hours: int = 24
    ):
        """Initialize backup scheduler.
        
        Args:
            backup_manager: BackupManager instance
            interval_hours: Hours between automatic backups
        """
        self.backup_manager = backup_manager
        self.interval_hours = interval_hours
        self.last_backup_time: Optional[datetime] = None
        
        logger.info(f"Backup scheduler initialized (interval: {interval_hours}h)")

    def should_backup(self) -> bool:
        """Check if backup should be performed.
        
        Returns:
            True if backup is due
        """
        if self.last_backup_time is None:
            return True
        
        hours_since_backup = (
            datetime.now() - self.last_backup_time
        ).total_seconds() / 3600
        
        return hours_since_backup >= self.interval_hours

    def run_backup(
        self,
        db_path: str = "alphacent.db",
        config_dir: str = "config",
        logs_dir: Optional[str] = None,
        include_logs: bool = False
    ) -> Optional[Path]:
        """Run backup if due.
        
        Args:
            db_path: Path to database file
            config_dir: Path to configuration directory
            logs_dir: Path to logs directory (optional)
            include_logs: Whether to include log files
            
        Returns:
            Path to backup if created, None if not due
        """
        if not self.should_backup():
            logger.debug("Backup not due yet")
            return None
        
        try:
            backup_path = self.backup_manager.create_backup(
                db_path=db_path,
                config_dir=config_dir,
                logs_dir=logs_dir,
                include_logs=include_logs
            )
            self.last_backup_time = datetime.now()
            logger.info(f"Scheduled backup completed: {backup_path}")
            return backup_path
        except BackupError as e:
            logger.error(f"Scheduled backup failed: {e}")
            return None
