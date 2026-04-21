"""
Trade Frequency Limiter - Enforces trading frequency constraints.

Implements:
1. Maximum trades per strategy per month
2. Minimum holding period enforcement
3. Trade tracking and rejection logging
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.models.dataclasses import Strategy, TradingSignal
from src.models.database import Database

logger = logging.getLogger(__name__)


@dataclass
class TradeFrequencyCheck:
    """Result of trade frequency check."""
    allowed: bool
    reason: str
    trades_this_month: int
    max_trades_per_month: int
    days_since_last_trade: Optional[float]
    min_holding_period_days: int


class TradeFrequencyLimiter:
    """
    Enforces trade frequency limits to reduce transaction costs.
    
    Tracks:
    - Trades per strategy per month
    - Minimum holding period between trades
    - Rejected signals with reasons
    """
    
    def __init__(self, config: Dict[str, Any], database: Database):
        """
        Initialize trade frequency limiter.
        
        Args:
            config: Configuration dictionary
            database: Database instance for tracking trades
        """
        self.config = config
        self.database = database
        
        # Get frequency limits from config
        alpha_edge_config = config.get('alpha_edge', {})
        self.min_holding_period_days = alpha_edge_config.get('min_holding_period_days', 7)
        self.max_trades_per_strategy_per_month = alpha_edge_config.get(
            'max_trades_per_strategy_per_month', 4
        )
        
        # Cache for trade counts (strategy_id -> {month: count})
        self._trade_count_cache: Dict[str, Dict[str, int]] = {}
        
        # Cache for last trade dates (strategy_id -> datetime)
        self._last_trade_cache: Dict[str, datetime] = {}
        
        logger.info(
            f"TradeFrequencyLimiter initialized - "
            f"Min holding: {self.min_holding_period_days} days, "
            f"Max trades/month: {self.max_trades_per_strategy_per_month}"
        )
    
    def check_signal_allowed(
        self,
        signal: TradingSignal,
        strategy: Strategy
    ) -> TradeFrequencyCheck:
        """
        Check if a signal is allowed based on frequency limits.

        Monthly trade cap and minimum holding period only apply to Alpha Edge
        strategies — they are fundamental plays with specific entry windows where
        churning in and out is genuinely harmful.

        DSL strategies (EMA crossover, RSI dip buy, etc.) should trade whenever
        the signal fires. Applying a monthly cap to a systematic DSL strategy
        defeats the purpose of running it.
        """
        is_alpha_edge = (
            hasattr(strategy, 'metadata') and
            isinstance(strategy.metadata, dict) and
            strategy.metadata.get('strategy_category') == 'alpha_edge'
        )

        trades_this_month = self._get_trades_this_month(strategy.id)

        if is_alpha_edge:
            # Alpha Edge: enforce monthly cap and minimum holding period
            if trades_this_month >= self.max_trades_per_strategy_per_month:
                return TradeFrequencyCheck(
                    allowed=False,
                    reason=f"Monthly trade limit reached ({trades_this_month}/{self.max_trades_per_strategy_per_month})",
                    trades_this_month=trades_this_month,
                    max_trades_per_month=self.max_trades_per_strategy_per_month,
                    days_since_last_trade=None,
                    min_holding_period_days=self.min_holding_period_days
                )

            last_trade_date = self._get_last_trade_date(strategy.id)
            if last_trade_date:
                days_since_last = (datetime.now() - last_trade_date).total_seconds() / 86400
                if days_since_last < self.min_holding_period_days:
                    return TradeFrequencyCheck(
                        allowed=False,
                        reason=f"Minimum holding period not met ({days_since_last:.1f}/{self.min_holding_period_days} days)",
                        trades_this_month=trades_this_month,
                        max_trades_per_month=self.max_trades_per_strategy_per_month,
                        days_since_last_trade=days_since_last,
                        min_holding_period_days=self.min_holding_period_days
                    )
                days_since_last_trade = days_since_last
            else:
                days_since_last_trade = None
        else:
            # DSL strategies: no frequency constraints — trade on every valid signal
            days_since_last_trade = None

        return TradeFrequencyCheck(
            allowed=True,
            reason="Signal allowed",
            trades_this_month=trades_this_month,
            max_trades_per_month=self.max_trades_per_strategy_per_month,
            days_since_last_trade=days_since_last_trade,
            min_holding_period_days=self.min_holding_period_days
        )
    
    def record_trade(self, strategy_id: str, symbol: str, timestamp: Optional[datetime] = None):
        """
        Record a trade for frequency tracking.
        
        Args:
            strategy_id: Strategy ID
            symbol: Symbol traded
            timestamp: Trade timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Update trade count cache
        month_key = timestamp.strftime('%Y-%m')
        
        if strategy_id not in self._trade_count_cache:
            self._trade_count_cache[strategy_id] = {}
        
        if month_key not in self._trade_count_cache[strategy_id]:
            self._trade_count_cache[strategy_id][month_key] = 0
        
        self._trade_count_cache[strategy_id][month_key] += 1
        
        # Update last trade cache
        self._last_trade_cache[strategy_id] = timestamp
        
        logger.info(
            f"Recorded trade for strategy {strategy_id}: {symbol} at {timestamp}, "
            f"trades this month: {self._trade_count_cache[strategy_id][month_key]}"
        )
    
    def log_rejected_signal(
        self,
        signal: TradingSignal,
        strategy: Strategy,
        check_result: TradeFrequencyCheck
    ):
        """
        Log a rejected signal for analysis.
        
        Args:
            signal: Rejected signal
            strategy: Strategy that generated the signal
            check_result: Frequency check result
        """
        logger.info(
            f"Signal rejected for {signal.symbol} (strategy: {strategy.name}): "
            f"{check_result.reason}"
        )
        
        # Store in database for later analysis
        try:
            with self.database.get_session() as session:
                # Create rejected signal record
                from src.models.orm import RejectedSignalORM
                
                rejected = RejectedSignalORM(
                    strategy_id=strategy.id,
                    symbol=signal.symbol,
                    signal_type=signal.action.value if hasattr(signal.action, 'value') else str(signal.action),
                    rejection_reason=check_result.reason,
                    trades_this_month=check_result.trades_this_month,
                    days_since_last_trade=check_result.days_since_last_trade,
                    timestamp=datetime.now()
                )
                
                session.add(rejected)
                session.commit()
                
        except Exception as e:
            # Don't fail if we can't log - just warn
            logger.warning(f"Failed to log rejected signal: {e}")
    
    def _get_trades_this_month(self, strategy_id: str) -> int:
        """
        Get number of trades for strategy this month.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Number of trades this month
        """
        current_month = datetime.now().strftime('%Y-%m')
        
        # Check cache first
        if strategy_id in self._trade_count_cache:
            if current_month in self._trade_count_cache[strategy_id]:
                return self._trade_count_cache[strategy_id][current_month]
        
        # Query database
        try:
            with self.database.get_session() as session:
                from src.models.orm import PositionORM
                
                # Get start of current month
                now = datetime.now()
                month_start = datetime(now.year, now.month, 1)
                
                # Count positions opened this month
                count = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy_id,
                    PositionORM.opened_at >= month_start
                ).count()
                
                # Update cache
                if strategy_id not in self._trade_count_cache:
                    self._trade_count_cache[strategy_id] = {}
                self._trade_count_cache[strategy_id][current_month] = count
                
                return count
                
        except Exception as e:
            logger.warning(f"Error getting trade count: {e}")
            return 0
    
    def _get_last_trade_date(self, strategy_id: str) -> Optional[datetime]:
        """
        Get date of last trade for strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Datetime of last trade, or None if no trades
        """
        # Check cache first
        if strategy_id in self._last_trade_cache:
            return self._last_trade_cache[strategy_id]
        
        # Query database
        try:
            with self.database.get_session() as session:
                from src.models.orm import PositionORM
                
                # Get most recent position
                last_position = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy_id
                ).order_by(PositionORM.opened_at.desc()).first()
                
                if last_position:
                    last_date = last_position.opened_at
                    self._last_trade_cache[strategy_id] = last_date
                    return last_date
                
                return None
                
        except Exception as e:
            logger.warning(f"Error getting last trade date: {e}")
            return None
    
    def get_strategy_stats(self, strategy_id: str) -> Dict[str, Any]:
        """
        Get frequency statistics for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Dictionary with frequency stats
        """
        trades_this_month = self._get_trades_this_month(strategy_id)
        last_trade_date = self._get_last_trade_date(strategy_id)
        
        days_since_last = None
        if last_trade_date:
            days_since_last = (datetime.now() - last_trade_date).total_seconds() / 86400
        
        return {
            'trades_this_month': trades_this_month,
            'max_trades_per_month': self.max_trades_per_strategy_per_month,
            'trades_remaining': max(0, self.max_trades_per_strategy_per_month - trades_this_month),
            'last_trade_date': last_trade_date.isoformat() if last_trade_date else None,
            'days_since_last_trade': days_since_last,
            'min_holding_period_days': self.min_holding_period_days,
            'can_trade_now': (
                trades_this_month < self.max_trades_per_strategy_per_month and
                (days_since_last is None or days_since_last >= self.min_holding_period_days)
            )
        }
    
    def clear_cache(self):
        """Clear internal caches (useful for testing)."""
        self._trade_count_cache.clear()
        self._last_trade_cache.clear()
        logger.info("Trade frequency limiter cache cleared")
