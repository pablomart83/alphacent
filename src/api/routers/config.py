"""
Configuration endpoints for AlphaCent Trading Platform.

Provides endpoints for managing configuration and API credentials.
Validates: Requirements 2.1, 2.6
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.config import Configuration, ConfigurationError
from src.models.enums import TradingMode
from src.models.dataclasses import RiskConfig
from src.api.dependencies import get_configuration, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["configuration"])


class CredentialsRequest(BaseModel):
    """API credentials request model."""
    mode: TradingMode
    public_key: str = Field(..., min_length=1)
    user_key: str = Field(..., min_length=1)


class CredentialsResponse(BaseModel):
    """API credentials response model."""
    success: bool
    message: str


class ConnectionStatusResponse(BaseModel):
    """Connection status response model."""
    connected: bool
    mode: Optional[TradingMode] = None
    message: str


class RiskConfigRequest(BaseModel):
    """Risk configuration request model."""
    mode: TradingMode
    max_position_size_pct: float = Field(ge=0.0, le=1.0)
    max_exposure_pct: float = Field(ge=0.0, le=1.0)
    max_daily_loss_pct: float = Field(ge=0.0, le=1.0)
    max_drawdown_pct: float = Field(ge=0.0, le=1.0)
    position_risk_pct: float = Field(ge=0.0, le=1.0)
    stop_loss_pct: float = Field(ge=0.0, le=1.0)
    take_profit_pct: float = Field(ge=0.0, le=1.0)
    # Position Management fields
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_activation_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
    trailing_stop_distance_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
    partial_exit_enabled: Optional[bool] = None
    partial_exit_levels: Optional[List[Dict[str, float]]] = None
    correlation_adjustment_enabled: Optional[bool] = None
    correlation_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    correlation_reduction_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    regime_based_sizing_enabled: Optional[bool] = None
    regime_multipliers: Optional[Dict[str, float]] = None
    cancel_stale_orders: Optional[bool] = None
    stale_order_hours: Optional[int] = Field(None, ge=1, le=168)


class RiskConfigResponse(BaseModel):
    """Risk configuration response model."""
    mode: TradingMode
    max_position_size_pct: float
    max_exposure_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    position_risk_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    # Position Management fields
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_activation_pct: Optional[float] = None
    trailing_stop_distance_pct: Optional[float] = None
    partial_exit_enabled: Optional[bool] = None
    partial_exit_levels: Optional[List[Dict[str, float]]] = None
    correlation_adjustment_enabled: Optional[bool] = None
    correlation_threshold: Optional[float] = None
    correlation_reduction_factor: Optional[float] = None
    regime_based_sizing_enabled: Optional[bool] = None
    regime_multipliers: Optional[Dict[str, float]] = None
    cancel_stale_orders: Optional[bool] = None
    stale_order_hours: Optional[int] = None


class AppConfigResponse(BaseModel):
    """Application configuration response model."""
    config: Dict[str, Any]


class AppConfigRequest(BaseModel):
    """Application configuration request model."""
    config: Dict[str, Any]


@router.post("/credentials", response_model=CredentialsResponse)
async def set_credentials(
    request: CredentialsRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Set API credentials for trading mode.
    
    Args:
        request: Credentials to save
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Success response
        
    Validates: Requirement 2.1
    """
    logger.info(f"Setting credentials for {request.mode.value} mode by user {username}")
    
    try:
        config.save_credentials(
            mode=request.mode,
            public_key=request.public_key,
            user_key=request.user_key
        )
        
        logger.info(f"Credentials saved for {request.mode.value} mode")
        
        return CredentialsResponse(
            success=True,
            message=f"Credentials saved for {request.mode.value} mode"
        )
    
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {str(e)}"
        )


