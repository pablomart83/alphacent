"""Unit tests for API rate limit monitoring."""

import pytest
import time
from datetime import datetime

from src.api.rate_limit_monitor import (
    RateLimitConfig,
    RateLimitMonitor,
    RateLimitStatus,
    RateLimitTracker,
    get_rate_limit_monitor
)


@pytest.fixture
def rate_limit_config():
    """Create test rate limit configuration."""
    return RateLimitConfig(
        max_requests=10,
        time_window=1,  # 1 second window for fast tests
        warning_threshold=0.7,
        throttle_threshold=0.9
    )


@pytest.fixture
def rate_limit_tracker(rate_limit_config):
    """Create test rate limit tracker."""
    return RateLimitTracker(rate_limit_config)


@pytest.fixture
def rate_limit_monitor():
    """Create test rate limit monitor."""
    configs = {
        "test_endpoint": RateLimitConfig(max_requests=10, time_window=1),
        "default": RateLimitConfig(max_requests=5, time_window=1)
    }
    return RateLimitMonitor(configs)


def test_rate_limit_config_creation():
    """Test rate limit configuration creation."""
    config = RateLimitConfig(
        max_requests=100,
        time_window=60,
        warning_threshold=0.8,
        throttle_threshold=0.9
    )
    
    assert config.max_requests == 100
    assert config.time_window == 60
    assert config.warning_threshold == 0.8
    assert config.throttle_threshold == 0.9


def test_tracker_records_requests(rate_limit_tracker):
    """Test tracker records requests correctly."""
    # Make some requests
    for _ in range(5):
        delay = rate_limit_tracker.record_request()
        assert delay == 0.0  # No throttling yet
    
    stats = rate_limit_tracker.get_stats("test")
    assert stats.requests_made == 5


def test_tracker_status_normal(rate_limit_tracker):
    """Test tracker status is NORMAL under threshold."""
    # Make 6 requests (60% of 10)
    for _ in range(6):
        rate_limit_tracker.record_request()
    
    status = rate_limit_tracker.get_status()
    assert status == RateLimitStatus.NORMAL


def test_tracker_status_warning(rate_limit_tracker):
    """Test tracker status is WARNING at warning threshold."""
    # Make 8 requests (80% of 10)
    for _ in range(8):
        rate_limit_tracker.record_request()
    
    status = rate_limit_tracker.get_status()
    assert status == RateLimitStatus.WARNING


def test_tracker_status_throttled(rate_limit_tracker):
    """Test tracker status is THROTTLED at throttle threshold."""
    # Make 9 requests (90% of 10)
    for _ in range(9):
        rate_limit_tracker.record_request()
    
    status = rate_limit_tracker.get_status()
    assert status == RateLimitStatus.THROTTLED


def test_tracker_status_exceeded(rate_limit_tracker):
    """Test tracker status is EXCEEDED when limit reached."""
    # Make 10 requests (100% of 10)
    for _ in range(10):
        rate_limit_tracker.record_request()
    
    status = rate_limit_tracker.get_status()
    assert status == RateLimitStatus.EXCEEDED


def test_tracker_throttles_when_approaching_limit(rate_limit_tracker):
    """Test tracker returns throttle delay when approaching limit."""
    # Make 9 requests (90% of 10)
    for _ in range(9):
        rate_limit_tracker.record_request()
    
    # Next request should have throttle delay
    delay = rate_limit_tracker.record_request()
    assert delay > 0.0


def test_tracker_can_make_request(rate_limit_tracker):
    """Test can_make_request checks limit correctly."""
    # Under limit
    for _ in range(9):
        rate_limit_tracker.record_request()
    
    assert rate_limit_tracker.can_make_request() is True
    
    # At limit
    rate_limit_tracker.record_request()
    assert rate_limit_tracker.can_make_request() is False


def test_tracker_cleans_old_requests():
    """Test tracker removes requests outside time window."""
    # Use very short time window for fast test
    config = RateLimitConfig(max_requests=10, time_window=0.05)
    tracker = RateLimitTracker(config)
    
    # Make 5 requests
    for _ in range(5):
        tracker.record_request()
    
    assert tracker.get_stats("test").requests_made == 5
    
    # Wait for time window to expire
    time.sleep(0.06)
    
    # Old requests should be cleaned
    stats = tracker.get_stats("test")
    assert stats.requests_made == 0


def test_tracker_reset(rate_limit_tracker):
    """Test tracker reset clears all requests."""
    # Make some requests
    for _ in range(5):
        rate_limit_tracker.record_request()
    
    assert rate_limit_tracker.get_stats("test").requests_made == 5
    
    # Reset
    rate_limit_tracker.reset()
    
    assert rate_limit_tracker.get_stats("test").requests_made == 0


def test_tracker_get_stats(rate_limit_tracker):
    """Test tracker returns correct statistics."""
    # Make 8 requests
    for _ in range(8):
        rate_limit_tracker.record_request()
    
    stats = rate_limit_tracker.get_stats("test_endpoint")
    
    assert stats.endpoint == "test_endpoint"
    assert stats.requests_made == 8
    assert stats.max_requests == 10
    assert stats.time_window == 1
    assert stats.status == RateLimitStatus.WARNING
    assert stats.reset_time is not None


def test_monitor_initialization(rate_limit_monitor):
    """Test monitor initializes correctly."""
    assert rate_limit_monitor is not None


def test_monitor_records_request(rate_limit_monitor):
    """Test monitor records requests to endpoints."""
    delay = rate_limit_monitor.record_request("test_endpoint")
    assert delay == 0.0
    
    stats = rate_limit_monitor.get_stats("test_endpoint")
    assert stats.requests_made == 1


