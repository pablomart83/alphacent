"""
Market data endpoints for AlphaCent Trading Platform.

Provides endpoints for market data and social insights.
Validates: Requirements 11.7, 11.8
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.models.enums import DataSource, TradingMode
from src.api.dependencies import get_current_user, get_configuration
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.core.config import Configuration
from src.utils.symbol_mapper import normalize_symbol, get_display_symbol, get_all_aliases

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


class SymbolAliasResponse(BaseModel):
    """Symbol alias mapping response."""
    aliases: Dict[str, str] = Field(description="Map of user-friendly symbols to eToro format")
    count: int = Field(description="Total number of aliases")


def get_etoro_client(mode: TradingMode, config: Configuration) -> Optional[EToroAPIClient]:
    """Get eToro API client with credentials.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        config: Configuration instance
        
    Returns:
        Authenticated eToro client or None if credentials not configured
    """
    try:
        credentials = config.load_credentials(mode)
        if not credentials:
            logger.warning(f"eToro credentials not configured for {mode.value} mode")
            return None
        
        client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=mode
        )
        
        logger.info(f"eToro client created for {mode.value} mode")
        return client
        
    except Exception as e:
        logger.error(f"Failed to create eToro client: {e}")
        return None


class QuoteResponse(BaseModel):
    """Real-time quote response model."""
    symbol: str
    timestamp: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: float
    change: float
    change_percent: float
    source: DataSource


class HistoricalDataPoint(BaseModel):
    """Historical data point model."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class HistoricalDataResponse(BaseModel):
    """Historical data response model."""
    symbol: str
    interval: str
    data: List[HistoricalDataPoint]
    source: DataSource


class SocialInsightsResponse(BaseModel):
    """Social insights response model."""
    symbol: str
    sentiment_score: float
    trending_rank: Optional[int] = None
    popularity_score: float
    pro_investor_positions: int
    updated_at: str
    metadata: Dict[str, Any]


class SmartPortfolioResponse(BaseModel):
    """Smart Portfolio response model."""
    id: str
    name: str
    description: str
    composition: Dict[str, float]
    performance_1m: float
    performance_3m: float
    performance_1y: float
    risk_rating: int
    min_investment: float
    updated_at: str


class SmartPortfoliosResponse(BaseModel):
    """Smart Portfolios list response model."""
    portfolios: List[SmartPortfolioResponse]
    total_count: int


class TradeableSymbolsResponse(BaseModel):
    """Tradeable symbols response."""
    symbols: List[str] = Field(description="List of tradeable symbols")
    count: int = Field(description="Total number of tradeable symbols")
    mode: str = Field(description="Trading mode (DEMO or LIVE)")
    default_watchlist: List[str] = Field(description="Recommended symbols for watchlist")


class DataQualityIssueResponse(BaseModel):
    """Data quality issue response."""
    issue_type: str
    severity: str
    message: str
    timestamp: str
    details: Optional[Dict[str, Any]] = None


class DataQualityReportResponse(BaseModel):
    """Data quality report response."""
    symbol: str
    timestamp: str
    quality_score: float
    total_points: int
    issues: List[DataQualityIssueResponse]
    metrics: Dict[str, Any]


class AllDataQualityResponse(BaseModel):
    """All data quality reports response."""
    reports: Dict[str, DataQualityReportResponse]
    count: int


@router.get("/data-quality", response_model=AllDataQualityResponse)
async def get_all_data_quality(
    username: str = Depends(get_current_user)
):
    """
    Get data quality reports for all symbols.
    
    Args:
        username: Current authenticated user
        
    Returns:
        Data quality reports for all symbols
    """
    logger.info(f"Getting all data quality reports, user {username}")
    
    from src.core.trading_system import TradingSystem
    
    try:
        # Get trading system instance
        trading_system = TradingSystem.get_instance()
        
        if not trading_system or not trading_system.market_data_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Trading system not initialized"
            )
        
        # Get all quality reports
        reports = trading_system.market_data_manager.get_all_quality_reports()
        
        # Convert to response format
        report_responses = {}
        for symbol, report in reports.items():
            report_responses[symbol] = DataQualityReportResponse(
                symbol=report.symbol,
                timestamp=report.timestamp.isoformat(),
                quality_score=report.quality_score,
                total_points=report.total_points,
                issues=[
                    DataQualityIssueResponse(
                        issue_type=issue.issue_type,
                        severity=issue.severity,
                        message=issue.message,
                        timestamp=issue.timestamp.isoformat(),
                        details=issue.details
                    )
                    for issue in report.issues
                ],
                metrics=report.metrics
            )
        
        return AllDataQualityResponse(
            reports=report_responses,
            count=len(report_responses)
        )
        
    except Exception as e:
        logger.error(f"Error getting data quality reports: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data quality reports: {str(e)}"
        )


