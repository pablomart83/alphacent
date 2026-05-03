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
        
        # Save to JSON file (backup / fallback)
        import json
        from pathlib import Path
        
        risk_config_file = Path(config.config_dir) / "risk_config.json"
        
        if risk_config_file.exists():
            all_configs = json.loads(risk_config_file.read_text())
        else:
            all_configs = {}
        
        all_configs[request.mode.value] = risk_config_dict
        risk_config_file.write_text(json.dumps(all_configs, indent=2))

        # Also persist to database (primary source — load_risk_config reads DB first)
        try:
            from src.models.database import get_database
            from src.models.orm import RiskConfigORM

            db = get_database()
            session = db.get_session()
            try:
                existing = session.query(RiskConfigORM).filter(
                    RiskConfigORM.mode == request.mode
                ).first()
                if existing:
                    existing.max_position_size_pct = request.max_position_size_pct
                    existing.max_exposure_pct = request.max_exposure_pct
                    existing.max_daily_loss_pct = request.max_daily_loss_pct
                    existing.max_drawdown_pct = request.max_drawdown_pct
                    if hasattr(existing, 'position_risk_pct') and request.position_risk_pct is not None:
                        existing.position_risk_pct = request.position_risk_pct
                    if hasattr(existing, 'stop_loss_pct') and request.stop_loss_pct is not None:
                        existing.stop_loss_pct = request.stop_loss_pct
                    if hasattr(existing, 'take_profit_pct') and request.take_profit_pct is not None:
                        existing.take_profit_pct = request.take_profit_pct
                    if request.trailing_stop_enabled is not None:
                        existing.trailing_stop_enabled = int(request.trailing_stop_enabled)
                    if request.trailing_stop_activation_pct is not None:
                        existing.trailing_stop_activation_pct = request.trailing_stop_activation_pct
                    if request.trailing_stop_distance_pct is not None:
                        existing.trailing_stop_distance_pct = request.trailing_stop_distance_pct
                    if request.partial_exit_enabled is not None:
                        existing.partial_exit_enabled = int(request.partial_exit_enabled)
                    if request.partial_exit_levels is not None:
                        existing.partial_exit_levels = request.partial_exit_levels
                    if request.correlation_adjustment_enabled is not None:
                        existing.correlation_adjustment_enabled = int(request.correlation_adjustment_enabled)
                    if request.correlation_threshold is not None:
                        existing.correlation_threshold = request.correlation_threshold
                    if request.correlation_reduction_factor is not None:
                        existing.correlation_reduction_factor = request.correlation_reduction_factor
                    if request.regime_based_sizing_enabled is not None:
                        existing.regime_based_sizing_enabled = int(request.regime_based_sizing_enabled)
                    if request.regime_multipliers is not None:
                        existing.regime_multipliers = request.regime_multipliers
                    if request.cancel_stale_orders is not None:
                        existing.cancel_stale_orders = int(request.cancel_stale_orders)
                    if request.stale_order_hours is not None:
                        existing.stale_order_hours = request.stale_order_hours
                else:
                    session.add(RiskConfigORM(
                        mode=request.mode,
                        max_position_size_pct=request.max_position_size_pct,
                        max_exposure_pct=request.max_exposure_pct,
                        max_daily_loss_pct=request.max_daily_loss_pct,
                        max_drawdown_pct=request.max_drawdown_pct,
                        position_risk_pct=request.position_risk_pct or 0.01,
                        stop_loss_pct=request.stop_loss_pct or 0.03,
                        take_profit_pct=request.take_profit_pct or 0.06,
                        trailing_stop_enabled=int(request.trailing_stop_enabled or False),
                        trailing_stop_activation_pct=request.trailing_stop_activation_pct or 0.05,
                        trailing_stop_distance_pct=request.trailing_stop_distance_pct or 0.03,
                        partial_exit_enabled=int(request.partial_exit_enabled or False),
                        partial_exit_levels=request.partial_exit_levels,
                        correlation_adjustment_enabled=int(request.correlation_adjustment_enabled if request.correlation_adjustment_enabled is not None else True),
                        correlation_threshold=request.correlation_threshold or 0.7,
                        correlation_reduction_factor=request.correlation_reduction_factor or 0.5,
                        regime_based_sizing_enabled=int(request.regime_based_sizing_enabled or False),
                        regime_multipliers=request.regime_multipliers,
                        cancel_stale_orders=int(request.cancel_stale_orders if request.cancel_stale_orders is not None else True),
                        stale_order_hours=request.stale_order_hours or 24,
                    ))
                session.commit()
                logger.info(f"Risk config saved to database for {request.mode.value} mode")
            finally:
                session.close()
        except Exception as db_err:
            logger.warning(f"Failed to save risk config to database: {db_err} — JSON file saved as fallback")

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
            min_conviction_score=alpha_edge.get('min_conviction_score', 57),
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
        # Try to get usage from FundamentalDataProvider singleton
        try:
            from src.data.fundamental_data_provider import get_fundamental_data_provider
            provider = get_fundamental_data_provider()

            if provider:
                # Use the real rate limiter stats
                raw_usage = provider.get_api_usage()
                fmp_raw = raw_usage.get('fmp', {})
                rate_limit = fmp_raw.get('max_calls', 300)
                calls_made = fmp_raw.get('calls_made', 0)
                fmp_usage = {
                    'calls_today': calls_made,
                    'limit': rate_limit,
                    'percentage': round(fmp_raw.get('usage_percent', 0), 1),
                    'remaining': fmp_raw.get('calls_remaining', rate_limit - calls_made),
                }
                cache_size = raw_usage.get('cache_size', 0)
            else:
                raise ValueError("Singleton not registered yet")

            # Alpha Vantage — disabled, always 0
            av_usage = {'calls_today': 0, 'limit': 25, 'percentage': 0, 'remaining': 25}

            cache_stats = {
                'size': cache_size,
                'hit_rate': 0,
            }

        except Exception as e:
            logger.debug(f"Could not load FundamentalDataProvider: {e}")
            fmp_usage = {'calls_today': 0, 'limit': 300, 'percentage': 0, 'remaining': 300}
            av_usage = {'calls_today': 0, 'limit': 25, 'percentage': 0, 'remaining': 25}
            cache_stats = {'size': 0, 'hit_rate': 0}
        
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

