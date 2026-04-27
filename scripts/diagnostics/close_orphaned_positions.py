"""
Close all eToro positions that have no matching open record in our DB.
Runs the diff, then calls close_position for each orphan.
"""
import sys, subprocess
sys.path.insert(0, '/home/ubuntu/alphacent')

from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.utils.symbol_normalizer import normalize_symbol
from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

# Fetch eToro positions
print("Fetching eToro positions...")
etoro_positions = client.get_positions()
etoro_by_id = {str(p.etoro_position_id): p for p in etoro_positions}
print(f"eToro open: {len(etoro_by_id)}")

# Fetch DB open positions via psql
result = subprocess.run(
    ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-c",
     "SELECT etoro_position_id FROM positions WHERE closed_at IS NULL;"],
    capture_output=True, text=True
)
db_open_ids = set()
for line in result.stdout.strip().splitlines():
    line = line.strip()
    if line:
        db_open_ids.add(line)
print(f"DB open:    {len(db_open_ids)}")

# Find orphans: on eToro but not in DB
orphans = {eid: p for eid, p in etoro_by_id.items() if eid not in db_open_ids}
print(f"\nOrphans to close: {len(orphans)}")

if not orphans:
    print("Nothing to do.")
    sys.exit(0)

for eid, pos in sorted(orphans.items(), key=lambda x: normalize_symbol(x[1].symbol)):
    sym = normalize_symbol(pos.symbol)
    instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(sym)
    print(f"  Closing {sym:10s} etoro_id={eid} instrument_id={instrument_id} ... ", end="", flush=True)
    try:
        client.close_position(eid, instrument_id=instrument_id)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")

print("\nDone. Run etoro_position_diff.py again to verify.")