@router.get("/data-quality/{symbol}", response_model=DataQualityReportResponse)
async def get_data_quality(
    symbol: str,
    username: str = Depends(get_current_user)
):
    """
    Get data quality report for specific symbol.
    
    Args:
        symbol: Instrument symbol
        username: Current authenticated user
        
    Returns:
        Data quality report for symbol
    """
    # Normalize symbol
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"Getting data quality report for {symbol} (normalized: {normalized_symbol}), user {username}")
    
    from src.core.trading_system import TradingSystem
    
    try:
        # Get trading system instance
        trading_system = TradingSystem.get_instance()
        
        if not trading_system or not trading_system.market_data_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Trading system not initialized"
            )
        
        # Get quality report
        report = trading_system.market_data_manager.get_quality_report(normalized_symbol)
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data quality report available for {symbol}"
            )
        
        # Convert to response format
        return DataQualityReportResponse(
            symbol=report.symbol,
            timestamp=report.timestamp.isoformat(),
            quality_score=report.quality_score,
            total_points=report.total_points,
            issues=[
                DataQualityIssueResponse(
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    message=issue.message,
                    timestamp=issue.timestamp.isoformat(),
                    details=issue.details
                )
                for issue in report.issues
            ],
            metrics=report.metrics
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting data quality report for {normalized_symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data quality report: {str(e)}"
        )


# IMPORTANT: Specific routes must come BEFORE parameterized routes
# Otherwise /{symbol} will match everything

@router.get("/symbol-aliases", response_model=SymbolAliasResponse)
async def get_symbol_aliases(
    username: str = Depends(get_current_user)
):
    """
    Get available symbol aliases.
    
    Returns a mapping of user-friendly symbols (e.g., "BTC") to eToro format (e.g., "BTCUSD").
    Users can use either format when requesting market data.
    
    Args:
        username: Current authenticated user
        
    Returns:
        Dictionary of symbol aliases
    """
    logger.info(f"Getting symbol aliases, user {username}")
    
    aliases = get_all_aliases()
    
    return SymbolAliasResponse(
        aliases=aliases,
        count=len(aliases)
    )


@router.get("/smart-portfolios", response_model=SmartPortfoliosResponse)
async def get_smart_portfolios(
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get available Smart Portfolios.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        List of Smart Portfolios
        
    Validates: Requirement 11.8
    """
    logger.info(f"Getting Smart Portfolios for {mode.value} mode, user {username}")
    
    # Try to get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if etoro_client:
        try:
            # Fetch real Smart Portfolios from eToro
            portfolios = etoro_client.get_smart_portfolios()
            
            portfolio_responses = [
                SmartPortfolioResponse(
                    id=portfolio.id,
                    name=portfolio.name,
                    description=portfolio.description,
                    composition=portfolio.composition,
                    performance_1m=portfolio.performance_1m,
                    performance_3m=portfolio.performance_3m,
                    performance_1y=portfolio.performance_1y,
                    risk_rating=portfolio.risk_rating,
                    min_investment=portfolio.min_investment,
                    updated_at=portfolio.updated_at.isoformat()
                )
                for portfolio in portfolios
            ]
            
            return SmartPortfoliosResponse(
                portfolios=portfolio_responses,
                total_count=len(portfolio_responses)
            )
            
        except EToroAPIError as e:
            logger.error(f"eToro API error for Smart Portfolios: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch Smart Portfolios: eToro API unavailable"
            )
    
    # No eToro client available
    logger.error(f"No eToro client configured for {mode.value} mode")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Smart Portfolios unavailable: eToro credentials not configured for {mode.value} mode"
    )


@router.get("/tradeable-symbols", response_model=TradeableSymbolsResponse)
async def get_tradeable_symbols(
    mode: TradingMode,
    username: str = Depends(get_current_user)
):
    """
    Get list of tradeable symbols for the given trading mode.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        
    Returns:
        List of tradeable symbols and default watchlist
        
    Validates: Requirement 11.7
    """
    logger.info(f"Getting tradeable symbols for {mode.value} mode, user {username}")
    
    from src.core.tradeable_instruments import get_tradeable_symbols, get_default_watchlist
    
    symbols = get_tradeable_symbols(mode)
    watchlist = get_default_watchlist(mode)
    
    return TradeableSymbolsResponse(
        symbols=symbols,
        count=len(symbols),
        mode=mode.value,
        default_watchlist=watchlist
    )


@router.get("/social-insights/{symbol}", response_model=SocialInsightsResponse)
async def get_social_insights(
    symbol: str,
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get social trading insights for symbol.
    
    Args:
        symbol: Instrument symbol
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        Social insights data
        
    Validates: Requirement 11.8
    """
    # Normalize symbol to eToro format
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"Getting social insights for {symbol} (normalized: {normalized_symbol}), user {username}")
    
    # Try to get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if etoro_client:
        try:
            # Fetch real social insights from eToro
            insights = etoro_client.get_social_insights(normalized_symbol)
            
            return SocialInsightsResponse(
                symbol=insights.symbol,
                sentiment_score=insights.sentiment_score,
                trending_rank=insights.trending_rank,
                popularity_score=insights.popularity_score,
                pro_investor_positions=insights.pro_investor_positions,
                updated_at=insights.updated_at.isoformat(),
                metadata=insights.metadata
            )
            
        except EToroAPIError as e:
            logger.error(f"eToro API error for social insights {normalized_symbol}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch social insights for {symbol}: eToro API unavailable"
            )
    
    # No eToro client available
    logger.error(f"No eToro client configured for {mode.value} mode")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Social insights unavailable: eToro credentials not configured for {mode.value} mode"
    )


