"""
Service dependency manager for AlphaCent Trading Platform.

Manages platform service lifecycle and health checking.
Strategy generation uses templates (no external LLM dependency).
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ServiceHealthStatus(str, Enum):
    """Service health status."""
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class ServiceStatus:
    """Service status information."""
    name: str
    is_healthy: bool
    status: ServiceHealthStatus
    endpoint: str
    last_check: datetime
    error_message: Optional[str] = None


class ServiceManager:
    """
    Manages platform service lifecycle.
    
    No external service dependencies — strategy generation uses
    template-based approach with market statistics analysis.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.services: Dict = {}  # No external services required
        self._health_check_thread: Optional[threading.Thread] = None
        self._stop_health_check = threading.Event()
        logger.info("ServiceManager initialized (no external service dependencies)")
    
    def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check status of all dependent services. Currently none required."""
        return {}
    
    def ensure_services_running(self) -> Tuple[bool, List[str]]:
        """
        Ensure all required services are running.
        No external services required — always returns healthy.
        """
        return True, []
    
    def start_health_checks(self):
        """Start periodic health checks (no-op, no external services)."""
        logger.info("Health checks: no external services to monitor")
    
    def stop_health_checks(self):
        """Stop periodic health checks."""
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._stop_health_check.set()
            self._health_check_thread.join(timeout=5)
            logger.info("Health check thread stopped")
    
    def start_service(self, service_name: str) -> bool:
        raise ValueError(f"Unknown service: {service_name}")
    
    def stop_service(self, service_name: str) -> bool:
        raise ValueError(f"Unknown service: {service_name}")
    
    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        return None


# Global service manager instance
_service_manager: Optional[ServiceManager] = None


def get_service_manager() -> ServiceManager:
    """
    Get or create global service manager instance.
    
    Returns:
        ServiceManager instance
    """
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
