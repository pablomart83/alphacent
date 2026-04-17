"""Close remaining XLK duplicate positions still open on eToro."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.enums import TradingMode
from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials['public_key'],
    user_key=credentials['user_key'],
    mode=TradingMode.DEMO
)

# (pos_id, symbol, invested_amount) — must pass Amount or eToro creates stuck order
to_close = [
    ('3492786659', 'XLK', 2400.0),
    ('3492786689', 'XLK', 498.53),
    ('3492786975', 'XLK', 2399.99),
]

for pos_id, symbol, amount in to_close:
    try:
        iid = SYMBOL_TO_INSTRUMENT_ID.get(symbol)
        result = client.close_position(pos_id, instrument_id=iid, amount=amount)
        print(f'OK {symbol} {pos_id} amount={amount} -> {result}')
    except Exception as e:
        print(f'FAIL {symbol} {pos_id}: {e}')
