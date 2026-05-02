"""
Comprehensive logging system with timestamp, severity, component, and context.

This module provides centralized logging configuration with:
- Categorization by component and severity level
- Rolling log files with automatic rotation
- Structured logging format with context
- Support for different log levels per component

Log files:
  logs/alphacent.log   — full INFO+ audit trail (rotates at 10MB, 5 backups)
  logs/errors.log      — ERROR and CRITICAL only (near-empty on healthy days)
  logs/warnings.log    — WARNING only (position sizing bumps, stale data, etc.)
  logs/<component>.log — per-component INFO+ (api, strategy, risk, execution, data, ...)
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


# Map source module prefixes to LogComponent for automatic routing
_MODULE_TO_COMPONENT = {
    'src.api':        LogComponent.API,
    'src.strategy':   LogComponent.STRATEGY,
    'src.risk':       LogComponent.RISK,
    'src.execution':  LogComponent.EXECUTION,
    'src.data':       LogComponent.DATA,
    'src.models':     LogComponent.DATABASE,
    'src.core':       LogComponent.SYSTEM,
    'src.analytics':  LogComponent.STRATEGY,
    'src.ml':         LogComponent.STRATEGY,
}


class ComponentRoutingFilter(logging.Filter):
    """Routes log records to the correct component file handler based on module name."""

    def __init__(self, component: LogComponent):
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        # Accept records whose module name starts with the component's prefix(es)
        for prefix, comp in _MODULE_TO_COMPONENT.items():
            if record.name.startswith(prefix) and comp == self.component:
                return True
        return False


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
        self.logger.debug(self._format_message(message, context))

    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.logger.info(self._format_message(message, context))

    def warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.logger.warning(self._format_message(message, context))

    def error(self, message: str, context: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        self.logger.error(self._format_message(message, context), exc_info=exc_info)

    def critical(self, message: str, context: Optional[Dict[str, Any]] = None, exc_info: bool = False):
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
        backup_count: int = 100,  # 100 × 10MB = 1GB main log = ~36-48h history at current rate
        console_output: bool = True
    ):
        """
        Initialize logging system with rolling file handlers.

        Creates:
          alphacent.log  — full INFO+ audit trail
          errors.log     — ERROR and CRITICAL only
          warnings.log   — WARNING only
          <component>.log — per-component INFO+ for api/strategy/risk/execution/data/...
        """
        if cls._initialized:
            return

        log_dir.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level.value)
        root_logger.handlers.clear()

        # ── Console handler ──────────────────────────────────────────────────
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level.value)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        # ── Main log: full INFO+ audit trail ─────────────────────────────────
        main_handler = logging.handlers.RotatingFileHandler(
            log_dir / "alphacent.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        main_handler.setLevel(log_level.value)
        main_handler.setFormatter(formatter)
        root_logger.addHandler(main_handler)

        # ── errors.log: ERROR and CRITICAL only ──────────────────────────────
        # Near-empty on a healthy day. Any entry here needs attention.
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "errors.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

        # ── warnings.log: WARNING only ───────────────────────────────────────
        # Position sizing bumps, stale data, minor issues. Review periodically.
        class WarningOnlyFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                return record.levelno == logging.WARNING

        warning_handler = logging.handlers.RotatingFileHandler(
            log_dir / "warnings.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        warning_handler.setLevel(logging.WARNING)
        warning_handler.addFilter(WarningOnlyFilter())
        warning_handler.setFormatter(formatter)
        root_logger.addHandler(warning_handler)

        # ── Component-specific logs: routed by module name prefix ────────────
        # Each component file captures INFO+ from its own source modules.
        # e.g. strategy.log gets everything from src.strategy.*, src.analytics.*, src.ml.*
        # Component logs are for targeted debugging. Matched to main-log retention
        # (50 backups × 10MB = 500MB per component) so cross-component investigation
        # spans the same time window as the main audit trail.
        component_backup_count = 50
        for component in LogComponent:
            handler = logging.handlers.RotatingFileHandler(
                log_dir / f"{component.value}.log",
                maxBytes=max_bytes,
                backupCount=component_backup_count
            )
            handler.setLevel(log_level.value)
            handler.setFormatter(formatter)
            handler.addFilter(ComponentRoutingFilter(component))
            root_logger.addHandler(handler)

            component_logger = logging.getLogger(f"alphacent.{component.value}")
            component_logger.setLevel(log_level.value)
            cls._loggers[component] = ContextLogger(component, component_logger)

        cls._initialized = True

    @classmethod
    def get_logger(cls, component: LogComponent) -> ContextLogger:
        if not cls._initialized:
            cls.initialize()
        return cls._loggers[component]

    @classmethod
    def set_level(cls, component: LogComponent, level: LogSeverity):
        if not cls._initialized:
            cls.initialize()
        logger = cls._loggers[component].logger
        logger.setLevel(level.value)
        for handler in logger.handlers:
            handler.setLevel(level.value)

    @classmethod
    def set_global_level(cls, level: LogSeverity):
        if not cls._initialized:
            cls.initialize()
        root_logger = logging.getLogger()
        root_logger.setLevel(level.value)
        for handler in root_logger.handlers:
            handler.setLevel(level.value)
        for component in LogComponent:
            cls.set_level(component, level)


def get_logger(component: LogComponent) -> ContextLogger:
    return LoggingConfig.get_logger(component)
