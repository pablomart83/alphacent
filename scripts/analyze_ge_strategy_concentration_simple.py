#!/usr/bin/env python3
"""
Simple analysis of GE strategy concentration using raw SQL.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from datetime import datetime, timedelta

def analyze_ge():
    """Analyze GE concentration."""
    conn = sqlite3.connect('alphacent.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("  GE STRATEGY CONCENTRATION ANALYSIS")
    print("=" * 80)
    print()
    
    # 1. Find strategies that trade GE (via positions)
    print("1. STRATEGIES TRADING GE")
    print("-" * 80)
    
    cursor.execute("""
        SELECT DISTINCT s.id, s.name, s.status, s.symbols,
               s.backtest_results
        FROM strategies s
        WHERE s.status IN ('ACTIVE', 'DEMO')
        AND (s.symbols LIKE '%"GE"%' OR s.symbols LIKE "%'GE'%")
        ORDER BY s.activated_at DESC
    """)
    
    ge_strategies = cursor.fetchall()
    print(f"Active strategies with GE in symbols: {len(ge_strategies)}")
    print()
    
    for strat in ge_strategies:
        print(f"  📊 {strat['name']}")
        print(f"     Status: {strat['status']}")
        print(f"     Symbols: {strat['symbols']}")
        if strat['backtest_results']:
            import json
            try:
                bt = json.loads(strat['backtest_results'])
                if 'sharpe_ratio' in bt:
                    print(f"     Backtest: Sharpe={bt.get('sharpe_ratio', 0):.2f}, "
                          f"Win={bt.get('win_rate', 0):.1f}%, "
                          f"Return={bt.get('total_return', 0):.1f}%")
            except:
                pass
        print()
    
    # 2. Symbol distribution
    print("\n2. SYMBOL DISTRIBUTION (Top 10)")
    print("-" * 80)
    
    cursor.execute("""
        SELECT symbol, COUNT(*) as position_count,
               SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) as open_count,
               SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) as closed_count
        FROM positions
        GROUP BY symbol
        ORDER BY position_count DESC
        LIMIT 10
    """)
    
    print(f"{'Symbol':<10} {'Total':<8} {'Open':<8} {'Closed':<8}")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row['symbol']:<10} {row['position_count']:<8} {row['open_count']:<8} {row['closed_count']:<8}")
    
    # 3. GE position performance
    print("\n3. GE POSITION PERFORMANCE")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_positions,
            SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) as open_positions,
            SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) as closed_positions
        FROM positions
        WHERE symbol = 'GE'
    """)
    
    stats = cursor.fetchone()
    print(f"Total GE positions: {stats['total_positions']}")
    print(f"  Open: {stats['open_positions']}")
    print(f"  Closed: {stats['closed_positions']}")
    print()
    
    # Closed position stats - need to calculate P&L from entry/exit prices
    cursor.execute("""
        SELECT 
            COUNT(*) as closed_count,
            AVG((current_price - entry_price) / entry_price * 100) as avg_pnl_pct,
            SUM(CASE WHEN current_price > entry_price THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
            MIN((current_price - entry_price) / entry_price * 100) as worst_loss_pct,
            MAX((current_price - entry_price) / entry_price * 100) as best_win_pct
        FROM positions
        WHERE symbol = 'GE' AND closed_at IS NOT NULL
    """)
    
    perf = cursor.fetchone()
    if perf and perf['closed_count'] > 0:
        print(f"Closed position performance:")
        print(f"  Avg P&L %: {perf['avg_pnl_pct']:.2f}%")
        print(f"  Win Rate: {perf['win_rate']:.1f}%")
        print(f"  Best Win %: {perf['best_win_pct']:.2f}%")
        print(f"  Worst Loss %: {perf['worst_loss_pct']:.2f}%")
    else:
        print("No closed GE positions")
    print()
    
    # 4. Recent GE signals
    print("\n4. GE SIGNAL ACTIVITY (Last 30 days)")
    print("-" * 80)
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    
    cursor.execute("""
        SELECT 
            DATE(generated_at) as signal_date,
            COUNT(*) as signal_count,
            SUM(CASE WHEN action = 'ENTER_LONG' THEN 1 ELSE 0 END) as long_signals,
            SUM(CASE WHEN action = 'ENTER_SHORT' THEN 1 ELSE 0 END) as short_signals
        FROM trading_signals
        WHERE symbol = 'GE' AND generated_at >= ?
        GROUP BY DATE(generated_at)
        ORDER BY signal_date DESC
        LIMIT 10
    """, (thirty_days_ago,))
    
    signals = cursor.fetchall()
    if signals:
        total_signals = sum(s['signal_count'] for s in signals)
        print(f"Total signals in last 30 days: {total_signals}")
        print(f"Signal days: {len(signals)}")
        print()
        print("Recent activity:")
        for s in signals:
            print(f"  {s['signal_date']}: {s['signal_count']} signals "
                  f"(LONG: {s['long_signals']}, SHORT: {s['short_signals']})")
    else:
        print("No GE signals in last 30 days")
    
    # 5. Compare to portfolio
    print("\n5. GE VS PORTFOLIO COMPARISON")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            symbol,
            COUNT(*) as closed_count,
            AVG((current_price - entry_price) / entry_price * 100) as avg_pnl_pct,
            SUM(CASE WHEN current_price > entry_price THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
        FROM positions
        WHERE closed_at IS NOT NULL
        GROUP BY symbol
        HAVING COUNT(*) >= 3
        ORDER BY avg_pnl_pct DESC
    """)
    
    portfolio_stats = cursor.fetchall()
    
    if portfolio_stats:
        ge_stats = next((s for s in portfolio_stats if s['symbol'] == 'GE'), None)
        ge_rank = next((i+1 for i, s in enumerate(portfolio_stats) if s['symbol'] == 'GE'), None) if ge_stats else None
        
        portfolio_avg_pct = sum(s['avg_pnl_pct'] for s in portfolio_stats) / len(portfolio_stats)
        portfolio_avg_wr = sum(s['win_rate'] for s in portfolio_stats) / len(portfolio_stats)
        
        print(f"Portfolio averages ({len(portfolio_stats)} symbols):")
        print(f"  Avg P&L %: {portfolio_avg_pct:.2f}%")
        print(f"  Avg Win Rate: {portfolio_avg_wr:.1f}%")
        print()
        
        if ge_stats:
            print(f"GE performance:")
            print(f"  Rank: #{ge_rank}/{len(portfolio_stats)}")
            print(f"  Avg P&L %: {ge_stats['avg_pnl_pct']:.2f}%")
            print(f"  Win Rate: {ge_stats['win_rate']:.1f}%")
            print(f"  Closed trades: {ge_stats['closed_count']}")
            print()
            
            pct_diff = ((ge_stats['avg_pnl_pct'] - portfolio_avg_pct) / portfolio_avg_pct * 100)
            wr_diff = ((ge_stats['win_rate'] - portfolio_avg_wr) / portfolio_avg_wr * 100)
            
            print("GE vs Portfolio:")
            print(f"  P&L %: {'+' if pct_diff > 0 else ''}{pct_diff:.1f}%")
            print(f"  Win Rate: {'+' if wr_diff > 0 else ''}{wr_diff:.1f}%")
        else:
            print("GE has insufficient closed positions (need 3+)")
    
    # 6. Concentration analysis
    print("\n" + "=" * 80)
    print("  CONCENTRATION ANALYSIS")
    print("=" * 80)
    print()
    
    cursor.execute("SELECT COUNT(*) as count FROM strategies WHERE status IN ('ACTIVE', 'DEMO')")
    total_strategies = cursor.fetchone()['count']
    
    ge_strategy_count = len(ge_strategies)
    ge_concentration_pct = (ge_strategy_count / total_strategies * 100) if total_strategies > 0 else 0
    
    print(f"📊 GE Concentration: {ge_strategy_count}/{total_strategies} strategies ({ge_concentration_pct:.1f}%)")
    print()
    
    # Verdict
    if ge_stats and portfolio_stats:
        ge_outperforms = ge_stats['avg_pnl_pct'] > portfolio_avg_pct
        ge_high_wr = ge_stats['win_rate'] > 60
        ge_top_30 = ge_rank and ge_rank <= len(portfolio_stats) * 0.3
        
        score = sum([ge_outperforms, ge_high_wr, ge_top_30])
        
        print("🔍 Justification:")
        print(f"  {'✅' if ge_outperforms else '❌'} Outperforms portfolio: {ge_outperforms}")
        print(f"  {'✅' if ge_high_wr else '⚠️ '} High win rate (>60%): {ge_high_wr}")
        print(f"  {'✅' if ge_top_30 else '⚠️ '} Top 30% performer: {ge_top_30}")
        print()
        
        if score >= 2:
            print("✅ VERDICT: GE concentration is JUSTIFIED")
            print("   Strong performance metrics warrant multiple strategies")
        elif score == 1:
            print("⚠️  VERDICT: GE concentration is PARTIALLY JUSTIFIED")
            print("   Monitor performance closely")
        else:
            print("❌ VERDICT: GE concentration is NOT JUSTIFIED")
            print("   Consider reducing exposure")
        
        print()
        print("📋 RECOMMENDATIONS:")
        print()
        
        if ge_concentration_pct > 20:
            print("  1. 🔴 HIGH: Reduce GE concentration")
            print(f"     Current: {ge_concentration_pct:.1f}% (Target: <15%)")
        elif ge_concentration_pct > 15:
            print("  1. 🟡 MEDIUM: Monitor GE concentration")
            print(f"     Current: {ge_concentration_pct:.1f}% (Target: <15%)")
        else:
            print("  1. ✅ GE concentration acceptable")
            print(f"     Current: {ge_concentration_pct:.1f}%")
        
        if not ge_outperforms:
            print("\n  2. 🔴 Review GE strategy quality")
            print("     Underperforms portfolio average")
    
    conn.close()

if __name__ == "__main__":
    analyze_ge()
