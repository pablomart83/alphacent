#!/usr/bin/env python3
"""Test script for data quality validation."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from src.data.data_quality_validator import DataQualityValidator
from src.models import MarketData, DataSource


def create_sample_data(quality: str = "good"):
    """Create sample data with different quality levels."""
    base_time = datetime.now() - timedelta(days=99)
    data = []
    
    if quality == "good":
        # Create good quality data
        for i in range(100):
            data.append(MarketData(
                symbol="AAPL",
                timestamp=base_time + timedelta(days=i),
                open=100.0 + i * 0.5,
                high=102.0 + i * 0.5,
                low=99.0 + i * 0.5,
                close=101.0 + i * 0.5,
                volume=1000000.0,
                source=DataSource.YAHOO_FINANCE
            ))
    
    elif quality == "price_jump":
        # Create data with price jump
        for i in range(100):
            price_multiplier = 1.3 if i == 50 else 1.0
            data.append(MarketData(
                symbol="AAPL",
                timestamp=base_time + timedelta(days=i),
                open=100.0 * price_multiplier + i * 0.5,
                high=102.0 * price_multiplier + i * 0.5,
                low=99.0 * price_multiplier + i * 0.5,
                close=101.0 * price_multiplier + i * 0.5,
                volume=1000000.0,
                source=DataSource.YAHOO_FINANCE
            ))
    
    elif quality == "zero_volume":
        # Create data with zero volume days
        for i in range(100):
            volume = 0.0 if i % 10 == 0 else 1000000.0
            data.append(MarketData(
                symbol="AAPL",
                timestamp=base_time + timedelta(days=i),
                open=100.0 + i * 0.5,
                high=102.0 + i * 0.5,
                low=99.0 + i * 0.5,
                close=101.0 + i * 0.5,
                volume=volume,
                source=DataSource.YAHOO_FINANCE
            ))
    
    elif quality == "gap":
        # Create data with gap > 5 days
        for i in range(50):
            data.append(MarketData(
                symbol="AAPL",
                timestamp=base_time + timedelta(days=i),
                open=100.0 + i * 0.5,
                high=102.0 + i * 0.5,
                low=99.0 + i * 0.5,
                close=101.0 + i * 0.5,
                volume=1000000.0,
                source=DataSource.YAHOO_FINANCE
            ))
        
        # Add 7-day gap (more than 5 days threshold)
        gap_start = base_time + timedelta(days=49)
        for i in range(50, 100):
            data.append(MarketData(
                symbol="AAPL",
                timestamp=gap_start + timedelta(days=i-49+7),  # 7 day gap
                open=100.0 + i * 0.5,
                high=102.0 + i * 0.5,
                low=99.0 + i * 0.5,
                close=101.0 + i * 0.5,
                volume=1000000.0,
                source=DataSource.YAHOO_FINANCE
            ))
    
    return data


def print_report(report):
    """Print quality report."""
    print(f"\n{'='*60}")
    print(f"Data Quality Report for {report.symbol}")
    print(f"{'='*60}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Quality Score: {report.quality_score:.1f}/100")
    print(f"Total Data Points: {report.total_points}")
    print(f"\nMetrics:")
    for key, value in report.metrics.items():
        if key != "issue_types":
            print(f"  {key}: {value}")
    
    if report.issues:
        print(f"\nIssues Found: {len(report.issues)}")
        for issue in report.issues:
            print(f"\n  [{issue.severity.upper()}] {issue.issue_type}")
            print(f"  Message: {issue.message}")
            if issue.details:
                print(f"  Details: {issue.details}")
    else:
        print("\nNo issues found - data quality is excellent!")
    
    print(f"\n{'='*60}\n")


def main():
    """Run data quality validation tests."""
    print("Data Quality Validation Test")
    print("="*60)
    
    validator = DataQualityValidator()
    
    # Test 1: Good quality data
    print("\nTest 1: Good Quality Data")
    good_data = create_sample_data("good")
    report = validator.validate_data_quality(good_data, "AAPL")
    print_report(report)
    
    # Test 2: Data with price jump
    print("\nTest 2: Data with Price Jump (Potential Split)")
    price_jump_data = create_sample_data("price_jump")
    report = validator.validate_data_quality(price_jump_data, "AAPL")
    print_report(report)
    
    # Test 3: Data with zero volume
    print("\nTest 3: Data with Zero Volume Days")
    zero_volume_data = create_sample_data("zero_volume")
    report = validator.validate_data_quality(zero_volume_data, "AAPL")
    print_report(report)
    
    # Test 4: Data with gap
    print("\nTest 4: Data with Missing Data Gap")
    gap_data = create_sample_data("gap")
    report = validator.validate_data_quality(gap_data, "AAPL")
    print_report(report)
    
    # Summary
    print("\nSummary")
    print("="*60)
    all_reports = validator.get_all_reports()
    print(f"Total symbols validated: {len(all_reports)}")
    for symbol, report in all_reports.items():
        status = "✓ PASS" if report.quality_score == 100.0 else "⚠ ISSUES"
        print(f"  {symbol}: {status} (Score: {report.quality_score:.1f}/100)")
    
    print("\n✓ Data quality validation test complete!")


if __name__ == "__main__":
    main()
