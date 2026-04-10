#!/usr/bin/env python3
"""Check data quality for actual trading symbols."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from datetime import datetime, timedelta
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode


async def check_data_quality():
    """Check data quality for actual symbols."""
    print("Checking Live Data Quality")
    print("="*80)
    
    # Test symbols from config
    test_symbols = ["AAPL", "MSFT", "GOOGL", "SPY", "QQQ"]
    
    # Create a mock eToro client (we'll use Yahoo Finance fallback)
    etoro_client = EToroAPIClient(
        public_key="mock",
        user_key="mock",
        mode=TradingMode.DEMO
    )
    
    manager = MarketDataManager(etoro_client, cache_ttl=60)
    
    # Fetch data for each symbol
    end = datetime.now()
    start = end - timedelta(days=365)  # 1 year of data
    
    results = []
    
    for symbol in test_symbols:
        print(f"\nChecking {symbol}...")
        try:
            # Fetch historical data (will use Yahoo Finance)
            data = manager.get_historical_data(
                symbol=symbol,
                start=start,
                end=end,
                interval="1d",
                prefer_yahoo=True
            )
            
            # Get quality report
            report = manager.get_quality_report(symbol)
            
            if report:
                results.append({
                    "symbol": symbol,
                    "data_points": len(data),
                    "quality_score": report.quality_score,
                    "issues": len(report.issues),
                    "error_count": report.metrics.get("error_count", 0),
                    "warning_count": report.metrics.get("warning_count", 0),
                    "date_range_days": report.metrics.get("date_range_days", 0),
                    "report": report
                })
                
                status = "✓ GOOD" if report.quality_score >= 95 else "⚠ ISSUES"
                print(f"  {status} - Score: {report.quality_score:.1f}/100, "
                      f"Points: {len(data)}, Issues: {len(report.issues)}")
                
                if report.issues:
                    for issue in report.issues:
                        print(f"    [{issue.severity.upper()}] {issue.message}")
            else:
                print(f"  ✗ No quality report available")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                "symbol": symbol,
                "error": str(e)
            })
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    if results:
        successful = [r for r in results if "quality_score" in r]
        
        if successful:
            avg_score = sum(r["quality_score"] for r in successful) / len(successful)
            avg_points = sum(r["data_points"] for r in successful) / len(successful)
            total_issues = sum(r["issues"] for r in successful)
            
            print(f"\nSymbols Checked: {len(test_symbols)}")
            print(f"Successful: {len(successful)}")
            print(f"Average Quality Score: {avg_score:.1f}/100")
            print(f"Average Data Points: {avg_points:.0f}")
            print(f"Total Issues Found: {total_issues}")
            
            print("\nPer-Symbol Results:")
            for r in successful:
                status_icon = "✓" if r["quality_score"] >= 95 else "⚠"
                print(f"  {status_icon} {r['symbol']:6s}: {r['quality_score']:5.1f}/100 "
                      f"({r['data_points']:3d} points, {r['issues']} issues)")
            
            # Overall assessment
            print("\nOVERALL ASSESSMENT:")
            if avg_score >= 95:
                print("  ✓ EXCELLENT - Data quality is very good")
            elif avg_score >= 85:
                print("  ⚠ GOOD - Minor data quality issues detected")
            elif avg_score >= 70:
                print("  ⚠ FAIR - Some data quality issues need attention")
            else:
                print("  ✗ POOR - Significant data quality issues detected")
            
            # Recommendations
            if total_issues > 0:
                print("\nRECOMMENDATIONS:")
                issue_types = {}
                for r in successful:
                    if "report" in r:
                        for issue in r["report"].issues:
                            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1
                
                for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
                    print(f"  - {issue_type}: {count} occurrences")
                    
                    if issue_type == "stale_data":
                        print(f"    → Data may be outdated, consider refreshing more frequently")
                    elif issue_type == "price_jump":
                        print(f"    → Check for stock splits or data errors")
                    elif issue_type == "zero_volume":
                        print(f"    → May indicate holidays or data gaps")
                    elif issue_type == "missing_data_gap":
                        print(f"    → Consider using a more reliable data source")
        else:
            print("✗ No successful data quality checks")
    else:
        print("✗ No results to display")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(check_data_quality())
