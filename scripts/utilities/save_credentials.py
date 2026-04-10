#!/usr/bin/env python3
"""Script to save eToro API credentials."""

from src.core.config import Configuration
from src.models import TradingMode

def save_credentials():
    """Save eToro API credentials."""
    
    print("=" * 60)
    print("eToro API Credentials Setup")
    print("=" * 60)
    print()
    print("Please enter your eToro API credentials.")
    print("You can find these in: eToro Settings > Trading > API Key Management")
    print()
    
    # Get mode
    mode_input = input("Trading Mode (DEMO/LIVE) [DEMO]: ").strip().upper() or "DEMO"
    mode = TradingMode.DEMO if mode_input == "DEMO" else TradingMode.LIVE
    
    print()
    print(f"Selected mode: {mode.value}")
    print()
    
    # Get credentials
    public_key = input("Enter your Public API Key (x-api-key): ").strip()
    if not public_key:
        print("Error: Public key is required")
        return
    
    user_key = input("Enter your User Key (x-user-key): ").strip()
    if not user_key:
        print("Error: User key is required")
        return
    
    print()
    print("Saving credentials...")
    
    # Save credentials
    config = Configuration()
    config.save_credentials(
        mode=mode,
        public_key=public_key,
        user_key=user_key
    )
    
    print(f"✅ Credentials saved successfully for {mode.value} mode!")
    print()
    print("Credentials are encrypted and stored in:")
    print(f"  config/{mode.value.lower()}_credentials.json")
    print()
    print("You can now use the eToro API integration.")

if __name__ == "__main__":
    save_credentials()
