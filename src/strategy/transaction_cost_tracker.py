"""
Transaction Cost Tracker - Tracks and reports transaction costs.

Calculates:
1. Commission costs
2. Slippage costs
3. Spread costs
4. Total transaction costs
5. Cost as % of returns
6. Cost savings from reduced trading frequency
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.models.database import Database

logger = logging.getLogger(__name__)


@dataclass
class TransactionCosts:
    """Transaction cost breakdown."""
    commission: float
    slippage: float
    spread: float
    total: float
    trade_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'commission': self.commission,
            'slippage': self.slippage,
            'spread': self.spread,
            'total': self.total,
            'trade_count': self.trade_count,
            'avg_cost_per_trade': self.total / self.trade_count if self.trade_count > 0 else 0
        }


@dataclass
class CostComparison:
    """Comparison of costs before and after changes."""
    before_costs: TransactionCosts
    after_costs: TransactionCosts
    savings: float
    savings_percent: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'before': self.before_costs.to_dict(),
            'after': self.after_costs.to_dict(),
            'savings': self.savings,
            'savings_percent': self.savings_percent
        }


class TransactionCostTracker:
    """
    Tracks transaction costs and calculates savings.
    
    Monitors:
    - Commission costs per trade
    - Slippage (difference between expected and filled price)
    - Spread costs
    - Total costs as % of returns
    """
    
    def __init__(self, config: Dict[str, Any], database: Database):
        """
        Initialize transaction cost tracker.
        
        Args:
            config: Configuration dictionary
            database: Database instance
        """
        self.config = config
        self.database = database
        
        # Get transaction cost parameters from config
        backtest_config = config.get('backtest', {})
        cost_config = backtest_config.get('transaction_costs', {})
        
        self.commission_per_share = cost_config.get('commission_per_share', 0.005)
        self.commission_percent = cost_config.get('commission_percent', 0.001)
        self.slippage_percent = cost_config.get('slippage_percent', 0.0005)
        self.spread_percent = cost_config.get('spread_percent', 0.0002)
        
        logger.info(
            f"TransactionCostTracker initialized - "
            f"Commission: {self.commission_percent*100:.3f}%, "
            f"Slippage: {self.slippage_percent*100:.3f}%, "
            f"Spread: {self.spread_percent*100:.3f}%"
        )
    
    def calculate_trade_cost(
        self,
        symbol: str,
        quantity: float,
        price: float,
        filled_price: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate transaction costs for a single trade.
        
        Args:
            symbol: Symbol traded
            quantity: Quantity traded
            price: Expected price
            filled_price: Actual filled price (if available)
            
        Returns:
            Dictionary with cost breakdown
        """
        trade_value = quantity * price
        
        # Calculate commission
        commission_share = quantity * self.commission_per_share
        commission_pct = trade_value * self.commission_percent
        commission = commission_share + commission_pct
        
        # Calculate slippage (if we have filled price)
        if filled_price:
            slippage = abs(filled_price - price) * quantity
        else:
            # Estimate slippage
            slippage = trade_value * self.slippage_percent
        
        # Calculate spread
        spread = trade_value * self.spread_percent
        
        # Total cost
        total = commission + slippage + spread
        
        return {
            'commission': commission,
            'slippage': slippage,
            'spread': spread,
            'total': total,
            'total_percent': (total / trade_value * 100) if trade_value > 0 else 0
        }
    
    def get_period_costs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_id: Optional[str] = None
    ) -> TransactionCosts:
        """
        Get transaction costs for a period.
        
        Args:
            start_date: Start date (defaults to 30 days ago)
            end_date: End date (defaults to now)
            strategy_id: Optional strategy ID filter
            
        Returns:
            TransactionCosts with breakdown
        """
        if end_date is None:
            end_date = datetime.now()
        
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        try:
            with self.database.get_session() as session:
                from src.models.orm import OrderORM, OrderStatus
                
                # Query filled orders in period
                query = session.query(OrderORM).filter(
                    OrderORM.status == OrderStatus.FILLED,
                    OrderORM.filled_at >= start_date,
                    OrderORM.filled_at <= end_date
                )
                
                if strategy_id:
                    query = query.filter(OrderORM.strategy_id == strategy_id)
                
                orders = query.all()
                
                # Calculate costs
                total_commission = 0.0
                total_slippage = 0.0
                total_spread = 0.0
                
                for order in orders:
                    costs = self.calculate_trade_cost(
                        symbol=order.symbol,
                        quantity=order.filled_quantity or order.quantity,
                        price=order.expected_price or order.price or order.filled_price,
                        filled_price=order.filled_price
                    )
                    
                    total_commission += costs['commission']
                    total_slippage += costs['slippage']
                    total_spread += costs['spread']
                
                return TransactionCosts(
                    commission=total_commission,
                    slippage=total_slippage,
                    spread=total_spread,
                    total=total_commission + total_slippage + total_spread,
                    trade_count=len(orders)
                )
                
        except Exception as e:
            logger.error(f"Error calculating period costs: {e}")
            return TransactionCosts(
                commission=0.0,
                slippage=0.0,
                spread=0.0,
                total=0.0,
                trade_count=0
            )
    
    def calculate_cost_as_percent_of_returns(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate transaction costs as percentage of returns.
        
        Args:
            start_date: Start date
            end_date: End date
            strategy_id: Optional strategy ID filter
            
        Returns:
            Dictionary with cost analysis
        """
        costs = self.get_period_costs(start_date, end_date, strategy_id)
        
        # Get total returns for period
        try:
            with self.database.get_session() as session:
                from src.models.orm import PositionORM
                
                # Query closed positions in period
                query = session.query(PositionORM).filter(
                    PositionORM.closed_at.isnot(None),
                    PositionORM.closed_at >= start_date,
                    PositionORM.closed_at <= end_date
                )
                
                if strategy_id:
                    query = query.filter(PositionORM.strategy_id == strategy_id)
                
                positions = query.all()
                
                # Calculate total returns
                total_pnl = sum(p.realized_pnl for p in positions)
                
                # Calculate cost as % of returns
                if total_pnl > 0:
                    cost_percent = (costs.total / total_pnl) * 100
                else:
                    cost_percent = 0.0
                
                return {
                    'costs': costs.to_dict(),
                    'total_pnl': total_pnl,
                    'cost_as_percent_of_returns': cost_percent,
                    'net_pnl': total_pnl - costs.total,
                    'positions_closed': len(positions)
                }
                
        except Exception as e:
            logger.error(f"Error calculating cost as % of returns: {e}")
            return {
                'costs': costs.to_dict(),
                'total_pnl': 0.0,
                'cost_as_percent_of_returns': 0.0,
                'net_pnl': -costs.total,
                'positions_closed': 0
            }
    
    def compare_periods(
        self,
        before_start: datetime,
        before_end: datetime,
        after_start: datetime,
        after_end: datetime,
        strategy_id: Optional[str] = None
    ) -> CostComparison:
        """
        Compare transaction costs between two periods.
        
        Args:
            before_start: Start of "before" period
            before_end: End of "before" period
            after_start: Start of "after" period
            after_end: End of "after" period
            strategy_id: Optional strategy ID filter
            
        Returns:
            CostComparison with savings analysis
        """
        before_costs = self.get_period_costs(before_start, before_end, strategy_id)
        after_costs = self.get_period_costs(after_start, after_end, strategy_id)
        
        # Calculate savings
        savings = before_costs.total - after_costs.total
        
        if before_costs.total > 0:
            savings_percent = (savings / before_costs.total) * 100
        else:
            savings_percent = 0.0
        
        comparison = CostComparison(
            before_costs=before_costs,
            after_costs=after_costs,
            savings=savings,
            savings_percent=savings_percent
        )
        
        logger.info(
            f"Cost comparison - Before: ${before_costs.total:.2f} ({before_costs.trade_count} trades), "
            f"After: ${after_costs.total:.2f} ({after_costs.trade_count} trades), "
            f"Savings: ${savings:.2f} ({savings_percent:.1f}%)"
        )
        
        return comparison
    
    def get_monthly_report(
        self,
        year: int,
        month: int,
        strategy_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get monthly transaction cost report.
        
        Args:
            year: Year
            month: Month (1-12)
            strategy_id: Optional strategy ID filter
            
        Returns:
            Dictionary with monthly report
        """
        # Calculate period dates
        start_date = datetime(year, month, 1)
        
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Get costs and returns
        cost_analysis = self.calculate_cost_as_percent_of_returns(
            start_date, end_date, strategy_id
        )
        
        return {
            'period': f"{year}-{month:02d}",
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'strategy_id': strategy_id,
            **cost_analysis
        }
