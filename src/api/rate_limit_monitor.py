"""
API rate limit monitoring and throttling for eToro API.

This module provides:
- Rate limit tracking for eToro API
- Automatic throttling when approaching limits
- Warning logging when throttling is active
- Per-endpoint rate limit tracking
"""

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Deque, Dict, Optional

from src.core.logging_config import LogComponent, get_logger


logger = get_logger(LogComponent.API)


class RateLimitStatus(Enum):
    """Rate limit status."""
    NORMAL = "normal"
    WARNING = "warning"
    THROTTLED = "throttled"
    EXCEEDED = "exceeded"


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an endpoint."""
    max_requests: int  # Maximum requests allowed
    time_window: int  # Time window in seconds
    warning_threshold: float = 0.8  # Warn at 80% of limit
    throttle_threshold: float = 0.9  # Throttle at 90% of limit


@dataclass
class RateLimitStats:
    """Rate limit statistics."""
    endpoint: str
    requests_made: int
    max_requests: int
    time_window: int
    status: RateLimitStatus
    throttle_delay: float = 0.0
    reset_time: Optional[datetime] = None


class RateLimitTracker:
    """Tracks rate limits for a specific endpoint."""
    
    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limit tracker.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config
        self._requests: Deque[float] = deque()
        self._lock = Lock()
        self._throttle_active = False
        self._last_warning_time: Optional[float] = None
    
    def _clean_old_requests(self):
        """Remove requests outside the time window."""
        current_time = time.time()
        cutoff_time = current_time - self.config.time_window
        
        while self._requests and self._requests[0] < cutoff_time:
            self._requests.popleft()
    
    def record_request(self) -> float:
        """
        Record a new request and return throttle delay if needed.
        
        Returns:
            Delay in seconds before making the request (0 if no throttle)
        """
        with self._lock:
            self._clean_old_requests()
            
            current_count = len(self._requests)
            usage_ratio = current_count / self.config.max_requests
            
            # Calculate throttle delay if needed
            delay = 0.0
            
            if usage_ratio >= self.config.throttle_threshold:
                # Throttle: add delay to spread out requests
                if not self._throttle_active:
                    self._throttle_active = True
                    logger.warning(
                        f"Rate limit throttling activated",
                        context={
                            "requests": current_count,
                            "max_requests": self.config.max_requests,
                            "usage": f"{usage_ratio * 100:.1f}%"
                        }
                    )
                
                # Calculate delay to stay under limit
                # Spread remaining requests evenly over remaining time
                if self._requests:
                    oldest_request = self._requests[0]
                    time_until_reset = self.config.time_window - (time.time() - oldest_request)
                    remaining_capacity = self.config.max_requests - current_count
                    
                    if remaining_capacity > 0:
                        delay = time_until_reset / remaining_capacity
                    else:
                        # At limit, wait for oldest request to expire
                        delay = time_until_reset
            
            elif usage_ratio >= self.config.warning_threshold:
                # Warning: approaching limit
                current_time = time.time()
                # Only log warning once per minute
                if (self._last_warning_time is None or 
                    current_time - self._last_warning_time > 60):
                    logger.warning(
                        f"Approaching rate limit",
                        context={
                            "requests": current_count,
                            "max_requests": self.config.max_requests,
                            "usage": f"{usage_ratio * 100:.1f}%"
                        }
                    )
                    self._last_warning_time = current_time
            
            else:
                # Normal operation
                if self._throttle_active:
                    self._throttle_active = False
                    logger.info("Rate limit throttling deactivated")
            
            # Record the request
            self._requests.append(time.time())
            
            return delay
    
    def get_status(self) -> RateLimitStatus:
        """
        Get current rate limit status.
        
        Returns:
            Current status
        """
        with self._lock:
            self._clean_old_requests()
            
            current_count = len(self._requests)
            usage_ratio = current_count / self.config.max_requests
            
            if usage_ratio >= 1.0:
                return RateLimitStatus.EXCEEDED
            elif usage_ratio >= self.config.throttle_threshold:
                return RateLimitStatus.THROTTLED
            elif usage_ratio >= self.config.warning_threshold:
                return RateLimitStatus.WARNING
            else:
                return RateLimitStatus.NORMAL
    
    def get_stats(self, endpoint: str) -> RateLimitStats:
        """
        Get rate limit statistics.
        
        Args:
            endpoint: Endpoint name
            
        Returns:
            Rate limit statistics
        """
        with self._lock:
            self._clean_old_requests()
            
            current_count = len(self._requests)
            status = self.get_status()
            
            # Calculate reset time
            reset_time = None
            if self._requests:
                oldest_request = self._requests[0]
                reset_time = datetime.fromtimestamp(
                    oldest_request + self.config.time_window
                )
            
            # Calculate throttle delay
            usage_ratio = current_count / self.config.max_requests
            throttle_delay = 0.0
            if usage_ratio >= self.config.throttle_threshold and self._requests:
                oldest_request = self._requests[0]
                time_until_reset = self.config.time_window - (time.time() - oldest_request)
                remaining_capacity = self.config.max_requests - current_count
                if remaining_capacity > 0:
                    throttle_delay = time_until_reset / remaining_capacity
            
            return RateLimitStats(
                endpoint=endpoint,
                requests_made=current_count,
                max_requests=self.config.max_requests,
                time_window=self.config.time_window,
                status=status,
                throttle_delay=throttle_delay,
                reset_time=reset_time
            )
    
    def can_make_request(self) -> bool:
        """
        Check if a request can be made without exceeding limits.
        
        Returns:
            True if request can be made
        """
        with self._lock:
            self._clean_old_requests()
            return len(self._requests) < self.config.max_requests
    
    def reset(self):
        """Reset rate limit tracker."""
        with self._lock:
            self._requests.clear()
            self._throttle_active = False
            self._last_warning_time = None
            logger.info("Rate limit tracker reset")


class RateLimitMonitor:
    """
    Monitors rate limits for multiple API endpoints.
    
    Tracks usage per endpoint and provides throttling when approaching limits.
    """
    
    # Default rate limit configurations for eToro API endpoints
    # These are placeholder values - actual limits should come from eToro API docs
    DEFAULT_CONFIGS = {
        "market_data": RateLimitConfig(max_requests=100, time_window=60),  # 100 req/min
        "account": RateLimitConfig(max_requests=50, time_window=60),  # 50 req/min
        "orders": RateLimitConfig(max_requests=30, time_window=60),  # 30 req/min
        "positions": RateLimitConfig(max_requests=50, time_window=60),  # 50 req/min
        "social": RateLimitConfig(max_requests=20, time_window=60),  # 20 req/min
        "default": RateLimitConfig(max_requests=60, time_window=60),  # 60 req/min
    }
    
    def __init__(self, configs: Optional[Dict[str, RateLimitConfig]] = None):
        """
        Initialize rate limit monitor.
        
        Args:
            configs: Custom rate limit configurations per endpoint
        """
        self._configs = configs or self.DEFAULT_CONFIGS
        self._trackers: Dict[str, RateLimitTracker] = {}
        self._lock = Lock()
        
        logger.info("Rate limit monitor initialized", context={"endpoints": len(self._configs)})
    
    def _get_tracker(self, endpoint: str) -> RateLimitTracker:
        """Get or create tracker for endpoint."""
        with self._lock:
            if endpoint not in self._trackers:
                config = self._configs.get(endpoint, self._configs["default"])
                self._trackers[endpoint] = RateLimitTracker(config)
            return self._trackers[endpoint]
    
    def record_request(self, endpoint: str) -> float:
        """
        Record a request to an endpoint and get throttle delay.
        
        Args:
            endpoint: API endpoint name
            
        Returns:
            Delay in seconds before making the request (0 if no throttle)
        """
        tracker = self._get_tracker(endpoint)
        delay = tracker.record_request()
        
        if delay > 0:
            logger.info(
                f"Throttling request to {endpoint}",
                context={"delay_seconds": f"{delay:.2f}"}
            )
        
        return delay
    
    def check_and_wait(self, endpoint: str):
        """
        Check rate limit and wait if throttling is needed.
        
        Args:
            endpoint: API endpoint name
        """
        delay = self.record_request(endpoint)
        if delay > 0:
            time.sleep(delay)
    
    def get_status(self, endpoint: str) -> RateLimitStatus:
        """
        Get rate limit status for endpoint.
        
        Args:
            endpoint: API endpoint name
            
        Returns:
            Current rate limit status
        """
        tracker = self._get_tracker(endpoint)
        return tracker.get_status()
    
    def get_stats(self, endpoint: str) -> RateLimitStats:
        """
        Get rate limit statistics for endpoint.
        
        Args:
            endpoint: API endpoint name
            
        Returns:
            Rate limit statistics
        """
        tracker = self._get_tracker(endpoint)
        return tracker.get_stats(endpoint)
    
    def get_all_stats(self) -> Dict[str, RateLimitStats]:
        """
        Get rate limit statistics for all endpoints.
        
        Returns:
            Dictionary of endpoint to statistics
        """
        with self._lock:
            return {
                endpoint: tracker.get_stats(endpoint)
                for endpoint, tracker in self._trackers.items()
            }
    
    def can_make_request(self, endpoint: str) -> bool:
        """
        Check if a request can be made to endpoint.
        
        Args:
            endpoint: API endpoint name
            
        Returns:
            True if request can be made without exceeding limits
        """
        tracker = self._get_tracker(endpoint)
        return tracker.can_make_request()
    
    def reset(self, endpoint: Optional[str] = None):
        """
        Reset rate limit tracking.
        
        Args:
            endpoint: Specific endpoint to reset, or None for all
        """
        with self._lock:
            if endpoint:
                if endpoint in self._trackers:
                    self._trackers[endpoint].reset()
            else:
                for tracker in self._trackers.values():
                    tracker.reset()
                logger.info("All rate limit trackers reset")


# Global rate limit monitor instance
_rate_limit_monitor: Optional[RateLimitMonitor] = None


def get_rate_limit_monitor() -> RateLimitMonitor:
    """
    Get global rate limit monitor instance.
    
    Returns:
        RateLimitMonitor instance
    """
    global _rate_limit_monitor
    if _rate_limit_monitor is None:
        _rate_limit_monitor = RateLimitMonitor()
    return _rate_limit_monitor