# --------------------------------------------------------------------------
# DESIGN NOTE (2026-05-03) — the Autonomous tab of the Settings page is the
# single UI entry point for every operationally-tunable parameter in
# `config/autonomous_trading.yaml`. The response model below exposes two
# categories of field:
#
#   (1) Trading-strategy tuning and portfolio-risk governance — editable.
#       Sharpe / WR / RPT floors, min trades per asset class × interval,
#       direction-aware thresholds, retirement logic, performance
#       feedback weights, directional quotas, adaptive risk bounds, etc.
#
#   (2) Advanced / system plumbing — read-only in `advanced_readonly`.
#       Per-symbol cost model, validation rules, symbol lists,
#       asset-class SL/TP defaults, data source settings. These are
#       visible for audit but must be changed in the yaml directly by ops
#       because editing them from a web UI invites correctness bugs (e.g.
#       changing BTC commission breaks all historical backtests).
#
# Every editable field round-trips through GET/PUT `/config/autonomous`.
# When a yaml key is a percentage (decimal 0.0-1.0 in yaml), the response
# converts to percentage units (0-100) and PUT converts back. When the
# key is already in its natural unit (int trades, int cycles, etc), no
# conversion happens. Comments next to each field document which is which.
#
# Runtime reload — writing the yaml takes effect on the next cycle because
# every code path that reads it re-opens the file fresh at cycle start.
# `autonomous.enabled` toggle and schedule changes may take a service
# restart to pick up cleanly.
# --------------------------------------------------------------------------


class DirectionAwareThreshold(BaseModel):
    """Min return/Sharpe/WR for one direction in one regime bucket."""
    min_return: float = 0.0
    min_sharpe: float = 0.3
    min_win_rate: float = 0.45


class DirectionAwareBucket(BaseModel):
    """Long + short thresholds for one regime bucket."""
    long: DirectionAwareThreshold = DirectionAwareThreshold()
    short: DirectionAwareThreshold = DirectionAwareThreshold()


class DirectionAwareThresholdsBlock(BaseModel):
    """All direction-aware WF thresholds — 5 regime buckets + default.

    Applied by `portfolio_manager.evaluate_for_activation` to relax Sharpe/
    WR per regime × direction so uptrend shorts and ranging longs aren't
    systematically rejected.
    """
    default: DirectionAwareThreshold = DirectionAwareThreshold()
    ranging: DirectionAwareBucket = DirectionAwareBucket()
    trending_up: DirectionAwareBucket = DirectionAwareBucket()
    trending_down: DirectionAwareBucket = DirectionAwareBucket()
    high_vol: DirectionAwareBucket = DirectionAwareBucket()


class DirectionalQuotasBucket(BaseModel):
    """Min long/short exposure ratios in one regime."""
    min_long_pct: float = 0.0
    min_short_pct: float = 0.0


class DirectionalQuotas(BaseModel):
    """Per-regime directional exposure quotas — drives proposer bias toward
    long or short in each regime. Values in percentage units (0-100)."""
    enabled: bool = True
    adjacent_regime_reserve_pct: float = 20.0
    ranging: DirectionalQuotasBucket = DirectionalQuotasBucket()
    ranging_low_vol: DirectionalQuotasBucket = DirectionalQuotasBucket()
    trending_up: DirectionalQuotasBucket = DirectionalQuotasBucket()
    trending_up_weak: DirectionalQuotasBucket = DirectionalQuotasBucket()
    trending_up_strong: DirectionalQuotasBucket = DirectionalQuotasBucket()
    trending_down: DirectionalQuotasBucket = DirectionalQuotasBucket()
    trending_down_weak: DirectionalQuotasBucket = DirectionalQuotasBucket()
    high_volatility: DirectionalQuotasBucket = DirectionalQuotasBucket()


class AdvancedReadonly(BaseModel):
    """Category (3) — read-only view of yaml values that should NOT be
    edited from the Settings UI. Exposed for audit / transparency only.

    Full editing lives in `config/autonomous_trading.yaml` on EC2, edited
    via the normal deployment workflow (scp from EC2 → local → edit → scp
    back → restart).
    """
    transaction_costs_crypto: Dict[str, float] = {}
    transaction_costs_stock: Dict[str, float] = {}
    transaction_costs_etf: Dict[str, float] = {}
    transaction_costs_forex: Dict[str, float] = {}
    transaction_costs_commodity: Dict[str, float] = {}
    transaction_costs_index: Dict[str, float] = {}
    transaction_costs_per_symbol: Dict[str, Dict[str, float]] = {}
    asset_class_parameters: Dict[str, Dict[str, Any]] = {}
    validation_rules: Dict[str, Any] = {}
    symbol_counts: Dict[str, int] = {}
    data_sources: Dict[str, Any] = {}


