#!/usr/bin/env python3
"""
Check fundamental data quality in the database cache.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import get_database
from src.models.orm import FundamentalDataORM
from datetime import datetime, timedelta


def check_data_quality():
    """Check fundamental data quality."""
    database = get_database()
    session = database.get_session()
    
    try:
        print("=" * 80)
        print("FUNDAMENTAL DATA QUALITY CHECK")
        print("=" * 80)
        print()
        
        # Get all cached data
        cached_data = session.query(FundamentalDataORM).all()
        
        if not cached_data:
            print("No fundamental data found in cache.")
            return
        
        print(f"Total cached symbols: {len(cached_data)}")
        print()
        
        # Check data completeness
        fields = ['eps', 'revenue_growth', 'pe_ratio', 'debt_to_equity', 'roe', 
                  'market_cap', 'shares_change_percent', 'insider_net_buying']
        
        field_stats = {}
        for field in fields:
            available = sum(1 for data in cached_data if getattr(data, field) is not None)
            field_stats[field] = {
                'available': available,
                'missing': len(cached_data) - available,
                'pct_available': (available / len(cached_data)) * 100
            }
        
        print("DATA COMPLETENESS:")
        print()
        for field, stats in field_stats.items():
            status = "✓" if stats['pct_available'] > 80 else "⚠️" if stats['pct_available'] > 50 else "❌"
            print(f"  {status} {field:25s}: {stats['available']:3d}/{len(cached_data):3d} ({stats['pct_available']:5.1f}%)")
        
        print()
        
        # Sample some data
        print("SAMPLE DATA (first 5 symbols):")
        print()
        for data in cached_data[:5]:
            print(f"  {data.symbol}:")
            print(f"    EPS: {data.eps}")
            print(f"    Revenue Growth: {data.revenue_growth}")
            print(f"    P/E Ratio: {data.pe_ratio}")
            print(f"    Market Cap: {data.market_cap}")
            print(f"    Fetched at: {data.fetched_at}")
            print()
        
        # Check cache freshness
        now = datetime.now()
        fresh = sum(1 for data in cached_data if (now - data.fetched_at).total_seconds() < 86400)
        stale = len(cached_data) - fresh
        
        print(f"CACHE FRESHNESS:")
        print(f"  Fresh (<24h): {fresh}")
        print(f"  Stale (>24h): {stale}")
        print()
        
    finally:
        session.close()


if __name__ == "__main__":
    check_data_quality()
