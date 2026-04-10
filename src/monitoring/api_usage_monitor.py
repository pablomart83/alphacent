"""
API Usage Monitoring & Alerts System

Provides real-time monitoring, alerting, and forecasting for API usage.
Implements graceful degradation when approaching limits.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import statistics

logger = logging.getLogger(__name__)


class ApiPriority(Enum):
    """API call priority levels for graceful degradation."""
    CRITICAL = 1  # Earnings data, essential for trading decisions
    HIGH = 2      # Fundamental data for active strategies
    MEDIUM = 3    # Fundamental data for new strategies
    LOW = 4       # Nice-to-have data, can be skipped


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ApiUsageStats:
    """API usage statistics."""
    api_name: str
    calls_made: int
    limit: int
    percentage: float
    remaining: int
    reset_time: Optional[datetime] = None
    circuit_breaker_active: bool = False
    forecast_exhaustion_time: Optional[datetime] = None
    current_rate: float = 0.0  # calls per hour
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'api_name': self.api_name,
            'calls_made': self.calls_made,
            'limit': self.limit,
            'percentage': round(self.percentage, 2),
            'remaining': self.remaining,
            'reset_time': self.reset_time.isoformat() if self.reset_time else None,
            'circuit_breaker_active': self.circuit_breaker_active,
            'forecast_exhaustion_time': self.forecast_exhaustion_time.isoformat() if self.forecast_exhaustion_time else None,
            'current_rate': round(self.current_rate, 2)
        }


@dataclass
class ApiAlert:
    """API usage alert."""
    api_name: str
    level: AlertLevel
    message: str
    timestamp: datetime
    percentage: float
    calls_remaining: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'api_name': self.api_name,
            'level': self.level.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'percentage': round(self.percentage, 2),
            'calls_remaining': self.calls_remaining
        }


class ApiUsageMonitor:
    """
    Monitors API usage across multiple data sources.
    
    Features:
    - Real-time usage tracking
    - Alert at 70% threshold
    - API call forecasting
    - Graceful degradation
    - Priority-based call management
    """
    
    # Alert thresholds
    WARNING_THRESHOLD = 0.70  # 70%
    CRITICAL_THRESHOLD = 0.85  # 85%
    EMERGENCY_THRESHOLD = 0.95  # 95%
    
    def __init__(self):
        """Initialize API usage monitor."""
        self.lock = Lock()
        
        # Track usage history for forecasting (timestamp, api_name)
        self.call_history: List[tuple] = []
        self.history_window = 3600  # 1 hour window for rate calculation
        
        # Alert history (to avoid duplicate alerts)
        self.alert_history: Dict[str, List[ApiAlert]] = {}
        self.alert_cooldown = 300  # 5 minutes between duplicate alerts
        
        # Graceful degradation state
        self.degradation_active: Dict[str, bool] = {}
        self.disabled_features: Dict[str, List[str]] = {}
        
        # Alert callbacks
        self.alert_callbacks: List[Callable[[ApiAlert], None]] = []
        
        logger.info("API Usage Monitor initialized")
    
    def record_call(self, api_name: str, priority: ApiPriority = ApiPriority.MEDIUM) -> None:
        """
        Record an API call.
        
        Args:
            api_name: Name of the API (e.g., 'fmp', 'alpha_vantage')
            priority: Priority level of the call
        """
        with self.lock:
            timestamp = time.time()
            self.call_history.append((timestamp, api_name, priority))
            
            # Clean old history
            cutoff = timestamp - self.history_window
            self.call_history = [(t, api, p) for t, api, p in self.call_history if t > cutoff]
    
    def get_usage_stats(self, api_name: str, limit: int, 
                       current_calls: int, reset_time: Optional[datetime] = None,
                       circuit_breaker_active: bool = False) -> ApiUsageStats:
        """
        Get comprehensive usage statistics for an API.
        
        Args:
            api_name: Name of the API
            limit: Daily call limit
            current_calls: Current number of calls made
            reset_time: When the limit resets
            circuit_breaker_active: Whether circuit breaker is active
            
        Returns:
            ApiUsageStats object
        """
        with self.lock:
            percentage = (current_calls / limit) * 100 if limit > 0 else 0
            remaining = max(0, limit - current_calls)
            
            # Calculate current rate (calls per hour)
            current_time = time.time()
            cutoff = current_time - self.history_window
            recent_calls = [t for t, api, _ in self.call_history 
                          if api == api_name and t > cutoff]
            current_rate = len(recent_calls)  # calls in last hour
            
            # Forecast when limit will be exhausted
            forecast_time = None
            if current_rate > 0 and remaining > 0:
                hours_until_exhaustion = remaining / current_rate
                forecast_time = datetime.now() + timedelta(hours=hours_until_exhaustion)
            
            stats = ApiUsageStats(
                api_name=api_name,
                calls_made=current_calls,
                limit=limit,
                percentage=percentage,
                remaining=remaining,
                reset_time=reset_time,
                circuit_breaker_active=circuit_breaker_active,
                forecast_exhaustion_time=forecast_time,
                current_rate=current_rate
            )
            
            # Check for alerts
            self._check_and_send_alerts(stats)
            
            return stats
    
    def _check_and_send_alerts(self, stats: ApiUsageStats) -> None:
        """
        Check usage stats and send alerts if thresholds are exceeded.
        
        Args:
            stats: API usage statistics
        """
        usage_ratio = stats.percentage / 100
        
        # Determine alert level
        alert_level = None
        message = None
        
        if usage_ratio >= self.EMERGENCY_THRESHOLD:
            alert_level = AlertLevel.CRITICAL
            message = f"{stats.api_name} API usage at {stats.percentage:.1f}% - EMERGENCY! Only {stats.remaining} calls remaining!"
        elif usage_ratio >= self.CRITICAL_THRESHOLD:
            alert_level = AlertLevel.CRITICAL
            message = f"{stats.api_name} API usage at {stats.percentage:.1f}% - CRITICAL! Only {stats.remaining} calls remaining!"
        elif usage_ratio >= self.WARNING_THRESHOLD:
            alert_level = AlertLevel.WARNING
            message = f"{stats.api_name} API usage at {stats.percentage:.1f}% - WARNING! {stats.remaining} calls remaining"
        
        if alert_level and message:
            # Check if we should send this alert (cooldown)
            if self._should_send_alert(stats.api_name, alert_level):
                alert = ApiAlert(
                    api_name=stats.api_name,
                    level=alert_level,
                    message=message,
                    timestamp=datetime.now(),
                    percentage=stats.percentage,
                    calls_remaining=stats.remaining
                )
                
                # Store alert
                if stats.api_name not in self.alert_history:
                    self.alert_history[stats.api_name] = []
                self.alert_history[stats.api_name].append(alert)
                
                # Log alert
                if alert_level == AlertLevel.CRITICAL:
                    logger.critical(message)
                else:
                    logger.warning(message)
                
                # Trigger callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Error in alert callback: {e}")
                
                # Activate graceful degradation if needed
                if usage_ratio >= self.CRITICAL_THRESHOLD:
                    self._activate_graceful_degradation(stats.api_name, usage_ratio)
    
    def _should_send_alert(self, api_name: str, level: AlertLevel) -> bool:
        """
        Check if an alert should be sent (respects cooldown).
        
        Args:
            api_name: Name of the API
            level: Alert level
            
        Returns:
            True if alert should be sent
        """
        if api_name not in self.alert_history:
            return True
        
        # Get recent alerts of same level
        recent_alerts = [
            alert for alert in self.alert_history[api_name]
            if alert.level == level and 
            (datetime.now() - alert.timestamp).total_seconds() < self.alert_cooldown
        ]
        
        return len(recent_alerts) == 0
    
    def _activate_graceful_degradation(self, api_name: str, usage_ratio: float) -> None:
        """
        Activate graceful degradation for an API.
        
        Args:
            api_name: Name of the API
            usage_ratio: Current usage ratio (0.0 to 1.0)
        """
        if api_name in self.degradation_active and self.degradation_active[api_name]:
            return  # Already active
        
        self.degradation_active[api_name] = True
        self.disabled_features[api_name] = []
        
        # Disable features based on usage level
        if usage_ratio >= self.EMERGENCY_THRESHOLD:
            # Emergency: Only allow CRITICAL priority calls
            self.disabled_features[api_name] = ['LOW', 'MEDIUM', 'HIGH']
            logger.critical(f"EMERGENCY degradation active for {api_name} - only CRITICAL calls allowed")
        elif usage_ratio >= self.CRITICAL_THRESHOLD:
            # Critical: Disable LOW and MEDIUM priority calls
            self.disabled_features[api_name] = ['LOW', 'MEDIUM']
            logger.warning(f"Graceful degradation active for {api_name} - LOW and MEDIUM priority calls disabled")
    
    def can_make_call(self, api_name: str, priority: ApiPriority) -> bool:
        """
        Check if an API call can be made based on priority and degradation state.
        
        Args:
            api_name: Name of the API
            priority: Priority level of the call
            
        Returns:
            True if call is allowed
        """
        with self.lock:
            if api_name not in self.degradation_active or not self.degradation_active[api_name]:
                return True  # No degradation active
            
            # Check if this priority level is disabled
            disabled = self.disabled_features.get(api_name, [])
            return priority.name not in disabled
    
    def deactivate_graceful_degradation(self, api_name: str) -> None:
        """
        Deactivate graceful degradation for an API.
        
        Args:
            api_name: Name of the API
        """
        with self.lock:
            if api_name in self.degradation_active:
                self.degradation_active[api_name] = False
                self.disabled_features[api_name] = []
                logger.info(f"Graceful degradation deactivated for {api_name}")
    
    def get_all_alerts(self, since: Optional[datetime] = None) -> List[ApiAlert]:
        """
        Get all alerts, optionally filtered by time.
        
        Args:
            since: Only return alerts after this time
            
        Returns:
            List of alerts
        """
        with self.lock:
            all_alerts = []
            for alerts in self.alert_history.values():
                if since:
                    all_alerts.extend([a for a in alerts if a.timestamp >= since])
                else:
                    all_alerts.extend(alerts)
            
            # Sort by timestamp (most recent first)
            all_alerts.sort(key=lambda a: a.timestamp, reverse=True)
            return all_alerts
    
    def register_alert_callback(self, callback: Callable[[ApiAlert], None]) -> None:
        """
        Register a callback to be called when alerts are triggered.
        
        Args:
            callback: Function to call with ApiAlert object
        """
        self.alert_callbacks.append(callback)
        logger.info(f"Registered alert callback: {callback.__name__}")
    
    def get_forecast(self, api_name: str, current_calls: int, limit: int) -> Dict[str, Any]:
        """
        Get usage forecast for an API.
        
        Args:
            api_name: Name of the API
            current_calls: Current number of calls made
            limit: Daily call limit
            
        Returns:
            Forecast dictionary
        """
        with self.lock:
            current_time = time.time()
            cutoff = current_time - self.history_window
            
            # Get recent calls for this API
            recent_calls = [(t, api, p) for t, api, p in self.call_history 
                          if api == api_name and t > cutoff]
            
            if not recent_calls:
                return {
                    'api_name': api_name,
                    'current_rate': 0,
                    'forecast_exhaustion_time': None,
                    'hours_until_exhaustion': None,
                    'recommendation': 'No recent activity'
                }
            
            # Calculate rate (calls per hour)
            rate = len(recent_calls)
            remaining = max(0, limit - current_calls)
            
            # Forecast exhaustion time
            if rate > 0 and remaining > 0:
                hours_until_exhaustion = remaining / rate
                exhaustion_time = datetime.now() + timedelta(hours=hours_until_exhaustion)
                
                # Generate recommendation
                if hours_until_exhaustion < 2:
                    recommendation = "CRITICAL: Limit will be exhausted within 2 hours at current rate"
                elif hours_until_exhaustion < 6:
                    recommendation = "WARNING: Limit will be exhausted within 6 hours at current rate"
                else:
                    recommendation = "OK: Current usage rate is sustainable"
            else:
                exhaustion_time = None
                hours_until_exhaustion = None
                recommendation = "Limit already exhausted" if remaining == 0 else "No usage"
            
            return {
                'api_name': api_name,
                'current_rate': round(rate, 2),
                'forecast_exhaustion_time': exhaustion_time.isoformat() if exhaustion_time else None,
                'hours_until_exhaustion': round(hours_until_exhaustion, 2) if hours_until_exhaustion else None,
                'recommendation': recommendation
            }
    
    def get_dashboard_data(self, apis: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data for all APIs.
        
        Args:
            apis: Dictionary of API configurations with 'limit', 'current_calls', etc.
            
        Returns:
            Dashboard data dictionary
        """
        dashboard = {
            'timestamp': datetime.now().isoformat(),
            'apis': {},
            'alerts': [alert.to_dict() for alert in self.get_all_alerts(since=datetime.now() - timedelta(hours=24))],
            'degradation_active': dict(self.degradation_active),
            'overall_health': 'healthy'
        }
        
        # Collect stats for each API
        for api_name, api_config in apis.items():
            stats = self.get_usage_stats(
                api_name=api_name,
                limit=api_config.get('limit', 0),
                current_calls=api_config.get('current_calls', 0),
                reset_time=api_config.get('reset_time'),
                circuit_breaker_active=api_config.get('circuit_breaker_active', False)
            )
            
            forecast = self.get_forecast(
                api_name=api_name,
                current_calls=api_config.get('current_calls', 0),
                limit=api_config.get('limit', 0)
            )
            
            dashboard['apis'][api_name] = {
                'stats': stats.to_dict(),
                'forecast': forecast
            }
            
            # Update overall health
            if stats.percentage >= 85:
                dashboard['overall_health'] = 'critical'
            elif stats.percentage >= 70 and dashboard['overall_health'] == 'healthy':
                dashboard['overall_health'] = 'warning'
        
        return dashboard
    
    def reset(self) -> None:
        """Reset all monitoring data."""
        with self.lock:
            self.call_history.clear()
            self.alert_history.clear()
            self.degradation_active.clear()
            self.disabled_features.clear()
            logger.info("API Usage Monitor reset")


# Global instance
_api_usage_monitor: Optional[ApiUsageMonitor] = None


def get_api_usage_monitor() -> ApiUsageMonitor:
    """
    Get global API usage monitor instance.
    
    Returns:
        ApiUsageMonitor instance
    """
    global _api_usage_monitor
    if _api_usage_monitor is None:
        _api_usage_monitor = ApiUsageMonitor()
    return _api_usage_monitor