class AutonomousConfigResponse(BaseModel):
    """Autonomous trading configuration response — full field surface."""

    # ─── Core ──────────────────────────────────────────────────────────
    enabled: bool = True
    proposal_count: int = 100
    max_active_strategies: int = 25
    min_active_strategies: int = 10
    watchlist_size: int = 10
    backtested_ttl_cycles: int = 48
    signal_generation_interval: int = 1800
    dynamic_symbol_additions: int = 10

    # ─── Activation thresholds — Sharpe / WR / DD ──────────────────────
    min_sharpe: float = 1.0
    min_sharpe_crypto: float = 0.3
    min_sharpe_commodity: float = 0.5
    max_drawdown: float = 25.0   # percentage
    min_win_rate: float = 45.0    # percentage
    min_win_rate_crypto: float = 30.0
    min_win_rate_commodity: float = 35.0

    # ─── Activation thresholds — Min Trades (per asset × interval) ────
    min_trades: int = 2
    min_trades_dsl: int = 8
    min_trades_dsl_4h: int = 8
    min_trades_dsl_1h: int = 15
    min_trades_alpha_edge: int = 8
    min_trades_crypto_1d: int = 4
    min_trades_crypto_4h: int = 4
    min_trades_crypto_1h: int = 15
    min_trades_commodity: int = 6

    # ─── Activation thresholds — Min Return Per Trade ─────────────────
    # All values in percentage units (0-100) in the API; yaml stores
    # decimal fractions (0.0-1.0). The conversion happens in handlers.
    min_rpt_stock: float = 0.15
    min_rpt_stock_4h: float = 0.08
    min_rpt_stock_1h: float = 0.03
    min_rpt_etf: float = 0.1
    min_rpt_etf_4h: float = 0.05
    min_rpt_etf_1h: float = 0.02
    min_rpt_forex: float = 0.05
    min_rpt_forex_1h: float = 0.01
    min_rpt_crypto: float = 5.0
    min_rpt_crypto_1d: float = 3.0
    min_rpt_crypto_4h: float = 3.0
    min_rpt_crypto_1h: float = 3.0
    min_rpt_index: float = 0.1
    min_rpt_index_1h: float = 0.02
    min_rpt_commodity: float = 0.15
    min_rpt_commodity_4h: float = 0.08

    # ─── Retirement thresholds + logic ─────────────────────────────────
    retirement_max_sharpe: float = 0.0
    retirement_max_drawdown: float = 31.0   # percentage
    retirement_min_win_rate: float = 28.0    # percentage
    retirement_min_trades_for_evaluation: int = 10
    retirement_min_live_trades: int = 5
    retirement_rolling_window_days: int = 60
    retirement_consecutive_failures: int = 3
    retirement_probation_days: int = 30

    # ─── Walk-Forward + Direction-Aware ────────────────────────────────
    wf_train_days: int = 365
    wf_test_days: int = 180
    direction_aware_thresholds: DirectionAwareThresholdsBlock = DirectionAwareThresholdsBlock()

    # ─── Adaptive Risk (SL/TP bounds) ──────────────────────────────────
    adaptive_risk_enabled: bool = True
    adaptive_min_sl_pct: float = 2.0   # percentage
    adaptive_max_sl_pct: float = 8.0
    adaptive_min_tp_pct: float = 4.0
    adaptive_max_tp_pct: float = 20.0
    adaptive_min_rr_ratio: float = 1.5

    # ─── Performance Feedback ──────────────────────────────────────────
    feedback_lookback_days: int = 60
    feedback_min_trades: int = 5
    feedback_max_weight: float = 1.5
    feedback_min_weight: float = 0.4
    feedback_weight_decay_per_day: float = 0.01

    # ─── Directional Balance + Quotas ──────────────────────────────────
    # Global balance — % of total portfolio that can be long/short
    directional_balance_enabled: bool = True
    directional_min_long_pct: float = 30.0
    directional_max_long_pct: float = 70.0
    directional_min_short_pct: float = 20.0
    directional_max_short_pct: float = 50.0
    # Per-regime quotas — min% long/short per regime
    directional_quotas: DirectionalQuotas = DirectionalQuotas()

    # ─── Portfolio balance / sector caps ────────────────────────────────
    max_long_exposure_pct: float = 70.0
    max_short_exposure_pct: float = 60.0
    max_sector_exposure_pct: float = 40.0

    # ─── Category (3) — read-only audit view ───────────────────────────
    advanced_readonly: AdvancedReadonly = AdvancedReadonly()