def test_monitor_check_and_wait():
    """Test monitor check_and_wait method."""
    # Use very short time window for fast test
    configs = {
        "test_endpoint": RateLimitConfig(max_requests=10, time_window=0.05),
    }
    monitor = RateLimitMonitor(configs)
    
    # Make requests up to throttle threshold
    for _ in range(9):
        monitor.record_request("test_endpoint")
    
    # This should trigger throttling but complete quickly
    start_time = time.time()
    monitor.check_and_wait("test_endpoint")
    elapsed = time.time() - start_time
    
    # Should complete (delay should be very short with 0.05s window)
    assert elapsed < 1.0


def test_monitor_get_status(rate_limit_monitor):
    """Test monitor returns correct status."""
    # Make some requests
    for _ in range(5):
        rate_limit_monitor.record_request("test_endpoint")
    
    status = rate_limit_monitor.get_status("test_endpoint")
    assert status == RateLimitStatus.NORMAL


def test_monitor_can_make_request(rate_limit_monitor):
    """Test monitor checks if request can be made."""
    assert rate_limit_monitor.can_make_request("test_endpoint") is True
    
    # Fill up to limit
    for _ in range(10):
        rate_limit_monitor.record_request("test_endpoint")
    
    assert rate_limit_monitor.can_make_request("test_endpoint") is False


def test_monitor_get_all_stats(rate_limit_monitor):
    """Test monitor returns stats for all endpoints."""
    rate_limit_monitor.record_request("test_endpoint")
    rate_limit_monitor.record_request("other_endpoint")
    
    all_stats = rate_limit_monitor.get_all_stats()
    
    assert "test_endpoint" in all_stats
    assert "other_endpoint" in all_stats


def test_monitor_reset_specific_endpoint(rate_limit_monitor):
    """Test monitor resets specific endpoint."""
    rate_limit_monitor.record_request("test_endpoint")
    rate_limit_monitor.record_request("other_endpoint")
    
    rate_limit_monitor.reset("test_endpoint")
    
    assert rate_limit_monitor.get_stats("test_endpoint").requests_made == 0
    assert rate_limit_monitor.get_stats("other_endpoint").requests_made == 1


def test_monitor_reset_all_endpoints(rate_limit_monitor):
    """Test monitor resets all endpoints."""
    rate_limit_monitor.record_request("test_endpoint")
    rate_limit_monitor.record_request("other_endpoint")
    
    rate_limit_monitor.reset()
    
    assert rate_limit_monitor.get_stats("test_endpoint").requests_made == 0
    assert rate_limit_monitor.get_stats("other_endpoint").requests_made == 0


def test_monitor_uses_default_config_for_unknown_endpoint(rate_limit_monitor):
    """Test monitor uses default config for unknown endpoints."""
    # "unknown_endpoint" not in configs, should use default (5 req/sec)
    for _ in range(5):
        rate_limit_monitor.record_request("unknown_endpoint")
    
    stats = rate_limit_monitor.get_stats("unknown_endpoint")
    assert stats.max_requests == 5  # Default config


def test_monitor_tracks_multiple_endpoints_independently(rate_limit_monitor):
    """Test monitor tracks endpoints independently."""
    # Fill up test_endpoint
    for _ in range(10):
        rate_limit_monitor.record_request("test_endpoint")
    
    # other_endpoint should still be available
    assert rate_limit_monitor.can_make_request("other_endpoint") is True
    assert rate_limit_monitor.can_make_request("test_endpoint") is False


def test_get_global_rate_limit_monitor():
    """Test getting global rate limit monitor instance."""
    monitor1 = get_rate_limit_monitor()
    monitor2 = get_rate_limit_monitor()
    
    # Should return same instance
    assert monitor1 is monitor2


def test_throttle_delay_calculation(rate_limit_tracker):
    """Test throttle delay is calculated correctly."""
    # Make 9 requests (90% of 10)
    for _ in range(9):
        rate_limit_tracker.record_request()
    
    # Get delay for next request
    delay = rate_limit_tracker.record_request()
    
    # Delay should be positive and reasonable
    assert delay > 0
    assert delay < 2.0  # Should be less than time window


def test_warning_threshold_triggers_warning(rate_limit_tracker):
    """Test warning threshold triggers warning status."""
    # Make 7 requests (70% of 10, at warning threshold)
    for _ in range(7):
        rate_limit_tracker.record_request()
    
    status = rate_limit_tracker.get_status()
    assert status == RateLimitStatus.WARNING


def test_requests_expire_after_time_window():
    """Test requests expire after time window."""
    config = RateLimitConfig(max_requests=5, time_window=0.05)
    tracker = RateLimitTracker(config)
    
    # Make 5 requests
    for _ in range(5):
        tracker.record_request()
    
    assert tracker.can_make_request() is False
    
    # Wait for window to expire
    time.sleep(0.06)
    
    # Should be able to make requests again
    assert tracker.can_make_request() is True


def test_stats_include_reset_time(rate_limit_tracker):
    """Test statistics include reset time."""
    rate_limit_tracker.record_request()
    
    stats = rate_limit_tracker.get_stats("test")
    
    assert stats.reset_time is not None
    assert isinstance(stats.reset_time, datetime)


def test_stats_include_throttle_delay(rate_limit_tracker):
    """Test statistics include throttle delay when throttling."""
    # Make 9 requests to trigger throttling
    for _ in range(9):
        rate_limit_tracker.record_request()
    
    stats = rate_limit_tracker.get_stats("test")
    
    assert stats.throttle_delay > 0
