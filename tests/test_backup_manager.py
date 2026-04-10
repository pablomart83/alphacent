"""Tests for backup manager."""

import json
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.data.backup_manager import BackupError, BackupManager, BackupScheduler


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as backup_dir, \
         tempfile.TemporaryDirectory() as data_dir:
        yield {
            "backup_dir": backup_dir,
            "data_dir": data_dir
        }


@pytest.fixture
def backup_manager(temp_dirs):
    """Create backup manager with temp directory."""
    return BackupManager(backup_dir=temp_dirs["backup_dir"], max_backups=3)


@pytest.fixture
def sample_data(temp_dirs):
    """Create sample data files for backup."""
    data_dir = Path(temp_dirs["data_dir"])
    
    # Create sample database
    db_file = data_dir / "alphacent.db"
    db_file.write_text("sample database content")
    
    # Create sample config
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "app_config.json").write_text('{"key": "value"}')
    (config_dir / "risk_config.json").write_text('{"max_loss": 0.03}')
    
    # Create sample logs
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "app.log").write_text("log content")
    
    return {
        "db_path": str(db_file),
        "config_dir": str(config_dir),
        "logs_dir": str(logs_dir)
    }


def test_create_backup(backup_manager, sample_data):
    """Test creating a backup."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"],
        include_logs=False
    )
    
    assert backup_path.exists()
    assert backup_path.is_dir()
    
    # Verify database backed up
    assert (backup_path / "alphacent.db").exists()
    
    # Verify config backed up
    assert (backup_path / "config").exists()
    assert (backup_path / "config" / "app_config.json").exists()
    assert (backup_path / "config" / "risk_config.json").exists()
    
    # Verify metadata created
    assert (backup_path / "backup_metadata.json").exists()
    metadata = json.loads((backup_path / "backup_metadata.json").read_text())
    assert "timestamp" in metadata
    assert "created_at" in metadata


def test_create_backup_with_logs(backup_manager, sample_data):
    """Test creating backup with logs included."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"],
        logs_dir=sample_data["logs_dir"],
        include_logs=True
    )
    
    # Verify logs backed up
    assert (backup_path / "logs").exists()
    assert (backup_path / "logs" / "app.log").exists()


def test_list_backups(backup_manager, sample_data):
    """Test listing backups."""
    # Create multiple backups with slight delay
    backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    time.sleep(0.01)  # Small delay to ensure different microsecond timestamps
    backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    backups = backup_manager.list_backups()
    assert len(backups) == 2
    
    # Verify sorted by timestamp (newest first)
    assert backups[0]["timestamp"] > backups[1]["timestamp"]


def test_get_latest_backup(backup_manager, sample_data):
    """Test getting latest backup."""
    # No backups initially
    assert backup_manager.get_latest_backup() is None
    
    # Create backups
    backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    time.sleep(0.1)
    backup_path2 = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    latest = backup_manager.get_latest_backup()
    assert latest == backup_path2


def test_delete_backup(backup_manager, sample_data):
    """Test deleting a backup."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    assert backup_path.exists()
    
    backup_manager.delete_backup(backup_path)
    
    assert not backup_path.exists()


def test_backup_rotation(backup_manager, sample_data):
    """Test automatic cleanup of old backups."""
    # Create more backups than max_backups
    for i in range(5):
        backup_manager.create_backup(
            db_path=sample_data["db_path"],
            config_dir=sample_data["config_dir"]
        )
        time.sleep(0.1)
    
    # Should only keep max_backups (3)
    backups = backup_manager.list_backups()
    assert len(backups) <= 3


def test_verify_backup_valid(backup_manager, sample_data):
    """Test verifying a valid backup."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    assert backup_manager.verify_backup(backup_path) is True


def test_verify_backup_missing_db(backup_manager, sample_data, temp_dirs):
    """Test verifying backup with missing database."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    # Remove database file
    (backup_path / "alphacent.db").unlink()
    
    assert backup_manager.verify_backup(backup_path) is False


def test_verify_backup_invalid_metadata(backup_manager, sample_data):
    """Test verifying backup with invalid metadata."""
    backup_path = backup_manager.create_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    # Corrupt metadata
    (backup_path / "backup_metadata.json").write_text("invalid json")
    
    assert backup_manager.verify_backup(backup_path) is False


def test_backup_scheduler_should_backup(backup_manager):
    """Test backup scheduler timing."""
    scheduler = BackupScheduler(backup_manager, interval_hours=1)
    
    # Should backup initially
    assert scheduler.should_backup() is True
    
    # Mark as backed up
    scheduler.last_backup_time = datetime.now()
    
    # Should not backup immediately
    assert scheduler.should_backup() is False


def test_backup_scheduler_run_backup(backup_manager, sample_data):
    """Test scheduled backup execution."""
    scheduler = BackupScheduler(backup_manager, interval_hours=1)
    
    # Should run backup
    backup_path = scheduler.run_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    assert backup_path is not None
    assert backup_path.exists()
    
    # Should not run again immediately
    backup_path2 = scheduler.run_backup(
        db_path=sample_data["db_path"],
        config_dir=sample_data["config_dir"]
    )
    
    assert backup_path2 is None


def test_create_backup_missing_files(backup_manager):
    """Test creating backup with missing source files."""
    # Should not raise error, just log warnings
    backup_path = backup_manager.create_backup(
        db_path="nonexistent.db",
        config_dir="nonexistent_config"
    )
    
    assert backup_path.exists()
    assert (backup_path / "backup_metadata.json").exists()
