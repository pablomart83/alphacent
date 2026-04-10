"""Tests for the Database-First Data Management Strategy (Task 11.7.6).

Tests cover:
1. HistoricalPriceCacheORM and CacheMetadataORM models
2. FMP Cache Warmer DB-first logic (check cache age before API)
3. MarketDataManager DB-first historical data retrieval
4. cleanup_stale_data() retention policy enforcement
5. Cache warm timestamp persistence in DB
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import (
    Base,
    HistoricalPriceCacheORM,
    CacheMetadataORM,
    FundamentalDataORM,
    FundamentalFilterLogORM,
    MLFilterLogORM,
    ConvictionScoreLogORM,
)
from src.models.database import cleanup_stale_data


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestHistoricalPriceCacheORM:
    """Test the HistoricalPriceCacheORM model."""

    def test_create_price_record(self, db_session):
        """Test creating a historical price record."""
        record = HistoricalPriceCacheORM(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            open=185.0,
            high=187.5,
            low=184.0,
            close=186.5,
            volume=50000000.0,
            source="YAHOO_FINANCE",
            fetched_at=datetime.now(),
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(HistoricalPriceCacheORM).filter_by(symbol="AAPL").first()
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.close == 186.5
        assert result.source == "YAHOO_FINANCE"

    def test_unique_constraint_symbol_date(self, db_session):
        """Test that symbol+date combination is unique."""
        record1 = HistoricalPriceCacheORM(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            open=185.0, high=187.5, low=184.0, close=186.5,
            volume=50000000.0, source="YAHOO_FINANCE",
            fetched_at=datetime.now(),
        )
        db_session.add(record1)
        db_session.commit()

        # Same symbol+date should violate unique constraint
        record2 = HistoricalPriceCacheORM(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            open=186.0, high=188.0, low=185.0, close=187.0,
            volume=60000000.0, source="FMP",
            fetched_at=datetime.now(),
        )
        db_session.add(record2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_multiple_symbols_same_date(self, db_session):
        """Test that different symbols can have the same date."""
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            record = HistoricalPriceCacheORM(
                symbol=symbol,
                date=datetime(2024, 1, 15),
                open=100.0, high=105.0, low=99.0, close=103.0,
                volume=1000000.0, source="YAHOO_FINANCE",
                fetched_at=datetime.now(),
            )
            db_session.add(record)
        db_session.commit()

        count = db_session.query(HistoricalPriceCacheORM).count()
        assert count == 3


class TestCacheMetadataORM:
    """Test the CacheMetadataORM model."""

    def test_create_metadata_record(self, db_session):
        """Test creating a cache metadata record."""
        now = datetime.now()
        record = CacheMetadataORM(
            key="fmp_last_cache_warm",
            value=now.isoformat(),
            updated_at=now,
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(CacheMetadataORM).filter_by(key="fmp_last_cache_warm").first()
        assert result is not None
        assert result.value == now.isoformat()

    def test_unique_key_constraint(self, db_session):
        """Test that key is unique."""
        record1 = CacheMetadataORM(key="test_key", value="value1", updated_at=datetime.now())
        db_session.add(record1)
        db_session.commit()

        record2 = CacheMetadataORM(key="test_key", value="value2", updated_at=datetime.now())
        db_session.add(record2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_update_metadata(self, db_session):
        """Test updating an existing metadata record."""
        record = CacheMetadataORM(key="test_key", value="old_value", updated_at=datetime.now())
        db_session.add(record)
        db_session.commit()

        record.value = "new_value"
        record.updated_at = datetime.now()
        db_session.commit()

        result = db_session.query(CacheMetadataORM).filter_by(key="test_key").first()
        assert result.value == "new_value"


class TestFMPCacheWarmerDBFirst:
    """Test the FMP Cache Warmer's DB-first strategy."""

    def test_get_db_cache_age_no_data(self):
        """Test cache age returns None when no data exists."""
        from src.data.fmp_cache_warmer import FMPCacheWarmer

        config = {'data_sources': {'financial_modeling_prep': {}}}
        warmer = FMPCacheWarmer(config)

        with patch('src.models.database.get_database') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            mock_db.return_value.get_session.return_value = mock_session

            age = warmer._get_db_cache_age("NONEXISTENT")
            assert age is None

    def test_get_db_cache_age_fresh_data(self):
        """Test cache age returns correct age for fresh data."""
        from src.data.fmp_cache_warmer import FMPCacheWarmer

        config = {'data_sources': {'financial_modeling_prep': {}}}
        warmer = FMPCacheWarmer(config)

        mock_record = MagicMock()
        mock_record.fetched_at = datetime.now() - timedelta(hours=2)

        with patch('src.models.database.get_database') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter_by.return_value.first.return_value = mock_record
            mock_db.return_value.get_session.return_value = mock_session

            age = warmer._get_db_cache_age("AAPL")
            assert age is not None
            # Should be approximately 2 hours in seconds
            assert 7100 < age < 7300

    def test_save_and_get_last_warm_timestamp(self):
        """Test saving and retrieving last warm timestamp from DB."""
        from src.data.fmp_cache_warmer import FMPCacheWarmer

        config = {'data_sources': {'financial_modeling_prep': {}}}
        warmer = FMPCacheWarmer(config)

        with patch('src.models.database.get_database') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            mock_db.return_value.get_session.return_value = mock_session

            warmer._save_last_warm_timestamp()
            # Verify session.add was called (new record)
            assert mock_session.add.called
            assert mock_session.commit.called

    def test_default_ttls_from_config(self):
        """Test that TTLs are loaded from config."""
        from src.data.fmp_cache_warmer import FMPCacheWarmer

        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'earnings_aware_cache': {
                        'default_ttl': 172800,  # 2 days
                        'earnings_calendar_ttl': 259200,  # 3 days
                    }
                }
            }
        }
        warmer = FMPCacheWarmer(config)
        assert warmer._fundamentals_ttl == 172800
        assert warmer._earnings_ttl == 259200