class AutonomousConfigRequest(BaseModel):
    """Autonomous trading configuration update request. All fields optional;
    None means "don't touch this yaml key." Matches response schema for
    editable fields only — `advanced_readonly` is GET-only."""

    # Core
    enabled: Optional[bool] = None
    proposal_count: Optional[int] = None
    max_active_strategies: Optional[int] = None
    min_active_strategies: Optional[int] = None
    watchlist_size: Optional[int] = None
    backtested_ttl_cycles: Optional[int] = None
    signal_generation_interval: Optional[int] = None
    dynamic_symbol_additions: Optional[int] = None

    # Activation — Sharpe / WR / DD
    min_sharpe: Optional[float] = None
    min_sharpe_crypto: Optional[float] = None
    min_sharpe_commodity: Optional[float] = None
    max_drawdown: Optional[float] = None
    min_win_rate: Optional[float] = None
    min_win_rate_crypto: Optional[float] = None
    min_win_rate_commodity: Optional[float] = None

    # Activation — Min Trades
    min_trades: Optional[int] = None
    min_trades_dsl: Optional[int] = None
    min_trades_dsl_4h: Optional[int] = None
    min_trades_dsl_1h: Optional[int] = None
    min_trades_alpha_edge: Optional[int] = None
    min_trades_crypto_1d: Optional[int] = None
    min_trades_crypto_4h: Optional[int] = None
    min_trades_crypto_1h: Optional[int] = None
    min_trades_commodity: Optional[int] = None

    # Activation — Min Return Per Trade (in %, API-side; yaml stores decimal)
    min_rpt_stock: Optional[float] = None
    min_rpt_stock_4h: Optional[float] = None
    min_rpt_stock_1h: Optional[float] = None
    min_rpt_etf: Optional[float] = None
    min_rpt_etf_4h: Optional[float] = None
    min_rpt_etf_1h: Optional[float] = None
    min_rpt_forex: Optional[float] = None
    min_rpt_forex_1h: Optional[float] = None
    min_rpt_crypto: Optional[float] = None
    min_rpt_crypto_1d: Optional[float] = None
    min_rpt_crypto_4h: Optional[float] = None
    min_rpt_crypto_1h: Optional[float] = None
    min_rpt_index: Optional[float] = None
    min_rpt_index_1h: Optional[float] = None
    min_rpt_commodity: Optional[float] = None
    min_rpt_commodity_4h: Optional[float] = None

    # Retirement
    retirement_max_sharpe: Optional[float] = None
    retirement_max_drawdown: Optional[float] = None
    retirement_min_win_rate: Optional[float] = None
    retirement_min_trades_for_evaluation: Optional[int] = None
    retirement_min_live_trades: Optional[int] = None
    retirement_rolling_window_days: Optional[int] = None
    retirement_consecutive_failures: Optional[int] = None
    retirement_probation_days: Optional[int] = None

    # Walk-forward + direction-aware
    wf_train_days: Optional[int] = None
    wf_test_days: Optional[int] = None
    direction_aware_thresholds: Optional[DirectionAwareThresholdsBlock] = None

    # Adaptive risk
    adaptive_risk_enabled: Optional[bool] = None
    adaptive_min_sl_pct: Optional[float] = None
    adaptive_max_sl_pct: Optional[float] = None
    adaptive_min_tp_pct: Optional[float] = None
    adaptive_max_tp_pct: Optional[float] = None
    adaptive_min_rr_ratio: Optional[float] = None

    # Performance feedback
    feedback_lookback_days: Optional[int] = None
    feedback_min_trades: Optional[int] = None
    feedback_max_weight: Optional[float] = None
    feedback_min_weight: Optional[float] = None
    feedback_weight_decay_per_day: Optional[float] = None

    # Directional balance + quotas
    directional_balance_enabled: Optional[bool] = None
    directional_min_long_pct: Optional[float] = None
    directional_max_long_pct: Optional[float] = None
    directional_min_short_pct: Optional[float] = None
    directional_max_short_pct: Optional[float] = None
    directional_quotas: Optional[DirectionalQuotas] = None

    # Portfolio balance
    max_long_exposure_pct: Optional[float] = None
    max_short_exposure_pct: Optional[float] = None
    max_sector_exposure_pct: Optional[float] = None


