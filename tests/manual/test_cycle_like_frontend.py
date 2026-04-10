"""
Test script that triggers autonomous cycle exactly like the frontend does.
This will help diagnose what's happening during the actual cycle execution.
"""

import logging
import sys
import requests
import time
import json
from pathlib import Path
from datetime import datetime

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cycle_test.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Backend URL
BACKEND_URL = "http://localhost:8000"

def check_backend_health():
    """Check if backend is running."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if response.status_code == 200:
            logger.info("✓ Backend is healthy")
            return True
        else:
            logger.error(f"✗ Backend health check failed: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"✗ Cannot connect to backend: {e}")
        return False

def get_session_cookie():
    """Get session cookie by logging in."""
    try:
        # Try to login (adjust credentials as needed)
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"username": "demo", "password": "demo"},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✓ Logged in successfully")
            return response.cookies
        else:
            logger.warning(f"⚠ Login failed: {response.status_code}")
            # Try without auth
            return None
    except Exception as e:
        logger.warning(f"⚠ Login error: {e}")
        return None

def get_autonomous_status(cookies=None):
    """Get current autonomous status."""
    try:
        response = requests.get(
            f"{BACKEND_URL}/strategies/autonomous/status",
            cookies=cookies,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info("✓ Got autonomous status")
            logger.info(f"  Enabled: {data.get('enabled')}")
            logger.info(f"  Market regime: {data.get('market_regime')}")
            logger.info(f"  Active strategies: {data.get('portfolio_health', {}).get('active_strategies')}")
            logger.info(f"  Last cycle: {data.get('last_cycle_time')}")
            return data
        else:
            logger.error(f"✗ Failed to get status: {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return None
    except Exception as e:
        logger.error(f"✗ Error getting status: {e}")
        return None

def trigger_cycle(cookies=None, force=False):
    """Trigger autonomous cycle exactly like frontend does."""
    logger.info("=" * 80)
    logger.info("TRIGGERING AUTONOMOUS CYCLE (like frontend)")
    logger.info("=" * 80)
    
    try:
        payload = {"force": force}
        logger.info(f"Sending POST to /strategies/autonomous/trigger with payload: {payload}")
        
        response = requests.post(
            f"{BACKEND_URL}/strategies/autonomous/trigger",
            json=payload,
            cookies=cookies,
            timeout=1800  # 30 minute timeout
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("✓ Cycle triggered successfully")
            logger.info(f"  Message: {data.get('message')}")
            logger.info(f"  Cycle ID: {data.get('cycle_id')}")
            logger.info(f"  Duration: {data.get('estimated_duration')}s")
            return data
        else:
            logger.error(f"✗ Cycle trigger failed: {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("✗ Request timed out after 30 minutes")
        return None
    except Exception as e:
        logger.error(f"✗ Error triggering cycle: {e}", exc_info=True)
        return None

def get_recent_strategies(cookies=None, limit=20):
    """Get recently created strategies."""
    try:
        response = requests.get(
            f"{BACKEND_URL}/strategies?mode=DEMO",
            cookies=cookies,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            strategies = data.get('data', {}).get('strategies', [])
            
            # Sort by created_at
            strategies.sort(key=lambda s: s.get('created_at', ''), reverse=True)
            
            logger.info(f"✓ Got {len(strategies)} total strategies")
            
            # Show recent ones
            recent = strategies[:limit]
            logger.info(f"\nRecent {len(recent)} strategies:")
            for i, s in enumerate(recent, 1):
                logger.info(f"  {i}. {s.get('name')} - {s.get('symbols')} - {s.get('status')}")
                logger.info(f"     Created: {s.get('created_at')}")
                if s.get('backtest_results'):
                    bt = s['backtest_results']
                    logger.info(f"     Sharpe: {bt.get('sharpe_ratio', 0):.2f}, "
                               f"Return: {bt.get('total_return', 0):.2%}, "
                               f"Trades: {bt.get('total_trades', 0)}")
            
            return strategies
        else:
            logger.error(f"✗ Failed to get strategies: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"✗ Error getting strategies: {e}")
        return []

def check_database_directly():
    """Check database directly to see what was created."""
    try:
        import sqlite3
        
        conn = sqlite3.connect('alphacent.db')
        cursor = conn.cursor()
        
        # Get recent strategies
        cursor.execute("""
            SELECT id, name, status, symbols, created_at 
            FROM strategies 
            WHERE created_at > datetime('now', '-1 hour')
            ORDER BY created_at DESC 
            LIMIT 20
        """)
        
        rows = cursor.fetchall()
        logger.info(f"\n✓ Database check: {len(rows)} strategies created in last hour")
        
        for row in rows:
            logger.info(f"  - {row[1]} ({row[2]}) - {row[3]}")
            logger.info(f"    Created: {row[4]}")
        
        conn.close()
        return rows
        
    except Exception as e:
        logger.error(f"✗ Database check failed: {e}")
        return []

def analyze_backend_logs():
    """Try to find and analyze backend logs."""
    logger.info("\n" + "=" * 80)
    logger.info("ANALYZING BACKEND LOGS")
    logger.info("=" * 80)
    
    # Common log locations
    log_files = [
        'backend.log',
        'nohup.out',
        'uvicorn.log',
        'app.log'
    ]
    
    for log_file in log_files:
        if Path(log_file).exists():
            logger.info(f"\nFound log file: {log_file}")
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    
                # Look for recent cycle-related logs
                relevant_lines = []
                for line in lines[-500:]:  # Last 500 lines
                    if any(keyword in line.lower() for keyword in [
                        'autonomous', 'cycle', 'proposal', 'strategy', 
                        'backtest', 'walk-forward', 'validation'
                    ]):
                        relevant_lines.append(line.strip())
                
                if relevant_lines:
                    logger.info(f"  Found {len(relevant_lines)} relevant log lines:")
                    for line in relevant_lines[-50:]:  # Show last 50
                        logger.info(f"    {line}")
                else:
                    logger.info("  No relevant log lines found")
                    
            except Exception as e:
                logger.error(f"  Error reading log: {e}")
        else:
            logger.debug(f"  Log file not found: {log_file}")

def main():
    """Main diagnostic flow."""
    logger.info("=" * 80)
    logger.info("AUTONOMOUS CYCLE DIAGNOSTIC TEST")
    logger.info("Simulating frontend trigger and analyzing results")
    logger.info("=" * 80)
    
    # Step 1: Check backend health
    logger.info("\n[1/7] Checking backend health...")
    if not check_backend_health():
        logger.error("Backend is not running. Please start it first.")
        return False
    
    # Step 2: Get session cookie
    logger.info("\n[2/7] Getting session cookie...")
    cookies = get_session_cookie()
    
    # Step 3: Get initial status
    logger.info("\n[3/7] Getting initial autonomous status...")
    initial_status = get_autonomous_status(cookies)
    
    if initial_status:
        initial_active = initial_status.get('portfolio_health', {}).get('active_strategies', 0)
        logger.info(f"  Initial active strategies: {initial_active}")
    
    # Step 4: Get initial strategy count
    logger.info("\n[4/7] Getting initial strategy list...")
    initial_strategies = get_recent_strategies(cookies, limit=5)
    initial_count = len(initial_strategies)
    logger.info(f"  Initial strategy count: {initial_count}")
    
    # Step 5: Trigger the cycle
    logger.info("\n[5/7] Triggering autonomous cycle...")
    logger.info("  This will take 15-30 minutes...")
    logger.info("  Watching for completion...")
    
    start_time = time.time()
    result = trigger_cycle(cookies, force=True)
    duration = time.time() - start_time
    
    if not result:
        logger.error("✗ Cycle trigger failed")
        logger.info("\n[6/7] Checking database anyway...")
        check_database_directly()
        logger.info("\n[7/7] Analyzing backend logs...")
        analyze_backend_logs()
        return False
    
    logger.info(f"✓ Cycle completed in {duration:.1f} seconds")
    
    # Step 6: Get final status and strategies
    logger.info("\n[6/7] Getting final status and strategies...")
    time.sleep(2)  # Wait a bit for database to update
    
    final_status = get_autonomous_status(cookies)
    final_strategies = get_recent_strategies(cookies, limit=20)
    
    # Check database directly
    db_strategies = check_database_directly()
    
    # Step 7: Analyze results
    logger.info("\n[7/7] Analyzing results...")
    logger.info("=" * 80)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 80)
    
    if result:
        logger.info(f"Cycle message: {result.get('message')}")
        logger.info(f"Cycle duration: {duration:.1f}s")
    
    if final_status and initial_status:
        final_active = final_status.get('portfolio_health', {}).get('active_strategies', 0)
        initial_active = initial_status.get('portfolio_health', {}).get('active_strategies', 0)
        logger.info(f"Active strategies: {initial_active} → {final_active} (Δ {final_active - initial_active})")
    
    new_strategies = len(final_strategies) - initial_count
    logger.info(f"New strategies created: {new_strategies}")
    
    if new_strategies < 10:
        logger.warning("⚠ WARNING: Only a few strategies were created!")
        logger.warning("  Expected: 30-50 strategies")
        logger.warning(f"  Actual: {new_strategies} strategies")
        logger.warning("\n  Possible causes:")
        logger.warning("  1. Walk-forward validation filtering too many")
        logger.warning("  2. Template generation failing")
        logger.warning("  3. Market data issues")
        logger.warning("  4. Configuration not loaded properly")
    else:
        logger.info(f"✓ Good! {new_strategies} strategies created")
    
    # Analyze backend logs
    analyze_backend_logs()
    
    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSTIC COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Full logs saved to: cycle_test.log")
    
    return new_strategies >= 10

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\nTest failed with error: {e}", exc_info=True)
        sys.exit(1)
