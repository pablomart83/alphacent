"""Tests for data quality validator."""

import pytest
from datetime import datetime, timedelta
from src.data.data_quality_validator import DataQualityValidator, DataQualityIssue, DataQualityReport
from src.models import MarketData, DataSource


@pytest.fixture
def validator():
    """Create validator instance."""
    return DataQualityValidator()


@pytest.fixture
def good_data():
    """Create good quality data."""
    # Use recent data to avoid stale data warnings
    base_time = datetime.now() - timedelta(days=99)
    data = []
    
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
    
    return data


def test_validate_good_data(validator, good_data):
    """Test validation of good quality data."""
    report = validator.validate_data_quality(good_data, "AAPL")
    
    assert report.symbol == "AAPL"
    assert report.quality_score == 100.0
    assert report.total_points == 100
    assert len(report.issues) == 0
    assert not report.has_critical_issues()
    assert not report.has_warnings()


def test_validate_empty_data(validator):
    """Test validation of empty data."""
    report = validator.validate_data_quality([], "AAPL")
    
    assert report.symbol == "AAPL"
    assert report.quality_score == 0.0
    assert report.total_points == 0
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "no_data"
    assert report.has_critical_issues()


def test_check_missing_data_gaps(validator, good_data):
    """Test detection of missing data gaps."""
    # Create data with a 7-day gap (more than 5 days threshold)
    data_with_gap = good_data[:50]
    gap_start = good_data[49].timestamp
    
    # Add data after gap
    for i in range(50, 100):
        data_with_gap.append(MarketData(
            symbol="AAPL",
            timestamp=gap_start + timedelta(days=i-49+7),  # 7 day gap
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(data_with_gap, "AAPL")
    
    # Should have warning for gap > 5 days
    gap_issues = [i for i in report.issues if i.issue_type == "missing_data_gap"]
    assert len(gap_issues) > 0
    assert gap_issues[0].severity == "warning"
    assert report.quality_score < 100.0


def test_check_price_jumps(validator, good_data):
    """Test detection of large price jumps."""
    # Create data with a 30% price jump
    data_with_jump = good_data[:50]
    
    # Add data with price jump
    for i in range(50, 100):
        # 30% jump at index 50
        price_multiplier = 1.3 if i == 50 else 1.0
        data_with_jump.append(MarketData(
            symbol="AAPL",
            timestamp=good_data[i].timestamp,
            open=100.0 * price_multiplier + i * 0.5,
            high=102.0 * price_multiplier + i * 0.5,
            low=99.0 * price_multiplier + i * 0.5,
            close=101.0 * price_multiplier + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(data_with_jump, "AAPL")
    
    # Should have warning for price jump
    jump_issues = [i for i in report.issues if i.issue_type == "price_jump"]
    assert len(jump_issues) > 0
    assert jump_issues[0].severity == "warning"
    assert "split" in jump_issues[0].message.lower()


def test_check_zero_volume(validator, good_data):
    """Test detection of zero volume days."""
    # Create data with 10% zero volume days
    data_with_zero_volume = []
    
    for i, point in enumerate(good_data):
        volume = 0.0 if i % 10 == 0 else 1000000.0
        data_with_zero_volume.append(MarketData(
            symbol=point.symbol,
            timestamp=point.timestamp,
            open=point.open,
            high=point.high,
            low=point.low,
            close=point.close,
            volume=volume,
            source=point.source
        ))
    
    report = validator.validate_data_quality(data_with_zero_volume, "AAPL")
    
    # Should have warning for zero volume
    volume_issues = [i for i in report.issues if i.issue_type == "zero_volume"]
    assert len(volume_issues) > 0
    assert volume_issues[0].severity == "warning"
    assert "10" in volume_issues[0].message  # 10% zero volume


def test_check_stale_data(validator):
    """Test detection of stale data."""
    # Create data that's 5 days old
    old_time = datetime.now() - timedelta(days=5)
    stale_data = []
    
    for i in range(100):
        stale_data.append(MarketData(
            symbol="AAPL",
            timestamp=old_time - timedelta(days=99-i),
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(stale_data, "AAPL")
    
    # Should have warning for stale data
    stale_issues = [i for i in report.issues if i.issue_type == "stale_data"]
    assert len(stale_issues) > 0
    assert stale_issues[0].severity == "warning"
    assert "days old" in stale_issues[0].message


def test_check_duplicate_timestamps(validator, good_data):
    """Test detection of duplicate timestamps."""
    # Create data with duplicates
    data_with_duplicates = good_data[:50]
    
    # Add duplicates
    data_with_duplicates.extend(good_data[45:55])  # 5 duplicates
    data_with_duplicates.extend(good_data[55:100])
    
    report = validator.validate_data_quality(data_with_duplicates, "AAPL")
    
    # Should have warning for duplicates
    dup_issues = [i for i in report.issues if i.issue_type == "duplicate_timestamps"]
    assert len(dup_issues) > 0
    assert dup_issues[0].severity == "warning"


def test_check_null_values(validator, good_data):
    """Test detection of null values."""
    # Create data with null values
    data_with_nulls = good_data[:50]
    
    # Add data with null values
    for i in range(50, 100):
        data_with_nulls.append(MarketData(
            symbol="AAPL",
            timestamp=good_data[i].timestamp,
            open=None if i % 10 == 0 else good_data[i].open,
            high=good_data[i].high,
            low=good_data[i].low,
            close=good_data[i].close,
            volume=good_data[i].volume,
            source=good_data[i].source
        ))
    
    report = validator.validate_data_quality(data_with_nulls, "AAPL")
    
    # Should have error for null values
    null_issues = [i for i in report.issues if i.issue_type == "null_values"]
    assert len(null_issues) > 0
    assert null_issues[0].severity == "error"
    assert report.has_critical_issues()


def test_quality_score_calculation(validator, good_data):
    """Test quality score calculation."""
    # Create data with multiple issues
    data_with_issues = good_data[:50]
    
    # Add data with null values (error = -20 points)
    data_with_issues.append(MarketData(
        symbol="AAPL",
        timestamp=good_data[50].timestamp,
        open=None,
        high=good_data[50].high,
        low=good_data[50].low,
        close=good_data[50].close,
        volume=good_data[50].volume,
        source=good_data[50].source
    ))
    
    # Continue with good data
    data_with_issues.extend(good_data[51:100])
    
    report = validator.validate_data_quality(data_with_issues, "AAPL")
    
    # Should have reduced quality score
    # 1 error (-20) = 80
    assert report.quality_score == 80.0
    assert report.has_critical_issues()


def test_report_storage(validator, good_data):
    """Test report storage and retrieval."""
    # Validate data
    report1 = validator.validate_data_quality(good_data, "AAPL")
    
    # Get latest report
    latest = validator.get_latest_report("AAPL")
    assert latest is not None
    assert latest.symbol == "AAPL"
    assert latest.quality_score == report1.quality_score
    
    # Validate again
    report2 = validator.validate_data_quality(good_data, "AAPL")
    
    # Should have 2 reports in history
    assert len(validator.validation_history["AAPL"]) == 2
    
    # Latest should be report2
    latest = validator.get_latest_report("AAPL")
    assert latest.timestamp == report2.timestamp


def test_get_all_reports(validator, good_data):
    """Test getting all reports."""
    # Validate multiple symbols
    validator.validate_data_quality(good_data, "AAPL")
    validator.validate_data_quality(good_data, "MSFT")
    validator.validate_data_quality(good_data, "GOOGL")
    
    # Get all reports
    all_reports = validator.get_all_reports()
    
    assert len(all_reports) == 3
    assert "AAPL" in all_reports
    assert "MSFT" in all_reports
    assert "GOOGL" in all_reports


def test_metrics_calculation(validator, good_data):
    """Test metrics calculation."""
    report = validator.validate_data_quality(good_data, "AAPL")
    
    assert "total_points" in report.metrics
    assert report.metrics["total_points"] == 100
    
    assert "total_issues" in report.metrics
    assert report.metrics["total_issues"] == 0
    
    assert "error_count" in report.metrics
    assert report.metrics["error_count"] == 0
    
    assert "warning_count" in report.metrics
    assert report.metrics["warning_count"] == 0
    
    assert "date_range_days" in report.metrics
    assert report.metrics["date_range_days"] == 99  # 100 days, 0-indexed


def test_trading_continues_despite_issues(validator, good_data):
    """Test that validation doesn't block trading."""
    # Create data with issues
    data_with_issues = good_data[:50]
    
    # Add data with null values
    data_with_issues.append(MarketData(
        symbol="AAPL",
        timestamp=good_data[50].timestamp,
        open=None,
        high=good_data[50].high,
        low=good_data[50].low,
        close=good_data[50].close,
        volume=good_data[50].volume,
        source=good_data[50].source
    ))
    
    # Validation should complete without raising exceptions
    report = validator.validate_data_quality(data_with_issues, "AAPL")
    
    # Report should indicate issues but not block
    assert report.has_critical_issues()
    assert report.quality_score < 100.0
    
    # No exception raised - trading can continue


def test_crypto_gap_detection(validator):
    """Test that crypto symbols have stricter gap detection (24/7 markets)."""
    base_time = datetime.now() - timedelta(days=99)
    crypto_data = []
    
    # Create crypto data with 2-day gap (should be flagged for crypto)
    for i in range(50):
        crypto_data.append(MarketData(
            symbol="BTCUSD",
            timestamp=base_time + timedelta(days=i),
            open=50000.0 + i * 100,
            high=51000.0 + i * 100,
            low=49000.0 + i * 100,
            close=50500.0 + i * 100,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    # Add 2-day gap (should be flagged for crypto since it trades 24/7)
    gap_start = base_time + timedelta(days=49)
    for i in range(50, 100):
        crypto_data.append(MarketData(
            symbol="BTCUSD",
            timestamp=gap_start + timedelta(days=i-49+2),  # 2 day gap
            open=50000.0 + i * 100,
            high=51000.0 + i * 100,
            low=49000.0 + i * 100,
            close=50500.0 + i * 100,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(crypto_data, "BTCUSD")
    
    # Should have warning for gap (crypto trades 24/7)
    gap_issues = [i for i in report.issues if i.issue_type == "missing_data_gap"]
    assert len(gap_issues) > 0
    assert gap_issues[0].severity == "warning"
    assert "asset_class" in gap_issues[0].details
    assert gap_issues[0].details["asset_class"] == "crypto"


def test_stock_weekend_gaps_ignored(validator):
    """Test that stock weekend gaps are not flagged."""
    base_time = datetime.now() - timedelta(days=99)
    stock_data = []
    
    # Create stock data with 4-day gaps (weekends + holiday, normal for stocks)
    for i in range(50):
        stock_data.append(MarketData(
            symbol="AAPL",
            timestamp=base_time + timedelta(days=i),
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    # Add 4-day gap (should NOT be flagged for stocks)
    gap_start = base_time + timedelta(days=49)
    for i in range(50, 100):
        stock_data.append(MarketData(
            symbol="AAPL",
            timestamp=gap_start + timedelta(days=i-49+4),  # 4 day gap
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(stock_data, "AAPL")
    
    # Should NOT have gap warnings (4 days is normal for stocks)
    gap_issues = [i for i in report.issues if i.issue_type == "missing_data_gap"]
    assert len(gap_issues) == 0
    assert report.quality_score == 100.0


def test_forex_gap_detection(validator):
    """Test that forex symbols have moderate gap detection (weekends only)."""
    base_time = datetime.now() - timedelta(days=99)
    forex_data = []
    
    # Create forex data with 4-day gap (should be flagged for forex)
    for i in range(50):
        forex_data.append(MarketData(
            symbol="EURUSD",
            timestamp=base_time + timedelta(days=i),
            open=1.1000 + i * 0.001,
            high=1.1020 + i * 0.001,
            low=1.0980 + i * 0.001,
            close=1.1010 + i * 0.001,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    # Add 4-day gap (should be flagged for forex, threshold is 3 days)
    gap_start = base_time + timedelta(days=49)
    for i in range(50, 100):
        forex_data.append(MarketData(
            symbol="EURUSD",
            timestamp=gap_start + timedelta(days=i-49+4),  # 4 day gap
            open=1.1000 + i * 0.001,
            high=1.1020 + i * 0.001,
            low=1.0980 + i * 0.001,
            close=1.1010 + i * 0.001,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    report = validator.validate_data_quality(forex_data, "EURUSD")
    
    # Should have warning for gap (forex threshold is 3 days)
    gap_issues = [i for i in report.issues if i.issue_type == "missing_data_gap"]
    assert len(gap_issues) > 0
    assert gap_issues[0].severity == "warning"
    assert gap_issues[0].details["asset_class"] == "forex"
