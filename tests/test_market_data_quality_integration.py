"""Integration tests for market data quality validation."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from src.data.market_data_manager import MarketDataManager
from src.models import MarketData, DataSource


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client."""
    client = Mock()
    return client


@pytest.fixture
def market_data_manager(mock_etoro_client):
    """Create market data manager with mock client."""
    return MarketDataManager(mock_etoro_client, cache_ttl=60)


@pytest.fixture
def sample_historical_data():
    """Create sample historical data."""
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


def test_quality_validator_initialized(market_data_manager):
    """Test that quality validator is initialized."""
    assert market_data_manager.quality_validator is not None


def test_quality_validation_on_historical_data(market_data_manager, mock_etoro_client, sample_historical_data):
    """Test that quality validation runs on historical data fetch."""
    # Mock the eToro client to return sample data
    mock_etoro_client.get_historical_data.return_value = sample_historical_data
    
    # Fetch historical data
    start = datetime.now() - timedelta(days=100)
    end = datetime.now()
    
    result = market_data_manager.get_historical_data("AAPL", start, end, prefer_yahoo=False)
    
    # Should return data
    assert len(result) == 100
    
    # Should have quality report cached
    quality_report = market_data_manager.get_quality_report("AAPL")
    assert quality_report is not None
    assert quality_report.symbol == "AAPL"
    assert quality_report.quality_score == 100.0


def test_quality_validation_with_bad_data(market_data_manager, mock_etoro_client, sample_historical_data):
    """Test quality validation with bad data."""
    # Create data with issues that pass basic validation but have quality issues
    bad_data = sample_historical_data[:50]
    
    # Add data with large price jump (30% - potential split)
    for i in range(50, 100):
        # 30% jump at index 50
        price_multiplier = 1.3 if i == 50 else 1.0
        bad_data.append(MarketData(
            symbol="AAPL",
            timestamp=sample_historical_data[i].timestamp,
            open=100.0 * price_multiplier + i * 0.5,
            high=102.0 * price_multiplier + i * 0.5,
            low=99.0 * price_multiplier + i * 0.5,
            close=101.0 * price_multiplier + i * 0.5,
            volume=1000000.0,
            source=DataSource.YAHOO_FINANCE
        ))
    
    # Mock the eToro client to return bad data
    mock_etoro_client.get_historical_data.return_value = bad_data
    
    # Fetch historical data - should not raise exception
    start = datetime.now() - timedelta(days=100)
    end = datetime.now()
    
    result = market_data_manager.get_historical_data("AAPL", start, end, prefer_yahoo=False)
    
    # Should return all data (price jump doesn't invalidate data)
    assert len(result) == 100
    
    # Should have quality report with warnings
    quality_report = market_data_manager.get_quality_report("AAPL")
    assert quality_report is not None
    assert quality_report.has_warnings()
    assert quality_report.quality_score < 100.0


def test_get_all_quality_reports(market_data_manager, mock_etoro_client, sample_historical_data):
    """Test getting all quality reports."""
    # Mock data for multiple symbols
    mock_etoro_client.get_historical_data.return_value = sample_historical_data
    
    start = datetime.now() - timedelta(days=100)
    end = datetime.now()
    
    # Fetch data for multiple symbols
    market_data_manager.get_historical_data("AAPL", start, end, prefer_yahoo=False)
    market_data_manager.get_historical_data("MSFT", start, end, prefer_yahoo=False)
    market_data_manager.get_historical_data("GOOGL", start, end, prefer_yahoo=False)
    
    # Get all reports
    all_reports = market_data_manager.get_all_quality_reports()
    
    assert len(all_reports) == 3
    assert "AAPL" in all_reports
    assert "MSFT" in all_reports
    assert "GOOGL" in all_reports


def test_quality_report_caching(market_data_manager, mock_etoro_client, sample_historical_data):
    """Test that quality reports are cached."""
    # Mock the eToro client
    mock_etoro_client.get_historical_data.return_value = sample_historical_data
    
    start = datetime.now() - timedelta(days=100)
    end = datetime.now()
    
    # Fetch data
    market_data_manager.get_historical_data("AAPL", start, end, prefer_yahoo=False)
    
    # Get quality report from cache
    cached_report = market_data_manager.cache.get_quality_report("AAPL")
    assert cached_report is not None
    assert cached_report.symbol == "AAPL"
    
    # Get quality report from manager (should use cache)
    manager_report = market_data_manager.get_quality_report("AAPL")
    assert manager_report is not None
    assert manager_report.timestamp == cached_report.timestamp


def test_trading_continues_despite_quality_issues(market_data_manager, mock_etoro_client, sample_historical_data):
    """Test that trading continues even with quality issues."""
    # Create data with multiple issues
    bad_data = []
    base_time = datetime.now() - timedelta(days=99)
    
    for i in range(100):
        # Add some zero volume days
        volume = 0.0 if i % 10 == 0 else 1000000.0
        
        bad_data.append(MarketData(
            symbol="AAPL",
            timestamp=base_time + timedelta(days=i),
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=volume,
            source=DataSource.YAHOO_FINANCE
        ))
    
    # Mock the eToro client
    mock_etoro_client.get_historical_data.return_value = bad_data
    
    start = datetime.now() - timedelta(days=100)
    end = datetime.now()
    
    # Should not raise exception
    result = market_data_manager.get_historical_data("AAPL", start, end, prefer_yahoo=False)
    
    # Should return data
    assert len(result) == 100
    
    # Should have quality report with warnings
    quality_report = market_data_manager.get_quality_report("AAPL")
    assert quality_report is not None
    assert quality_report.has_warnings()
    
    # But trading can continue
    assert quality_report.quality_score > 0
