"""
Tests for strategy management endpoints (proposals, retirements, templates).

Validates: Requirements 2.6, 2.7, 4.1, 4.2
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.models.orm import StrategyProposalORM, StrategyRetirementORM
from src.models.dataclasses import Strategy
from src.models.enums import StrategyStatus


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = Mock()
    return session


@pytest.fixture
def mock_strategy_engine():
    """Mock strategy engine."""
    engine = Mock()
    return engine


class TestProposalsEndpoint:
    """Tests for GET /api/strategies/proposals endpoint."""
    
    @pytest.mark.asyncio
    async def test_proposals_endpoint_structure(self, mock_db_session, mock_strategy_engine):
        """Test that proposals endpoint has correct structure."""
        from src.api.routers.strategies import get_strategy_proposals
        
        # Create mock proposals
        proposal1 = Mock(spec=StrategyProposalORM)
        proposal1.id = 1
        proposal1.strategy_id = "strat_001"
        proposal1.proposed_at = datetime(2024, 1, 1, 12, 0, 0)
        proposal1.market_regime = "TRENDING_UP"
        proposal1.backtest_sharpe = 1.85
        proposal1.activated = 1
        proposal1.to_dict.return_value = {
            "id": 1,
            "strategy_id": "strat_001",
            "proposed_at": "2024-01-01T12:00:00",
            "market_regime": "TRENDING_UP",
            "backtest_sharpe": 1.85,
            "activated": True
        }
        
        # Mock query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [proposal1]
        
        mock_db_session.query.return_value = mock_query
        
        # Mock strategy
        mock_strategy = Mock(spec=Strategy)
        mock_strategy.id = "strat_001"
        mock_strategy.name = "RSI Mean Reversion"
        mock_strategy.status = StrategyStatus.DEMO
        mock_strategy.symbols = ["SPY", "QQQ"]
        mock_strategy.template_name = "RSI Mean Reversion"
        mock_strategy.entry_rules = ["RSI(14) < 30"]
        mock_strategy.exit_rules = ["RSI(14) > 70"]
        
        mock_strategy_engine.get_strategy.return_value = mock_strategy
        
        with patch('src.api.routers.strategies._get_strategy_engine', return_value=mock_strategy_engine):
            result = await get_strategy_proposals(
                page=1,
                page_size=20,
                market_regime=None,
                activated=None,
                username="test_user",
                db=mock_db_session
            )
        
        assert result.total == 1
        assert result.page == 1
        assert result.page_size == 20
        assert len(result.proposals) == 1
        
        proposal = result.proposals[0]
        assert proposal.id == 1
        assert proposal.strategy_id == "strat_001"
        assert proposal.market_regime == "TRENDING_UP"
        assert proposal.backtest_sharpe == 1.85
        assert proposal.activated is True
        assert proposal.evaluation_score is not None


class TestRetirementsEndpoint:
    """Tests for GET /api/strategies/retirements endpoint."""
    
    @pytest.mark.asyncio
    async def test_retirements_endpoint_structure(self, mock_db_session, mock_strategy_engine):
        """Test that retirements endpoint has correct structure."""
        from src.api.routers.strategies import get_strategy_retirements
        
        # Create mock retirement
        retirement1 = Mock(spec=StrategyRetirementORM)
        retirement1.id = 1
        retirement1.strategy_id = "strat_003"
        retirement1.retired_at = datetime(2024, 1, 15, 12, 0, 0)
        retirement1.reason = "Performance degradation"
        retirement1.final_sharpe = 0.42
        retirement1.final_return = -8.2
        retirement1.to_dict.return_value = {
            "id": 1,
            "strategy_id": "strat_003",
            "retired_at": "2024-01-15T12:00:00",
            "reason": "Performance degradation",
            "final_sharpe": 0.42,
            "final_return": -8.2
        }
        
        # Mock query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [retirement1]
        
        mock_db_session.query.return_value = mock_query
        
        # Mock strategy
        mock_strategy = Mock(spec=Strategy)
        mock_strategy.name = "MACD Momentum"
        mock_strategy_engine.get_strategy.return_value = mock_strategy
        
        with patch('src.api.routers.strategies._get_strategy_engine', return_value=mock_strategy_engine):
            result = await get_strategy_retirements(
                page=1,
                page_size=20,
                reason=None,
                username="test_user",
                db=mock_db_session
            )
        
        assert result.total == 1
        assert result.page == 1
        assert len(result.retirements) == 1
        
        retirement = result.retirements[0]
        assert retirement.id == 1
        assert retirement.strategy_id == "strat_003"
        assert retirement.strategy_name == "MACD Momentum"
        assert retirement.reason == "Performance degradation"
        assert retirement.final_metrics["sharpe"] == 0.42
        assert retirement.final_metrics["totalReturn"] == -8.2


class TestTemplatesEndpoint:
    """Tests for GET /api/strategies/templates endpoint."""
    
    @pytest.mark.asyncio
    async def test_templates_endpoint_structure(self, mock_db_session):
        """Test that templates endpoint returns correct structure."""
        from src.api.routers.strategies import get_strategy_templates
        
        # Mock proposals query
        mock_query = Mock()
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query
        
        with patch('src.api.routers.strategies._get_strategy_engine'):
            result = await get_strategy_templates(
                market_regime=None,
                username="test_user",
                db=mock_db_session
            )
        
        assert result.total > 0  # Should have templates from library
        assert len(result.templates) > 0
        
        # Check template structure
        template = result.templates[0]
        assert hasattr(template, 'name')
        assert hasattr(template, 'description')
        assert hasattr(template, 'market_regimes')
        assert hasattr(template, 'indicators')
        assert hasattr(template, 'entry_rules')
        assert hasattr(template, 'exit_rules')
        assert hasattr(template, 'success_rate')
        assert hasattr(template, 'usage_count')
    
    @pytest.mark.asyncio
    async def test_templates_with_regime_filter(self, mock_db_session):
        """Test templates endpoint with market regime filter."""
        from src.api.routers.strategies import get_strategy_templates
        
        mock_query = Mock()
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query
        
        with patch('src.api.routers.strategies._get_strategy_engine'):
            result = await get_strategy_templates(
                market_regime="trending_up",  # Use lowercase with underscores
                username="test_user",
                db=mock_db_session
            )
        
        # Should only return templates for trending_up regime
        for template in result.templates:
            assert "trending_up" in template.market_regimes


def test_template_library_integration():
    """Test that StrategyTemplateLibrary is accessible and has templates."""
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    
    library = StrategyTemplateLibrary()
    templates = library.get_all_templates()
    
    assert len(templates) > 0
    assert all(hasattr(t, 'name') for t in templates)
    assert all(hasattr(t, 'description') for t in templates)
    assert all(hasattr(t, 'market_regimes') for t in templates)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
