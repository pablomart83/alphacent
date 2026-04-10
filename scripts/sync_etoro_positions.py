#!/usr/bin/env python3
"""
Sync positions from eToro to local database.

This script pulls all open positions from eToro and syncs them to the local database.
This is critical for order duplication prevention to work correctly.
"""
import sys
sys.path.insert(0, '.')

from src.core.order_monitor import OrderMonitor
from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.models.database import Database
from src.models.orm import PositionORM
from sqlalchemy import and_

def main():
    print("=" * 80)
    print("eToro Position Sync")
    print("=" * 80)
    
    # Get configuration
    config = get_config()
    
    # Load credentials for DEMO mode
    print("\n1. Loading credentials...")
    try:
        creds = config.load_credentials(TradingMode.DEMO)
    except Exception as e:
        print(f"   ❌ Failed to load credentials: {e}")
        print("   Please run: python scripts/utilities/save_credentials.py")
        return 1
    
    # Create eToro client for DEMO mode
    print("\n2. Connecting to eToro DEMO...")
    etoro_client = EToroAPIClient(
        public_key=creds['public_key'],
        user_key=creds['user_key'],
        mode=TradingMode.DEMO
    )
    
    # Create order monitor
    db = Database()
    monitor = OrderMonitor(etoro_client, db)
    
    # Check current database state
    print("\n2. Checking current database state...")
    with db.get_session() as session:
        open_positions = session.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        print(f"   Found {len(open_positions)} open positions in database")
        for pos in open_positions[:5]:  # Show first 5
            print(f"     - {pos.symbol}: {pos.side} qty={pos.quantity} @ ${pos.entry_price}")
        if len(open_positions) > 5:
            print(f"     ... and {len(open_positions) - 5} more")
    
    # Sync from eToro
    print("\n3. Syncing positions from eToro...")
    result = monitor.sync_positions(force=True)
    
    print(f"\n4. Sync Results:")
    print(f"   - Total positions from eToro: {result.get('total', 0)}")
    print(f"   - Created in database: {result.get('created', 0)}")
    print(f"   - Updated in database: {result.get('updated', 0)}")
    
    if 'error' in result:
        print(f"   ⚠️  Error: {result['error']}")
        return 1
    
    # Check final database state
    print("\n5. Final database state:")
    with db.get_session() as session:
        open_positions = session.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        print(f"   Total open positions: {len(open_positions)}")
        
        # Group by symbol
        by_symbol = {}
        for pos in open_positions:
            if pos.symbol not in by_symbol:
                by_symbol[pos.symbol] = []
            by_symbol[pos.symbol].append(pos)
        
        print(f"\n   Positions by symbol:")
        for symbol, positions in sorted(by_symbol.items()):
            print(f"     {symbol}: {len(positions)} position(s)")
            for pos in positions:
                print(f"       - Strategy: {pos.strategy_id}, Side: {pos.side}, Qty: {pos.quantity}")
    
    print("\n" + "=" * 80)
    print("✅ Sync complete!")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
