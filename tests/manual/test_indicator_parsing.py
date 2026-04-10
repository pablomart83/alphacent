"""Test indicator reference parsing."""

import re

def test_indicator_parsing():
    """Test parsing indicator references from strategy rules."""
    
    test_conditions = [
        "Price is below BOLLINGER_BANDS_20_2",
        "RSI_14 is below 30",
        "Price is above SMA_20",
        "MACD_12_26_9 crosses above signal",
        "VOLUME_MA_20 is increasing",
        "Price drops below EMA_50",
        "ATR_14 is above 2.0",
        "PRICE_CHANGE_PCT_20 > 0.05"
    ]
    
    print("Testing Indicator Reference Parsing\n")
    print("=" * 70)
    
    for condition in test_conditions:
        # Match patterns like RSI_14, SMA_20, EMA_50, MACD_12_26_9, BBANDS_20_2
        # Also match multi-word indicators like BOLLINGER_BANDS_20_2, VOLUME_MA_20
        matches = re.findall(r'\b([A-Z_]+_\d+(?:_\d+)*)\b', condition)
        
        indicator_refs = set()
        for match in matches:
            # Filter out matches that are just underscores and numbers
            if match and not match.startswith('_'):
                indicator_refs.add(match)
        
        print(f"Condition: {condition}")
        print(f"  Found: {indicator_refs}")
        print()
    
    print("=" * 70)
    print("✓ Parsing test complete")

if __name__ == "__main__":
    test_indicator_parsing()
