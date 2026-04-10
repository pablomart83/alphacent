"""Tests for GET /api/control/sync/status endpoint."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.api.routers.control import get_sync_status, SyncStatusResponse


class TestSyncStatus:
    """Tests for the sync status endpoint."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock DB session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_sync_status_no_data(self, mock_session):
        """When no data exists, all sources should report never_synced."""
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.query.return_value.order_by.return_value.first.return_value = None

        result = await get_sync_status(session=mock_session, _user="test")

        assert result.success is True
        sources = result.data["sources"]
        assert len(sources) == 4
        for s in sources:
            assert s["status"] in ("never_synced", "unknown")

    @pytest.mark.asyncio
    async def test_sync_status_with_fmp_data(self, mock_session):
        """When FMP cache warm exists, fundamental_data should report fresh/stale."""
        from src.models.orm import CacheMetadataORM

        fmp_record = MagicMock()
        fmp_record.value = datetime.utcnow().isoformat()

        def side_effect_filter_by(**kwargs):
            mock_result = MagicMock()
            if kwargs.get("key") == "fmp_last_cache_warm":
                mock_result.first.return_value = fmp_record
            else:
                mock_result.first.return_value = None
            return mock_result

        mock_query = MagicMock()
        mock_query.filter_by = side_effect_filter_by
        mock_query.order_by.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        result = await get_sync_status(session=mock_session, _user="test")

        assert result.success is True
        sources_dict = {s["source"]: s for s in result.data["sources"]}
        assert sources_dict["fundamental_data"]["status"] == "fresh"
        assert sources_dict["fundamental_data"]["last_sync"] is not None

    @pytest.mark.asyncio
    async def test_sync_status_response_format(self, mock_session):
        """Response should have success, data, and error fields."""
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.query.return_value.order_by.return_value.first.return_value = None

        result = await get_sync_status(session=mock_session, _user="test")

        assert hasattr(result, "success")
        assert hasattr(result, "data")
        assert hasattr(result, "error")
        assert "checked_at" in result.data
        assert "sources" in result.data

    @pytest.mark.asyncio
    async def test_sync_status_handles_exception(self, mock_session):
        """On DB error, should return success=False with error message."""
        mock_session.query.side_effect = Exception("DB connection failed")

        result = await get_sync_status(session=mock_session, _user="test")

        assert result.success is False
        assert result.error == "DB connection failed"