@router.get("/autonomous", response_model=AutonomousConfigResponse)
async def get_autonomous_config(
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """Get autonomous trading configuration.

    Reads from `config/autonomous_trading.yaml` and returns:
    - Every editable parameter (categories 1 + 2 per steering) at top level
    - Read-only audit view of category 3 under `advanced_readonly`
    """
    import yaml
    from pathlib import Path

    config_file = Path(config.config_dir) / "autonomous_trading.yaml"
    full_config: Dict[str, Any] = {}
    if config_file.exists():
        with open(config_file, 'r') as f:
            full_config = yaml.safe_load(f) or {}

    # Extract top-level sections with safe defaults
    autonomous = full_config.get('autonomous', {}) or {}
    activation = full_config.get('activation_thresholds', {}) or {}
    rpt = activation.get('min_return_per_trade', {}) or {}
    retirement = full_config.get('retirement_thresholds', {}) or {}
    ret_logic = full_config.get('retirement_logic', {}) or {}
    signal_gen = full_config.get('signal_generation', {}) or {}
    backtest = full_config.get('backtest', {}) or {}
    wf = backtest.get('walk_forward', {}) or {}
    da = wf.get('direction_aware_thresholds', {}) or {}
    adaptive = backtest.get('adaptive_risk', {}) or {}
    feedback = full_config.get('performance_feedback', {}) or {}
    dir_bal = full_config.get('directional_balance', {}) or {}
    pm = full_config.get('position_management', {}) or {}
    portfolio_balance = pm.get('portfolio_balance', {}) or {}
    dir_quotas = pm.get('directional_quotas', {}) or {}
    tx_costs = backtest.get('transaction_costs', {}) or {}
    tx_per_class = tx_costs.get('per_asset_class', {}) or {}
    tx_per_symbol = tx_costs.get('per_symbol', {}) or {}
    asset_class_params = full_config.get('asset_class_parameters', {}) or {}
    validation = full_config.get('validation_rules', {}) or {}
    symbols = full_config.get('symbols', {}) or {}
    data_sources = full_config.get('data_sources', {}) or {}

    # Helper: yaml decimal fraction (0-1) → API percentage (0-100)
    def pct(val, default=0.0):
        """Convert decimal fraction to percentage. Fail-open to default."""
        try:
            return float(val) * 100 if val is not None else default
        except (TypeError, ValueError):
            return default

    # Helper: build DirectionAwareThreshold from yaml dict
    def da_threshold(src: Dict[str, Any]) -> DirectionAwareThreshold:
        return DirectionAwareThreshold(
            min_return=float(src.get('min_return', 0.0) or 0.0),
            min_sharpe=float(src.get('min_sharpe', 0.3) or 0.3),
            min_win_rate=float(src.get('min_win_rate', 0.45) or 0.45),
        )

    def da_bucket(src: Dict[str, Any]) -> DirectionAwareBucket:
        return DirectionAwareBucket(
            long=da_threshold(src.get('long', {}) or {}),
            short=da_threshold(src.get('short', {}) or {}),
        )

    # Helper: build DirectionalQuotasBucket (yaml: decimal, API: percentage)
    def dq_bucket(src: Dict[str, Any]) -> DirectionalQuotasBucket:
        return DirectionalQuotasBucket(
            min_long_pct=pct(src.get('min_long_pct'), 0.0),
            min_short_pct=pct(src.get('min_short_pct'), 0.0),
        )

    return AutonomousConfigResponse(
        # Core
        enabled=bool(autonomous.get('enabled', True)),
        proposal_count=int(autonomous.get('proposal_count', 100)),
        max_active_strategies=int(autonomous.get('max_active_strategies', 25)),
        min_active_strategies=int(autonomous.get('min_active_strategies', 10)),
        watchlist_size=int(autonomous.get('watchlist_size', 10)),
        backtested_ttl_cycles=int(autonomous.get('backtested_ttl_cycles', 48)),
        signal_generation_interval=int(signal_gen.get('interval_seconds', 1800)),
        dynamic_symbol_additions=int(signal_gen.get('dynamic_symbol_additions', 10)),

        # Activation — Sharpe / WR / DD
        min_sharpe=float(activation.get('min_sharpe', 1.0)),
        min_sharpe_crypto=float(activation.get('min_sharpe_crypto', 0.3)),
        min_sharpe_commodity=float(activation.get('min_sharpe_commodity', 0.5)),
        max_drawdown=pct(activation.get('max_drawdown'), 25.0),
        min_win_rate=pct(activation.get('min_win_rate'), 45.0),
        min_win_rate_crypto=pct(activation.get('min_win_rate_crypto'), 30.0),
        min_win_rate_commodity=pct(activation.get('min_win_rate_commodity'), 35.0),

        # Activation — Min Trades
        min_trades=int(activation.get('min_trades', 2)),
        min_trades_dsl=int(activation.get('min_trades_dsl', 8)),
        min_trades_dsl_4h=int(activation.get('min_trades_dsl_4h', 8)),
        min_trades_dsl_1h=int(activation.get('min_trades_dsl_1h', 15)),
        min_trades_alpha_edge=int(activation.get('min_trades_alpha_edge', 8)),
        min_trades_crypto_1d=int(activation.get('min_trades_crypto_1d', 4)),
        min_trades_crypto_4h=int(activation.get('min_trades_crypto_4h', 4)),
        min_trades_crypto_1h=int(activation.get('min_trades_crypto_1h', 15)),
        min_trades_commodity=int(activation.get('min_trades_commodity', 6)),

        # Activation — Min Return Per Trade (yaml decimal → API pct)
        min_rpt_stock=pct(rpt.get('stock'), 0.15),
        min_rpt_stock_4h=pct(rpt.get('stock_4h'), 0.08),
        min_rpt_stock_1h=pct(rpt.get('stock_1h'), 0.03),
        min_rpt_etf=pct(rpt.get('etf'), 0.1),
        min_rpt_etf_4h=pct(rpt.get('etf_4h'), 0.05),
        min_rpt_etf_1h=pct(rpt.get('etf_1h'), 0.02),
        min_rpt_forex=pct(rpt.get('forex'), 0.05),
        min_rpt_forex_1h=pct(rpt.get('forex_1h'), 0.01),
        min_rpt_crypto=pct(rpt.get('crypto'), 5.0),
        min_rpt_crypto_1d=pct(rpt.get('crypto_1d'), 3.0),
        min_rpt_crypto_4h=pct(rpt.get('crypto_4h'), 3.0),
        min_rpt_crypto_1h=pct(rpt.get('crypto_1h'), 3.0),
        min_rpt_index=pct(rpt.get('index'), 0.1),
        min_rpt_index_1h=pct(rpt.get('index_1h'), 0.02),
        min_rpt_commodity=pct(rpt.get('commodity'), 0.15),
        min_rpt_commodity_4h=pct(rpt.get('commodity_4h'), 0.08),

        # Retirement + retirement_logic
        retirement_max_sharpe=float(retirement.get('max_sharpe', 0.0)),
        retirement_max_drawdown=pct(retirement.get('max_drawdown'), 31.0),
        retirement_min_win_rate=pct(retirement.get('min_win_rate'), 28.0),
        retirement_min_trades_for_evaluation=int(retirement.get('min_trades_for_evaluation', 10)),
        retirement_min_live_trades=int(ret_logic.get('min_live_trades_before_evaluation', 5)),
        retirement_rolling_window_days=int(ret_logic.get('rolling_window_days', 60)),
        retirement_consecutive_failures=int(ret_logic.get('consecutive_failures_required', 3)),
        retirement_probation_days=int(ret_logic.get('probation_period_days', 30)),

        # Walk-forward + direction-aware
        wf_train_days=int(wf.get('train_days', 365)),
        wf_test_days=int(wf.get('test_days', 180)),
        direction_aware_thresholds=DirectionAwareThresholdsBlock(
            default=da_threshold(da.get('default', {}) or {}),
            ranging=da_bucket(da.get('ranging', {}) or {}),
            trending_up=da_bucket(da.get('trending_up', {}) or {}),
            trending_down=da_bucket(da.get('trending_down', {}) or {}),
            high_vol=da_bucket(da.get('high_vol', {}) or {}),
        ),

        # Adaptive risk (SL/TP bounds)
        adaptive_risk_enabled=bool(adaptive.get('enabled', True)),
        adaptive_min_sl_pct=pct(adaptive.get('min_sl_pct'), 2.0),
        adaptive_max_sl_pct=pct(adaptive.get('max_sl_pct'), 8.0),
        adaptive_min_tp_pct=pct(adaptive.get('min_tp_pct'), 4.0),
        adaptive_max_tp_pct=pct(adaptive.get('max_tp_pct'), 20.0),
        adaptive_min_rr_ratio=float(adaptive.get('min_reward_risk_ratio', 1.5)),

        # Performance feedback
        feedback_lookback_days=int(feedback.get('feedback_lookback_days', 60)),
        feedback_min_trades=int(feedback.get('min_trades_for_feedback', 5)),
        feedback_max_weight=float(feedback.get('max_weight_adjustment', 1.5)),
        feedback_min_weight=float(feedback.get('min_weight_adjustment', 0.4)),
        feedback_weight_decay_per_day=float(feedback.get('weight_decay_per_day', 0.01)),

        # Directional balance + quotas
        directional_balance_enabled=bool(dir_bal.get('enabled', True)),
        directional_min_long_pct=float(dir_bal.get('min_long_pct', 30.0)),
        directional_max_long_pct=float(dir_bal.get('max_long_pct', 70.0)),
        directional_min_short_pct=float(dir_bal.get('min_short_pct', 20.0)),
        directional_max_short_pct=float(dir_bal.get('max_short_pct', 50.0)),
        directional_quotas=DirectionalQuotas(
            enabled=bool(dir_quotas.get('enabled', True)),
            adjacent_regime_reserve_pct=pct(dir_quotas.get('adjacent_regime_reserve_pct'), 20.0),
            ranging=dq_bucket(dir_quotas.get('ranging', {}) or {}),
            ranging_low_vol=dq_bucket(dir_quotas.get('ranging_low_vol', {}) or {}),
            trending_up=dq_bucket(dir_quotas.get('trending_up', {}) or {}),
            trending_up_weak=dq_bucket(dir_quotas.get('trending_up_weak', {}) or {}),
            trending_up_strong=dq_bucket(dir_quotas.get('trending_up_strong', {}) or {}),
            trending_down=dq_bucket(dir_quotas.get('trending_down', {}) or {}),
            trending_down_weak=dq_bucket(dir_quotas.get('trending_down_weak', {}) or {}),
            high_volatility=dq_bucket(dir_quotas.get('high_volatility', {}) or {}),
        ),

        # Portfolio balance
        max_long_exposure_pct=pct(portfolio_balance.get('max_directional_exposure_pct'), 70.0),
        max_short_exposure_pct=pct(portfolio_balance.get('max_directional_exposure_pct'), 60.0),
        max_sector_exposure_pct=pct(portfolio_balance.get('max_sector_exposure_pct'), 40.0),

        # Read-only audit view
        advanced_readonly=AdvancedReadonly(
            transaction_costs_crypto=tx_per_class.get('crypto', {}) or {},
            transaction_costs_stock=tx_per_class.get('stock', {}) or {},
            transaction_costs_etf=tx_per_class.get('etf', {}) or {},
            transaction_costs_forex=tx_per_class.get('forex', {}) or {},
            transaction_costs_commodity=tx_per_class.get('commodity', {}) or {},
            transaction_costs_index=tx_per_class.get('index', {}) or {},
            transaction_costs_per_symbol=tx_per_symbol,
            asset_class_parameters=asset_class_params,
            validation_rules=validation,
            symbol_counts={k: len(v) if isinstance(v, list) else 0 for k, v in symbols.items()},
            data_sources={
                k: {'enabled': v.get('enabled', False), 'cache_duration': v.get('cache_duration')}
                for k, v in data_sources.items() if isinstance(v, dict)
            },
        ),
    )


@router.put("/autonomous", response_model=CredentialsResponse)
async def update_autonomous_config(
    request: AutonomousConfigRequest,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """Update autonomous trading configuration. Only fields present in
    the request are updated — None means "leave yaml key unchanged"."""
    import yaml
    from pathlib import Path

    config_file = Path(config.config_dir) / "autonomous_trading.yaml"
    full_config: Dict[str, Any] = {}
    if config_file.exists():
        with open(config_file, 'r') as f:
            full_config = yaml.safe_load(f) or {}

    # Ensure top-level sections exist
    for section in ('autonomous', 'activation_thresholds', 'retirement_thresholds',
                    'retirement_logic', 'signal_generation', 'backtest',
                    'performance_feedback', 'directional_balance',
                    'position_management'):
        full_config.setdefault(section, {})
    full_config['backtest'].setdefault('walk_forward', {})
    full_config['backtest']['walk_forward'].setdefault('direction_aware_thresholds', {})
    full_config['backtest'].setdefault('adaptive_risk', {})
    full_config['activation_thresholds'].setdefault('min_return_per_trade', {})
    full_config['position_management'].setdefault('portfolio_balance', {})
    full_config['position_management'].setdefault('directional_quotas', {})

    # Shortcuts
    a = full_config['autonomous']
    act = full_config['activation_thresholds']
    rpt = act['min_return_per_trade']
    ret = full_config['retirement_thresholds']
    retl = full_config['retirement_logic']
    sg = full_config['signal_generation']
    bt = full_config['backtest']
    wf = bt['walk_forward']
    da = wf['direction_aware_thresholds']
    ar = bt['adaptive_risk']
    pf = full_config['performance_feedback']
    db = full_config['directional_balance']
    pm = full_config['position_management']
    pb = pm['portfolio_balance']
    dq = pm['directional_quotas']

    # Helper: percentage (API) → decimal fraction (yaml)
    def to_frac(v):
        return float(v) / 100 if v is not None else None

    # ─── Core ──────────────────────────────────────────────────────────
    if request.enabled is not None: a['enabled'] = request.enabled
    if request.proposal_count is not None: a['proposal_count'] = request.proposal_count
    if request.max_active_strategies is not None: a['max_active_strategies'] = request.max_active_strategies
    if request.min_active_strategies is not None: a['min_active_strategies'] = request.min_active_strategies
    if request.watchlist_size is not None: a['watchlist_size'] = request.watchlist_size
    if request.backtested_ttl_cycles is not None: a['backtested_ttl_cycles'] = request.backtested_ttl_cycles
    if request.signal_generation_interval is not None: sg['interval_seconds'] = request.signal_generation_interval
    if request.dynamic_symbol_additions is not None: sg['dynamic_symbol_additions'] = request.dynamic_symbol_additions

    # ─── Activation — Sharpe / WR / DD ──────────────────────────────────
    if request.min_sharpe is not None: act['min_sharpe'] = request.min_sharpe
    if request.min_sharpe_crypto is not None: act['min_sharpe_crypto'] = request.min_sharpe_crypto
    if request.min_sharpe_commodity is not None: act['min_sharpe_commodity'] = request.min_sharpe_commodity
    if request.max_drawdown is not None: act['max_drawdown'] = to_frac(request.max_drawdown)
    if request.min_win_rate is not None: act['min_win_rate'] = to_frac(request.min_win_rate)
    if request.min_win_rate_crypto is not None: act['min_win_rate_crypto'] = to_frac(request.min_win_rate_crypto)
    if request.min_win_rate_commodity is not None: act['min_win_rate_commodity'] = to_frac(request.min_win_rate_commodity)

    # ─── Activation — Min Trades ────────────────────────────────────────
    if request.min_trades is not None: act['min_trades'] = request.min_trades
    if request.min_trades_dsl is not None: act['min_trades_dsl'] = request.min_trades_dsl
    if request.min_trades_dsl_4h is not None: act['min_trades_dsl_4h'] = request.min_trades_dsl_4h
    if request.min_trades_dsl_1h is not None: act['min_trades_dsl_1h'] = request.min_trades_dsl_1h
    if request.min_trades_alpha_edge is not None: act['min_trades_alpha_edge'] = request.min_trades_alpha_edge
    if request.min_trades_crypto_1d is not None: act['min_trades_crypto_1d'] = request.min_trades_crypto_1d
    if request.min_trades_crypto_4h is not None: act['min_trades_crypto_4h'] = request.min_trades_crypto_4h
    if request.min_trades_crypto_1h is not None: act['min_trades_crypto_1h'] = request.min_trades_crypto_1h
    if request.min_trades_commodity is not None: act['min_trades_commodity'] = request.min_trades_commodity

    # ─── Activation — Min Return Per Trade (pct → decimal) ─────────────
    rpt_map = {
        'min_rpt_stock': 'stock', 'min_rpt_stock_4h': 'stock_4h', 'min_rpt_stock_1h': 'stock_1h',
        'min_rpt_etf': 'etf', 'min_rpt_etf_4h': 'etf_4h', 'min_rpt_etf_1h': 'etf_1h',
        'min_rpt_forex': 'forex', 'min_rpt_forex_1h': 'forex_1h',
        'min_rpt_crypto': 'crypto', 'min_rpt_crypto_1d': 'crypto_1d',
        'min_rpt_crypto_4h': 'crypto_4h', 'min_rpt_crypto_1h': 'crypto_1h',
        'min_rpt_index': 'index', 'min_rpt_index_1h': 'index_1h',
        'min_rpt_commodity': 'commodity', 'min_rpt_commodity_4h': 'commodity_4h',
    }
    for req_field, yaml_key in rpt_map.items():
        val = getattr(request, req_field)
        if val is not None:
            rpt[yaml_key] = to_frac(val)

    # ─── Retirement + retirement_logic ──────────────────────────────────
    if request.retirement_max_sharpe is not None: ret['max_sharpe'] = request.retirement_max_sharpe
    if request.retirement_max_drawdown is not None: ret['max_drawdown'] = to_frac(request.retirement_max_drawdown)
    if request.retirement_min_win_rate is not None: ret['min_win_rate'] = to_frac(request.retirement_min_win_rate)
    if request.retirement_min_trades_for_evaluation is not None:
        ret['min_trades_for_evaluation'] = request.retirement_min_trades_for_evaluation
    if request.retirement_min_live_trades is not None:
        retl['min_live_trades_before_evaluation'] = request.retirement_min_live_trades
    if request.retirement_rolling_window_days is not None:
        retl['rolling_window_days'] = request.retirement_rolling_window_days
    if request.retirement_consecutive_failures is not None:
        retl['consecutive_failures_required'] = request.retirement_consecutive_failures
    if request.retirement_probation_days is not None:
        retl['probation_period_days'] = request.retirement_probation_days

    # ─── Walk-forward + direction-aware ─────────────────────────────────
    if request.wf_train_days is not None: wf['train_days'] = request.wf_train_days
    if request.wf_test_days is not None: wf['test_days'] = request.wf_test_days
    if request.direction_aware_thresholds is not None:
        dat = request.direction_aware_thresholds
        da['default'] = dat.default.model_dump()
        for bucket_name in ('ranging', 'trending_up', 'trending_down', 'high_vol'):
            bucket = getattr(dat, bucket_name)
            da[bucket_name] = {
                'long': bucket.long.model_dump(),
                'short': bucket.short.model_dump(),
            }

    # ─── Adaptive risk ──────────────────────────────────────────────────
    if request.adaptive_risk_enabled is not None: ar['enabled'] = request.adaptive_risk_enabled
    if request.adaptive_min_sl_pct is not None: ar['min_sl_pct'] = to_frac(request.adaptive_min_sl_pct)
    if request.adaptive_max_sl_pct is not None: ar['max_sl_pct'] = to_frac(request.adaptive_max_sl_pct)
    if request.adaptive_min_tp_pct is not None: ar['min_tp_pct'] = to_frac(request.adaptive_min_tp_pct)
    if request.adaptive_max_tp_pct is not None: ar['max_tp_pct'] = to_frac(request.adaptive_max_tp_pct)
    if request.adaptive_min_rr_ratio is not None: ar['min_reward_risk_ratio'] = request.adaptive_min_rr_ratio

    # ─── Performance feedback ───────────────────────────────────────────
    if request.feedback_lookback_days is not None: pf['feedback_lookback_days'] = request.feedback_lookback_days
    if request.feedback_min_trades is not None: pf['min_trades_for_feedback'] = request.feedback_min_trades
    if request.feedback_max_weight is not None: pf['max_weight_adjustment'] = request.feedback_max_weight
    if request.feedback_min_weight is not None: pf['min_weight_adjustment'] = request.feedback_min_weight
    if request.feedback_weight_decay_per_day is not None:
        pf['weight_decay_per_day'] = request.feedback_weight_decay_per_day

    # ─── Directional balance + quotas ───────────────────────────────────
    if request.directional_balance_enabled is not None: db['enabled'] = request.directional_balance_enabled
    if request.directional_min_long_pct is not None: db['min_long_pct'] = request.directional_min_long_pct
    if request.directional_max_long_pct is not None: db['max_long_pct'] = request.directional_max_long_pct
    if request.directional_min_short_pct is not None: db['min_short_pct'] = request.directional_min_short_pct
    if request.directional_max_short_pct is not None: db['max_short_pct'] = request.directional_max_short_pct
    if request.directional_quotas is not None:
        dq_req = request.directional_quotas
        dq['enabled'] = dq_req.enabled
        dq['adjacent_regime_reserve_pct'] = to_frac(dq_req.adjacent_regime_reserve_pct)
        for bucket_name in ('ranging', 'ranging_low_vol', 'trending_up', 'trending_up_weak',
                            'trending_up_strong', 'trending_down', 'trending_down_weak',
                            'high_volatility'):
            bucket = getattr(dq_req, bucket_name)
            dq[bucket_name] = {
                'min_long_pct': to_frac(bucket.min_long_pct),
                'min_short_pct': to_frac(bucket.min_short_pct),
            }

    # ─── Portfolio balance ──────────────────────────────────────────────
    if request.max_long_exposure_pct is not None:
        pb['max_directional_exposure_pct'] = to_frac(request.max_long_exposure_pct)
    if request.max_sector_exposure_pct is not None:
        pb['max_sector_exposure_pct'] = to_frac(request.max_sector_exposure_pct)
    # (max_short_exposure_pct shares the same yaml key; long field wins if both set)

    # ─── Persist ────────────────────────────────────────────────────────
    with open(config_file, 'w') as f:
        yaml.dump(full_config, f, default_flow_style=False, sort_keys=False)

    return CredentialsResponse(success=True, message="Autonomous configuration updated")

