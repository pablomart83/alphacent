"""
Simple test: Trigger autonomous cycle and check results.
Uses current config (730 days, 50 proposals).
"""

import requests
import time
import sys

BACKEND_URL = "http://localhost:8000"

def main():
    print("=" * 80)
    print("SIMPLE AUTONOMOUS CYCLE TEST")
    print("=" * 80)
    
    # 1. Check backend
    print("\n[1/4] Checking backend...")
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if r.status_code == 200:
            print("✓ Backend is running")
        else:
            print(f"✗ Backend returned {r.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect to backend: {e}")
        return False
    
    # 2. Get initial status
    print("\n[2/4] Getting initial status...")
    try:
        r = requests.get(f"{BACKEND_URL}/strategies/autonomous/status", timeout=10)
        if r.status_code == 200:
            data = r.json()
            print(f"✓ Enabled: {data.get('enabled')}")
            print(f"  Market regime: {data.get('market_regime')}")
            print(f"  Active strategies: {data.get('portfolio_health', {}).get('active_strategies')}")
        else:
            print(f"⚠ Status check returned {r.status_code}")
    except Exception as e:
        print(f"⚠ Status check failed: {e}")
    
    # 3. Trigger cycle
    print("\n[3/4] Triggering cycle...")
    print("  This will take 15-30 minutes with 730 days of data...")
    print("  Press Ctrl+C to cancel\n")
    
    start_time = time.time()
    
    try:
        r = requests.post(
            f"{BACKEND_URL}/strategies/autonomous/trigger",
            json={"force": True},
            timeout=3600  # 1 hour timeout
        )
        
        duration = time.time() - start_time
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✓ Cycle completed in {duration:.1f}s ({duration/60:.1f} minutes)")
            print(f"  Message: {data.get('message')}")
            print(f"  Cycle ID: {data.get('cycle_id')}")
        else:
            print(f"\n✗ Cycle failed: {r.status_code}")
            print(f"  Response: {r.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("\n✗ Timeout after 1 hour")
        return False
    except KeyboardInterrupt:
        print("\n\n⚠ Cancelled by user")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False
    
    # 4. Check results
    print("\n[4/4] Checking results...")
    time.sleep(2)
    
    try:
        # Get strategies
        r = requests.get(f"{BACKEND_URL}/strategies?mode=DEMO", timeout=10)
        if r.status_code == 200:
            data = r.json()
            strategies = data.get('data', {}).get('strategies', [])
            
            # Filter recent ones (last hour)
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(hours=1)
            recent = [s for s in strategies if s.get('created_at', '') > cutoff.isoformat()]
            
            print(f"✓ Total strategies: {len(strategies)}")
            print(f"  Created in last hour: {len(recent)}")
            
            if len(recent) > 0:
                print(f"\n  Recent strategies:")
                for i, s in enumerate(recent[:10], 1):
                    print(f"    {i}. {s.get('name')}")
                    print(f"       Symbols: {s.get('symbols')}, Status: {s.get('status')}")
                    if s.get('backtest_results'):
                        bt = s['backtest_results']
                        print(f"       Sharpe: {bt.get('sharpe_ratio', 0):.2f}, "
                              f"Trades: {bt.get('total_trades', 0)}")
            
            # Check database directly
            print("\n  Checking database...")
            import sqlite3
            conn = sqlite3.connect('alphacent.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM strategies 
                WHERE created_at > datetime('now', '-1 hour')
            """)
            db_count = cursor.fetchone()[0]
            conn.close()
            
            print(f"  Database shows: {db_count} strategies in last hour")
            
            # Summary
            print("\n" + "=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Cycle duration: {duration:.1f}s ({duration/60:.1f} minutes)")
            print(f"Strategies created: {db_count}")
            
            if db_count < 10:
                print("\n⚠ WARNING: Only a few strategies created!")
                print("  Expected: 30-50 with proposal_count=50")
                print(f"  Actual: {db_count}")
                print("\n  Check backend logs for:")
                print("  - 'Proposing 50 strategies'")
                print("  - 'Generated X strategies from templates'")
                print("  - 'Walk-forward validation: X/Y strategies passed'")
                return False
            else:
                print(f"\n✓ SUCCESS: {db_count} strategies created")
                return True
                
        else:
            print(f"✗ Failed to get strategies: {r.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error checking results: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
