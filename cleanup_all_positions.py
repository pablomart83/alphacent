"""
Cleanup script: Close all ghost XLV/XLU positions on eToro demo and mark them closed in DB.
Run: source venv/bin/activate && python cleanup_all_positions.py
"""
import time
from datetime import datetime
from src.core.config import get_config
from src.models.enums import TradingMode
from src.api.etoro_client import EToroAPIClient
from src.models.database import get_database
from src.models.orm import PositionORM
from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

client = EToroAPIClient(
    public_key=credentials['public_key'],
    user_key=credentials['user_key'],
    mode=TradingMode.DEMO
)

# Get all positions from eToro
portfolio_data = client._make_request(method='GET', endpoint='/api/v1/trading/info/demo/portfolio')
positions = portfolio_data.get('clientPortfolio', {}).get('positions', [])
print(f'Found {len(positions)} positions on eToro to close')

closed = 0
failed = 0
for i, pos in enumerate(positions):
    pos_id = pos.get('positionID')
    instrument_id = pos.get('instrumentID')
    
    try:
        endpoint = f'/api/v1/trading/execution/demo/market-close-orders/positions/{pos_id}'
        client._make_request(method='POST', endpoint=endpoint, json_data={'InstrumentID': instrument_id})
        closed += 1
        if (i + 1) % 10 == 0:
            print(f'  Closed {i + 1}/{len(positions)}...')
        time.sleep(0.3)
    except Exception as e:
        print(f'  Failed to close {pos_id}: {e}')
        failed += 1

print(f'eToro cleanup: {closed} closed, {failed} failed')

# Mark all DB positions as closed
db = get_database()
session = db.get_session()
open_positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
for p in open_positions:
    p.closed_at = datetime.now()
    p.pending_closure = False
session.commit()
print(f'DB cleanup: {len(open_positions)} positions marked as closed')
session.close()

# Verify
time.sleep(2)
portfolio_data2 = client._make_request(method='GET', endpoint='/api/v1/trading/info/demo/portfolio')
remaining = portfolio_data2.get('clientPortfolio', {}).get('positions', [])
print(f'Verification: {len(remaining)} positions remaining on eToro')