class TestCleanupStaleData:
    """Test the cleanup_stale_data function."""

    @patch('src.models.database.get_database')
    def test_cleanup_old_historical_prices(self, mock_get_db):
        """Test that old historical price records are cleaned up."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.delete.return_value = 50
        mock_get_db.return_value.get_session.return_value = mock_session

        config = {
            'data_management': {
                'retention': {
                    'historical_prices_days': 2000,
                    'filter_logs_days': 90,
                    'retired_strategy_days': 90,
                }
            }
        }

        results = cleanup_stale_data(config)
        assert mock_session.commit.called

    @patch('src.models.database.get_database')
    def test_cleanup_with_default_config(self, mock_get_db):
        """Test cleanup works with no config (uses defaults)."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.delete.return_value = 0
        mock_get_db.return_value.get_session.return_value = mock_session

        results = cleanup_stale_data()
        assert mock_session.commit.called

    @patch('src.models.database.get_database')
    def test_cleanup_handles_errors_gracefully(self, mock_get_db):
        """Test cleanup handles errors without crashing."""
        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("DB error")
        mock_get_db.return_value.get_session.return_value = mock_session

        results = cleanup_stale_data()
        # Should not raise, should return empty results
        assert isinstance(results, dict)


class TestMarketDataManagerDBFirst:
    """Test MarketDataManager's DB-first historical data strategy."""

    def test_get_historical_from_db_returns_none_for_non_daily(self):
        """Test that DB cache is only used for daily data."""
        from src.data.market_data_manager import MarketDataManager

        mock_client = MagicMock()
        manager = MarketDataManager(mock_client, config={})

        result = manager._get_historical_from_db("AAPL", datetime.now() - timedelta(days=30), datetime.now(), "1h")
        assert result is None

    def test_get_historical_from_db_returns_none_when_empty(self):
        """Test that DB cache returns None when no data exists."""
        from src.data.market_data_manager import MarketDataManager

        mock_client = MagicMock()
        manager = MarketDataManager(mock_client, config={})

        with patch('src.models.database.get_database') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.return_value.get_session.return_value = mock_session

            result = manager._get_historical_from_db(
                "AAPL",
                datetime.now() - timedelta(days=30),
                datetime.now(),
                "1d"
            )
            assert result is None

    def test_save_historical_to_db_skips_existing(self):
        """Test that saving to DB skips existing bars."""
        from src.data.market_data_manager import MarketDataManager
        from src.models.dataclasses import MarketData
        from src.models.enums import DataSource

        mock_client = MagicMock()
        manager = MarketDataManager(mock_client, config={})

        data = [
            MarketData(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 15),
                open=185.0, high=187.5, low=184.0, close=186.5,
                volume=50000000.0, source=DataSource.YAHOO_FINANCE
            )
        ]

        with patch('src.models.database.get_database') as mock_db:
            mock_session = MagicMock()
            # Simulate existing record
            mock_session.query.return_value.filter.return_value.first.return_value = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session

            manager._save_historical_to_db("AAPL", data)
            # Should not add new records since they already exist
            assert not mock_session.add.called

    def test_get_historical_data_has_force_fresh_param(self):
        """Test that get_historical_data accepts force_fresh parameter."""
        from src.data.market_data_manager import MarketDataManager
        import inspect

        sig = inspect.signature(MarketDataManager.get_historical_data)
        assert 'force_fresh' in sig.parameters
        assert sig.parameters['force_fresh'].default is False


class TestConfigDataManagement:
    """Test data management configuration."""

    def test_config_has_data_management_section(self):
        """Test that the config file has the data_management section."""
        import yaml
        from pathlib import Path

        config_path = Path("config/autonomous_trading.yaml")
        assert config_path.exists(), "Config file not found"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert 'data_management' in config, "data_management section missing from config"
        dm = config['data_management']
        assert 'retention' in dm
        assert 'sync_schedule' in dm
        assert dm['retention']['historical_prices_days'] == 2000
        assert dm['retention']['filter_logs_days'] == 90
        assert dm['retention']['retired_strategy_days'] == 90
        assert dm['sync_schedule']['fmp_fundamentals_hours'] == 24
        assert dm['cleanup_enabled'] is True
