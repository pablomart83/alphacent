"""
Symbol normalization utility.

Ensures consistent symbol representation across the system.
Prevents duplication bugs caused by symbol mismatches (GE vs ID_1017 vs 1017).
"""

from typing import List
from src.utils.instrument_mappings import INSTRUMENT_ID_TO_SYMBOL, SYMBOL_TO_INSTRUMENT_ID


def normalize_symbol(symbol: str) -> str:
    """
    Normalize a symbol to its canonical form.
    
    Handles:
    - Instrument IDs (1017, "1017", "ID_1017") -> "GE"
    - Already normalized symbols ("GE") -> "GE"
    - Unknown symbols -> returns as-is
    
    Args:
        symbol: Symbol in any format
        
    Returns:
        Normalized symbol (canonical ticker)
        
    Examples:
        >>> normalize_symbol("GE")
        "GE"
        >>> normalize_symbol("1017")
        "GE"
        >>> normalize_symbol("ID_1017")
        "GE"
        >>> normalize_symbol(1017)
        "GE"
    """
    if not symbol:
        return symbol
    
    # Convert to string
    symbol_str = str(symbol).strip().upper()
    
    # If it's already a known symbol, return it
    if symbol_str in SYMBOL_TO_INSTRUMENT_ID:
        return symbol_str
    
    # Check if it's an instrument ID with "ID_" prefix
    if symbol_str.startswith("ID_"):
        try:
            instrument_id = int(symbol_str[3:])  # Remove "ID_" prefix
            normalized = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id)
            if normalized:
                return normalized
        except (ValueError, KeyError):
            pass
    
    # Check if it's a plain instrument ID (numeric string or int)
    try:
        instrument_id = int(symbol_str)
        normalized = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id)
        if normalized:
            return normalized
    except (ValueError, KeyError):
        pass
    
    # Return as-is if we can't normalize it
    return symbol_str


def get_symbol_variations(symbol: str) -> List[str]:
    """
    Get all possible variations of a symbol.
    
    Useful for database queries that need to match any variation.
    
    Args:
        symbol: Symbol to get variations for
        
    Returns:
        List of all possible symbol representations
        
    Examples:
        >>> get_symbol_variations("GE")
        ["GE", "1017", "ID_1017"]
    """
    normalized = normalize_symbol(symbol)
    variations = [normalized]
    
    # Get instrument ID if it exists
    instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(normalized)
    if instrument_id:
        variations.append(str(instrument_id))
        variations.append(f"ID_{instrument_id}")
    
    return list(set(variations))  # Remove duplicates


def symbols_match(symbol1: str, symbol2: str) -> bool:
    """
    Check if two symbols represent the same instrument.
    
    Args:
        symbol1: First symbol
        symbol2: Second symbol
        
    Returns:
        True if symbols represent the same instrument
        
    Examples:
        >>> symbols_match("GE", "1017")
        True
        >>> symbols_match("GE", "ID_1017")
        True
        >>> symbols_match("GE", "AAPL")
        False
    """
    return normalize_symbol(symbol1) == normalize_symbol(symbol2)
