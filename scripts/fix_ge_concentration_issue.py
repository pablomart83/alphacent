#!/usr/bin/env python3
"""
Fix GE concentration issue by retiring redundant strategies and verifying safeguards.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from datetime import datetime
import json

def retire_strategies():
    """Retire duplicate and redundant GE strategies."""
    conn = sqlite3.connect('alphacent.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("  RETIRING REDUNDANT GE STRATEGIES")
    print("=" * 80)
    print()
    
    # Get all GE strategies
    cursor.execute("""
        SELECT id, name, status, symbols, backtest_results
        FROM strategies
        WHERE status IN ('ACTIVE', 'DEMO')
        AND (symbols LIKE '%"GE"%' OR symbols LIKE "%'GE'%")
        ORDER BY name, id
    """)
    
    ge_strategies = cursor.fetchall()
    print(f"Found {len(ge_strategies)} active GE strategies")
    print()
    
    # Identify strategies to retire
    strategies_to_retire = []
    
    # Track seen strategy names to find duplicates
    seen_names = {}
    
    for strat in ge_strategies:
        name = strat['name']
        strategy_id = strat['id']
        
        # Check for exact duplicate names
        if name in seen_names:
            print(f"🔴 DUPLICATE FOUND: {name}")
            print(f"   Keeping: {seen_names[name]}")
            print(f"   Retiring: {strategy_id}")
            strategies_to_retire.append({
                'id': strategy_id,
                'name': name,
                'reason': 'Duplicate strategy name'
            })
        else:
            seen_names[name] = strategy_id
    
    # Identify redundant RSI strategies (keep only V10)
    rsi_strategies = [s for s in ge_strategies if 'RSI Overbought Short Ranging GE' in s['name']]
    
    if len(rsi_strategies) > 1:
        print(f"\n🔴 REDUNDANT RSI STRATEGIES: Found {len(rsi_strategies)}")
        
        # Find V10 to keep
        v10_strategy = next((s for s in rsi_strategies if 'V10' in s['name']), None)
        
        if v10_strategy:
            print(f"   Keeping: {v10_strategy['name']} ({v10_strategy['id']})")
            
            for strat in rsi_strategies:
                if strat['id'] != v10_strategy['id'] and strat['id'] not in [s['id'] for s in strategies_to_retire]:
                    print(f"   Retiring: {strat['name']} ({strat['id']})")
                    strategies_to_retire.append({
                        'id': strat['id'],
                        'name': strat['name'],
                        'reason': 'Redundant RSI strategy (keeping V10 only)'
                    })
        else:
            # If no V10, keep the first one
            print(f"   No V10 found, keeping: {rsi_strategies[0]['name']}")
            for strat in rsi_strategies[1:]:
                if strat['id'] not in [s['id'] for s in strategies_to_retire]:
                    strategies_to_retire.append({
                        'id': strat['id'],
                        'name': strat['name'],
                        'reason': 'Redundant RSI strategy'
                    })
    
    print(f"\n📊 Summary:")
    print(f"   Total GE strategies: {len(ge_strategies)}")
    print(f"   Strategies to retire: {len(strategies_to_retire)}")
    print(f"   Strategies remaining: {len(ge_strategies) - len(strategies_to_retire)}")
    print()
    
    # Retire strategies
    if strategies_to_retire:
        print("Retiring strategies...")
        retired_at = datetime.now().isoformat()
        
        for strat in strategies_to_retire:
            cursor.execute("""
                UPDATE strategies
                SET status = 'RETIRED',
                    retired_at = ?
                WHERE id = ?
            """, (retired_at, strat['id']))
            
            print(f"  ✅ Retired: {strat['name']}")
            print(f"     ID: {strat['id']}")
            print(f"     Reason: {strat['reason']}")
            print()
        
        conn.commit()
        print(f"✅ Successfully retired {len(strategies_to_retire)} strategies")
    else:
        print("⚠️  No strategies to retire")
    
    conn.close()
    return len(strategies_to_retire)

def investigate_pnl_issue():
    """Investigate why P&L shows 0% for closed positions."""
    conn = sqlite3.connect('alphacent.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n" + "=" * 80)
    print("  INVESTIGATING P&L CALCULATION ISSUE")
    print("=" * 80)
    print()
    
    # Check GE positions
    cursor.execute("""
        SELECT id, symbol, side, entry_price, current_price, 
               unrealized_pnl, realized_pnl, opened_at, closed_at
        FROM positions
        WHERE symbol = 'GE'
        ORDER BY opened_at DESC
    """)
    
    positions = cursor.fetchall()
    
    print(f"Total GE positions: {len(positions)}")
    print()
    
    for pos in positions:
        is_closed = pos['closed_at'] is not None
        status = "CLOSED" if is_closed else "OPEN"
        
        # Calculate expected P&L
        if pos['entry_price'] and pos['current_price']:
            if pos['side'] == 'LONG':
                expected_pnl_pct = ((pos['current_price'] - pos['entry_price']) / pos['entry_price']) * 100
            else:  # SHORT
                expected_pnl_pct = ((pos['entry_price'] - pos['current_price']) / pos['entry_price']) * 100
        else:
            expected_pnl_pct = 0
        
        print(f"Position: {pos['id'][:8]}... ({status})")
        print(f"  Side: {pos['side']}")
        print(f"  Entry: ${pos['entry_price']:.2f}")
        print(f"  Current: ${pos['current_price']:.2f}")
        print(f"  Expected P&L %: {expected_pnl_pct:.2f}%")
        print(f"  Unrealized P&L: ${pos['unrealized_pnl']:.2f}" if pos['unrealized_pnl'] else "  Unrealized P&L: None")
        print(f"  Realized P&L: ${pos['realized_pnl']:.2f}" if pos['realized_pnl'] else "  Realized P&L: None")
        
        # Diagnosis
        if is_closed and expected_pnl_pct == 0:
            print(f"  ⚠️  ISSUE: Closed position with 0% P&L - entry price equals current price")
        elif is_closed and pos['realized_pnl'] == 0:
            print(f"  ⚠️  ISSUE: Closed position but realized_pnl is 0")
        elif not is_closed and pos['unrealized_pnl'] == 0 and expected_pnl_pct != 0:
            print(f"  ⚠️  ISSUE: Open position with 0 unrealized P&L but prices differ")
        
        print()
    
    # Check if there's a pattern
    closed_positions = [p for p in positions if p['closed_at'] is not None]
    if closed_positions:
        all_zero_pnl = all(p['realized_pnl'] == 0 or p['realized_pnl'] is None for p in closed_positions)
        all_same_price = all(p['entry_price'] == p['current_price'] for p in closed_positions if p['entry_price'] and p['current_price'])
        
        print("📊 Analysis:")
        if all_zero_pnl:
            print("  🔴 CRITICAL: All closed positions have 0 realized P&L")
            print("     Possible causes:")
            print("     1. P&L calculation not being performed on position close")
            print("     2. Positions closed at exact entry price (unlikely for all)")
            print("     3. Database field not being updated")
        
        if all_same_price:
            print("  🔴 CRITICAL: All closed positions have entry_price == current_price")
            print("     Possible causes:")
            print("     1. current_price not being updated from eToro on close")
            print("     2. Positions being closed immediately after opening")
            print("     3. Test/demo data issue")
    
    conn.close()

def verify_concentration_limits():
    """Verify that concentration limits are properly configured and enforced."""
    conn = sqlite3.connect('alphacent.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n" + "=" * 80)
    print("  VERIFYING CONCENTRATION LIMIT SAFEGUARDS")
    print("=" * 80)
    print()
    
    # Check configuration
    print("1. Checking Configuration Files")
    print("-" * 80)
    
    config_files = [
        'config/autonomous_trading.yaml',
        'config/risk_management.yaml'
    ]
    
    for config_file in config_files:
        try:
            with open(config_file, 'r') as f:
                content = f.read()
                if 'max_strategies_per_symbol' in content:
                    print(f"✅ {config_file}: Contains max_strategies_per_symbol")
                    # Extract value
                    for line in content.split('\n'):
                        if 'max_strategies_per_symbol' in line:
                            print(f"   {line.strip()}")
                if 'max_symbol_exposure' in content:
                    print(f"✅ {config_file}: Contains max_symbol_exposure")
                    for line in content.split('\n'):
                        if 'max_symbol_exposure' in line:
                            print(f"   {line.strip()}")
        except FileNotFoundError:
            print(f"⚠️  {config_file}: Not found")
    
    print()
    
    # Check actual concentration
    print("2. Current Symbol Concentration")
    print("-" * 80)
    
    cursor.execute("""
        SELECT COUNT(*) as total_strategies
        FROM strategies
        WHERE status IN ('ACTIVE', 'DEMO')
    """)
    total_strategies = cursor.fetchone()['total_strategies']
    
    cursor.execute("""
        SELECT 
            REPLACE(REPLACE(REPLACE(symbols, '["', ''), '"]', ''), '"', '') as symbol,
            COUNT(*) as strategy_count,
            ROUND(COUNT(*) * 100.0 / ?, 1) as concentration_pct
        FROM strategies
        WHERE status IN ('ACTIVE', 'DEMO')
        AND symbols IS NOT NULL
        GROUP BY symbols
        HAVING COUNT(*) > 1
        ORDER BY strategy_count DESC
    """, (total_strategies,))
    
    concentrations = cursor.fetchall()
    
    print(f"Total active strategies: {total_strategies}")
    print()
    print(f"{'Symbol':<15} {'Count':<8} {'Concentration':<15} {'Status'}")
    print("-" * 80)
    
    for row in concentrations:
        symbol = row['symbol']
        count = row['strategy_count']
        pct = row['concentration_pct']
        
        if pct > 20:
            status = "🔴 CRITICAL (>20%)"
        elif pct > 15:
            status = "🟡 WARNING (>15%)"
        else:
            status = "✅ OK"
        
        print(f"{symbol:<15} {count:<8} {pct:>6.1f}%{'':<8} {status}")
    
    print()
    
    # Check for duplicate strategy names
    print("3. Duplicate Strategy Name Detection")
    print("-" * 80)
    
    cursor.execute("""
        SELECT name, COUNT(*) as count
        FROM strategies
        WHERE status IN ('ACTIVE', 'DEMO')
        GROUP BY name
        HAVING COUNT(*) > 1
    """)
    
    duplicates = cursor.fetchall()
    
    if duplicates:
        print(f"🔴 FOUND {len(duplicates)} duplicate strategy names:")
        for dup in duplicates:
            print(f"   {dup['name']}: {dup['count']} instances")
    else:
        print("✅ No duplicate strategy names found")
    
    conn.close()

def check_signal_generation_safeguards():
    """Check if there are safeguards to prevent signal generation during analysis."""
    print("\n" + "=" * 80)
    print("  CHECKING SIGNAL GENERATION SAFEGUARDS")
    print("=" * 80)
    print()
    
    print("1. Checking for Signal Generation Pause Mechanism")
    print("-" * 80)
    
    # Check if there's a pause mechanism in the codebase
    files_to_check = [
        'src/strategy/strategy_engine.py',
        'src/core/trading_scheduler.py',
        'src/strategy/autonomous_strategy_manager.py'
    ]
    
    found_pause_mechanism = False
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if 'pause' in content.lower() or 'disable' in content.lower():
                    print(f"✅ {file_path}: Contains pause/disable logic")
                    found_pause_mechanism = True
                    
                    # Look for specific patterns
                    for line in content.split('\n'):
                        if 'pause' in line.lower() or 'disable' in line.lower():
                            if 'def ' in line or 'class ' in line or '=' in line:
                                print(f"   {line.strip()[:80]}")
                                break
        except FileNotFoundError:
            print(f"⚠️  {file_path}: Not found")
    
    if not found_pause_mechanism:
        print("⚠️  No obvious pause mechanism found in checked files")
        print("   Recommendation: Add a global pause flag for signal generation")
    
    print()
    
    print("2. Recommendation: Signal Generation Control")
    print("-" * 80)
    print("""
    To prevent strategies from generating signals during analysis/maintenance:
    
    Option 1: Environment Variable
      - Set SIGNAL_GENERATION_ENABLED=false
      - Check this flag in strategy_engine.generate_signals()
    
    Option 2: Database Flag
      - Add 'signal_generation_paused' to system_state table
      - Check before generating signals
    
    Option 3: Scheduler Control
      - Pause the trading scheduler
      - Prevents automatic signal generation cycles
    
    Current Status: Need to implement one of these options
    """)

def main():
    """Main execution function."""
    print("\n")
    print("=" * 80)
    print("  GE CONCENTRATION ISSUE - COMPREHENSIVE FIX")
    print("=" * 80)
    print()
    
    # Step 1: Retire redundant strategies
    retired_count = retire_strategies()
    
    # Step 2: Investigate P&L issue
    investigate_pnl_issue()
    
    # Step 3: Verify concentration limits
    verify_concentration_limits()
    
    # Step 4: Check signal generation safeguards
    check_signal_generation_safeguards()
    
    # Final summary
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    print(f"✅ Retired {retired_count} redundant GE strategies")
    print("✅ Investigated P&L calculation issue")
    print("✅ Verified concentration limit configuration")
    print("✅ Checked signal generation safeguards")
    print()
    print("Next Steps:")
    print("1. Review P&L calculation logic in position close handler")
    print("2. Implement signal generation pause mechanism")
    print("3. Add pre-activation concentration limit check")
    print("4. Improve duplicate detection in strategy proposer")
    print()

if __name__ == "__main__":
    main()
