"""Monitoring and metrics for signal generation in production."""

import logging
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass, field

from src.models import TradingSignal, SignalAction

logger = logging.getLogger(__name__)


@dataclass
class SignalGenerationMetrics:
    """Metrics for signal generation monitoring."""
    
    # Counters
    total_signals_generated: int = 0
    total_signals_validated: int = 0
    total_signals_rejected: int = 0
    
    # By action
    enter_long_signals: int = 0
    exit_long_signals: int = 0
    
    # Confidence distribution
    high_confidence_signals: int = 0  # confidence >= 0.7
    medium_confidence_signals: int = 0  # 0.4 <= confidence < 0.7
    low_confidence_signals: int = 0  # confidence < 0.4
    
    # Timing
    last_signal_generated_at: datetime = None
    last_validation_success_at: datetime = None
    last_validation_failure_at: datetime = None
    
    # Errors
    generation_errors: int = 0
    validation_errors: int = 0
    error_messages: List[str] = field(default_factory=list)
    
    # Per-strategy metrics
    signals_by_strategy: Dict[str, int] = field(default_factory=dict)
    
    def record_signal_generated(self, signal: TradingSignal) -> None:
        """Record a generated signal."""
        self.total_signals_generated += 1
        self.last_signal_generated_at = datetime.now()
        
        # Track by action
        if signal.action == SignalAction.ENTER_LONG:
            self.enter_long_signals += 1
        elif signal.action == SignalAction.EXIT_LONG:
            self.exit_long_signals += 1
        
        # Track by confidence
        if signal.confidence >= 0.7:
            self.high_confidence_signals += 1
        elif signal.confidence >= 0.4:
            self.medium_confidence_signals += 1
        else:
            self.low_confidence_signals += 1
        
        # Track by strategy
        strategy_id = signal.strategy_id
        self.signals_by_strategy[strategy_id] = self.signals_by_strategy.get(strategy_id, 0) + 1
        
        logger.info(
            f"📊 Signal generated: {signal.symbol} {signal.action.value} "
            f"(confidence: {signal.confidence:.2f})"
        )
    
    def record_validation_success(self, signal: TradingSignal, position_size: float) -> None:
        """Record a successful validation."""
        self.total_signals_validated += 1
        self.last_validation_success_at = datetime.now()
        
        logger.info(
            f"✅ Signal validated: {signal.symbol} {signal.action.value} "
            f"size=${position_size:.2f}"
        )
    
    def record_validation_failure(self, signal: TradingSignal, reason: str) -> None:
        """Record a failed validation."""
        self.total_signals_rejected += 1
        self.last_validation_failure_at = datetime.now()
        
        logger.warning(
            f"❌ Signal rejected: {signal.symbol} {signal.action.value} "
            f"reason={reason}"
        )
    
    def record_generation_error(self, error_message: str) -> None:
        """Record a signal generation error."""
        self.generation_errors += 1
        self.error_messages.append(f"{datetime.now().isoformat()}: {error_message}")
        
        # Keep only last 100 errors
        if len(self.error_messages) > 100:
            self.error_messages = self.error_messages[-100:]
        
        logger.error(f"🚨 Signal generation error: {error_message}")
    
    def record_validation_error(self, error_message: str) -> None:
        """Record a validation error."""
        self.validation_errors += 1
        self.error_messages.append(f"{datetime.now().isoformat()}: {error_message}")
        
        # Keep only last 100 errors
        if len(self.error_messages) > 100:
            self.error_messages = self.error_messages[-100:]
        
        logger.error(f"🚨 Validation error: {error_message}")
    
    def get_validation_success_rate(self) -> float:
        """Calculate validation success rate."""
        total = self.total_signals_validated + self.total_signals_rejected
        if total == 0:
            return 0.0
        return self.total_signals_validated / total
    
    def get_summary(self) -> Dict:
        """Get metrics summary for monitoring."""
        return {
            "total_signals_generated": self.total_signals_generated,
            "total_signals_validated": self.total_signals_validated,
            "total_signals_rejected": self.total_signals_rejected,
            "validation_success_rate": self.get_validation_success_rate(),
            "enter_long_signals": self.enter_long_signals,
            "exit_long_signals": self.exit_long_signals,
            "high_confidence_signals": self.high_confidence_signals,
            "medium_confidence_signals": self.medium_confidence_signals,
            "low_confidence_signals": self.low_confidence_signals,
            "generation_errors": self.generation_errors,
            "validation_errors": self.validation_errors,
            "last_signal_generated_at": (
                self.last_signal_generated_at.isoformat() 
                if self.last_signal_generated_at else None
            ),
            "signals_by_strategy": self.signals_by_strategy,
        }
    
    def check_health(self) -> Dict[str, any]:
        """Check health of signal generation system."""
        issues = []
        
        # Check if signals are being generated
        if self.last_signal_generated_at:
            time_since_last_signal = (datetime.now() - self.last_signal_generated_at).total_seconds()
            if time_since_last_signal > 3600:  # 1 hour
                issues.append(f"No signals generated in {time_since_last_signal/60:.0f} minutes")
        
        # Check validation success rate
        success_rate = self.get_validation_success_rate()
        if success_rate < 0.5 and self.total_signals_generated > 10:
            issues.append(f"Low validation success rate: {success_rate:.1%}")
        
        # Check error rate
        if self.generation_errors > 10:
            issues.append(f"High generation error count: {self.generation_errors}")
        
        if self.validation_errors > 10:
            issues.append(f"High validation error count: {self.validation_errors}")
        
        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "metrics": self.get_summary()
        }


# Global metrics instance
_metrics_instance: SignalGenerationMetrics = None


def get_signal_metrics() -> SignalGenerationMetrics:
    """Get global signal generation metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = SignalGenerationMetrics()
    return _metrics_instance


def reset_metrics() -> None:
    """Reset metrics (for testing)."""
    global _metrics_instance
    _metrics_instance = SignalGenerationMetrics()
