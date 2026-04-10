"""Close all open positions in eToro DEMO account to free up capital."""
import sys
sys.path.insert(0, '.')

from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
import time

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO,
)

print("=" * 70)
print("CLOSING ALL OPEN POSITIONS IN ETORO DEMO ACCOUNT")
print("=" * 70)

# Get account info
account_info = client.get_account_info()
print(f"\nCurrent Account Status:")
print(f"  Balance: ${account_info.balance:,.2f}")
print(f"  Buying Power: ${account_info.buying_power:,.2f}")
print(f"  Margin Used: ${account_info.margin_used:,.2f}")
print(f"  Open Positions: {account_info.positions_count}")

# Get all open positions
positions = client.get_positions()
print(f"\nFound {len(positions)} open positions to close")

if len(positions) == 0:
    print("\n✅ No positions to close!")
    sys.exit(0)

print("\nClosing positions...")
closed_count = 0
failed_count = 0

for i, position in enumerate(positions, 1):
    try:
        position_id = position.etoro_position_id or position.id
        
        # The position.symbol is the instrument ID (numeric string)
        try:
            instrument_id = int(position.symbol)
        except (ValueError, TypeError):
            instrument_id = None
        
        print(f"  [{i}/{len(positions)}] Closing position {position_id} (instrument {instrument_id})...", end=" ")
        
        # Try with instrument_id first
        try:
            result = client.close_position(
                position_id=str(position_id),
                instrument_id=instrument_id
            )
            closed_count += 1
            print("✅")
        except Exception as e:
            # If instrument_id fails, try without it
            if "does not exist" in str(e) or "Validation failed" in str(e):
                print("retrying without instrument_id...", end=" ")
                try:
                    result = client.close_position(
                        position_id=str(position_id),
                        instrument_id=None
                    )
                    closed_count += 1
                    print("✅")
                except Exception as e2:
                    raise e2  # Re-raise if second attempt fails
            else:
                raise e  # Re-raise if it's a different error
        
        # Rate limiting
        time.sleep(1.0)
        
    except Exception as e:
        failed_count += 1
        error_msg = str(e)
        if "does not exist" in error_msg or "Validation failed" in error_msg:
            print(f"❌ Invalid/closed")
        elif "not found" in error_msg.lower():
            print(f"❌ Not found")
        else:
            print(f"❌ {error_msg[:40]}")
        time.sleep(0.5)

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Total positions: {len(positions)}")
print(f"  Successfully closed: {closed_count}")
print(f"  Failed to close: {failed_count}")

# Get updated account info
print("\nFetching updated account info...")
time.sleep(2)  # Wait for positions to settle
account_info = client.get_account_info()
print(f"\nUpdated Account Status:")
print(f"  Balance: ${account_info.balance:,.2f}")
print(f"  Buying Power: ${account_info.buying_power:,.2f}")
print(f"  Margin Used: ${account_info.margin_used:,.2f}")
print(f"  Open Positions: {account_info.positions_count}")

if account_info.positions_count == 0:
    print("\n✅ All positions closed successfully!")
    print(f"✅ ${account_info.balance:,.2f} available for trading")
else:
    print(f"\n⚠️  {account_info.positions_count} positions still open")
    print("   You may need to close them manually through the eToro web interface")
