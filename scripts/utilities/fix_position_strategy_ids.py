#!/usr/bin/env python3
"""Fix strategy_id for positions that were created with default 'etoro_position' value."""

import logging
from datetime import datetime, timedelta

from src.models.database import Database
from src.models.orm import OrderORM, PositionORM, StrategyORM
from src.models.enums import OrderStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_position_strategy_ids():
    """Link positions to their correct strategies based on orders."""
    db = Database()
    db.initialize()
    
    with db.get_session() as session:
        # Find all positions with default strategy_id
        positions_to_fix = session.query(PositionORM).filter(
            PositionORM.strategy_id == "etoro_position"
        ).all()
        
        logger.info(f"Found {len(positions_to_fix)} positions with default strategy_id")
        
        fixed_count = 0
        
        for pos in positions_to_fix:
            # Find the order that created this position
            # Match by symbol and timestamp (within 30 seconds)
            if pos.opened_at and pos.symbol:
                time_window_start = pos.opened_at - timedelta(seconds=30)
                time_window_end = pos.opened_at + timedelta(seconds=30)
                
                matching_order = session.query(OrderORM).filter(
                    OrderORM.symbol == pos.symbol,
                    OrderORM.status == OrderStatus.FILLED,
                    OrderORM.filled_at >= time_window_start,
                    OrderORM.filled_at <= time_window_end
                ).first()
                
                if matching_order:
                    # Verify the strategy exists and is DEMO
                    strategy = session.query(StrategyORM).filter_by(
                        id=matching_order.strategy_id
                    ).first()
                    
                    if strategy and strategy.status == "DEMO":
                        pos.strategy_id = matching_order.strategy_id
                        fixed_count += 1
                        logger.info(f"Fixed position {pos.id[:8]}... ({pos.symbol}) -> strategy {strategy.name}")
                    else:
                        logger.debug(f"No DEMO strategy found for order {matching_order.id}")
                else:
                    logger.debug(f"No matching order found for position {pos.id[:8]}... ({pos.symbol})")
        
        session.commit()
        logger.info(f"Fixed {fixed_count} positions")
        
        # Verify results
        demo_positions = session.query(PositionORM).join(
            StrategyORM, PositionORM.strategy_id == StrategyORM.id
        ).filter(
            StrategyORM.status == "DEMO"
        ).all()
        
        logger.info(f"\nTotal DEMO positions after fix: {len(demo_positions)}")
        
        # Group by symbol
        from collections import Counter
        symbols = Counter([p.symbol for p in demo_positions])
        logger.info(f"\nDEMO positions by symbol:")
        for symbol, count in symbols.most_common():
            logger.info(f"  {symbol}: {count}")


if __name__ == "__main__":
    fix_position_strategy_ids()
