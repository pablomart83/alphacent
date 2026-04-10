"""
Comprehensive logging system with timestamp, severity, component, and context.

This module provides centralized logging configuration with:
- Categorization by component and severity level
- Rolling log files with automatic rotation
- Structured logging format with context
- Support for different log levels per component
"""

import logging
import logging.handlers
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class LogComponent(Enum):
    """Component categories for logging."""
    API = "api"
    STRATEGY = "strategy"
    RISK = "risk"
    EXECUTION = "execution"
    DATA = "data"
    LLM = "llm"
    SECURITY = "security"
    SYSTEM = "system"
    DATABASE = "database"
    VALIDATION = "validation"


class LogSeverity(Enum):
    """Severity levels for logging."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class ContextLogger:
    """Logger with component and context support."""
    
    def __init__(self, component: LogComponent, logger: logging.Logger):
        self.component = component
        self.logger = logger
    
    def _format_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Format message with component and context."""
        formatted = f"[{self.component.value.upper()}] {message}"
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            formatted = f"{formatted} | {context_str}"
        return formatted
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug message."""
        self.logger.debug(self._format_message(message, context))
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info message."""
        self.logger.info(self._format_message(message, context))
    
    def warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        self.logger.warning(self._format_message(message, context))
    
    def error(self, message: str, context: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        """Log error message."""
        self.logger.error(self._format_message(message, context), exc_info=exc_info)
    
    def critical(self, message: str, context: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        """Log critical message."""
        self.logger.critical(self._format_message(message, context), exc_info=exc_info)


class LoggingConfig:
    """Centralized logging configuration."""
    
    _initialized = False
    _loggers: Dict[LogComponent, ContextLogger] = {}
    
    @classmethod
    def initialize(
        cls,
        log_dir: Path = Path("logs"),
        log_level: LogSeverity = LogSeverity.INFO,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5,
        console_output: bool = True
    ):
        """
        Initialize logging system with rolling file handlers.
        
        Args:
            log_dir: Directory for log files
            log_level: Default log level
            max_bytes: Maximum size of each log file before rotation
            backup_count: Number of backup files to keep
            console_output: Whether to output logs to console
        """
        if cls._initialized:
            return
        
        # Create log directory
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level.value)
        
        # Remove existing handlers
        root_logger.handlers.clear()
        
        # Add console handler if requested
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level.value)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # Add main rotating file handler
        # Use single log file that rotates when it reaches max_bytes
        # This prevents creating a new file on every restart
        main_log_file = log_dir / "alphacent.log"
        file_handler = logging.handlers.RotatingFileHandler(
            main_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(log_level.value)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Create component-specific loggers
        for component in LogComponent:
            component_logger = logging.getLogger(f"alphacent.{component.value}")
            component_logger.setLevel(log_level.value)
            
            # Add component-specific file handler
            component_log_file = log_dir / f"{component.value}.log"
            component_handler = logging.handlers.RotatingFileHandler(
                component_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            component_handler.setLevel(log_level.value)
            component_handler.setFormatter(formatter)
            component_logger.addHandler(component_handler)
            
            # Create context logger
            cls._loggers[component] = ContextLogger(component, component_logger)
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, component: LogComponent) -> ContextLogger:
        """
        Get logger for specific component.
        
        Args:
            component: Component to get logger for
            
        Returns:
            ContextLogger for the component
        """
        if not cls._initialized:
            cls.initialize()
        
        return cls._loggers[component]
    
    @classmethod
    def set_level(cls, component: LogComponent, level: LogSeverity):
        """
        Set log level for specific component.
        
        Args:
            component: Component to set level for
            level: New log level
        """
        if not cls._initialized:
            cls.initialize()
        
        logger = cls._loggers[component].logger
        logger.setLevel(level.value)
        for handler in logger.handlers:
            handler.setLevel(level.value)
    
    @classmethod
    def set_global_level(cls, level: LogSeverity):
        """
        Set log level for all components.
        
        Args:
            level: New log level
        """
        if not cls._initialized:
            cls.initialize()
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level.value)
        for handler in root_logger.handlers:
            handler.setLevel(level.value)
        
        for component in LogComponent:
            cls.set_level(component, level)


# Convenience function for getting loggers
def get_logger(component: LogComponent) -> ContextLogger:
    """
    Get logger for specific component.
    
    Args:
        component: Component to get logger for
        
    Returns:
        ContextLogger for the component
    """
    return LoggingConfig.get_logger(component)
