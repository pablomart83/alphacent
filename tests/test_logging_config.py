"""Unit tests for comprehensive error logging system."""

import logging
import pytest
import tempfile
from pathlib import Path

from src.core.logging_config import (
    LogComponent,
    LogSeverity,
    LoggingConfig,
    ContextLogger,
    get_logger
)


@pytest.fixture
def temp_log_dir():
    """Create temporary log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test."""
    LoggingConfig._initialized = False
    LoggingConfig._loggers.clear()
    logging.getLogger().handlers.clear()
    yield
    LoggingConfig._initialized = False
    LoggingConfig._loggers.clear()
    logging.getLogger().handlers.clear()


def test_logging_initialization(temp_log_dir):
    """Test logging system initializes correctly."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    assert LoggingConfig._initialized
    assert len(LoggingConfig._loggers) == len(LogComponent)
    
    # Check main log file created
    log_files = list(temp_log_dir.glob("alphacent_*.log"))
    assert len(log_files) == 1
    
    # Check component log files created
    for component in LogComponent:
        component_log = temp_log_dir / f"{component.value}.log"
        assert component_log.exists()


def test_get_logger_returns_context_logger(temp_log_dir):
    """Test get_logger returns ContextLogger instance."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.API)
    
    assert isinstance(logger, ContextLogger)
    assert logger.component == LogComponent.API


def test_logger_formats_message_with_component(temp_log_dir):
    """Test logger formats messages with component prefix."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.STRATEGY)
    logger.info("Test message")
    
    # Read log file
    log_file = temp_log_dir / "strategy.log"
    content = log_file.read_text()
    
    assert "[STRATEGY]" in content
    assert "Test message" in content


def test_logger_formats_message_with_context(temp_log_dir):
    """Test logger formats messages with context."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.RISK)
    logger.info("Position validated", context={"symbol": "AAPL", "size": 100})
    
    # Read log file
    log_file = temp_log_dir / "risk.log"
    content = log_file.read_text()
    
    assert "[RISK]" in content
    assert "Position validated" in content
    assert "symbol=AAPL" in content
    assert "size=100" in content


def test_logger_severity_levels(temp_log_dir):
    """Test all severity levels work correctly."""
    LoggingConfig.initialize(
        log_dir=temp_log_dir,
        log_level=LogSeverity.DEBUG,
        console_output=False
    )
    
    logger = get_logger(LogComponent.EXECUTION)
    
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
    
    # Read log file
    log_file = temp_log_dir / "execution.log"
    content = log_file.read_text()
    
    assert "DEBUG" in content
    assert "INFO" in content
    assert "WARNING" in content
    assert "ERROR" in content
    assert "CRITICAL" in content


def test_set_component_log_level(temp_log_dir):
    """Test setting log level for specific component."""
    LoggingConfig.initialize(
        log_dir=temp_log_dir,
        log_level=LogSeverity.INFO,
        console_output=False
    )
    
    # Set API component to DEBUG
    LoggingConfig.set_level(LogComponent.API, LogSeverity.DEBUG)
    
    api_logger = get_logger(LogComponent.API)
    strategy_logger = get_logger(LogComponent.STRATEGY)
    
    api_logger.debug("API debug message")
    strategy_logger.debug("Strategy debug message")
    
    # API log should contain debug message
    api_log = temp_log_dir / "api.log"
    api_content = api_log.read_text()
    assert "API debug message" in api_content
    
    # Strategy log should not contain debug message (INFO level)
    strategy_log = temp_log_dir / "strategy.log"
    strategy_content = strategy_log.read_text()
    assert "Strategy debug message" not in strategy_content


def test_set_global_log_level(temp_log_dir):
    """Test setting log level globally."""
    LoggingConfig.initialize(
        log_dir=temp_log_dir,
        log_level=LogSeverity.INFO,
        console_output=False
    )
    
    # Set global level to WARNING
    LoggingConfig.set_global_level(LogSeverity.WARNING)
    
    logger = get_logger(LogComponent.DATA)
    
    logger.info("Info message")
    logger.warning("Warning message")
    
    # Read log file
    log_file = temp_log_dir / "data.log"
    content = log_file.read_text()
    
    # Info should not be logged
    assert "Info message" not in content
    # Warning should be logged
    assert "Warning message" in content


def test_log_rotation_configuration(temp_log_dir):
    """Test log rotation is configured correctly."""
    max_bytes = 1024  # 1 KB
    backup_count = 3
    
    LoggingConfig.initialize(
        log_dir=temp_log_dir,
        max_bytes=max_bytes,
        backup_count=backup_count,
        console_output=False
    )
    
    # Check root logger handler configuration
    root_logger = logging.getLogger()
    found_rotating_handler = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            assert handler.maxBytes == max_bytes
            assert handler.backupCount == backup_count
            found_rotating_handler = True
            break
    
    assert found_rotating_handler, "No RotatingFileHandler found"


def test_error_with_exception_info(temp_log_dir):
    """Test logging errors with exception information."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.DATABASE)
    
    try:
        raise ValueError("Test exception")
    except ValueError:
        logger.error("Database error occurred", exc_info=True)
    
    # Read log file
    log_file = temp_log_dir / "database.log"
    content = log_file.read_text()
    
    assert "Database error occurred" in content
    assert "ValueError: Test exception" in content
    assert "Traceback" in content


def test_multiple_components_log_independently(temp_log_dir):
    """Test different components log to separate files."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    api_logger = get_logger(LogComponent.API)
    risk_logger = get_logger(LogComponent.RISK)
    
    api_logger.info("API message")
    risk_logger.info("Risk message")
    
    # Check API log
    api_log = temp_log_dir / "api.log"
    api_content = api_log.read_text()
    assert "API message" in api_content
    assert "Risk message" not in api_content
    
    # Check Risk log
    risk_log = temp_log_dir / "risk.log"
    risk_content = risk_log.read_text()
    assert "Risk message" in risk_content
    assert "API message" not in risk_content


def test_timestamp_format_in_logs(temp_log_dir):
    """Test timestamp format is correct."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.SECURITY)
    logger.info("Test message")
    
    # Read log file
    log_file = temp_log_dir / "security.log"
    content = log_file.read_text()
    
    # Check timestamp format: YYYY-MM-DD HH:MM:SS
    import re
    timestamp_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
    assert re.search(timestamp_pattern, content)


def test_auto_initialization_on_first_use(temp_log_dir):
    """Test logging auto-initializes on first use."""
    # Don't call initialize explicitly
    logger = get_logger(LogComponent.VALIDATION)
    
    assert LoggingConfig._initialized
    assert isinstance(logger, ContextLogger)


def test_context_with_multiple_fields(temp_log_dir):
    """Test logging with multiple context fields."""
    LoggingConfig.initialize(log_dir=temp_log_dir, console_output=False)
    
    logger = get_logger(LogComponent.EXECUTION)
    logger.info(
        "Order executed",
        context={
            "order_id": "12345",
            "symbol": "TSLA",
            "quantity": 50,
            "price": 250.50
        }
    )
    
    # Read log file
    log_file = temp_log_dir / "execution.log"
    content = log_file.read_text()
    
    assert "order_id=12345" in content
    assert "symbol=TSLA" in content
    assert "quantity=50" in content
    # Price may be formatted as 250.5 or 250.50
    assert "price=250.5" in content
