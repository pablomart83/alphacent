"""
Execution quality tracking for order execution analysis.

Tracks metrics like slippage, fill rate, fill time, and rejection rate
to monitor and improve order execution quality.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

logger = logging.getLogger(__name__)


@dataclass
class ExecutionQualityMetrics:
    """Execution quality metrics."""
    avg_slippage: float  # Average slippage in price units
    avg_slippage_bps: float  # Average slippage in basis points
    fill_rate: float  # Percentage of orders filled
    avg_fill_time_seconds: float  # Average time to fill
    rejection_rate: float  # Percentage of orders rejected
    total_orders: int
    filled_orders: int
    rejected_orders: int
    pending_orders: int
    slippage_by_strategy: Dict[str, float]
    rejection_reasons: Dict[str, int]


class ExecutionQualityTracker:
    """
    Tracks execution quality metrics for orders.
    
    Analyzes order execution to provide insights into:
    - Slippage (difference between expected and filled price)
    - Fill rate (percentage of orders successfully filled)
    - Fill time (time from submission to fill)
    - Rejection rate (percentage of orders rejected)
    """
    
    def __init__(self, db: Optional[Database] = None):
        """
        Initialize execution quality tracker.
        
        Args:
            db: Database instance (creates new if not provided)
        """
        self.db = db or Database()
        logger.info("ExecutionQualityTracker initialized")
    
    def get_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_id: Optional[str] = None
    ) -> ExecutionQualityMetrics:
        """
        Get execution quality metrics for a time period.
        
        Args:
            start_date: Start of time period (default: 30 days ago)
            end_date: End of time period (default: now)
            strategy_id: Optional strategy filter
            
        Returns:
            ExecutionQualityMetrics with calculated metrics
        """
        session = self.db.get_session()
        
        try:
            # Default to last 30 days
            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()
            
            # Query orders in time period
            query = session.query(OrderORM).filter(
                OrderORM.submitted_at >= start_date,
                OrderORM.submitted_at <= end_date
            )
            
            # Apply strategy filter if provided
            if strategy_id:
                query = query.filter(OrderORM.strategy_id == strategy_id)
            
            orders = query.all()
            
            if not orders:
                return ExecutionQualityMetrics(
                    avg_slippage=0.0,
                    avg_slippage_bps=0.0,
                    fill_rate=0.0,
                    avg_fill_time_seconds=0.0,
                    rejection_rate=0.0,
                    total_orders=0,
                    filled_orders=0,
                    rejected_orders=0,
                    pending_orders=0,
                    slippage_by_strategy={},
                    rejection_reasons={}
                )
            
            # Calculate metrics
            total_orders = len(orders)
            filled_orders = [o for o in orders if o.status == OrderStatus.FILLED]
            rejected_orders = [o for o in orders if o.status == OrderStatus.FAILED]
            pending_orders = [o for o in orders if o.status == OrderStatus.PENDING]
            
            fill_rate = (len(filled_orders) / total_orders * 100) if total_orders > 0 else 0.0
            rejection_rate = (len(rejected_orders) / total_orders * 100) if total_orders > 0 else 0.0
            
            # Calculate slippage metrics
            slippages = []
            slippages_bps = []
            fill_times = []
            slippage_by_strategy = {}
            strategy_order_counts = {}
            
            for order in filled_orders:
                # Calculate slippage
                if order.slippage is not None:
                    slippages.append(order.slippage)
                    
                    # Calculate slippage in basis points (bps)
                    if order.expected_price and order.expected_price > 0:
                        slippage_bps = (order.slippage / order.expected_price) * 10000
                        slippages_bps.append(slippage_bps)
                    
                    # Track by strategy
                    strategy_id_key = order.strategy_id or "unknown"
                    if strategy_id_key not in slippage_by_strategy:
                        slippage_by_strategy[strategy_id_key] = 0.0
                        strategy_order_counts[strategy_id_key] = 0
                    slippage_by_strategy[strategy_id_key] += order.slippage
                    strategy_order_counts[strategy_id_key] += 1
                
                # Calculate fill time
                if order.fill_time_seconds is not None:
                    fill_times.append(order.fill_time_seconds)
            
            # Average slippage by strategy
            for strategy_id_key in slippage_by_strategy:
                if strategy_order_counts[strategy_id_key] > 0:
                    slippage_by_strategy[strategy_id_key] /= strategy_order_counts[strategy_id_key]
            
            avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0
            avg_slippage_bps = sum(slippages_bps) / len(slippages_bps) if slippages_bps else 0.0
            avg_fill_time = sum(fill_times) / len(fill_times) if fill_times else 0.0
            
            # Track rejection reasons (placeholder - would need to parse error messages)
            rejection_reasons = {}
            for order in rejected_orders:
                # In a real implementation, parse error messages from eToro
                reason = "Unknown"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            
            return ExecutionQualityMetrics(
                avg_slippage=avg_slippage,
                avg_slippage_bps=avg_slippage_bps,
                fill_rate=fill_rate,
                avg_fill_time_seconds=avg_fill_time,
                rejection_rate=rejection_rate,
                total_orders=total_orders,
                filled_orders=len(filled_orders),
                rejected_orders=len(rejected_orders),
                pending_orders=len(pending_orders),
                slippage_by_strategy=slippage_by_strategy,
                rejection_reasons=rejection_reasons
            )
        
        finally:
            session.close()
    
    def get_slippage_by_strategy(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Get average slippage by strategy.
        
        Args:
            start_date: Start of time period (default: 30 days ago)
            end_date: End of time period (default: now)
            
        Returns:
            Dictionary mapping strategy_id to average slippage
        """
        metrics = self.get_metrics(start_date, end_date)
        return metrics.slippage_by_strategy
    
    def get_fill_rate_by_strategy(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Get fill rate by strategy.
        
        Args:
            start_date: Start of time period (default: 30 days ago)
            end_date: End of time period (default: now)
            
        Returns:
            Dictionary mapping strategy_id to fill rate percentage
        """
        session = self.db.get_session()
        
        try:
            # Default to last 30 days
            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()
            
            # Query orders in time period
            orders = session.query(OrderORM).filter(
                OrderORM.submitted_at >= start_date,
                OrderORM.submitted_at <= end_date
            ).all()
            
            # Group by strategy
            strategy_stats = {}  # strategy_id -> (total, filled)
            
            for order in orders:
                strategy_id = order.strategy_id or "unknown"
                if strategy_id not in strategy_stats:
                    strategy_stats[strategy_id] = {"total": 0, "filled": 0}
                
                strategy_stats[strategy_id]["total"] += 1
                if order.status == OrderStatus.FILLED:
                    strategy_stats[strategy_id]["filled"] += 1
            
            # Calculate fill rates
            fill_rates = {}
            for strategy_id, stats in strategy_stats.items():
                if stats["total"] > 0:
                    fill_rates[strategy_id] = (stats["filled"] / stats["total"]) * 100
                else:
                    fill_rates[strategy_id] = 0.0
            
            return fill_rates
        
        finally:
            session.close()


# Global instance
_execution_quality_tracker: Optional[ExecutionQualityTracker] = None


def get_execution_quality_tracker() -> ExecutionQualityTracker:
    """Get or create global execution quality tracker instance."""
    global _execution_quality_tracker
    if _execution_quality_tracker is None:
        _execution_quality_tracker = ExecutionQualityTracker()
    return _execution_quality_tracker
