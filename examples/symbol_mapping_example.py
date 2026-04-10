"""
Example demonstrating the symbol mapping feature.

This example shows how users can use friendly symbols like "BTC"
which automatically map to eToro's format like "BTCUSD".
"""

from src.utils.symbol_mapper import (
    normalize_symbol,
    get_display_symbol,
    add_alias,
    get_all_aliases
)


def main():
    """Demonstrate symbol mapping functionality."""
    
    print("=" * 60)
    print("Symbol Mapping Feature Demo")
    print("=" * 60)
    print()
    
    # Example 1: Normalize user-friendly symbols
    print("1. Normalizing user-friendly symbols to eToro format:")
    print("-" * 60)
    
    symbols = ["BTC", "ETH", "DOGE", "AAPL", "GOLD"]
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        print(f"   {symbol:10} → {normalized}")
    print()
    
    # Example 2: Case-insensitive and whitespace handling
    print("2. Case-insensitive and whitespace handling:")
    print("-" * 60)
    
    variations = ["btc", "BTC", "Btc", " btc ", "  BTC  "]
    for var in variations:
        normalized = normalize_symbol(var)
        print(f"   '{var:10}' → {normalized}")
    print()
    
    # Example 3: Get display symbols (reverse mapping)
    print("3. Converting eToro format back to user-friendly:")
    print("-" * 60)
    
    etoro_symbols = ["BTCUSD", "ETHUSD", "XAUUSD", "AAPL"]
    for etoro_sym in etoro_symbols:
        display = get_display_symbol(etoro_sym)
        print(f"   {etoro_sym:10} → {display}")
    print()
    
    # Example 4: Add custom alias
    print("4. Adding custom aliases at runtime:")
    print("-" * 60)
    
    add_alias("MYTOKEN", "MYTOKENUSD")
    print(f"   Added: MYTOKEN → MYTOKENUSD")
    print(f"   Test: {normalize_symbol('MYTOKEN')}")
    print()
    
    # Example 5: Get all available aliases
    print("5. Available symbol aliases:")
    print("-" * 60)
    
    aliases = get_all_aliases()
    print(f"   Total aliases: {len(aliases)}")
    print()
    print("   Cryptocurrencies:")
    crypto_aliases = {k: v for k, v in aliases.items() if "USD" in v and k not in ["EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]}
    for user_sym, etoro_sym in sorted(crypto_aliases.items())[:5]:
        print(f"      {user_sym:10} → {etoro_sym}")
    print(f"      ... and {len(crypto_aliases) - 5} more")
    print()
    
    print("   Forex:")
    forex_aliases = {k: v for k, v in aliases.items() if k in ["EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]}
    for user_sym, etoro_sym in sorted(forex_aliases.items()):
        print(f"      {user_sym:10} → {etoro_sym}")
    print()
    
    print("   Commodities:")
    commodity_aliases = {k: v for k, v in aliases.items() if k in ["GOLD", "SILVER", "OIL", "BRENT"]}
    for user_sym, etoro_sym in sorted(commodity_aliases.items()):
        print(f"      {user_sym:10} → {etoro_sym}")
    print()
    
    # Example 6: Practical usage in API calls
    print("6. Practical usage example:")
    print("-" * 60)
    print("""
    # In your code, you can now use either format:
    
    # User-friendly (recommended)
    market_data = manager.get_quote("BTC")
    
    # eToro format (still works)
    market_data = manager.get_quote("BTCUSD")
    
    # Both will work identically!
    """)
    
    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
