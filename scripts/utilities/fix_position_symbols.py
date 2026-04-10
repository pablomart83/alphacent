#!/usr/bin/env python3
"""
Fix position symbols in database by mapping ID_xxx to actual symbols.
"""

import sqlite3

# Mapping from the etoro_client.py
INSTRUMENT_ID_TO_SYMBOL = {
    # Forex
    1: "EURUSD",
    2: "GBPUSD",
    3: "USDJPY",
    4: "AUDUSD",
    5: "USDCAD",
    6: "USDCHF",
    
    # Commodities
    17: "OIL",
    18: "GOLD",
    19: "SILVER",
    21: "COPPER",
    
    # Indices
    27: "SPX500",
    28: "NSDQ100",
    29: "DJ30",
    30: "UK100",
    32: "GER40",
    
    # Cryptocurrencies
    100000: "BTC",
    100001: "ETH",
    100002: "BCH",
    100003: "XRP",
    100005: "LTC",
    100017: "ADA",
    100037: "DOT",
    100040: "LINK",
    100043: "DOGE",
    100063: "SOL",
    100085: "AVAX",
    100315: "APT",
    100330: "INJ",
    100333: "ARB",
    100334: "RENDER",
    100335: "OP",
    100337: "NEAR",
    100340: "SUI",
    
    # US Stocks
    1001: "AAPL",
    1003: "META",
    1004: "MSFT",
    1005: "AMZN",
    1010: "BA",
    1013: "CSCO",
    1016: "DIS",
    1017: "GE",
    1018: "HD",
    1021: "INTC",
    1022: "JNJ",
    1023: "JPM",
    1024: "KO",
    1025: "MCD",
    1029: "PG",
    1032: "UNH",
    1035: "WMT",
    1041: "MA",
    1042: "NKE",
    1043: "PEP",
    1046: "V",
    1111: "TSLA",
    1126: "ADBE",
    1127: "NFLX",
    1135: "ORCL",
    1137: "NVDA",
    1142: "SBUX",
    1155: "BABA",
    1186: "UBER",
    1461: "COST",
    1474: "LOW",
    1484: "PYPL",
    1490: "TGT",
    1832: "AMD",
    1839: "CRM",
    1979: "SNAP",
    6168: "COIN",
    6434: "GOOGL",
    7991: "PLTR",
    8047: "ABNB",
    
    # ETFs
    3000: "SPY",
    3005: "IWM",
    3006: "QQQ",
    3025: "GLD",
    3026: "DIA",
    4237: "VTI",
    4238: "VOO",
    4430: "SLV",
}

def fix_position_symbols():
    """Fix position symbols in the database."""
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Get all positions with ID_ symbols
    cursor.execute("SELECT id, symbol FROM positions WHERE symbol LIKE 'ID_%'")
    positions = cursor.fetchall()
    
    print(f"Found {len(positions)} positions with ID_ symbols")
    
    fixed_count = 0
    for position_id, symbol in positions:
        # Extract instrument ID from ID_xxx format
        if symbol.startswith('ID_'):
            instrument_id_str = symbol[3:]  # Remove 'ID_' prefix
            try:
                instrument_id = int(instrument_id_str)
                
                # Look up the actual symbol
                if instrument_id in INSTRUMENT_ID_TO_SYMBOL:
                    actual_symbol = INSTRUMENT_ID_TO_SYMBOL[instrument_id]
                    
                    # Update the database
                    cursor.execute(
                        "UPDATE positions SET symbol = ? WHERE id = ?",
                        (actual_symbol, position_id)
                    )
                    print(f"  Fixed: {symbol} → {actual_symbol} (position {position_id})")
                    fixed_count += 1
                else:
                    print(f"  Warning: No mapping for instrument ID {instrument_id} (position {position_id})")
            except ValueError:
                print(f"  Error: Invalid instrument ID format: {symbol} (position {position_id})")
    
    conn.commit()
    conn.close()
    
    print(f"\nFixed {fixed_count} positions")
    print("Done!")

if __name__ == "__main__":
    fix_position_symbols()
