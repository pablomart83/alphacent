#!/usr/bin/env python3
"""Test eToro API with saved credentials."""

from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode
from src.core.config import Configuration

# Load your credentials
config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)

# Create client
client = EToroAPIClient(
    public_key=creds['public_key'],
    user_key=creds['user_key'],
    mode=TradingMode.DEMO
)

print('Testing eToro API with your credentials...')
print()

# Test 1: Market data for EURUSD
print('Test 1: Get market data for EURUSD')
try:
    data = client.get_market_data('EURUSD')
    print(f'✅ SUCCESS!')
    print(f'   Symbol: {data.symbol}')
    print(f'   Price: ${data.close:.5f}')
    print(f'   Timestamp: {data.timestamp}')
    print(f'   Source: {data.source}')
except Exception as e:
    print(f'❌ Error: {e}')

print()

# Test 2: Try to get account info (will likely fail with 401)
print('Test 2: Get account info (authenticated endpoint)')
try:
    account = client.get_account_info()
    print(f'✅ SUCCESS!')
    print(f'   Account ID: {account.account_id}')
    print(f'   Balance: ${account.balance}')
except Exception as e:
    print(f'❌ Expected failure: {e}')
    print('   Note: Authenticated endpoints return 401 - may need different auth method')
