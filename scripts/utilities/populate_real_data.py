#!/usr/bin/env python3
"""
Populate database with real data from eToro API.

This script:
1. Loads real eToro credentials
2. Fetches account info, positions, and market data
3. Saves to database
4. Allows frontend to display real data
"""

import asyncio
import logging
from datetime import datetime

from src.core.config import Configuration
from src.models.database import get_database
from src.models.enums import TradingMode
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.orm import AccountInfoORM, PositionORM

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def populate_account_data(mode: TradingMode = TradingMode.DEMO):
    """
    Fetch and populate account data from eToro.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
    """
    logger.info(f"=" * 60)
    logger.info(f"POPULATING DATABASE WITH REAL ETORO DATA")
    logger.info(f"Mode: {mode.value}")
    logger.info(f"=" * 60)
    
    # Initialize configuration
    config = Configuration()
    
    # Load credentials
    try:
        credentials = config.load_credentials(mode)
        if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
            logger.error(f"No credentials configured for {mode.value} mode")
            return False
            
        logger.info(f"✓ Credentials loaded for {mode.value} mode")
        
    except Exception as e:
        logger.error(f"Failed to load credentials: {e}")
        return False
    
    # Create eToro client
    try:
        client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=mode
        )
        logger.info(f"✓ eToro client created")
        
    except Exception as e:
        logger.error(f"Failed to create eToro client: {e}")
        return False
    
    # Get database
    db = get_database("alphacent.db")
    session = db.get_session()
    
    try:
        # Fetch account info
        logger.info(f"\nFetching account info...")
        try:
            account_info = client.get_account_info()
            logger.info(f"✓ Account info retrieved:")
            logger.info(f"  Account ID: {account_info.account_id}")
            logger.info(f"  Balance: ${account_info.balance:,.2f}")
            logger.info(f"  Buying Power: ${account_info.buying_power:,.2f}")
            logger.info(f"  Margin Used: ${account_info.margin_used:,.2f}")
            logger.info(f"  Daily P&L: ${account_info.daily_pnl:,.2f}")
            logger.info(f"  Total P&L: ${account_info.total_pnl:,.2f}")
            logger.info(f"  Positions: {account_info.positions_count}")
            
            # Save to database
            account_orm = session.query(AccountInfoORM).filter_by(
                account_id=account_info.account_id
            ).first()
            
            if account_orm:
                # Update existing
                account_orm.mode = account_info.mode
                account_orm.balance = account_info.balance
                account_orm.equity = account_info.equity
                account_orm.buying_power = account_info.buying_power
                account_orm.margin_used = account_info.margin_used
                account_orm.margin_available = account_info.margin_available
                account_orm.daily_pnl = account_info.daily_pnl
                account_orm.total_pnl = account_info.total_pnl
                account_orm.positions_count = account_info.positions_count
                account_orm.updated_at = account_info.updated_at
                logger.info(f"✓ Updated existing account record")
            else:
                # Create new
                account_orm = AccountInfoORM(
                    account_id=account_info.account_id,
                    mode=account_info.mode,
                    balance=account_info.balance,
                    equity=account_info.equity,
                    buying_power=account_info.buying_power,
                    margin_used=account_info.margin_used,
                    margin_available=account_info.margin_available,
                    daily_pnl=account_info.daily_pnl,
                    total_pnl=account_info.total_pnl,
                    positions_count=account_info.positions_count,
                    updated_at=account_info.updated_at
                )
                session.add(account_orm)
                logger.info(f"✓ Created new account record")
            
            session.commit()
            
        except EToroAPIError as e:
            logger.error(f"✗ Failed to fetch account info: {e}")
            logger.error(f"  This might mean:")
            logger.error(f"  - eToro API is unavailable")
            logger.error(f"  - Credentials are invalid")
            logger.error(f"  - Network connectivity issues")
            return False
        
        # Fetch positions
        logger.info(f"\nFetching positions...")
        try:
            positions = client.get_positions()
            logger.info(f"✓ Positions retrieved: {len(positions)} positions")
            
            for position in positions:
                logger.info(f"  - {position.symbol}: {position.quantity} @ ${position.entry_price:.2f}")
                logger.info(f"    Current: ${position.current_price:.2f}, P&L: ${position.unrealized_pnl:.2f}")
                
                # Save to database
                position_orm = session.query(PositionORM).filter_by(id=position.id).first()
                
                if position_orm:
                    # Update existing
                    position_orm.current_price = position.current_price
                    position_orm.unrealized_pnl = position.unrealized_pnl
                    position_orm.realized_pnl = position.realized_pnl
                    position_orm.stop_loss = position.stop_loss
                    position_orm.take_profit = position.take_profit
                    position_orm.closed_at = position.closed_at
                else:
                    # Create new
                    position_orm = PositionORM(
                        id=position.id,
                        strategy_id=position.strategy_id,
                        symbol=position.symbol,
                        side=position.side,
                        quantity=position.quantity,
                        entry_price=position.entry_price,
                        current_price=position.current_price,
                        unrealized_pnl=position.unrealized_pnl,
                        realized_pnl=position.realized_pnl,
                        opened_at=position.opened_at,
                        etoro_position_id=position.etoro_position_id,
                        stop_loss=position.stop_loss,
                        take_profit=position.take_profit,
                        closed_at=position.closed_at
                    )
                    session.add(position_orm)
            
            session.commit()
            logger.info(f"✓ Saved {len(positions)} positions to database")
            
        except EToroAPIError as e:
            logger.error(f"✗ Failed to fetch positions: {e}")
        
        logger.info(f"\n" + "=" * 60)
        logger.info(f"DATABASE POPULATION COMPLETE")
        logger.info(f"=" * 60)
        logger.info(f"\nYou can now:")
        logger.info(f"1. Refresh the frontend")
        logger.info(f"2. Account Overview will show real balance")
        logger.info(f"3. Positions will show real open positions")
        logger.info(f"4. Data is cached in database for fast access")
        
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return False
        
    finally:
        session.close()


def main():
    """Main entry point."""
    import sys
    
    # Parse command line arguments
    mode = TradingMode.DEMO
    if len(sys.argv) > 1:
        mode_arg = sys.argv[1].upper()
        if mode_arg == "LIVE":
            mode = TradingMode.LIVE
            logger.warning("⚠️  Using LIVE mode - real money account!")
            response = input("Are you sure? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Cancelled")
                return
    
    success = populate_account_data(mode)
    
    if success:
        logger.info("\n✓ SUCCESS: Database populated with real eToro data")
        sys.exit(0)
    else:
        logger.error("\n✗ FAILED: Could not populate database")
        logger.error("Check the errors above for details")
        sys.exit(1)


if __name__ == '__main__':
    main()
