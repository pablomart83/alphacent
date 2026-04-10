"""Tests for state manager."""

import tempfile
from pathlib import Path

import pytest

from src.data.backup_manager import BackupManager
from src.data.state_manager import StateManager


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
    """Create backup manager."""
    return BackupManager(backup_dir=temp_dirs["backup_dir"], max_backups=5)


@pytest.fixture
def state_manager(backup_manager, temp_dirs):
    """Create state manager."""
    data_dir = Path(temp_dirs["data_dir"])
    return StateManager(
        backup_manager=backup_manager,
        db_path=str(data_dir / "alphacent.db"),
        config_dir=str(data_dir / "config")
    )


@pytest.fixture
def sample_backup(backup_manager, temp_dirs):
    """Create a sample backup."""
    data_dir = Path(temp_dirs["data_dir"])
    
    # Create sample data
    db_file = data_dir / "alphacent.db"
    db_file.write_text("sample database content")
    
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "app_config.json").write_text('{"key": "value"}')
    
    # Create backup
    backup_path = backup_manager.create_backup(
        db_path=str(db_file),
        config_dir=str(config_dir)
    )
    
    # Clean up original files
    db_file.unlink()
    (config_dir / "app_config.json").unlink()
    
    return backup_path


def test_restore_from_latest_backup(state_manager, sample_backup):
    """Test restoring from latest backup."""
    result = state_manager.restore_from_backup()
    
    assert result is True
    assert state_manager.db_path.exists()
    assert (state_manager.config_dir / "app_config.json").exists()


def test_restore_from_specific_backup(state_manager, sample_backup):
    """Test restoring from specific backup."""
    result = state_manager.restore_from_backup(backup_path=sample_backup)
    
    assert result is True
    assert state_manager.db_path.exists()


def test_restore_without_config(state_manager, sample_backup):
    """Test restoring without configuration files."""
    result = state_manager.restore_from_backup(restore_config=False)
    
    assert result is True
    assert state_manager.db_path.exists()
    # Config should not be restored
    assert not (state_manager.config_dir / "app_config.json").exists()


def test_restore_no_backups_available(state_manager):
    """Test restoration when no backups available."""
    result = state_manager.restore_from_backup()
    
    assert result is False


def test_restore_corrupted_backup_fallback(backup_manager, state_manager, temp_dirs):
    """Test fallback to older backup when latest is corrupted."""
    data_dir = Path(temp_dirs["data_dir"])
    
    # Create first good backup
    db_file = data_dir / "alphacent.db"
    db_file.write_text("good database")
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "app_config.json").write_text('{"key": "value1"}')
    
    backup1 = backup_manager.create_backup(
        db_path=str(db_file),
        config_dir=str(config_dir)
    )
    
    # Create second backup and corrupt it
    db_file.write_text("newer database")
    (config_dir / "app_config.json").write_text('{"key": "value2"}')
    
    backup2 = backup_manager.create_backup(
        db_path=str(db_file),
        config_dir=str(config_dir)
    )
    
    # Corrupt the latest backup by removing database
    (backup2 / "alphacent.db").unlink()
    
    # Clean up original files
    db_file.unlink()
    (config_dir / "app_config.json").unlink()
    
    # Restore should fallback to backup1
    result = state_manager.restore_from_backup()
    
    assert result is True
    assert state_manager.db_path.exists()
    assert state_manager.db_path.read_text() == "good database"


def test_restore_on_startup_db_exists(state_manager, temp_dirs):
    """Test restore on startup when database already exists."""
    # Create existing database
    state_manager.db_path.parent.mkdir(parents=True, exist_ok=True)
    state_manager.db_path.write_text("existing database")
    
    result = state_manager.restore_on_startup()
    
    assert result is True
    assert state_manager.db_path.read_text() == "existing database"


def test_restore_on_startup_from_backup(state_manager, sample_backup):
    """Test restore on startup from backup."""
    result = state_manager.restore_on_startup()
    
    assert result is True
    assert state_manager.db_path.exists()


def test_restore_on_startup_default_state(state_manager):
    """Test restore on startup with default state when no backups."""
    result = state_manager.restore_on_startup()
    
    # Should initialize default state
    assert result is True
    assert state_manager.config_dir.exists()


def test_restore_backs_up_current_files(state_manager, sample_backup):
    """Test that current files are backed up before restoration."""
    # Create current database
    state_manager.db_path.parent.mkdir(parents=True, exist_ok=True)
    state_manager.db_path.write_text("current database")
    
    # Restore from backup
    state_manager.restore_from_backup()
    
    # Check that current database was backed up
    backup_file = state_manager.db_path.with_suffix(".db.backup")
    assert backup_file.exists()
    assert backup_file.read_text() == "current database"


def test_restore_with_logs(backup_manager, state_manager, temp_dirs):
    """Test restoring with log files."""
    data_dir = Path(temp_dirs["data_dir"])
    
    # Create sample data with logs
    db_file = data_dir / "alphacent.db"
    db_file.write_text("sample database")
    
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "app_config.json").write_text('{"key": "value"}')
    
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "app.log").write_text("log content")
    
    # Create backup with logs
    backup_path = backup_manager.create_backup(
        db_path=str(db_file),
        config_dir=str(config_dir),
        logs_dir=str(logs_dir),
        include_logs=True
    )
    
    # Clean up original files
    db_file.unlink()
    (config_dir / "app_config.json").unlink()
    (logs_dir / "app.log").unlink()
    
    # Restore with logs
    result = state_manager.restore_from_backup(restore_logs=True)
    
    assert result is True
    assert (Path("logs") / "app.log").exists()
    
    # Clean up
    (Path("logs") / "app.log").unlink()
