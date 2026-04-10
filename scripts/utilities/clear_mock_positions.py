"""Clear mock positions from database."""

import sys
sys.path.insert(0, '.')

from src.models.database import get_database
from src.models.orm import PositionORM

print("=" * 70)
print("Clearing Mock Positions")
print("=" * 70)

db = get_database()
session = db.get_session()

# Get all positions
positions = session.query(PositionORM).all()

print(f"\nFound {len(positions)} positions in database:")
for pos in positions:
    print(f"  - {pos.id}: {pos.symbol} (eToro ID: {pos.etoro_position_id})")

# Delete mock positions (those with etoro_pos_ prefix)
mock_positions = [p for p in positions if p.etoro_position_id and p.etoro_position_id.startswith('etoro_pos_')]

if mock_positions:
    print(f"\nDeleting {len(mock_positions)} mock positions...")
    for pos in mock_positions:
        print(f"  - Deleting {pos.id}: {pos.symbol}")
        session.delete(pos)
    
    session.commit()
    print(f"\n✅ Deleted {len(mock_positions)} mock positions")
else:
    print("\n✅ No mock positions found")

# Show remaining positions
remaining = session.query(PositionORM).all()
print(f"\nRemaining positions: {len(remaining)}")
for pos in remaining:
    print(f"  - {pos.id}: {pos.symbol} (eToro ID: {pos.etoro_position_id})")

session.close()
print("\n" + "=" * 70)
