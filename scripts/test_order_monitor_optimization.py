#!/usr/bin/env python3
"""
Quick test to verify order monitor optimization.

Tests that position sync is skipped when not needed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.order_monitor import OrderMonitor
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

def main():
    print("=" * 80)
    print("Order Monitor Optimization Test")
    print("=" * 80)
    
    # Initialize
    config = get_config()
    credentials = config.load_credentials(TradingMode.DEMO)
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO,
    )
    
    monitor = OrderMonitor(etoro_client)
    
    print("\nTest 1: First cycle (should sync positions)")
    print("-" * 80)
    t0 = time.time()
    result1 = monitor.run_monitoring_cycle()
    elapsed1 = time.time() - t0
    print(f"Cycle 1 completed in {elapsed1:.1f}s")
    print(f"Position sync: {result1['positions']}")
    
    print("\nTest 2: Second cycle immediately after (should SKIP sync)")
    print("-" * 80)
    t0 = time.time()
    result2 = monitor.run_monitoring_cycle()
    elapsed2 = time.time() - t0
    print(f"Cycle 2 completed in {elapsed2:.1f}s")
    print(f"Position sync: {result2['positions']}")
    
    print("\nTest 3: Third cycle immediately after (should SKIP sync)")
    print("-" * 80)
    t0 = time.time()
    result3 = monitor.run_monitoring_cycle()
    elapsed3 = time.time() - t0
    print(f"Cycle 3 completed in {elapsed3:.1f}s")
    print(f"Position sync: {result3['positions']}")
    
    print("\n" + "=" * 80)
    print("Results Summary")
    print("=" * 80)
    
    skipped_2 = result2['positions'].get('skipped', False)
    skipped_3 = result3['positions'].get('skipped', False)
    
    print(f"Cycle 1: {elapsed1:.1f}s (synced {result1['positions'].get('total', 0)} positions)")
    print(f"Cycle 2: {elapsed2:.1f}s (skipped: {skipped_2})")
    print(f"Cycle 3: {elapsed3:.1f}s (skipped: {skipped_3})")
    
    if skipped_2 and skipped_3:
        speedup = elapsed1 / ((elapsed2 + elapsed3) / 2)
        print(f"\n✅ Optimization working! Cycles 2-3 are {speedup:.1f}x faster")
        print(f"   Average cycle time: {(elapsed2 + elapsed3) / 2:.1f}s (vs {elapsed1:.1f}s)")
        return True
    else:
        print(f"\n❌ Optimization not working - syncs not being skipped")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