@router.get("/{symbol}", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get real-time quote for symbol.
    
    Supports both user-friendly symbols (e.g., "BTC") and eToro format (e.g., "BTCUSD").
    
    Args:
        symbol: Instrument symbol (e.g., "AAPL", "BTC", "BTCUSD")
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        Real-time quote
        
    Validates: Requirement 11.7
    """
    # Normalize symbol to eToro format (e.g., BTC -> BTCUSD)
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"Getting quote for {symbol} (normalized: {normalized_symbol}), mode {mode.value}, user {username}")
    
    # Try to get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if etoro_client:
        try:
            # Fetch real market data from eToro
            market_data = etoro_client.get_market_data(normalized_symbol)
            
            # Calculate change (mock for now since we don't have previous close)
            change = 0.0
            change_percent = 0.0
            
            return QuoteResponse(
                symbol=market_data.symbol,
                timestamp=market_data.timestamp.isoformat(),
                price=market_data.close,
                bid=None,  # Not available in current endpoint
                ask=None,  # Not available in current endpoint
                volume=market_data.volume,
                change=change,
                change_percent=change_percent,
                source=market_data.source
            )
            
        except EToroAPIError as e:
            logger.error(f"eToro API error for {normalized_symbol}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch market data for {symbol}: eToro API unavailable"
            )
    
    # No eToro client available
    logger.error(f"No eToro client configured for {mode.value} mode")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Market data service unavailable: eToro credentials not configured for {mode.value} mode"
    )


@router.get("/{symbol}/historical", response_model=HistoricalDataResponse)
async def get_historical_data(
    symbol: str,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get historical data for symbol.
    
    Supports both user-friendly symbols (e.g., "BTC") and eToro format (e.g., "BTCUSD").
    
    Args:
        symbol: Instrument symbol (e.g., "AAPL", "BTC", "BTCUSD")
        interval: Data interval (1m, 5m, 1h, 1d, etc.)
        start: Start date (ISO format)
        end: End date (ISO format)
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        Historical OHLCV data
        
    Validates: Requirement 11.7
    """
    # Normalize symbol to eToro format
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"Getting historical data for {symbol} (normalized: {normalized_symbol}), interval {interval}, user {username}")
    
    # Try to get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if etoro_client:
        try:
            # Parse dates
            start_dt = datetime.fromisoformat(start) if start else datetime.now()
            end_dt = datetime.fromisoformat(end) if end else datetime.now()
            
            # Fetch real historical data from eToro
            historical_data = etoro_client.get_historical_data(
                symbol=normalized_symbol,
                start=start_dt,
                end=end_dt,
                interval=interval
            )
            
            # Convert to response format
            data_points = [
                HistoricalDataPoint(
                    timestamp=md.timestamp.isoformat(),
                    open=md.open,
                    high=md.high,
                    low=md.low,
                    close=md.close,
                    volume=md.volume
                )
                for md in historical_data
            ]
            
            return HistoricalDataResponse(
                symbol=symbol,
                interval=interval,
                data=data_points,
                source=DataSource.ETORO
            )
            
        except EToroAPIError as e:
            logger.error(f"eToro API error for historical data {normalized_symbol}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch historical data for {symbol}: eToro API unavailable"
            )
    
    # No eToro client available
    logger.error(f"No eToro client configured for {mode.value} mode")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Historical data service unavailable: eToro credentials not configured for {mode.value} mode"
    )
