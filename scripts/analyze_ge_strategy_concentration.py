#!/usr/bin/env python3
"""
Comprehensive analysis of GE strategy concentration.
Investigates why multiple strategies are being created around GE and whether it's justified.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import StrategyORM, PositionORM, TradingSignalORM
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
from collections import defaultdict

def analyze_ge_concentration():
    """Analyze GE strategy concentration and performance."""
    db = get_database()
    session = db.get_session()
    
    try:
        print("=" * 80)
        print("  GE STRATEGY CONCENTRATION ANALYSIS")
        print("=" * 80)
        print()
        
        # 1. Current active strategies targeting GE
        print("1. ACTIVE STRATEGIES TARGETING GE")
        print("-" * 80)
        
        ge_strategies = session.query(StrategyORM).filter(
            StrategyORM.symbol == 'GE',
            StrategyORM.status.in_(['ACTIVE', 'DEMO'])
        ).order_by(StrategyORM.activated_at.desc()).all()
        
        print(f"Total active GE strategies: {len(ge_strategies)}")
        print()
        
        if ge_strategies:
            for strat in ge_strategies:
                print(f"  📊 {strat.name}")
                print(f"     ID: {strat.id}")
                print(f"     Direction: {strat.direction}")
                print(f"     Status: {strat.status}")
                print(f"     Activated: {strat.activated_at}")
                print(f"     Backtest: Sharpe={strat.backtest_sharpe_ratio:.2f}, "
                      f"Win={strat.backtest_win_rate:.1f}%, "
                      f"Drawdown={strat.backtest_max_drawdown:.1f}%, "
                      f"Return={strat.backtest_total_return:.1f}%, "
                      f"Trades={strat.backtest_total_trades}")
                print()
        
        # 2. Compare GE to other symbols
        print("\n2. SYMBOL DISTRIBUTION ACROSS ALL ACTIVE STRATEGIES")
        print("-" * 80)
        
        symbol_stats = session.query(
            StrategyORM.symbol,
            func.count(StrategyORM.id).label('strategy_count'),
            func.avg(StrategyORM.backtest_sharpe_ratio).label('avg_sharpe'),
            func.avg(StrategyORM.backtest_win_rate).label('avg_win_rate'),
            func.avg(StrategyORM.backtest_total_return).label('avg_return'),
            func.sum(func.case((StrategyORM.direction == 'LONG', 1), else_=0)).label('long_count'),
            func.sum(func.case((StrategyORM.direction == 'SHORT', 1), else_=0)).label('short_count')
        ).filter(
            StrategyORM.status.in_(['ACTIVE', 'DEMO'])
        ).group_by(StrategyORM.symbol).order_by(func.count(StrategyORM.id).desc()).limit(10).all()
        
        print(f"{'Symbol':<10} {'Count':<8} {'Avg Sharpe':<12} {'Avg Win%':<12} {'Avg Return%':<12} {'Long':<6} {'Short':<6}")
        print("-" * 80)
        for row in symbol_stats:
            print(f"{row.symbol:<10} {row.strategy_count:<8} "
                  f"{row.avg_sharpe:<12.2f} {row.avg_win_rate:<12.1f} "
                  f"{row.avg_return:<12.1f} {row.long_count:<6} {row.short_count:<6}")
        
        # 3. GE historical performance
        print("\n3. GE HISTORICAL TRADING PERFORMANCE")
        print("-" * 80)
        
        ge_positions = session.query(PositionORM).join(Strategy).filter(
            PositionORM.symbol == 'GE',
            PositionORM.status == 'CLOSED'
        ).order_by(PositionORM.closed_at.desc()).limit(20).all()
        
        if ge_positions:
            print(f"Recent closed GE positions: {len(ge_positions)}")
            print()
            
            total_pnl = sum(p.pnl or 0 for p in ge_positions)
            winning_trades = [p for p in ge_positions if (p.pnl or 0) > 0]
            losing_trades = [p for p in ge_positions if (p.pnl or 0) <= 0]
            
            print(f"  Total P&L: ${total_pnl:.2f}")
            print(f"  Win Rate: {len(winning_trades)}/{len(ge_positions)} ({len(winning_trades)/len(ge_positions)*100:.1f}%)")
            print(f"  Avg Win: ${sum(p.pnl for p in winning_trades)/len(winning_trades):.2f}" if winning_trades else "  Avg Win: N/A")
            print(f"  Avg Loss: ${sum(p.pnl for p in losing_trades)/len(losing_trades):.2f}" if losing_trades else "  Avg Loss: N/A")
            
            if ge_positions[0].closed_at and ge_positions[0].opened_at:
                avg_holding = sum((p.closed_at - p.opened_at).days for p in ge_positions if p.closed_at and p.opened_at) / len(ge_positions)
                print(f"  Avg Holding: {avg_holding:.1f} days")
            print()
            
            print("  Recent trades:")
            for p in ge_positions[:5]:
                pnl_str = f"${p.pnl:.2f}" if p.pnl else "N/A"
                pnl_pct = f"({p.pnl_percentage:.1f}%)" if p.pnl_percentage else ""
                status = "✅" if (p.pnl or 0) > 0 else "❌"
                strategy_name = p.strategy.name if p.strategy else "Unknown"
                print(f"    {status} {strategy_name[:40]:<40} | {p.direction:<6} | {pnl_str:>10} {pnl_pct:<8}")
        else:
            print("  No closed GE positions found")
        
        # 4. Current open GE positions
        print("\n4. CURRENT OPEN GE POSITIONS")
        print("-" * 80)
        
        open_ge_positions = session.query(PositionORM).join(Strategy).filter(
            PositionORM.symbol == 'GE',
            PositionORM.status == 'OPEN'
        ).order_by(PositionORM.opened_at.desc()).all()
        
        if open_ge_positions:
            print(f"Open GE positions: {len(open_ge_positions)}")
            print()
            
            total_unrealized = sum(p.unrealized_pnl or 0 for p in open_ge_positions)
            print(f"  Total Unrealized P&L: ${total_unrealized:.2f}")
            print()
            
            for p in open_ge_positions:
                pnl_str = f"${p.unrealized_pnl:.2f}" if p.unrealized_pnl else "N/A"
                pnl_pct = f"({p.unrealized_pnl_percentage:.1f}%)" if p.unrealized_pnl_percentage else ""
                status = "📈" if (p.unrealized_pnl or 0) > 0 else "📉"
                strategy_name = p.strategy.name if p.strategy else "Unknown"
                holding_days = (datetime.now() - p.opened_at).days if p.opened_at else 0
                print(f"  {status} {strategy_name[:40]:<40} | {p.direction:<6} | {pnl_str:>10} {pnl_pct:<8} | {holding_days}d")
        else:
            print("  No open GE positions")
        
        # 5. GE signal generation frequency
        print("\n5. GE SIGNAL GENERATION FREQUENCY (Last 30 days)")
        print("-" * 80)
        
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        ge_signals = session.query(
            func.date(TradingSignalORM.created_at).label('signal_date'),
            func.count(TradingSignalORM.id).label('signal_count'),
            func.sum(func.case((TradingSignalORM.action == 'ENTER_LONG', 1), else_=0)).label('long_signals'),
            func.sum(func.case((TradingSignalORM.action == 'ENTER_SHORT', 1), else_=0)).label('short_signals')
        ).filter(
            TradingSignalORM.symbol == 'GE',
            TradingSignalORM.created_at >= thirty_days_ago
        ).group_by(func.date(TradingSignalORM.created_at)).order_by(func.date(TradingSignalORM.created_at).desc()).all()
        
        if ge_signals:
            print(f"Total signal days: {len(ge_signals)}")
            total_signals = sum(s.signal_count for s in ge_signals)
            print(f"Total signals: {total_signals}")
            print(f"Avg signals per day: {total_signals/30:.1f}")
            print()
            
            print("  Recent signal activity:")
            for s in ge_signals[:10]:
                print(f"    {s.signal_date}: {s.signal_count} signals "
                      f"(LONG: {s.long_signals}, SHORT: {s.short_signals})")
        else:
            print("  No GE signals in last 30 days")
        
        # 6. Strategy type analysis for GE
        print("\n6. GE STRATEGY TYPE ANALYSIS")
        print("-" * 80)
        
        if ge_strategies:
            type_counts = defaultdict(int)
            strategy_details = []
            
            for s in ge_strategies:
                if 'RSI' in s.name:
                    stype = 'RSI-based'
                elif 'BB' in s.name or 'Bollinger' in s.name:
                    stype = 'Bollinger Band'
                elif 'MACD' in s.name:
                    stype = 'MACD-based'
                elif 'SMA' in s.name or 'EMA' in s.name:
                    stype = 'Moving Average'
                else:
                    stype = 'Other'
                
                type_counts[stype] += 1
                strategy_details.append({
                    'type': stype,
                    'direction': s.direction,
                    'sharpe': s.backtest_sharpe_ratio,
                    'win_rate': s.backtest_win_rate,
                    'return': s.backtest_total_return
                })
            
            print("  Strategy type distribution:")
            for stype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"    {stype}: {count}")
            print()
            
            print("  All GE strategies:")
            for sd in strategy_details:
                print(f"    {sd['type']:<20} | {sd['direction']:<6} | "
                      f"Sharpe={sd['sharpe']:.2f} | "
                      f"Win={sd['win_rate']:.1f}% | "
                      f"Return={sd['return']:.1f}%")
        
        # 7. Compare GE performance to portfolio average
        print("\n7. GE PERFORMANCE VS PORTFOLIO AVERAGE")
        print("-" * 80)
        
        portfolio_stats = session.query(
            PositionORM.symbol,
            func.count(PositionORM.id).label('closed_positions'),
            func.avg(PositionORM.pnl).label('avg_pnl'),
            func.avg(PositionORM.pnl_percentage).label('avg_pnl_pct'),
            (func.sum(func.case((PositionORM.pnl > 0, 1), else_=0)) * 100.0 / func.count(PositionORM.id)).label('win_rate')
        ).filter(
            PositionORM.status == 'CLOSED',
            PositionORM.pnl.isnot(None)
        ).group_by(PositionORM.symbol).having(func.count(PositionORM.id) >= 3).order_by(func.avg(PositionORM.pnl_percentage).desc()).all()
        
        ge_stats = None
        portfolio_avg_pct = None
        portfolio_avg_wr = None
        ge_rank = None
        
        if portfolio_stats:
            ge_stats = next((s for s in portfolio_stats if s.symbol == 'GE'), None)
            
            if ge_stats:
                ge_rank = next((i+1 for i, s in enumerate(portfolio_stats) if s.symbol == 'GE'), None)
                print(f"  GE Rank: #{ge_rank} out of {len(portfolio_stats)} symbols")
                print(f"  GE Avg P&L: ${ge_stats.avg_pnl:.2f}")
                print(f"  GE Avg P&L %: {ge_stats.avg_pnl_pct:.2f}%")
                print(f"  GE Win Rate: {ge_stats.win_rate:.1f}%")
                print()
                
                portfolio_avg_pnl = sum(s.avg_pnl for s in portfolio_stats) / len(portfolio_stats)
                portfolio_avg_pct = sum(s.avg_pnl_pct for s in portfolio_stats) / len(portfolio_stats)
                portfolio_avg_wr = sum(s.win_rate for s in portfolio_stats) / len(portfolio_stats)
                
                print(f"  Portfolio Avg P&L: ${portfolio_avg_pnl:.2f}")
                print(f"  Portfolio Avg P&L %: {portfolio_avg_pct:.2f}%")
                print(f"  Portfolio Avg Win Rate: {portfolio_avg_wr:.1f}%")
                print()
                
                print("  GE vs Portfolio:")
                print(f"    P&L: {'+' if ge_stats.avg_pnl > portfolio_avg_pnl else ''}"
                      f"{((ge_stats.avg_pnl - portfolio_avg_pnl) / portfolio_avg_pnl * 100):.1f}%")
                print(f"    P&L %: {'+' if ge_stats.avg_pnl_pct > portfolio_avg_pct else ''}"
                      f"{((ge_stats.avg_pnl_pct - portfolio_avg_pct) / portfolio_avg_pct * 100):.1f}%")
                print(f"    Win Rate: {'+' if ge_stats.win_rate > portfolio_avg_wr else ''}"
                      f"{((ge_stats.win_rate - portfolio_avg_wr) / portfolio_avg_wr * 100):.1f}%")
            else:
                print("  GE has insufficient closed positions for comparison")
        
        # 8. Recent strategy proposals for GE
        print("\n8. RECENT STRATEGY PROPOSALS FOR GE")
        print("-" * 80)
        
        ge_proposals = session.query(StrategyORM).filter(
            StrategyORM.symbol == 'GE',
            StrategyORM.status.in_(['PROPOSED', 'BACKTESTING', 'REJECTED'])
        ).order_by(StrategyORM.created_at.desc()).limit(10).all()
        
        if ge_proposals:
            print(f"Recent GE proposals: {len(ge_proposals)}")
            print()
            for p in ge_proposals:
                print(f"  {p.status:<12} | {p.name[:50]:<50}")
                if p.rejection_reason:
                    print(f"               Reason: {p.rejection_reason}")
        else:
            print("  No recent GE proposals")
        
        # 9. Analysis and recommendations
        print("\n" + "=" * 80)
        print("  ANALYSIS & RECOMMENDATIONS")
        print("=" * 80)
        print()
        
        # Calculate concentration metrics
        total_active_strategies = session.query(func.count(StrategyORM.id)).filter(
            StrategyORM.status.in_(['ACTIVE', 'DEMO'])
        ).scalar()
        
        ge_strategy_count = len(ge_strategies)
        ge_concentration_pct = (ge_strategy_count / total_active_strategies * 100) if total_active_strategies > 0 else 0
        
        print(f"📊 GE Concentration: {ge_strategy_count}/{total_active_strategies} strategies ({ge_concentration_pct:.1f}%)")
        print()
        
        # Determine if concentration is justified
        if ge_stats and portfolio_stats:
            ge_outperformance = ge_stats.avg_pnl_pct > portfolio_avg_pct
            ge_high_win_rate = ge_stats.win_rate > 60
            ge_top_performer = ge_rank and ge_rank <= len(portfolio_stats) * 0.3  # Top 30%
            
            print("🔍 Justification Analysis:")
            print()
            
            if ge_outperformance:
                print(f"  ✅ GE outperforms portfolio average by {((ge_stats.avg_pnl_pct - portfolio_avg_pct) / portfolio_avg_pct * 100):.1f}%")
            else:
                print(f"  ❌ GE underperforms portfolio average by {((portfolio_avg_pct - ge_stats.avg_pnl_pct) / portfolio_avg_pct * 100):.1f}%")
            
            if ge_high_win_rate:
                print(f"  ✅ GE has high win rate ({ge_stats.win_rate:.1f}%)")
            else:
                print(f"  ⚠️  GE has moderate win rate ({ge_stats.win_rate:.1f}%)")
            
            if ge_top_performer:
                print(f"  ✅ GE ranks in top 30% of symbols (#{ge_rank}/{len(portfolio_stats)})")
            else:
                print(f"  ⚠️  GE ranks in bottom 70% of symbols (#{ge_rank}/{len(portfolio_stats)})")
            
            print()
            
            # Overall verdict
            justification_score = sum([ge_outperformance, ge_high_win_rate, ge_top_performer])
            
            if justification_score >= 2:
                print("✅ VERDICT: GE concentration is JUSTIFIED")
                print("   GE demonstrates strong performance metrics that warrant multiple strategies.")
            elif justification_score == 1:
                print("⚠️  VERDICT: GE concentration is PARTIALLY JUSTIFIED")
                print("   GE shows some positive metrics but concentration should be monitored.")
            else:
                print("❌ VERDICT: GE concentration is NOT JUSTIFIED")
                print("   GE underperforms portfolio average. Consider reducing exposure.")
            
            print()
            print("📋 RECOMMENDATIONS:")
            print()
            
            if ge_concentration_pct > 20:
                print("  1. 🔴 HIGH PRIORITY: Reduce GE concentration")
                print(f"     Current: {ge_concentration_pct:.1f}% (Target: <15%)")
                print("     Action: Retire lowest-performing GE strategies")
            elif ge_concentration_pct > 15:
                print("  1. 🟡 MEDIUM PRIORITY: Monitor GE concentration")
                print(f"     Current: {ge_concentration_pct:.1f}% (Target: <15%)")
                print("     Action: Avoid activating new GE strategies")
            else:
                print("  1. ✅ GE concentration within acceptable limits")
                print(f"     Current: {ge_concentration_pct:.1f}% (Target: <15%)")
            
            print()
            
            if not ge_outperformance:
                print("  2. 🔴 Review GE strategy quality")
                print("     GE underperforms portfolio average")
                print("     Action: Analyze why GE strategies are underperforming")
            
            print()
            
            # Check for strategy diversity
            if ge_strategies:
                strategy_types = set()
                for s in ge_strategies:
                    if 'RSI' in s.name:
                        strategy_types.add('RSI-based')
                    elif 'BB' in s.name or 'Bollinger' in s.name:
                        strategy_types.add('Bollinger Band')
                    elif 'MACD' in s.name:
                        strategy_types.add('MACD-based')
                    elif 'SMA' in s.name or 'EMA' in s.name:
                        strategy_types.add('Moving Average')
                    else:
                        strategy_types.add('Other')
                
                unique_types = len(strategy_types)
                if unique_types <= 2:
                    print("  3. 🟡 Low strategy diversity for GE")
                    print(f"     Only {unique_types} strategy types active")
                    print("     Action: Consider diversifying strategy types")
            
            print()
            
            # Check for directional bias
            if ge_strategies:
                short_count = sum(1 for s in ge_strategies if s.direction == 'SHORT')
                long_count = sum(1 for s in ge_strategies if s.direction == 'LONG')
                
                if short_count > long_count * 2 or long_count > short_count * 2:
                    dominant_direction = 'SHORT' if short_count > long_count else 'LONG'
                    print(f"  4. 🟡 Strong directional bias: {dominant_direction}")
                    print(f"     SHORT: {short_count}, LONG: {long_count}")
                    print("     Action: Consider balancing directional exposure")
        else:
            print("⚠️  Insufficient data for comprehensive analysis")
            print("   Need at least 3 closed positions per symbol for comparison")
    
    finally:
        session.close()

if __name__ == "__main__":
    analyze_ge_concentration()
