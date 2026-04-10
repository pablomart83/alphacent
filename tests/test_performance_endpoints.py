"""
Tests for Performance & Analytics API endpoints.

Tests the /api/performance endpoints for metrics, portfolio composition,
and historical events.

Validates: Requirements 5.1, 5.2, 5.3, 6.1, 6.2
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.models.orm import StrategyProposalORM, StrategyRetirementORM
from src.models.dataclasses import Strategy


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


@pytest.fixture
def mock_portfolio_manager():
    """Mock portfolio manager."""
    manager = Mock()
    return manager


@pytest.fixture
def sample_proposals():
    """Create sample strategy proposals."""
    proposals = []
    base_time = datetime.now() - timedelta(days=30)
    
    for i in range(5):
        proposal = Mock(spec=StrategyProposalORM)
        proposal.id = i + 1
        proposal.strategy_id = f"strategy_{i}"
        proposal.proposed_at = base_time + timedelta(days=i*5)
        proposal.market_regime = "TRENDING_UP" if i % 2 == 0 else "RANGING"
        proposal.evaluation_score = 0.75 + (i * 0.05)
        proposal.activated = (i < 3)  # First 3 are activated
        proposals.append(proposal)
    
    return proposals


@pytest.fixture
def sample_retirements():
    """Create sample strategy retirements."""
    retirements = []
    base_time = datetime.now() - timedelta(days=20)
    
    for i in range(3):
        retirement = Mock(spec=StrategyRetirementORM)
        retirement.id = i + 1
        retirement.strategy_id = f"retired_strategy_{i}"
        retirement.retired_at = base_time + timedelta(days=i*5)
        retirement.reason = "Performance degradation" if i % 2 == 0 else "Drawdown exceeded"
        retirement.final_sharpe = 0.5 - (i * 0.1)
        retirement.final_return = -5.0 - (i * 2.0)
        retirement.final_drawdown = -15.0 - (i * 3.0)
        retirements.append(retirement)
    
    return retirements


@pytest.fixture
def sample_strategies():
    """Create sample active strategies."""
    strategies = []
    
    for i in range(3):
        strategy = Mock(spec=Strategy)
        strategy.id = f"strategy_{i}"
        strategy.name = f"Test Strategy {i}"
        strategy.allocation_pct = 10.0 + (i * 5.0)
        strategy.sharpe_ratio = 1.5 + (i * 0.2)
        strategy.total_return = 10.0 + (i * 3.0)
        strategy.max_drawdown = -5.0 - (i * 1.0)
        strategy.win_rate = 60.0 + (i * 2.0)
        strategy.trades = [
            {"pnl": 100.0 * (j + 1)} if j % 2 == 0 else {"pnl": -50.0 * (j + 1)}
            for j in range(10)
        ]
        strategies.append(strategy)
    
    return strategies


class TestPerformanceMetricsEndpoint:
    """Tests for GET /api/performance/metrics endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_metrics_default_period(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test fetching metrics with default period (3M)."""
        from src.api.routers.performance import get_performance_metrics, TimePeriod
        
        # Setup mocks
        mock_strategy_engine.get_active_strategies.return_value = sample_strategies
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {
            'total_return': 15.0,
            'sharpe_ratio': 1.75
        }
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                # Call endpoint
                result = await get_performance_metrics(
                    period=TimePeriod.THREE_MONTHS,
                    strategy_id=None,
                    username="testuser",
                    db=mock_db_session
                )
        
        # Verify response structure
        assert result.sharpe is not None
        assert result.total_return is not None
        assert result.max_drawdown is not None
        assert result.win_rate is not None
        assert result.portfolio_history is not None
        assert result.strategy_contributions is not None
        assert result.period == "3M"
    
    @pytest.mark.asyncio
    async def test_get_metrics_with_strategy_filter(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test fetching metrics filtered by strategy."""
        from src.api.routers.performance import get_performance_metrics, TimePeriod
        
        # Setup mocks - return single strategy
        mock_strategy_engine.get_strategy.return_value = sample_strategies[0]
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {
            'total_return': 10.0,
            'sharpe_ratio': 1.5
        }
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                result = await get_performance_metrics(
                    period=TimePeriod.ONE_MONTH,
                    strategy_id="strategy_0",
                    username="testuser",
                    db=mock_db_session
                )
        
        # Should have called get_strategy
        mock_strategy_engine.get_strategy.assert_called_once_with("strategy_0")
        assert result.period == "1M"
    
    @pytest.mark.asyncio
    async def test_get_metrics_empty_strategies(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager):
        """Test fetching metrics with no active strategies."""
        from src.api.routers.performance import get_performance_metrics, TimePeriod
        
        # Setup mocks - no strategies
        mock_strategy_engine.get_active_strategies.return_value = []
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                result = await get_performance_metrics(
                    period=TimePeriod.THREE_MONTHS,
                    strategy_id=None,
                    username="testuser",
                    db=mock_db_session
                )
        
        # Should return empty metrics
        assert result.sharpe.value == 0.0
        assert result.total_return.value == 0.0
        assert len(result.portfolio_history) == 0
        assert len(result.strategy_contributions) == 0


class TestPortfolioCompositionEndpoint:
    """Tests for GET /api/performance/portfolio endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_portfolio_composition(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test fetching portfolio composition."""
        from src.api.routers.performance import get_portfolio_composition
        
        # Setup mocks
        mock_strategy_engine.get_active_strategies.return_value = sample_strategies
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {
            'total_return': 15.0,
            'sharpe_ratio': 1.75
        }
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                with patch('src.api.routers.performance._get_correlation_analyzer'):
                    result = await get_portfolio_composition(
                        username="testuser",
                        db=mock_db_session
                    )
        
        # Verify response structure
        assert result.strategies is not None
        assert result.correlation_matrix is not None
        assert result.risk_metrics is not None
        assert result.total_value > 0
        assert len(result.strategies) == 3
    
    @pytest.mark.asyncio
    async def test_get_portfolio_correlation_matrix(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test correlation matrix calculation."""
        from src.api.routers.performance import get_portfolio_composition
        
        mock_strategy_engine.get_active_strategies.return_value = sample_strategies
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {}
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                with patch('src.api.routers.performance._get_correlation_analyzer'):
                    result = await get_portfolio_composition(
                        username="testuser",
                        db=mock_db_session
                    )
        
        # Verify correlation matrix
        matrix = result.correlation_matrix
        assert len(matrix) == 3  # 3 strategies
        assert all(len(row) == 3 for row in matrix)
        
        # Diagonal should be 1.0
        for i in range(3):
            assert matrix[i][i] == pytest.approx(1.0, abs=0.01)
    
    @pytest.mark.asyncio
    async def test_get_portfolio_empty_strategies(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager):
        """Test portfolio with no active strategies."""
        from src.api.routers.performance import get_portfolio_composition
        
        mock_strategy_engine.get_active_strategies.return_value = []
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                with patch('src.api.routers.performance._get_correlation_analyzer'):
                    result = await get_portfolio_composition(
                        username="testuser",
                        db=mock_db_session
                    )
        
        # Should handle empty portfolio
        assert len(result.strategies) == 0
        assert len(result.correlation_matrix) == 0
        assert result.risk_metrics.portfolio_var == 0.0


class TestPerformanceHistoryEndpoint:
    """Tests for GET /api/performance/history endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_history_default_params(self, mock_db_session, sample_proposals, sample_retirements):
        """Test fetching history with default parameters."""
        from src.api.routers.performance import get_performance_history
        
        # Setup mock query - return actual proposal/retirement objects
        proposals_query = Mock()
        proposals_query.filter.return_value = proposals_query
        proposals_query.order_by.return_value = proposals_query
        proposals_query.limit.return_value = proposals_query
        proposals_query.all.return_value = sample_proposals
        
        retirements_query = Mock()
        retirements_query.filter.return_value = retirements_query
        retirements_query.order_by.return_value = retirements_query
        retirements_query.limit.return_value = retirements_query
        retirements_query.all.return_value = sample_retirements
        
        # First call returns proposals query, second returns retirements query
        mock_db_session.query.side_effect = [proposals_query, retirements_query]
        
        result = await get_performance_history(
            start_date=None,
            end_date=None,
            event_types=None,
            limit=100,
            username="testuser",
            db=mock_db_session
        )
        
        # Verify response structure
        assert result.events is not None
        assert result.total >= 0
        assert result.start_date is not None
        assert result.end_date is not None
    
    @pytest.mark.asyncio
    async def test_get_history_with_date_range(self, mock_db_session, sample_proposals):
        """Test fetching history with custom date range."""
        from src.api.routers.performance import get_performance_history
        
        start_date = datetime.now() - timedelta(days=20)
        end_date = datetime.now()
        
        # Setup mock query - return actual proposal objects
        proposals_query = Mock()
        proposals_query.filter.return_value = proposals_query
        proposals_query.order_by.return_value = proposals_query
        proposals_query.limit.return_value = proposals_query
        proposals_query.all.return_value = sample_proposals
        
        retirements_query = Mock()
        retirements_query.filter.return_value = retirements_query
        retirements_query.order_by.return_value = retirements_query
        retirements_query.limit.return_value = retirements_query
        retirements_query.all.return_value = []
        
        # First call returns proposals query, second returns retirements query
        mock_db_session.query.side_effect = [proposals_query, retirements_query]
        
        result = await get_performance_history(
            start_date=start_date,
            end_date=end_date,
            event_types=None,
            limit=100,
            username="testuser",
            db=mock_db_session
        )
        
        # Verify dates are set
        assert result.start_date == start_date
        assert result.end_date == end_date
    
    @pytest.mark.asyncio
    async def test_get_history_proposals_events(self, mock_db_session, sample_proposals):
        """Test that proposal events are included."""
        from src.api.routers.performance import get_performance_history, EventType
        
        # Setup mock query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = sample_proposals
        
        mock_db_session.query.return_value = mock_query
        
        result = await get_performance_history(
            start_date=None,
            end_date=None,
            event_types=[EventType.STRATEGIES_PROPOSED],
            limit=100,
            username="testuser",
            db=mock_db_session
        )
        
        # Should have proposal events
        assert result.total > 0
        proposal_events = [e for e in result.events if e.type == EventType.STRATEGIES_PROPOSED]
        assert len(proposal_events) > 0
    
    @pytest.mark.asyncio
    async def test_get_history_retirement_events(self, mock_db_session, sample_retirements):
        """Test that retirement events are included."""
        from src.api.routers.performance import get_performance_history, EventType
        
        # Setup mock query for retirements
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        
        # First query returns empty proposals, second returns retirements
        mock_db_session.query.side_effect = [
            Mock(filter=Mock(return_value=Mock(
                order_by=Mock(return_value=Mock(
                    limit=Mock(return_value=Mock(all=Mock(return_value=[])))
                ))
            ))),
            Mock(filter=Mock(return_value=Mock(
                order_by=Mock(return_value=Mock(
                    limit=Mock(return_value=Mock(all=Mock(return_value=sample_retirements)))
                ))
            )))
        ]
        
        result = await get_performance_history(
            start_date=None,
            end_date=None,
            event_types=[EventType.STRATEGY_RETIRED],
            limit=100,
            username="testuser",
            db=mock_db_session
        )
        
        # Should have retirement events
        retirement_events = [e for e in result.events if e.type == EventType.STRATEGY_RETIRED]
        assert len(retirement_events) > 0
        
        # Verify retirement event data
        if retirement_events:
            event = retirement_events[0]
            assert "reason" in event.data
            assert "final_sharpe" in event.data


class TestPerformanceEndpointsIntegration:
    """Integration tests for performance endpoints."""
    
    @pytest.mark.asyncio
    async def test_metrics_response_structure(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test that metrics endpoint returns proper structure."""
        from src.api.routers.performance import get_performance_metrics, TimePeriod
        
        mock_strategy_engine.get_active_strategies.return_value = sample_strategies
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {}
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                result = await get_performance_metrics(
                    period=TimePeriod.THREE_MONTHS,
                    strategy_id=None,
                    username="testuser",
                    db=mock_db_session
                )
        
        # Verify all required fields
        assert hasattr(result, 'sharpe')
        assert hasattr(result, 'total_return')
        assert hasattr(result, 'max_drawdown')
        assert hasattr(result, 'win_rate')
        assert hasattr(result, 'portfolio_history')
        assert hasattr(result, 'strategy_contributions')
        assert hasattr(result, 'period')
        assert hasattr(result, 'last_updated')
    
    @pytest.mark.asyncio
    async def test_portfolio_response_structure(self, mock_db_session, mock_strategy_engine, mock_portfolio_manager, sample_strategies):
        """Test that portfolio endpoint returns proper structure."""
        from src.api.routers.performance import get_portfolio_composition
        
        mock_strategy_engine.get_active_strategies.return_value = sample_strategies
        mock_portfolio_manager.calculate_portfolio_metrics.return_value = {}
        
        with patch('src.api.routers.performance._get_strategy_engine', return_value=mock_strategy_engine):
            with patch('src.api.routers.performance._get_portfolio_manager', return_value=mock_portfolio_manager):
                with patch('src.api.routers.performance._get_correlation_analyzer'):
                    result = await get_portfolio_composition(
                        username="testuser",
                        db=mock_db_session
                    )
        
        # Verify all required fields
        assert hasattr(result, 'strategies')
        assert hasattr(result, 'correlation_matrix')
        assert hasattr(result, 'risk_metrics')
        assert hasattr(result, 'total_value')
        assert hasattr(result, 'last_updated')
    
    @pytest.mark.asyncio
    async def test_history_response_structure(self, mock_db_session):
        """Test that history endpoint returns proper structure."""
        from src.api.routers.performance import get_performance_history
        
        # Setup empty mock query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        
        mock_db_session.query.return_value = mock_query
        
        result = await get_performance_history(
            start_date=None,
            end_date=None,
            event_types=None,
            limit=100,
            username="testuser",
            db=mock_db_session
        )
        
        # Verify all required fields
        assert hasattr(result, 'events')
        assert hasattr(result, 'total')
        assert hasattr(result, 'start_date')
        assert hasattr(result, 'end_date')




class TestHistoryAnalyticsEndpoint:
    """Tests for GET /api/performance/history endpoint with analytics."""
    
    @pytest.mark.asyncio
    async def test_get_history_analytics_default_period(self, mock_db_session, sample_proposals, sample_retirements):
        """Test fetching history analytics with default period."""
        from src.api.routers.performance import get_performance_history
        
        # Setup mock query - return actual proposal/retirement objects
        proposals_query = Mock()
        proposals_query.filter.return_value = proposals_query
        proposals_query.order_by.return_value = proposals_query
        proposals_query.limit.return_value = proposals_query
        proposals_query.all.return_value = sample_proposals
        
        retirements_query = Mock()
        retirements_query.filter.return_value = retirements_query
        retirements_query.order_by.return_value = retirements_query
        retirements_query.limit.return_value = retirements_query
        retirements_query.all.return_value = sample_retirements
        
        # First call returns proposals query, second returns retirements query
        mock_db_session.query.side_effect = [proposals_query, retirements_query]
        
        result = await get_performance_history(
            period="1M",
            username="testuser",
            db=mock_db_session
        )
        
        # Verify response structure
        assert hasattr(result, 'events')
        assert hasattr(result, 'template_performance')
        assert hasattr(result, 'regime_analysis')
        assert hasattr(result, 'last_updated')
        
        # Verify events
        assert isinstance(result.events, list)
        
        # Verify template performance
        assert isinstance(result.template_performance, list)
        assert len(result.template_performance) > 0
        
        # Verify regime analysis
        assert isinstance(result.regime_analysis, list)
        assert len(result.regime_analysis) > 0
    
    @pytest.mark.asyncio
    async def test_get_history_analytics_template_stats(self, mock_db_session, sample_proposals):
        """Test template performance statistics calculation."""
        from src.api.routers.performance import get_performance_history
        
        # Setup mock query
        proposals_query = Mock()
        proposals_query.filter.return_value = proposals_query
        proposals_query.order_by.return_value = proposals_query
        proposals_query.limit.return_value = proposals_query
        proposals_query.all.return_value = sample_proposals
        
        retirements_query = Mock()
        retirements_query.filter.return_value = retirements_query
        retirements_query.order_by.return_value = retirements_query
        retirements_query.limit.return_value = retirements_query
        retirements_query.all.return_value = []
        
        mock_db_session.query.side_effect = [proposals_query, retirements_query]
        
        result = await get_performance_history(
            period="1W",
            username="testuser",
            db=mock_db_session
        )
        
        # Verify template performance structure
        if result.template_performance:
            template = result.template_performance[0]
            assert hasattr(template, 'name')
            assert hasattr(template, 'success_rate')
            assert hasattr(template, 'usage_count')
            assert hasattr(template, 'avg_sharpe')
            assert hasattr(template, 'avg_return')
            assert hasattr(template, 'avg_drawdown')
    
    @pytest.mark.asyncio
    async def test_get_history_analytics_regime_stats(self, mock_db_session, sample_proposals):
        """Test regime analysis statistics calculation."""
        from src.api.routers.performance import get_performance_history
        
        # Setup mock query
        proposals_query = Mock()
        proposals_query.filter.return_value = proposals_query
        proposals_query.order_by.return_value = proposals_query
        proposals_query.limit.return_value = proposals_query
        proposals_query.all.return_value = sample_proposals
        
        retirements_query = Mock()
        retirements_query.filter.return_value = retirements_query
        retirements_query.order_by.return_value = retirements_query
        retirements_query.limit.return_value = retirements_query
        retirements_query.all.return_value = []
        
        mock_db_session.query.side_effect = [proposals_query, retirements_query]
        
        result = await get_performance_history(
            period="1D",
            username="testuser",
            db=mock_db_session
        )
        
        # Verify regime analysis structure
        if result.regime_analysis:
            regime = result.regime_analysis[0]
            assert hasattr(regime, 'regime')
            assert hasattr(regime, 'strategy_count')
            assert hasattr(regime, 'avg_sharpe')
            assert hasattr(regime, 'avg_return')
            assert hasattr(regime, 'win_rate')
