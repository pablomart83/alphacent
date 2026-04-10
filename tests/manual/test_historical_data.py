"""Test historical data fetching from eToro client."""

import sys
from datetime import datetime, timedelta
from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode
from src.core.config import get_config

def test_historical_data():
    """Test fetching 90 days of historical data for SPY, QQQ, DIA."""
    # Load credentials
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    client = EToroAPIClient(
        public_key=creds["public_key"],
        user_key=creds["user_key"],
        mode=TradingMode.DEMO
    )
    
    symbols = ["SPY", "QQQ", "DIA"]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print(f"Testing historical data fetch from {start_date.date()} to {end_date.date()}\n")
    
    for symbol in symbols:
        try:
            print(f"Fetching {symbol}...")
            data = client.get_historical_data(symbol, start_date, end_date)
            
            print(f"  ✓ Retrieved {len(data)} days of data")
            print(f"  First date: {data[0].timestamp.date()}")
            print(f"  Last date: {data[-1].timestamp.date()}")
            print(f"  Sample data: Open=${data[-1].open:.2f}, Close=${data[-1].close:.2f}, Volume={data[-1].volume:,.0f}")
            print()
            
            # Verify we have at least 60 days (accounting for weekends/holidays)
            if len(data) < 60:
                print(f"  ⚠ Warning: Only {len(data)} days retrieved (expected ~90)")
            else:
                print(f"  ✓ Sufficient data for backtesting")
            print()
            
        except Exception as e:
            print(f"  ✗ Error: {e}\n")
            return False
    
    print("✓ All tests passed!")
    return True

if __name__ == "__main__":
    success = test_historical_data()
    sys.exit(0 if success else 1)
