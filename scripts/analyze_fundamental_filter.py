#!/usr/bin/env python3
"""
Analyze fundamental filter performance and recommend threshold adjustments.

This script:
1. Analyzes historical filter pass rates
2. Identifies which checks fail most often
3. Correlates filter results with trade outcomes
4. Recommends threshold adjustments
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import get_database
from src.models.orm import FundamentalFilterLogORM, OrderORM, PositionORM
from sqlalchemy import func, and_, or_, Integer
from datetime import datetime, timedelta
from collections import defaultdict
import json


def analyze_filter_performance():
    """Analyze fundamental filter performance."""
    database = get_database()
    session = database.get_session()
    
    try:
        print("=" * 80)
        print("FUNDAMENTAL FILTER PERFORMANCE ANALYSIS")
        print("=" * 80)
        print()
        
        # 1. Overall pass rate
        total_filters = session.query(FundamentalFilterLogORM).count()
        passed_filters = session.query(FundamentalFilterLogORM).filter(
            FundamentalFilterLogORM.passed == True
        ).count()
        
        if total_filters == 0:
            print("No fundamental filter logs found in database.")
            return
        
        pass_rate = (passed_filters / total_filters) * 100
        print(f"1. OVERALL PASS RATE")
        print(f"   Total filters run: {total_filters}")
        print(f"   Passed: {passed_filters}")
        print(f"   Failed: {total_filters - passed_filters}")
        print(f"   Pass rate: {pass_rate:.1f}%")
        print(f"   Target: 50-70%")
        
        if pass_rate > 70:
            print(f"   ⚠️  PASS RATE TOO HIGH - Filters may be too permissive")
        elif pass_rate < 50:
            print(f"   ⚠️  PASS RATE TOO LOW - Filters may be too restrictive")
        else:
            print(f"   ✓ Pass rate within target range")
        print()
        
        # 2. Individual check failure rates
        print(f"2. INDIVIDUAL CHECK FAILURE RATES")
        print(f"   (Higher failure rate = more restrictive check)")
        print()
        
        checks = ['profitable', 'growing', 'valuation', 'dilution', 'insider_buying']
        check_stats = {}
        
        for check in checks:
            column = getattr(FundamentalFilterLogORM, check)
            total = session.query(FundamentalFilterLogORM).filter(
                column.isnot(None)
            ).count()
            
            if total == 0:
                continue
            
            failed = session.query(FundamentalFilterLogORM).filter(
                column == False
            ).count()
            
            failure_rate = (failed / total) * 100 if total > 0 else 0
            check_stats[check] = {
                'total': total,
                'failed': failed,
                'failure_rate': failure_rate
            }
            
            print(f"   {check.upper()}")
            print(f"     Total: {total}, Failed: {failed}, Failure rate: {failure_rate:.1f}%")
        
        print()
        
        # 3. Most common failure reasons
        print(f"3. MOST COMMON FAILURE REASONS")
        print()
        
        failed_logs = session.query(FundamentalFilterLogORM).filter(
            FundamentalFilterLogORM.passed == False,
            FundamentalFilterLogORM.failure_reasons.isnot(None)
        ).all()
        
        reason_counts = defaultdict(int)
        for log in failed_logs:
            if log.failure_reasons:
                for reason in log.failure_reasons:
                    reason_counts[reason] += 1
        
        sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons[:10]:
            print(f"   {count:4d}x: {reason}")
        
        print()
        
        # 4. Pass rate by strategy type
        print(f"4. PASS RATE BY STRATEGY TYPE")
        print()
        
        strategy_types = session.query(
            FundamentalFilterLogORM.strategy_type,
            func.count(FundamentalFilterLogORM.id).label('total'),
            func.sum(func.cast(FundamentalFilterLogORM.passed, Integer)).label('passed')
        ).group_by(FundamentalFilterLogORM.strategy_type).all()
        
        for strategy_type, total, passed in strategy_types:
            passed = passed or 0
            pass_rate = (passed / total) * 100 if total > 0 else 0
            print(f"   {strategy_type}: {pass_rate:.1f}% ({passed}/{total})")
        
        print()
        
        # 5. Correlation with trade outcomes (if we have trade data)
        print(f"5. CORRELATION WITH TRADE OUTCOMES")
        print()
        
        # Get symbols that passed filter
        passed_symbols = set(
            log.symbol for log in session.query(FundamentalFilterLogORM).filter(
                FundamentalFilterLogORM.passed == True
            ).all()
        )
        
        # Get symbols that failed filter
        failed_symbols = set(
            log.symbol for log in session.query(FundamentalFilterLogORM).filter(
                FundamentalFilterLogORM.passed == False
            ).all()
        )
        
        # Get closed positions (trades with outcomes)
        closed_positions = session.query(PositionORM).filter(
            PositionORM.closed_at.isnot(None)
        ).all()
        
        if closed_positions:
            passed_trades = [p for p in closed_positions if p.symbol in passed_symbols]
            failed_trades = [p for p in closed_positions if p.symbol in failed_symbols]
            
            if passed_trades:
                passed_wins = sum(1 for p in passed_trades if p.realized_pnl and p.realized_pnl > 0)
                passed_win_rate = (passed_wins / len(passed_trades)) * 100
                passed_avg_pnl = sum(p.realized_pnl or 0 for p in passed_trades) / len(passed_trades)
                
                print(f"   Symbols that PASSED filter:")
                print(f"     Trades: {len(passed_trades)}")
                print(f"     Win rate: {passed_win_rate:.1f}%")
                print(f"     Avg P&L: ${passed_avg_pnl:.2f}")
            
            if failed_trades:
                failed_wins = sum(1 for p in failed_trades if p.realized_pnl and p.realized_pnl > 0)
                failed_win_rate = (failed_wins / len(failed_trades)) * 100
                failed_avg_pnl = sum(p.realized_pnl or 0 for p in failed_trades) / len(failed_trades)
                
                print(f"   Symbols that FAILED filter:")
                print(f"     Trades: {len(failed_trades)}")
                print(f"     Win rate: {failed_win_rate:.1f}%")
                print(f"     Avg P&L: ${failed_avg_pnl:.2f}")
            
            if passed_trades and failed_trades:
                print()
                if passed_win_rate > failed_win_rate:
                    print(f"   ✓ Filter is working: Passed symbols have higher win rate")
                else:
                    print(f"   ⚠️  Filter may not be effective: Failed symbols have higher win rate")
        else:
            print(f"   No closed positions found - cannot correlate with outcomes")
        
        print()
        
        # 6. Data quality issues
        print(f"6. DATA QUALITY ISSUES")
        print()
        
        # Check for missing data
        missing_data_logs = session.query(FundamentalFilterLogORM).filter(
            or_(
                FundamentalFilterLogORM.profitable.is_(None),
                FundamentalFilterLogORM.growing.is_(None),
                FundamentalFilterLogORM.valuation.is_(None)
            )
        ).count()
        
        if missing_data_logs > 0:
            missing_rate = (missing_data_logs / total_filters) * 100
            print(f"   Logs with missing data: {missing_data_logs} ({missing_rate:.1f}%)")
            
            # Break down by check
            for check in ['profitable', 'growing', 'valuation', 'dilution', 'insider_buying']:
                column = getattr(FundamentalFilterLogORM, check)
                missing = session.query(FundamentalFilterLogORM).filter(
                    column.is_(None)
                ).count()
                if missing > 0:
                    missing_pct = (missing / total_filters) * 100
                    print(f"     {check}: {missing} missing ({missing_pct:.1f}%)")
        else:
            print(f"   ✓ No data quality issues detected")
        
        print()
        
        # 7. Recommendations
        print(f"7. RECOMMENDATIONS")
        print()
        
        recommendations = []
        
        # Pass rate recommendations
        if pass_rate > 75:
            recommendations.append("⚠️  CRITICAL: Pass rate is too high (>75%)")
            recommendations.append("   → Tighten P/E thresholds (reduce from 60 to 50 for growth, 25 to 20 for value)")
            recommendations.append("   → Increase min_checks_passed from 4 to 5 (require all checks to pass)")
            recommendations.append("   → Add minimum market cap filter ($500M+) to avoid micro-caps")
        elif pass_rate > 70:
            recommendations.append("⚠️  Pass rate slightly high (>70%)")
            recommendations.append("   → Consider tightening P/E thresholds by 10-20%")
            recommendations.append("   → Monitor for 1-2 weeks before making changes")
        elif pass_rate < 50:
            recommendations.append("⚠️  Pass rate too low (<50%)")
            recommendations.append("   → Loosen P/E thresholds (increase by 20%)")
            recommendations.append("   → Reduce min_checks_passed from 4 to 3")
        else:
            recommendations.append("✓ Pass rate is within target range (50-70%)")
        
        # Check-specific recommendations
        if 'valuation' in check_stats:
            val_failure_rate = check_stats['valuation']['failure_rate']
            if val_failure_rate > 40:
                recommendations.append(f"⚠️  Valuation check failing too often ({val_failure_rate:.1f}%)")
                recommendations.append("   → P/E thresholds may be too strict")
                recommendations.append("   → Consider: growth P/E 60→70, value P/E 25→30")
        
        if 'profitable' in check_stats:
            prof_failure_rate = check_stats['profitable']['failure_rate']
            if prof_failure_rate > 30:
                recommendations.append(f"⚠️  Profitable check failing often ({prof_failure_rate:.1f}%)")
                recommendations.append("   → Many unprofitable companies in universe")
                recommendations.append("   → This is expected - keep threshold at EPS > 0")
        
        # Data quality recommendations
        if missing_data_logs > total_filters * 0.1:
            recommendations.append("⚠️  High rate of missing fundamental data (>10%)")
            recommendations.append("   → Improve data provider fallback logic")
            recommendations.append("   → Consider passing checks when data unavailable (conservative)")
        
        for rec in recommendations:
            print(f"   {rec}")
        
        print()
        print("=" * 80)
        
    finally:
        session.close()


if __name__ == "__main__":
    analyze_filter_performance()