@router.get("/connection-status", response_model=ConnectionStatusResponse)
async def get_connection_status(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get eToro API connection status.
    
    Args:
        mode: Trading mode to check
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Connection status
        
    Validates: Requirement 2.6
    """
    logger.info(f"Checking connection status for {mode.value} mode")
    
    # Check if credentials exist
    has_credentials = config.validate_credentials(mode)
    
    if not has_credentials:
        return ConnectionStatusResponse(
            connected=False,
            mode=mode,
            message="No credentials configured"
        )
    
    # Test connection to eToro API
    try:
        from src.api.etoro_client import EToroAPIClient
        
        # Load credentials for the mode
        credentials = config.load_credentials(mode)
        
        # Initialize eToro client with credentials
        etoro_client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=mode
        )
        
        # Quick connection test — just hit the portfolio endpoint, don't enrich positions.
        # get_account_info() calls get_positions() which fetches live prices for every
        # open position (18+ API calls) — way too slow for a connection check.
        portfolio_endpoint = "/api/v1/trading/info/demo/portfolio" if mode == TradingMode.DEMO else "/api/v1/trading/info/portfolio"
        portfolio_data = etoro_client._make_request(method="GET", endpoint=portfolio_endpoint)
        
        if portfolio_data:
            logger.info(f"Successfully connected to eToro API in {mode.value} mode")
            return ConnectionStatusResponse(
                connected=True,
                mode=mode,
                message="Connected to eToro API"
            )
        else:
            return ConnectionStatusResponse(
                connected=False,
                mode=mode,
                message="Failed to retrieve account info"
            )
    
    except Exception as e:
        logger.error(f"Failed to connect to eToro API: {e}")
        # Return that credentials exist but connection failed
        # This is different from "no credentials configured"
        return ConnectionStatusResponse(
            connected=False,
            mode=mode,
            message=f"Credentials configured but connection test failed: {str(e)[:100]}"
        )


@router.get("/risk", response_model=RiskConfigResponse)
async def get_risk_config(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get risk configuration for trading mode.
    
    Args:
        mode: Trading mode
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Risk configuration
        
    Validates: Requirement 2.1
    """
    logger.info(f"Getting risk config for {mode.value} mode")
    
    # Load risk config from JSON file directly
    import json
    from pathlib import Path
    
    risk_config_file = Path(config.config_dir) / "risk_config.json"
    
    if risk_config_file.exists():
        all_configs = json.loads(risk_config_file.read_text())
        risk_config_dict = all_configs.get(mode.value, {})
    else:
        risk_config_dict = {}
    
    return RiskConfigResponse(
        mode=mode,
        max_position_size_pct=risk_config_dict.get('max_position_size_pct', 0.05),
        max_exposure_pct=risk_config_dict.get('max_exposure_pct', 0.5),
        max_daily_loss_pct=risk_config_dict.get('max_daily_loss_pct', 0.03),
        max_drawdown_pct=risk_config_dict.get('max_drawdown_pct', 0.1),
        position_risk_pct=risk_config_dict.get('position_risk_pct', 0.01),
        stop_loss_pct=risk_config_dict.get('stop_loss_pct', 0.02),
        take_profit_pct=risk_config_dict.get('take_profit_pct', 0.05),
        # Position management fields
        trailing_stop_enabled=risk_config_dict.get('trailing_stop_enabled'),
        trailing_stop_activation_pct=risk_config_dict.get('trailing_stop_activation_pct'),
        trailing_stop_distance_pct=risk_config_dict.get('trailing_stop_distance_pct'),
        partial_exit_enabled=risk_config_dict.get('partial_exit_enabled'),
        partial_exit_levels=risk_config_dict.get('partial_exit_levels'),
        correlation_adjustment_enabled=risk_config_dict.get('correlation_adjustment_enabled'),
        correlation_threshold=risk_config_dict.get('correlation_threshold'),
        correlation_reduction_factor=risk_config_dict.get('correlation_reduction_factor'),
        regime_based_sizing_enabled=risk_config_dict.get('regime_based_sizing_enabled'),
        regime_multipliers=risk_config_dict.get('regime_multipliers'),
        cancel_stale_orders=risk_config_dict.get('cancel_stale_orders'),
        stale_order_hours=risk_config_dict.get('stale_order_hours')
    )


@router.put("/risk", response_model=CredentialsResponse)
async def update_risk_config(
    request: RiskConfigRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Update risk configuration for trading mode.
    
    Args:
        request: Risk configuration to save
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Success response
        
    Validates: Requirement 2.1
    """
    logger.info(f"Updating risk config for {request.mode.value} mode by user {username}")
    
    try:
        # Build risk config dict with all fields
        risk_config_dict = {
            'max_position_size_pct': request.max_position_size_pct,
            'max_exposure_pct': request.max_exposure_pct,
            'max_daily_loss_pct': request.max_daily_loss_pct,
            'max_drawdown_pct': request.max_drawdown_pct,
            'position_risk_pct': request.position_risk_pct,
            'stop_loss_pct': request.stop_loss_pct,
            'take_profit_pct': request.take_profit_pct,
        }
        
        # Add position management fields if provided
        if request.trailing_stop_enabled is not None:
            risk_config_dict['trailing_stop_enabled'] = request.trailing_stop_enabled
        if request.trailing_stop_activation_pct is not None:
            risk_config_dict['trailing_stop_activation_pct'] = request.trailing_stop_activation_pct
        if request.trailing_stop_distance_pct is not None:
            risk_config_dict['trailing_stop_distance_pct'] = request.trailing_stop_distance_pct
        if request.partial_exit_enabled is not None:
            risk_config_dict['partial_exit_enabled'] = request.partial_exit_enabled
        if request.partial_exit_levels is not None:
            risk_config_dict['partial_exit_levels'] = request.partial_exit_levels
        if request.correlation_adjustment_enabled is not None:
            risk_config_dict['correlation_adjustment_enabled'] = request.correlation_adjustment_enabled
        if request.correlation_threshold is not None:
            risk_config_dict['correlation_threshold'] = request.correlation_threshold
        if request.correlation_reduction_factor is not None:
            risk_config_dict['correlation_reduction_factor'] = request.correlation_reduction_factor
        if request.regime_based_sizing_enabled is not None:
            risk_config_dict['regime_based_sizing_enabled'] = request.regime_based_sizing_enabled
        if request.regime_multipliers is not None:
            risk_config_dict['regime_multipliers'] = request.regime_multipliers
        if request.cancel_stale_orders is not None:
            risk_config_dict['cancel_stale_orders'] = request.cancel_stale_orders
        if request.stale_order_hours is not None:
            risk_config_dict['stale_order_hours'] = request.stale_order_hours
        
        # Save to JSON file directly
        import json
        from pathlib import Path
        
        risk_config_file = Path(config.config_dir) / "risk_config.json"
        
        if risk_config_file.exists():
            all_configs = json.loads(risk_config_file.read_text())
        else:
            all_configs = {}
        
        all_configs[request.mode.value] = risk_config_dict
        
        risk_config_file.write_text(json.dumps(all_configs, indent=2))
        
        logger.info(f"Risk config saved for {request.mode.value} mode")
        
        return CredentialsResponse(
            success=True,
            message=f"Risk configuration saved for {request.mode.value} mode"
        )
    
    except Exception as e:
        logger.error(f"Error saving risk config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save risk configuration: {str(e)}"
        )


@router.get("", response_model=AppConfigResponse)
async def get_app_config(
    config: Configuration = Depends(get_configuration),
    username: Optional[str] = Depends(lambda: None)  # Make username optional for public access
):
    """
    Get application configuration.
    
    Args:
        username: Current authenticated user (optional)
        config: Configuration dependency
        
    Returns:
        Application configuration
        
    Validates: Requirement 2.1
    """
    logger.info(f"Getting app config for user {username}")
    
    app_config = config.load_app_config()
    
    return AppConfigResponse(config=app_config)


@router.put("", response_model=CredentialsResponse)
async def update_app_config(
    request: AppConfigRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Update application configuration.
    
    Args:
        request: Configuration to save
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Success response
        
    Validates: Requirement 2.1
    """
    logger.info(f"Updating app config by user {username}")
    
    try:
        config.save_app_config(request.config)
        
        logger.info("App config saved")
        
        return CredentialsResponse(
            success=True,
            message="Application configuration saved"
        )
    
    except Exception as e:
        logger.error(f"Error saving app config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save configuration: {str(e)}"
        )


# ============================================================================
# Alpha Edge Settings Endpoints
# ============================================================================

class AlphaEdgeSettingsResponse(BaseModel):
    """Alpha Edge settings response model."""
    # Fundamental filters
    fundamental_filters_enabled: bool
    fundamental_min_checks_passed: int
    fundamental_checks: Dict[str, bool]
    
    # ML filter
    ml_filter_enabled: bool
    ml_min_confidence: float
    ml_retrain_frequency_days: int
    
    # Trading frequency
    max_active_strategies: int
    min_conviction_score: int
    min_holding_period_days: int
    max_trades_per_strategy_per_month: int
    
    # Strategy templates
    earnings_momentum_enabled: bool
    sector_rotation_enabled: bool
    quality_mean_reversion_enabled: bool


class AlphaEdgeSettingsRequest(BaseModel):
    """Alpha Edge settings request model."""
    # Fundamental filters
    fundamental_filters_enabled: Optional[bool] = None
    fundamental_min_checks_passed: Optional[int] = Field(None, ge=1, le=5)
    fundamental_checks: Optional[Dict[str, bool]] = None
    
    # ML filter
    ml_filter_enabled: Optional[bool] = None
    ml_min_confidence: Optional[float] = Field(None, ge=0.5, le=0.95)
    ml_retrain_frequency_days: Optional[int] = Field(None, ge=1, le=90)
    
    # Trading frequency
    max_active_strategies: Optional[int] = Field(None, ge=5, le=20)
    min_conviction_score: Optional[int] = Field(None, ge=50, le=90)
    min_holding_period_days: Optional[int] = Field(None, ge=1, le=30)
    max_trades_per_strategy_per_month: Optional[int] = Field(None, ge=1, le=10)
    
    # Strategy templates
    earnings_momentum_enabled: Optional[bool] = None
    sector_rotation_enabled: Optional[bool] = None
    quality_mean_reversion_enabled: Optional[bool] = None


class ApiUsageResponse(BaseModel):
    """API usage statistics response model."""
    fmp_usage: Dict[str, Any]
    alpha_vantage_usage: Dict[str, Any]
    cache_stats: Dict[str, Any]


@router.get("/alpha-edge", response_model=AlphaEdgeSettingsResponse)
async def get_alpha_edge_settings(
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get Alpha Edge configuration settings.
    
    Args:
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Alpha Edge settings
    """
    logger.info(f"Getting Alpha Edge settings for user {username}")
    
    try:
        # Load autonomous trading config
        import yaml
        from pathlib import Path
        
        config_file = Path(config.config_dir) / "autonomous_trading.yaml"
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                full_config = yaml.safe_load(f)
        else:
            full_config = {}
        
        alpha_edge = full_config.get('alpha_edge', {})
        
        return AlphaEdgeSettingsResponse(
            # Fundamental filters
            fundamental_filters_enabled=alpha_edge.get('fundamental_filters', {}).get('enabled', True),
            fundamental_min_checks_passed=alpha_edge.get('fundamental_filters', {}).get('min_checks_passed', 4),
            fundamental_checks=alpha_edge.get('fundamental_filters', {}).get('checks', {
                'profitable': True,
                'growing': True,
                'reasonable_valuation': True,
                'no_dilution': True,
                'insider_buying': True
            }),
            
            # ML filter
            ml_filter_enabled=alpha_edge.get('ml_filter', {}).get('enabled', True),
            ml_min_confidence=alpha_edge.get('ml_filter', {}).get('min_confidence', 0.70),
            ml_retrain_frequency_days=alpha_edge.get('ml_filter', {}).get('retrain_frequency_days', 30),
            
            # Trading frequency
            max_active_strategies=alpha_edge.get('max_active_strategies', 10),
            min_conviction_score=alpha_edge.get('min_conviction_score', 70),
            min_holding_period_days=alpha_edge.get('min_holding_period_days', 7),
            max_trades_per_strategy_per_month=alpha_edge.get('max_trades_per_strategy_per_month', 4),
            
            # Strategy templates
            earnings_momentum_enabled=alpha_edge.get('earnings_momentum', {}).get('enabled', False),
            sector_rotation_enabled=alpha_edge.get('sector_rotation', {}).get('enabled', False),
            quality_mean_reversion_enabled=alpha_edge.get('quality_mean_reversion', {}).get('enabled', False)
        )
    
    except Exception as e:
        logger.error(f"Error loading Alpha Edge settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load Alpha Edge settings: {str(e)}"
        )


@router.put("/alpha-edge", response_model=CredentialsResponse)
async def update_alpha_edge_settings(
    request: AlphaEdgeSettingsRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Update Alpha Edge configuration settings.
    
    Args:
        request: Alpha Edge settings to save
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        Success response
    """
    logger.info(f"Updating Alpha Edge settings by user {username}")
    
    try:
        # Load autonomous trading config
        import yaml
        from pathlib import Path
        
        config_file = Path(config.config_dir) / "autonomous_trading.yaml"
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                full_config = yaml.safe_load(f)
        else:
            full_config = {}
        
        # Ensure alpha_edge section exists
        if 'alpha_edge' not in full_config:
            full_config['alpha_edge'] = {}
        
        alpha_edge = full_config['alpha_edge']
        
        # Update fundamental filters
        if request.fundamental_filters_enabled is not None:
            if 'fundamental_filters' not in alpha_edge:
                alpha_edge['fundamental_filters'] = {}
            alpha_edge['fundamental_filters']['enabled'] = request.fundamental_filters_enabled
        
        if request.fundamental_min_checks_passed is not None:
            if 'fundamental_filters' not in alpha_edge:
                alpha_edge['fundamental_filters'] = {}
            alpha_edge['fundamental_filters']['min_checks_passed'] = request.fundamental_min_checks_passed
        
        if request.fundamental_checks is not None:
            if 'fundamental_filters' not in alpha_edge:
                alpha_edge['fundamental_filters'] = {}
            alpha_edge['fundamental_filters']['checks'] = request.fundamental_checks
        
        # Update ML filter
        if request.ml_filter_enabled is not None:
            if 'ml_filter' not in alpha_edge:
                alpha_edge['ml_filter'] = {}
            alpha_edge['ml_filter']['enabled'] = request.ml_filter_enabled
        
        if request.ml_min_confidence is not None:
            if 'ml_filter' not in alpha_edge:
                alpha_edge['ml_filter'] = {}
            alpha_edge['ml_filter']['min_confidence'] = request.ml_min_confidence
        
        if request.ml_retrain_frequency_days is not None:
            if 'ml_filter' not in alpha_edge:
                alpha_edge['ml_filter'] = {}
            alpha_edge['ml_filter']['retrain_frequency_days'] = request.ml_retrain_frequency_days
        
        # Update trading frequency
        if request.max_active_strategies is not None:
            alpha_edge['max_active_strategies'] = request.max_active_strategies
        
        if request.min_conviction_score is not None:
            alpha_edge['min_conviction_score'] = request.min_conviction_score
        
        if request.min_holding_period_days is not None:
            alpha_edge['min_holding_period_days'] = request.min_holding_period_days
        
        if request.max_trades_per_strategy_per_month is not None:
            alpha_edge['max_trades_per_strategy_per_month'] = request.max_trades_per_strategy_per_month
        
        # Update strategy templates
        if request.earnings_momentum_enabled is not None:
            if 'earnings_momentum' not in alpha_edge:
                alpha_edge['earnings_momentum'] = {}
            alpha_edge['earnings_momentum']['enabled'] = request.earnings_momentum_enabled
        
        if request.sector_rotation_enabled is not None:
            if 'sector_rotation' not in alpha_edge:
                alpha_edge['sector_rotation'] = {}
            alpha_edge['sector_rotation']['enabled'] = request.sector_rotation_enabled
        
        if request.quality_mean_reversion_enabled is not None:
            if 'quality_mean_reversion' not in alpha_edge:
                alpha_edge['quality_mean_reversion'] = {}
            alpha_edge['quality_mean_reversion']['enabled'] = request.quality_mean_reversion_enabled
        
        # Save config
        with open(config_file, 'w') as f:
            yaml.dump(full_config, f, default_flow_style=False, sort_keys=False)
        
        logger.info("Alpha Edge settings saved")
        
        return CredentialsResponse(
            success=True,
            message="Alpha Edge settings saved successfully"
        )
    
    except Exception as e:
        logger.error(f"Error saving Alpha Edge settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Alpha Edge settings: {str(e)}"
        )


@router.get("/alpha-edge/api-usage", response_model=ApiUsageResponse)
async def get_api_usage(
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get API usage statistics for Alpha Edge data sources.
    
    Args:
        username: Current authenticated user
        config: Configuration dependency
        
    Returns:
        API usage statistics
    """
    logger.info(f"Getting API usage statistics for user {username}")
    
    try:
        # Try to get usage from FundamentalDataProvider if available
        try:
            from src.data.fundamental_data_provider import FundamentalDataProvider
            import yaml
            from pathlib import Path
            _cfg = {}
            _cfg_path = Path("config/autonomous_trading.yaml")
            if _cfg_path.exists():
                with open(_cfg_path, 'r') as _f:
                    _cfg = yaml.safe_load(_f) or {}
            provider = FundamentalDataProvider(_cfg)
            
            # Get FMP usage
            fmp_usage = {
                'calls_today': provider.fmp_calls_today,
                'limit': 250,
                'percentage': (provider.fmp_calls_today / 250) * 100,
                'remaining': 250 - provider.fmp_calls_today
            }
            
            # Get Alpha Vantage usage
            av_usage = {
                'calls_today': provider.av_calls_today,
                'limit': 500,
                'percentage': (provider.av_calls_today / 500) * 100,
                'remaining': 500 - provider.av_calls_today
            }
            
            # Get cache stats
            cache_stats = {
                'size': len(provider.cache),
                'hit_rate': provider.cache_hits / max(provider.cache_hits + provider.cache_misses, 1) * 100 if hasattr(provider, 'cache_hits') else 0
            }
        
        except Exception as e:
            logger.warning(f"Could not load FundamentalDataProvider: {e}")
            # Return default values if provider not available
            fmp_usage = {
                'calls_today': 0,
                'limit': 250,
                'percentage': 0,
                'remaining': 250
            }
            
            av_usage = {
                'calls_today': 0,
                'limit': 500,
                'percentage': 0,
                'remaining': 500
            }
            
            cache_stats = {
                'size': 0,
                'hit_rate': 0
            }
        
        return ApiUsageResponse(
            fmp_usage=fmp_usage,
            alpha_vantage_usage=av_usage,
            cache_stats=cache_stats
        )
    
    except Exception as e:
        logger.error(f"Error getting API usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get API usage: {str(e)}"
        )


# ============================================================================
# Autonomous Configuration Endpoints
# ============================================================================

class AutonomousConfigResponse(BaseModel):
    """Autonomous trading configuration response."""
    enabled: bool = True
    proposal_count: int = 100
    max_active_strategies: int = 25
    min_active_strategies: int = 10
    watchlist_size: int = 10
    backtested_ttl_cycles: int = 48
    signal_generation_interval: int = 1800
    dynamic_symbol_additions: int = 10
    # Activation thresholds
    min_sharpe: float = 1.0
    min_sharpe_crypto: float = 0.4
    max_drawdown: float = 12.0  # percentage
    min_win_rate: float = 50.0  # percentage
    min_win_rate_crypto: float = 38.0  # percentage
    min_trades: int = 3
    min_trades_alpha_edge: int = 5
    min_trades_dsl: int = 10
    # Retirement thresholds
    retirement_max_sharpe: float = 0.5
    retirement_max_drawdown: float = 15.0  # percentage
    retirement_min_win_rate: float = 40.0  # percentage
    # Portfolio balance
    max_long_exposure_pct: float = 70.0
    max_short_exposure_pct: float = 60.0
    max_sector_exposure_pct: float = 40.0


class AutonomousConfigRequest(BaseModel):
    """Autonomous trading configuration update request."""
    enabled: Optional[bool] = None
    proposal_count: Optional[int] = None
    max_active_strategies: Optional[int] = None
    min_active_strategies: Optional[int] = None
    watchlist_size: Optional[int] = None
    backtested_ttl_cycles: Optional[int] = None
    signal_generation_interval: Optional[int] = None
    dynamic_symbol_additions: Optional[int] = None
    min_sharpe: Optional[float] = None
    min_sharpe_crypto: Optional[float] = None
    max_drawdown: Optional[float] = None
    min_win_rate: Optional[float] = None
    min_win_rate_crypto: Optional[float] = None
    min_trades: Optional[int] = None
    min_trades_alpha_edge: Optional[int] = None
    min_trades_dsl: Optional[int] = None
    retirement_max_sharpe: Optional[float] = None
    retirement_max_drawdown: Optional[float] = None
    retirement_min_win_rate: Optional[float] = None
    max_long_exposure_pct: Optional[float] = None
    max_short_exposure_pct: Optional[float] = None
    max_sector_exposure_pct: Optional[float] = None


@router.get("/autonomous", response_model=AutonomousConfigResponse)
async def get_autonomous_config(
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """Get autonomous trading configuration."""
    import yaml
    from pathlib import Path

    config_file = Path(config.config_dir) / "autonomous_trading.yaml"
    full_config = {}
    if config_file.exists():
        with open(config_file, 'r') as f:
            full_config = yaml.safe_load(f) or {}

    autonomous = full_config.get('autonomous', {})
    activation = full_config.get('activation_thresholds', {})
    retirement = full_config.get('retirement_thresholds', {})
    portfolio_balance = full_config.get('position_management', {}).get('portfolio_balance', {})

    return AutonomousConfigResponse(
        enabled=autonomous.get('enabled', True),
        proposal_count=autonomous.get('proposal_count', 100),
        max_active_strategies=autonomous.get('max_active_strategies', 25),
        min_active_strategies=autonomous.get('min_active_strategies', 10),
        watchlist_size=autonomous.get('watchlist_size', 10),
        backtested_ttl_cycles=autonomous.get('backtested_ttl_cycles', 48),
        signal_generation_interval=1800,  # From trading scheduler default
        dynamic_symbol_additions=full_config.get('signal_generation', {}).get('dynamic_symbol_additions', 10),
        min_sharpe=activation.get('min_sharpe', 1.0),
        min_sharpe_crypto=activation.get('min_sharpe_crypto', 0.4),
        max_drawdown=activation.get('max_drawdown', 0.12) * 100,  # Convert to percentage
        min_win_rate=activation.get('min_win_rate', 0.5) * 100,  # Convert to percentage
        min_win_rate_crypto=activation.get('min_win_rate_crypto', 0.38) * 100,
        min_trades=activation.get('min_trades', 3),
        min_trades_alpha_edge=activation.get('min_trades_alpha_edge', 5),
        min_trades_dsl=activation.get('min_trades_dsl', 10),
        retirement_max_sharpe=retirement.get('max_sharpe', 0.5),
        retirement_max_drawdown=retirement.get('max_drawdown', 0.15) * 100,
        retirement_min_win_rate=retirement.get('min_win_rate', 0.4) * 100,
        max_long_exposure_pct=portfolio_balance.get('max_directional_exposure_pct', 0.7) * 100,
        max_short_exposure_pct=portfolio_balance.get('max_directional_exposure_pct', 0.6) * 100,
        max_sector_exposure_pct=portfolio_balance.get('max_sector_exposure_pct', 0.4) * 100,
    )


@router.put("/autonomous", response_model=CredentialsResponse)
async def update_autonomous_config(
    request: AutonomousConfigRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """Update autonomous trading configuration."""
    import yaml
    from pathlib import Path

    config_file = Path(config.config_dir) / "autonomous_trading.yaml"
    full_config = {}
    if config_file.exists():
        with open(config_file, 'r') as f:
            full_config = yaml.safe_load(f) or {}

    # Update autonomous section
    if 'autonomous' not in full_config:
        full_config['autonomous'] = {}
    if request.enabled is not None:
        full_config['autonomous']['enabled'] = request.enabled
    if request.proposal_count is not None:
        full_config['autonomous']['proposal_count'] = request.proposal_count
    if request.max_active_strategies is not None:
        full_config['autonomous']['max_active_strategies'] = request.max_active_strategies
    if request.min_active_strategies is not None:
        full_config['autonomous']['min_active_strategies'] = request.min_active_strategies
    if request.watchlist_size is not None:
        full_config['autonomous']['watchlist_size'] = request.watchlist_size
    if request.backtested_ttl_cycles is not None:
        full_config['autonomous']['backtested_ttl_cycles'] = request.backtested_ttl_cycles

    # Update dynamic_symbol_additions in signal_generation section
    if request.dynamic_symbol_additions is not None:
        if 'signal_generation' not in full_config:
            full_config['signal_generation'] = {}
        full_config['signal_generation']['dynamic_symbol_additions'] = request.dynamic_symbol_additions

    # Update activation thresholds
    if 'activation_thresholds' not in full_config:
        full_config['activation_thresholds'] = {}
    if request.min_sharpe is not None:
        full_config['activation_thresholds']['min_sharpe'] = request.min_sharpe
    if request.min_sharpe_crypto is not None:
        full_config['activation_thresholds']['min_sharpe_crypto'] = request.min_sharpe_crypto
    if request.max_drawdown is not None:
        full_config['activation_thresholds']['max_drawdown'] = request.max_drawdown / 100  # Convert to decimal
    if request.min_win_rate is not None:
        full_config['activation_thresholds']['min_win_rate'] = request.min_win_rate / 100
    if request.min_win_rate_crypto is not None:
        full_config['activation_thresholds']['min_win_rate_crypto'] = request.min_win_rate_crypto / 100
    if request.min_trades is not None:
        full_config['activation_thresholds']['min_trades'] = request.min_trades
    if request.min_trades_alpha_edge is not None:
        full_config['activation_thresholds']['min_trades_alpha_edge'] = request.min_trades_alpha_edge
    if request.min_trades_dsl is not None:
        full_config['activation_thresholds']['min_trades_dsl'] = request.min_trades_dsl

    # Update retirement thresholds
    if 'retirement_thresholds' not in full_config:
        full_config['retirement_thresholds'] = {}
    if request.retirement_max_sharpe is not None:
        full_config['retirement_thresholds']['max_sharpe'] = request.retirement_max_sharpe
    if request.retirement_max_drawdown is not None:
        full_config['retirement_thresholds']['max_drawdown'] = request.retirement_max_drawdown / 100
    if request.retirement_min_win_rate is not None:
        full_config['retirement_thresholds']['min_win_rate'] = request.retirement_min_win_rate / 100

    # Update portfolio balance
    if request.max_long_exposure_pct is not None or request.max_short_exposure_pct is not None or request.max_sector_exposure_pct is not None:
        if 'position_management' not in full_config:
            full_config['position_management'] = {}
        if 'portfolio_balance' not in full_config['position_management']:
            full_config['position_management']['portfolio_balance'] = {}
        pb = full_config['position_management']['portfolio_balance']
        if request.max_long_exposure_pct is not None:
            pb['max_directional_exposure_pct'] = request.max_long_exposure_pct / 100
        if request.max_short_exposure_pct is not None:
            # Note: currently uses same key as long — store separately if needed
            pass  # max_directional_exposure_pct covers both
        if request.max_sector_exposure_pct is not None:
            pb['max_sector_exposure_pct'] = request.max_sector_exposure_pct / 100

    # Save
    with open(config_file, 'w') as f:
        yaml.dump(full_config, f, default_flow_style=False, sort_keys=False)

    return CredentialsResponse(success=True, message="Autonomous configuration updated")

