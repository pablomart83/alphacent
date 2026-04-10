"""Unit tests for graceful degradation system."""

import pytest
from unittest.mock import Mock

from src.core.graceful_degradation import (
    ComponentCriticality,
    ComponentStatus,
    GracefulDegradationManager,
    get_degradation_manager,
    report_component_failure
)


@pytest.fixture
def degradation_manager():
    """Create fresh degradation manager for each test."""
    return GracefulDegradationManager()


def test_register_component(degradation_manager):
    """Test registering a component."""
    degradation_manager.register_component(
        name="test_component",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    health = degradation_manager.get_component_health("test_component")
    
    assert health is not None
    assert health.name == "test_component"
    assert health.criticality == ComponentCriticality.OPTIONAL
    assert health.status == ComponentStatus.HEALTHY


def test_report_failure_optional_component(degradation_manager):
    """Test reporting failure of optional component."""
    degradation_manager.register_component(
        name="optional_feature",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    can_continue = degradation_manager.report_failure(
        component="optional_feature",
        error_message="Feature unavailable"
    )
    
    assert can_continue is True
    assert degradation_manager.is_degraded() is True
    assert "optional_feature" in degradation_manager.get_degraded_components()


def test_report_failure_critical_component(degradation_manager):
    """Test reporting failure of critical component."""
    degradation_manager.register_component(
        name="critical_service",
        criticality=ComponentCriticality.CRITICAL
    )
    
    can_continue = degradation_manager.report_failure(
        component="critical_service",
        error_message="Critical failure"
    )
    
    assert can_continue is False
    assert degradation_manager.can_continue() is False


def test_fallback_handler_activated(degradation_manager):
    """Test fallback handler is called on failure."""
    fallback_called = Mock()
    
    degradation_manager.register_component(
        name="service_with_fallback",
        criticality=ComponentCriticality.IMPORTANT,
        fallback_handler=fallback_called,
        fallback_description="Using cached data"
    )
    
    degradation_manager.report_failure(
        component="service_with_fallback",
        error_message="Service down"
    )
    
    fallback_called.assert_called_once()
    
    health = degradation_manager.get_component_health("service_with_fallback")
    assert health.fallback_active is True
    assert health.fallback_description == "Using cached data"


def test_fallback_not_activated_when_disabled(degradation_manager):
    """Test fallback is not activated when activate_fallback=False."""
    fallback_called = Mock()
    
    degradation_manager.register_component(
        name="service",
        criticality=ComponentCriticality.OPTIONAL,
        fallback_handler=fallback_called
    )
    
    degradation_manager.report_failure(
        component="service",
        error_message="Error",
        activate_fallback=False
    )
    
    fallback_called.assert_not_called()


def test_component_disabled_on_failure(degradation_manager):
    """Test component is disabled when configured."""
    degradation_manager.register_component(
        name="disableable_service",
        criticality=ComponentCriticality.OPTIONAL,
        disable_on_failure=True
    )
    
    degradation_manager.report_failure(
        component="disableable_service",
        error_message="Error"
    )
    
    health = degradation_manager.get_component_health("disableable_service")
    assert health.status == ComponentStatus.DISABLED


def test_report_recovery(degradation_manager):
    """Test reporting component recovery."""
    degradation_manager.register_component(
        name="recoverable_service",
        criticality=ComponentCriticality.IMPORTANT
    )
    
    # Fail the component
    degradation_manager.report_failure(
        component="recoverable_service",
        error_message="Temporary error"
    )
    
    assert degradation_manager.is_degraded() is True
    
    # Recover the component
    degradation_manager.report_recovery("recoverable_service")
    
    assert degradation_manager.is_degraded() is False
    
    health = degradation_manager.get_component_health("recoverable_service")
    assert health.status == ComponentStatus.HEALTHY
    assert health.error_message is None
    assert health.fallback_active is False


def test_is_degraded(degradation_manager):
    """Test is_degraded returns correct status."""
    degradation_manager.register_component(
        name="service1",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    assert degradation_manager.is_degraded() is False
    
    degradation_manager.report_failure("service1", "Error")
    
    assert degradation_manager.is_degraded() is True


def test_get_degraded_components(degradation_manager):
    """Test getting list of degraded components."""
    degradation_manager.register_component(
        name="service1",
        criticality=ComponentCriticality.OPTIONAL
    )
    degradation_manager.register_component(
        name="service2",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    degradation_manager.report_failure("service1", "Error 1")
    degradation_manager.report_failure("service2", "Error 2")
    
    degraded = degradation_manager.get_degraded_components()
    
    assert len(degraded) == 2
    assert "service1" in degraded
    assert "service2" in degraded


def test_get_all_health(degradation_manager):
    """Test getting health of all components."""
    degradation_manager.register_component(
        name="service1",
        criticality=ComponentCriticality.OPTIONAL
    )
    degradation_manager.register_component(
        name="service2",
        criticality=ComponentCriticality.IMPORTANT
    )
    
    all_health = degradation_manager.get_all_health()
    
    assert len(all_health) == 2
    assert "service1" in all_health
    assert "service2" in all_health


def test_can_continue_with_optional_failures(degradation_manager):
    """Test system can continue with optional component failures."""
    degradation_manager.register_component(
        name="optional1",
        criticality=ComponentCriticality.OPTIONAL
    )
    degradation_manager.register_component(
        name="optional2",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    degradation_manager.report_failure("optional1", "Error")
    degradation_manager.report_failure("optional2", "Error")
    
    assert degradation_manager.can_continue() is True


def test_cannot_continue_with_critical_failure(degradation_manager):
    """Test system cannot continue with critical component failure."""
    degradation_manager.register_component(
        name="critical",
        criticality=ComponentCriticality.CRITICAL
    )
    
    degradation_manager.report_failure("critical", "Critical error")
    
    assert degradation_manager.can_continue() is False


def test_component_health_updated_on_failure(degradation_manager):
    """Test component health is updated correctly on failure."""
    degradation_manager.register_component(
        name="service",
        criticality=ComponentCriticality.IMPORTANT
    )
    
    degradation_manager.report_failure(
        component="service",
        error_message="Connection timeout"
    )
    
    health = degradation_manager.get_component_health("service")
    
    assert health.status == ComponentStatus.FAILED
    assert health.error_message == "Connection timeout"
    assert health.last_check is not None


def test_fallback_failure_handled_gracefully(degradation_manager):
    """Test fallback handler failure doesn't crash system."""
    def failing_fallback():
        raise Exception("Fallback error")
    
    degradation_manager.register_component(
        name="service",
        criticality=ComponentCriticality.OPTIONAL,
        fallback_handler=failing_fallback
    )
    
    # Should not raise exception
    can_continue = degradation_manager.report_failure(
        component="service",
        error_message="Service error"
    )
    
    assert can_continue is True


def test_unknown_component_failure_handled(degradation_manager):
    """Test reporting failure of unknown component is handled."""
    # Should not crash
    can_continue = degradation_manager.report_failure(
        component="unknown_component",
        error_message="Error"
    )
    
    assert can_continue is True


def test_unknown_component_recovery_handled(degradation_manager):
    """Test reporting recovery of unknown component is handled."""
    # Should not crash
    degradation_manager.report_recovery("unknown_component")


def test_multiple_failures_and_recoveries(degradation_manager):
    """Test multiple component failures and recoveries."""
    for i in range(3):
        degradation_manager.register_component(
            name=f"service{i}",
            criticality=ComponentCriticality.OPTIONAL
        )
    
    # Fail all components
    for i in range(3):
        degradation_manager.report_failure(f"service{i}", f"Error {i}")
    
    assert len(degradation_manager.get_degraded_components()) == 3
    
    # Recover one component
    degradation_manager.report_recovery("service1")
    
    assert len(degradation_manager.get_degraded_components()) == 2
    assert "service1" not in degradation_manager.get_degraded_components()


def test_get_global_degradation_manager():
    """Test getting global degradation manager instance."""
    manager1 = get_degradation_manager()
    manager2 = get_degradation_manager()
    
    # Should return same instance
    assert manager1 is manager2


def test_report_component_failure_convenience_function():
    """Test global report_component_failure convenience function."""
    manager = get_degradation_manager()
    
    manager.register_component(
        name="test_service",
        criticality=ComponentCriticality.OPTIONAL
    )
    
    can_continue = report_component_failure(
        component="test_service",
        error_message="Test error"
    )
    
    assert can_continue is True
    assert manager.is_degraded() is True


def test_component_status_degraded_with_fallback(degradation_manager):
    """Test component status is DEGRADED when fallback is active."""
    degradation_manager.register_component(
        name="service",
        criticality=ComponentCriticality.IMPORTANT,
        fallback_handler=lambda: None,
        fallback_description="Using fallback"
    )
    
    degradation_manager.report_failure("service", "Error")
    
    health = degradation_manager.get_component_health("service")
    assert health.status == ComponentStatus.DEGRADED


def test_important_component_allows_continuation(degradation_manager):
    """Test important component failure allows system to continue."""
    degradation_manager.register_component(
        name="important_service",
        criticality=ComponentCriticality.IMPORTANT
    )
    
    can_continue = degradation_manager.report_failure(
        component="important_service",
        error_message="Service down"
    )
    
    assert can_continue is True
    assert degradation_manager.can_continue() is True
