"""
Graceful degradation system for AlphaCent.

This module provides:
- Fallback behavior for non-critical component failures
- Continued core operations when optional features fail
- Degraded mode activation logging
- Component health tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Callable, Dict, List, Optional, Set

from src.core.logging_config import LogComponent, get_logger
from src.core.notification_system import get_notification_system


logger = get_logger(LogComponent.SYSTEM)


class ComponentCriticality(Enum):
    """Component criticality levels."""
    CRITICAL = "critical"  # System cannot function without this
    IMPORTANT = "important"  # Core features affected but system can continue
    OPTIONAL = "optional"  # Nice-to-have features, system fully functional without


class ComponentStatus(Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    criticality: ComponentCriticality
    status: ComponentStatus
    last_check: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    fallback_active: bool = False
    fallback_description: Optional[str] = None


@dataclass
class DegradedModeConfig:
    """Configuration for degraded mode behavior."""
    component: str
    criticality: ComponentCriticality
    fallback_handler: Optional[Callable] = None
    fallback_description: Optional[str] = None
    disable_on_failure: bool = False


class GracefulDegradationManager:
    """
    Manages graceful degradation for component failures.
    
    Tracks component health and activates fallback behaviors when
    non-critical components fail.
    """
    
    def __init__(self):
        """Initialize graceful degradation manager."""
        self._components: Dict[str, ComponentHealth] = {}
        self._configs: Dict[str, DegradedModeConfig] = {}
        self._degraded_components: Set[str] = set()
        self._lock = Lock()
        self._notification_system = get_notification_system()
        
        logger.info("Graceful degradation manager initialized")
    
    def register_component(
        self,
        name: str,
        criticality: ComponentCriticality,
        fallback_handler: Optional[Callable] = None,
        fallback_description: Optional[str] = None,
        disable_on_failure: bool = False
    ):
        """
        Register a component for health tracking.
        
        Args:
            name: Component name
            criticality: Component criticality level
            fallback_handler: Optional fallback function to call on failure
            fallback_description: Description of fallback behavior
            disable_on_failure: Whether to disable component on failure
        """
        with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                criticality=criticality,
                status=ComponentStatus.HEALTHY
            )
            
            self._configs[name] = DegradedModeConfig(
                component=name,
                criticality=criticality,
                fallback_handler=fallback_handler,
                fallback_description=fallback_description,
                disable_on_failure=disable_on_failure
            )
            
            logger.info(
                f"Registered component: {name}",
                context={
                    "criticality": criticality.value,
                    "has_fallback": fallback_handler is not None
                }
            )
    
    def report_failure(
        self,
        component: str,
        error_message: str,
        activate_fallback: bool = True
    ) -> bool:
        """
        Report a component failure and activate fallback if available.
        
        Args:
            component: Component name
            error_message: Error description
            activate_fallback: Whether to activate fallback behavior
            
        Returns:
            True if system can continue (non-critical or fallback available)
        """
        with self._lock:
            if component not in self._components:
                logger.warning(f"Unknown component reported failure: {component}")
                return True
            
            health = self._components[component]
            config = self._configs[component]
            
            # Update component status
            health.status = ComponentStatus.FAILED
            health.error_message = error_message
            health.last_check = datetime.now()
            
            # Log failure
            logger.error(
                f"Component failure: {component}",
                context={
                    "criticality": health.criticality.value,
                    "error": error_message
                }
            )
            
            # Check criticality
            if health.criticality == ComponentCriticality.CRITICAL:
                # Critical component failed - system cannot continue
                logger.critical(
                    f"CRITICAL component failed: {component}",
                    context={"error": error_message}
                )
                
                self._notification_system.send_critical_error(
                    title=f"Critical Component Failure: {component}",
                    message=f"System cannot continue. Error: {error_message}",
                    component=component,
                    suggested_actions=[
                        "Check component logs for details",
                        "Restart the system",
                        "Contact support if issue persists"
                    ]
                )
                
                return False
            
            # Non-critical component - activate degraded mode
            self._degraded_components.add(component)
            
            # Activate fallback if available
            if activate_fallback and config.fallback_handler:
                try:
                    config.fallback_handler()
                    health.fallback_active = True
                    health.fallback_description = config.fallback_description
                    health.status = ComponentStatus.DEGRADED
                    
                    logger.warning(
                        f"Activated fallback for {component}",
                        context={"fallback": config.fallback_description}
                    )
                except Exception as e:
                    logger.error(
                        f"Fallback activation failed for {component}: {e}",
                        exc_info=True
                    )
            
            # Disable component if configured
            if config.disable_on_failure:
                health.status = ComponentStatus.DISABLED
                logger.warning(f"Component disabled: {component}")
            
            # Log degraded mode activation
            logger.warning(
                f"Degraded mode activated for {component}",
                context={
                    "criticality": health.criticality.value,
                    "fallback_active": health.fallback_active,
                    "total_degraded": len(self._degraded_components)
                }
            )
            
            # Send notification
            self._notification_system.send_warning(
                title=f"Component Degraded: {component}",
                message=f"System continuing with reduced functionality. Error: {error_message}",
                component=component,
                suggested_actions=self._get_suggested_actions(component, health),
                context={
                    "criticality": health.criticality.value,
                    "fallback_active": health.fallback_active
                }
            )
            
            return True
    
    def report_recovery(self, component: str):
        """
        Report component recovery from failure.
        
        Args:
            component: Component name
        """
        with self._lock:
            if component not in self._components:
                logger.warning(f"Unknown component reported recovery: {component}")
                return
            
            health = self._components[component]
            
            # Update status
            health.status = ComponentStatus.HEALTHY
            health.error_message = None
            health.fallback_active = False
            health.fallback_description = None
            health.last_check = datetime.now()
            
            # Remove from degraded set
            self._degraded_components.discard(component)
            
            logger.info(
                f"Component recovered: {component}",
                context={"degraded_count": len(self._degraded_components)}
            )
            
            # Send notification
            self._notification_system.send_info(
                title=f"Component Recovered: {component}",
                message=f"Component is now healthy and fully functional.",
                component=component
            )
    
    def is_degraded(self) -> bool:
        """
        Check if system is in degraded mode.
        
        Returns:
            True if any components are degraded
        """
        with self._lock:
            return len(self._degraded_components) > 0
    
    def get_degraded_components(self) -> List[str]:
        """
        Get list of degraded components.
        
        Returns:
            List of component names
        """
        with self._lock:
            return list(self._degraded_components)
    
    def get_component_health(self, component: str) -> Optional[ComponentHealth]:
        """
        Get health status of a component.
        
        Args:
            component: Component name
            
        Returns:
            Component health or None if not registered
        """
        with self._lock:
            return self._components.get(component)
    
    def get_all_health(self) -> Dict[str, ComponentHealth]:
        """
        Get health status of all components.
        
        Returns:
            Dictionary of component name to health
        """
        with self._lock:
            return dict(self._components)
    
    def can_continue(self) -> bool:
        """
        Check if system can continue operating.
        
        Returns:
            True if no critical components have failed
        """
        with self._lock:
            for health in self._components.values():
                if (health.criticality == ComponentCriticality.CRITICAL and
                    health.status == ComponentStatus.FAILED):
                    return False
            return True
    
    def _get_suggested_actions(
        self,
        component: str,
        health: ComponentHealth
    ) -> List[str]:
        """Get suggested actions for component failure."""
        actions = [
            f"Check {component} logs for details",
            "Monitor system performance"
        ]
        
        if health.fallback_active:
            actions.append(f"Fallback active: {health.fallback_description}")
        else:
            actions.append(f"Some {component} features may be unavailable")
        
        if health.criticality == ComponentCriticality.IMPORTANT:
            actions.append("Consider restarting the component")
        
        return actions


# Global graceful degradation manager instance
_degradation_manager: Optional[GracefulDegradationManager] = None


def get_degradation_manager() -> GracefulDegradationManager:
    """
    Get global graceful degradation manager instance.
    
    Returns:
        GracefulDegradationManager instance
    """
    global _degradation_manager
    if _degradation_manager is None:
        _degradation_manager = GracefulDegradationManager()
    return _degradation_manager


def report_component_failure(
    component: str,
    error_message: str,
    activate_fallback: bool = True
) -> bool:
    """
    Convenience function to report component failure.
    
    Args:
        component: Component name
        error_message: Error description
        activate_fallback: Whether to activate fallback behavior
        
    Returns:
        True if system can continue
    """
    return get_degradation_manager().report_failure(
        component=component,
        error_message=error_message,
        activate_fallback=activate_fallback
    )
