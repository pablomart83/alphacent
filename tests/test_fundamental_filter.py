"""
Tests for FundamentalFilter.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime
from src.strategy.fundamental_filter import FundamentalFilter, FilterResult, FundamentalFilterReport
from src.data.fundamental_data_provider import FundamentalData, FundamentalDataProvider


class TestFundamentalFilter:
    """Tests for FundamentalFilter."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            'alpha_edge': {
                'fundamental_filters': {
                    'enabled': True,
                    'min_checks_passed': 4,
                    'checks': {
                        'profitable': True,
                        'growing': True,
                        'reasonable_valuation': True,
                        'no_dilution': True,
                        'insider_buying': True
                    }
                }
            }
        }
    
    @pytest.fixture
    def mock_provider(self):
        """Mock data provider."""
        return Mock(spec=FundamentalDataProvider)
    
    @pytest.fixture
    def filter_instance(self, config, mock_provider):
        """Create filter instance."""
        return FundamentalFilter(config, mock_provider)
    
    def test_initialization(self, filter_instance):
        """Test filter initialization."""
        assert filter_instance.enabled is True
        assert filter_instance.min_checks_passed == 4
        assert filter_instance.check_profitable is True
    
    def test_passes_when_disabled(self, config, mock_provider):
        """Test that filter passes everything when disabled."""
        config['alpha_edge']['fundamental_filters']['enabled'] = False
        filter_instance = FundamentalFilter(config, mock_provider)
        
        report = filter_instance.filter_symbol("AAPL")
        
        assert report.passed is True
        assert report.checks_passed == 5
    
    def test_fails_when_no_data_available(self, filter_instance, mock_provider):
        """Test that filter fails when no fundamental data is available."""
        mock_provider.get_fundamental_data.return_value = None
        
        report = filter_instance.filter_symbol("AAPL")
        
        assert report.passed is False
        assert report.checks_passed == 0
        assert len(report.results) == 1
        assert report.results[0].check_name == "data_availability"
    
    def test_profitable_check_passes(self, filter_instance, mock_provider):
        """Test profitable check with positive EPS."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        profitable_result = next(r for r in report.results if r.check_name == "profitable")
        assert profitable_result.passed is True
        assert profitable_result.value == 6.05
    
    def test_profitable_check_fails(self, filter_instance, mock_provider):
        """Test profitable check with negative EPS."""
        data = FundamentalData(
            symbol="LOSS",
            timestamp=datetime.now(),
            eps=-2.50,
            revenue_growth=0.08,
            pe_ratio=28.5,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("LOSS")
        
        profitable_result = next(r for r in report.results if r.check_name == "profitable")
        assert profitable_result.passed is False
        assert profitable_result.value == -2.50
    
    def test_growing_check_passes(self, filter_instance, mock_provider):
        """Test growing check with positive revenue growth."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.15,  # 15% growth
            pe_ratio=28.5,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        growing_result = next(r for r in report.results if r.check_name == "growing")
        assert growing_result.passed is True
        assert growing_result.value == 15.0  # Converted to percentage
    
    def test_growing_check_fails(self, filter_instance, mock_provider):
        """Test growing check with negative revenue growth."""
        data = FundamentalData(
            symbol="SHRINK",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=-0.05,  # -5% growth
            pe_ratio=28.5,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("SHRINK")
        
        growing_result = next(r for r in report.results if r.check_name == "growing")
        assert growing_result.passed is False
        assert growing_result.value == -5.0
    
    def test_valuation_check_value_stock(self, filter_instance, mock_provider):
        """Test valuation check for value stock (P/E < 30)."""
        data = FundamentalData(
            symbol="VALUE",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=25.0,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("VALUE", strategy_type="value")
        
        valuation_result = next(r for r in report.results if r.check_name == "reasonable_valuation")
        assert valuation_result.passed is True
        assert valuation_result.threshold == 30.0
    
    def test_valuation_check_growth_stock(self, filter_instance, mock_provider):
        """Test valuation check for growth stock (P/E < 50)."""
        data = FundamentalData(
            symbol="GROWTH",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.25,
            pe_ratio=45.0,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("GROWTH", strategy_type="growth")
        
        valuation_result = next(r for r in report.results if r.check_name == "reasonable_valuation")
        assert valuation_result.passed is True
        assert valuation_result.threshold == 70.0  # Updated from 50.0 to 70.0 (task 11.6.3)
    
    def test_valuation_check_fails_overvalued(self, filter_instance, mock_provider):
        """Test valuation check fails for overvalued stock."""
        data = FundamentalData(
            symbol="EXPENSIVE",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=100.0,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("EXPENSIVE", strategy_type="value")
        
        valuation_result = next(r for r in report.results if r.check_name == "reasonable_valuation")
        assert valuation_result.passed is False
    
    def test_valuation_check_fails_negative_pe(self, filter_instance, mock_provider):
        """Test valuation check fails for negative P/E."""
        data = FundamentalData(
            symbol="NEGATIVE",
            timestamp=datetime.now(),
            eps=-1.0,
            revenue_growth=0.08,
            pe_ratio=-15.0,
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("NEGATIVE")
        
        valuation_result = next(r for r in report.results if r.check_name == "reasonable_valuation")
        assert valuation_result.passed is False
    
    def test_dilution_check_passes_by_default(self, filter_instance, mock_provider):
        """Test dilution check passes when data not available."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            shares_change_percent=None,  # No data
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        dilution_result = next(r for r in report.results if r.check_name == "no_dilution")
        assert dilution_result.passed is True
    
    def test_dilution_check_passes_low_dilution(self, filter_instance, mock_provider):
        """Test dilution check passes with low dilution."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            shares_change_percent=5.0,  # 5% increase
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        dilution_result = next(r for r in report.results if r.check_name == "no_dilution")
        assert dilution_result.passed is True
    
    def test_dilution_check_fails_high_dilution(self, filter_instance, mock_provider):
        """Test dilution check fails with high dilution."""
        data = FundamentalData(
            symbol="DILUTED",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            shares_change_percent=15.0,  # 15% increase
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("DILUTED")
        
        dilution_result = next(r for r in report.results if r.check_name == "no_dilution")
        assert dilution_result.passed is False
    
    def test_insider_buying_check_passes_by_default(self, filter_instance, mock_provider):
        """Test insider buying check passes when data not available."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            insider_net_buying=None,  # No data
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        insider_result = next(r for r in report.results if r.check_name == "insider_buying")
        assert insider_result.passed is True
    
    def test_insider_buying_check_passes(self, filter_instance, mock_provider):
        """Test insider buying check passes with positive buying."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            insider_net_buying=1000000.0,  # $1M net buying
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        insider_result = next(r for r in report.results if r.check_name == "insider_buying")
        assert insider_result.passed is True
    
    def test_insider_buying_check_fails(self, filter_instance, mock_provider):
        """Test insider buying check fails with net selling."""
        data = FundamentalData(
            symbol="SELLING",
            timestamp=datetime.now(),
            eps=6.05,
            revenue_growth=0.08,
            pe_ratio=28.5,
            insider_net_buying=-500000.0,  # $500K net selling
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("SELLING")
        
        insider_result = next(r for r in report.results if r.check_name == "insider_buying")
        assert insider_result.passed is False
    
    def test_passes_with_4_out_of_5_checks(self, filter_instance, mock_provider):
        """Test that stock passes with 4 out of 5 checks."""
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,  # Pass
            revenue_growth=0.08,  # Pass
            pe_ratio=28.5,  # Pass
            shares_change_percent=5.0,  # Pass
            insider_net_buying=-100000.0,  # Fail
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("AAPL")
        
        assert report.passed is True
        assert report.checks_passed == 4
        assert report.checks_total == 5
    
    def test_fails_with_3_out_of_5_checks(self, filter_instance, mock_provider):
        """Test that stock fails with only 3 out of 5 checks."""
        data = FundamentalData(
            symbol="WEAK",
            timestamp=datetime.now(),
            eps=6.05,  # Pass
            revenue_growth=0.08,  # Pass
            pe_ratio=28.5,  # Pass
            shares_change_percent=15.0,  # Fail
            insider_net_buying=-100000.0,  # Fail
            source="test"
        )
        mock_provider.get_fundamental_data.return_value = data
        
        report = filter_instance.filter_symbol("WEAK")
        
        assert report.passed is False
        assert report.checks_passed == 3
        assert report.checks_total == 5
    
    def test_filter_multiple_symbols(self, filter_instance, mock_provider):
        """Test filtering multiple symbols."""
        def get_data(symbol):
            if symbol == "AAPL":
                return FundamentalData(
                    symbol="AAPL",
                    timestamp=datetime.now(),
                    eps=6.05,
                    revenue_growth=0.08,
                    pe_ratio=28.5,
                    source="test"
                )
            elif symbol == "WEAK":
                return FundamentalData(
                    symbol="WEAK",
                    timestamp=datetime.now(),
                    eps=-1.0,
                    revenue_growth=-0.05,
                    pe_ratio=100.0,
                    source="test"
                )
            return None
        
        mock_provider.get_fundamental_data.side_effect = get_data
        
        results = filter_instance.filter_symbols(["AAPL", "WEAK"])
        
        assert len(results) == 2
        assert results["AAPL"].passed is True
        assert results["WEAK"].passed is False
    
    def test_get_passed_symbols(self, filter_instance, mock_provider):
        """Test getting only passed symbols."""
        def get_data(symbol):
            if symbol in ["AAPL", "MSFT"]:
                return FundamentalData(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    eps=6.05,
                    revenue_growth=0.08,
                    pe_ratio=28.5,
                    source="test"
                )
            else:
                return FundamentalData(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    eps=-1.0,
                    revenue_growth=-0.05,
                    pe_ratio=100.0,
                    source="test"
                )
        
        mock_provider.get_fundamental_data.side_effect = get_data
        
        passed = filter_instance.get_passed_symbols(["AAPL", "WEAK", "MSFT", "LOSS"])
        
        assert len(passed) == 2
        assert "AAPL" in passed
        assert "MSFT" in passed
        assert "WEAK" not in passed
        assert "LOSS" not in passed
