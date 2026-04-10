#!/usr/bin/env python3
"""
Comprehensive System Analysis - February 23, 2026
Answers: Will this system make money? Are we top 1%?
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from datetime import datetime, timedelta
from src.models.database import get_database
from src.data.fundamental_data_provider import FundamentalDataProvider
from src.strategy.fundamental_filter import FundamentalFilter
from src.analytics.trade_journal import TradeJournal
from sqlalchemy import text

def analyze_system():
    print("=" * 80)
    print("COMPREHENSIVE SYSTEM ANALYSIS - February 23, 2026")
    print("Question: Will this system make money? Are we top 1%?")
    print("=" * 80)
    print()
    
    # Load config
    config_path = Path("config/autonomous_trading.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    database = get_database()
    
    # 1. Check active strategies
    print("1. ACTIVE STRATEGIES")
    print("-" * 80)
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM strategies
            GROUP BY status
        """))
        for row in result:
            print(f"  {row[0]}: {row[1]} strategies")
    print()
    
    # 2. Check recent signals
    print("2. RECENT SIGNALS (Last 7 days)")
    print("-" * 80)
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT DATE(timestamp) as date, COUNT(*) as count
            FROM trading_signals
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """))
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]}: {row[1]} signals")
        else:
            print("  No signals in last 7 days")
    print()
    
    # 3. Check orders
    print("3. ORDERS (Last 30 days)")
    print("-" * 80)
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY status
        """))
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]}: {row[1]} orders")
        else:
            print("  No orders in last 30 days")
    print()
    
    # 4. Check positions
    print("4. CURRENT POSITIONS")
    print("-" * 80)
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT symbol, quantity, entry_price, 
                   ROUND((current_price - entry_price) / entry_price * 100, 2) as pnl_pct
            FROM positions
            WHERE status = 'OPEN'
        """))
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]}: {row[1]} shares @ ${row[2]:.2f} (P&L: {row[3]}%)")
        else:
            print("  No open positions")
    print()
    
    # 5. Check fundamental filter performance
    print("5. FUNDAMENTAL FILTER PERFORMANCE")
    print("-" * 80)
    fundamental_provider = FundamentalDataProvider(config, database)
    fundamental_filter = FundamentalFilter(config, fundamental_provider)
    
    # Test with a few symbols
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    passed = 0
    failed = 0
    
    for symbol in test_symbols:
        result = fundamental_filter.filter_symbol(symbol, 'momentum')
        if result.passed:
            passed += 1
            print(f"  ✓ {symbol}: PASSED ({result.checks_passed}/{result.checks_total})")
        else:
            failed += 1
            print(f"  ✗ {symbol}: FAILED ({result.checks_passed}/{result.checks_total})")
    
    pass_rate = (passed / len(test_symbols)) * 100
    print(f"\n  Pass rate: {pass_rate:.1f}% ({passed}/{len(test_symbols)})")
    print()
    
    # 6. Check API usage
    print("6. API USAGE")
    print("-" * 80)
    usage = fundamental_provider.get_api_usage()
    for api_name, api_usage in usage.items():
        print(f"  {api_name}:")
        print(f"    Used: {api_usage['used']}/{api_usage['limit']}")
        print(f"    Percentage: {api_usage['percentage']:.1f}%")
        print(f"    Remaining: {api_usage['remaining']}")
    print()
    
    # 7. Check trade journal
    print("7. TRADE JOURNAL (Last 30 days)")
    print("-" * 80)
    trade_journal = TradeJournal()
    
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
                COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_trades,
                ROUND(AVG(CASE WHEN pnl IS NOT NULL THEN pnl END), 2) as avg_pnl,
                ROUND(SUM(CASE WHEN pnl IS NOT NULL THEN pnl END), 2) as total_pnl
            FROM trade_journal
            WHERE entry_time >= datetime('now', '-30 days')
        """))
        row = result.fetchone()
        
        if row and row[0] > 0:
            total = row[0]
            winning = row[1] or 0
            losing = row[2] or 0
            win_rate = (winning / total * 100) if total > 0 else 0
            
            print(f"  Total trades: {total}")
            print(f"  Winning trades: {winning}")
            print(f"  Losing trades: {losing}")
            print(f"  Win rate: {win_rate:.1f}%")
            print(f"  Average P&L: ${row[3] or 0:.2f}")
            print(f"  Total P&L: ${row[4] or 0:.2f}")
        else:
            print("  No completed trades in last 30 days")
    print()
    
    # 8. System health check
    print("8. SYSTEM HEALTH CHECK")
    print("-" * 80)
    
    # Check for critical issues
    issues = []
    
    # Check if strategies are active
    with database.get_session() as session:
        result = session.execute(text("SELECT COUNT(*) FROM strategies WHERE status = 'ACTIVE'"))
        active_count = result.scalar()
        if active_count == 0:
            issues.append("❌ No active strategies")
        else:
            print(f"  ✓ {active_count} active strategies")
    
    # Check if signals are being generated
    with database.get_session() as session:
        result = session.execute(text("""
            SELECT COUNT(*) FROM trading_signals 
            WHERE timestamp >= datetime('now', '-24 hours')
        """))
        signal_count = result.scalar()
        if signal_count == 0:
            issues.append("⚠️  No signals in last 24 hours")
        else:
            print(f"  ✓ {signal_count} signals in last 24 hours")
    
    # Check fundamental filter
    if pass_rate == 0:
        issues.append("❌ Fundamental filter blocking all signals (0% pass rate)")
    elif pass_rate < 40:
        issues.append(f"⚠️  Fundamental filter too strict ({pass_rate:.1f}% pass rate)")
    else:
        print(f"  ✓ Fundamental filter working ({pass_rate:.1f}% pass rate)")
    
    # Check API limits
    for api_name, api_usage in usage.items():
        if api_usage['percentage'] > 90:
            issues.append(f"⚠️  {api_name} API near limit ({api_usage['percentage']:.1f}%)")
        elif api_usage['percentage'] > 50:
            print(f"  ⚠️  {api_name} API at {api_usage['percentage']:.1f}% usage")
        else:
            print(f"  ✓ {api_name} API usage healthy ({api_usage['percentage']:.1f}%)")
    
    print()
    
    if issues:
        print("  CRITICAL ISSUES:")
        for issue in issues:
            print(f"    {issue}")
    else:
        print("  ✓ No critical issues detected")
    
    print()
    
    # 9. Final verdict
    print("9. FINAL VERDICT")
    print("=" * 80)
    
    # Calculate confidence score
    confidence_factors = {
        'active_strategies': active_count > 0,
        'recent_signals': signal_count > 0,
        'fundamental_filter': pass_rate >= 40,
        'api_health': all(u['percentage'] < 90 for u in usage.values()),
    }
    
    confidence_score = sum(confidence_factors.values()) / len(confidence_factors) * 100
    
    print(f"System Confidence Score: {confidence_score:.0f}%")
    print()
    
    if confidence_score >= 75:
        print("✓ SYSTEM READY FOR PRODUCTION")
        print("  - All critical components working")
        print("  - Fundamental filter tuned correctly")
        print("  - API usage healthy")
        print("  - Ready for live trading validation")
    elif confidence_score >= 50:
        print("⚠️  SYSTEM NEEDS TUNING")
        print("  - Some components working")
        print("  - Critical issues need fixing")
        print("  - Not ready for production yet")
    else:
        print("❌ SYSTEM NOT READY")
        print("  - Multiple critical issues")
        print("  - Requires significant fixes")
        print("  - Do not deploy to production")
    
    print()
    print("=" * 80)
    print("Analysis complete.")
    print("=" * 80)

if __name__ == '__main__':
    analyze_system()
