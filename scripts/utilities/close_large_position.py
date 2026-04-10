#!/usr/bin/env python3
"""Close the large autonomous position that's blocking new trades"""

from src.models.database import get_database
from src.models.orm import PositionORM
from src.risk.risk_manager import EXTERNAL_POSITION_STRATEGY_IDS
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
from datetime import datetime

# Initialize API client
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO,
)

# Find the large autonomous position
db = get_database()
session = db.get_session()

try:
    positions = session.query(PositionORM).filter(
        PositionORM.closed_at == None
    ).all()

    autonomous = [p for p in positions if p.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS]

    print(f'Found {len(autonomous)} autonomous position(s)')
    
    for pos in autonomous:
        value = pos.quantity * pos.current_price
        print(f'\nPosition:')
        print(f'  ID: {pos.id}')
        print(f'  Symbol: {pos.symbol}')
        print(f'  Quantity: {pos.quantity:.2f}')
        print(f'  Value: ${value:,.2f}')
        print(f'  eToro Position ID: {pos.etoro_position_id}')
        
        # Close on eToro
        print(f'\nClosing position on eToro...')
        try:
            # Extract instrument ID from symbol (ID_1137 -> 1137)
            instrument_id = int(pos.symbol.replace('ID_', ''))
            result = client.close_position(pos.etoro_position_id, instrument_id)
            print(f'  ✅ Closed on eToro: {result}')
            
            # Update database
            pos.closed_at = datetime.now()
            session.commit()
            print(f'  ✅ Updated database')
            
        except Exception as e:
            print(f'  ❌ Error closing position: {e}')
            session.rollback()

finally:
    session.close()

print('\n✅ Done!')
