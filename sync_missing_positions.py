#!/usr/bin/env python3
"""Sync missing positions and fix symbol normalization"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
from src.models.database import get_database
from src.models.orm import PositionORM
from src.utils.symbol_normalizer import normalize_symbol

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
etoro_client = EToroAPIClient(
    public_key=credentials['public_key'],
    user_key=credentials['user_key'],
    mode=TradingMode.DEMO,
)

# Get positions from eToro
etoro_positions = etoro_client.get_positions()
print(f'eToro has {len(etoro_positions)} positions')

# Get positions from database
db = get_database()
session = db.get_session()

try:
    db_positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
    print(f'Database has {len(db_positions)} open positions')
    
    # Map by etoro_position_id
    db_position_ids = {p.etoro_position_id for p in db_positions}
    etoro_position_ids = {p.etoro_position_id for p in etoro_positions}
    
    missing_ids = etoro_position_ids - db_position_ids
    print(f'\nMissing {len(missing_ids)} positions in database')
    
    # Fix symbol normalization for existing positions
    print('\nFixing symbol normalization for existing positions...')
    fixed_count = 0
    for pos in db_positions:
        normalized = normalize_symbol(pos.symbol)
        if pos.symbol != normalized:
            print(f'  Fixing: {pos.symbol} -> {normalized} (etoro_id={pos.etoro_position_id})')
            pos.symbol = normalized
            fixed_count += 1
    
    if fixed_count > 0:
        session.commit()
        print(f'Fixed {fixed_count} positions')
    
    # Show what's in database now
    print('\nPositions in database after fix:')
    db_positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
    symbols = {}
    for p in db_positions:
        symbols[p.symbol] = symbols.get(p.symbol, 0) + 1
    
    for symbol, count in sorted(symbols.items()):
        print(f'  {symbol}: {count}')
    
finally:
    session.close()
