#!/usr/bin/env python3
"""Check current exposure and positions"""

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO,
)

# Get positions (all returned positions are open)
positions = client.get_positions()
print(f'Open positions: {len(positions)}')
print()

# Calculate exposure
total_exposure = sum(abs(p.quantity * p.current_price) for p in positions)
print(f'Total exposure from open positions: ${total_exposure:,.2f}')
print()

# Get account info
account = client.get_account_info()
balance = account.balance
max_exposure_pct = 0.90
max_exposure = balance * max_exposure_pct
available = max_exposure - total_exposure

print(f'Account balance: ${balance:,.2f}')
print(f'Max exposure (90%): ${max_exposure:,.2f}')
print(f'Current exposure: ${total_exposure:,.2f}')
print(f'Available for new trades: ${available:,.2f}')
print()

# Show top 10 positions by size
positions.sort(key=lambda x: abs(x.quantity * x.current_price), reverse=True)
print(f'Top {min(10, len(positions))} positions by size:')
for p in positions[:10]:
    exposure = abs(p.quantity * p.current_price)
    print(f"  {p.symbol} | qty={p.quantity:.2f} | price=${p.current_price:.2f} | exposure=${exposure:,.2f} | pnl=${p.unrealized_pnl:,.2f}")
