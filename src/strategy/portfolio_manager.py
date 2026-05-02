"""Portfolio Manager for autonomous strategy activation and retirement."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.models.dataclasses import BacktestResults, Strategy
from src.models.enums import StrategyStatus, TradingMode
from src.models.orm import PositionORM
from src.strategy.portfolio_risk import PortfolioRiskManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.performance_degradation_monitor import (
    PerformanceDegradationMonitor,
    DegradationAlert
)

logger = logging.getLogger(__name__)


class PortfolioManager:
    """Manages portfolio of active strategies, handles activation and retirement."""

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        max_correlation: float = 0.7,
        min_trades: int = 20,
        portfolio_stop_loss_pct: float = 0.10,
        daily_loss_limit_pct: float = 0.03,
        market_analyzer: Optional['MarketStatisticsAnalyzer'] = None,
        etoro_client=None
    ):
        """
        Initialize Portfolio Manager.

        Args:
            strategy_engine: StrategyEngine instance for strategy operations
            max_correlation: Maximum allowed correlation between strategies (default 0.7)
            min_trades: Minimum trades required for strategy inclusion (default 20)
            portfolio_stop_loss_pct: Portfolio-wide stop-loss percentage (default 10%)
            daily_loss_limit_pct: Daily loss limit percentage (default 3%)
            market_analyzer: MarketStatisticsAnalyzer for regime detection (optional)
            etoro_client: Optional eToro API client for submitting close orders
        """
        self.strategy_engine = strategy_engine
        self.risk_manager = PortfolioRiskManager(max_correlation=max_correlation, min_trades=min_trades)
        self.market_analyzer = market_analyzer
        self.etoro_client = etoro_client

        # Portfolio-wide risk controls
        self.portfolio_stop_loss_pct = portfolio_stop_loss_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.trading_paused = False
        self.trading_paused_reason = None
        self.initial_portfolio_value = None
        self.daily_start_value = None
        self.daily_reset_date = None
        
        # Regime change tracking
        self.regime_change_override = {}  # strategy_id -> bool (manual override)
        
        # Performance degradation monitoring
        self.degradation_monitor = PerformanceDegradationMonitor(strategy_engine.db)
        self.degradation_overrides = {}  # strategy_id -> bool (manual override)

    def calculate_confidence_score(
        self, strategy: Strategy, backtest_results: BacktestResults
    ) -> float:
        """
        Calculate confidence score for a strategy based on multiple factors.

        Factors:
        - Sharpe ratio (higher is better)
        - Win rate (higher is better)
        - Trade count (more trades = more statistical significance)
        - Walk-forward consistency (if available)

        Args:
            strategy: Strategy to evaluate
            backtest_results: Backtest results for the strategy

        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0

        # Sharpe ratio component (40% weight)
        sharpe = backtest_results.sharpe_ratio
        if sharpe >= 1.0:
            sharpe_score = 1.0
        elif sharpe >= 0.5:
            sharpe_score = 0.7
        elif sharpe >= 0.3:
            sharpe_score = 0.4
        else:
            sharpe_score = 0.0
        score += sharpe_score * 0.4

        # Win rate component (30% weight)
        win_rate = backtest_results.win_rate
        if win_rate >= 0.55:
            win_rate_score = 1.0
        elif win_rate >= 0.50:
            win_rate_score = 0.8
        elif win_rate >= 0.45:
            win_rate_score = 0.6
        else:
            win_rate_score = 0.3
        score += win_rate_score * 0.3

        # Trade count component (20% weight)
        trades = backtest_results.total_trades
        if trades >= 30:
            trade_score = 1.0
        elif trades >= 20:
            trade_score = 0.8
        elif trades >= 10:
            trade_score = 0.6
        else:
            trade_score = 0.3
        score += trade_score * 0.2

        # Walk-forward consistency component (10% weight)
        # Check if walk-forward results are available in metadata
        if strategy.metadata and 'walk_forward_results' in strategy.metadata:
            wf_results = strategy.metadata['walk_forward_results']
            train_sharpe = wf_results.get('train_sharpe', 0)
            test_sharpe = wf_results.get('test_sharpe', 0)

            if train_sharpe > 0 and test_sharpe > 0:
                # Calculate consistency (lower difference is better)
                diff_pct = abs(test_sharpe - train_sharpe) / abs(train_sharpe)
                if diff_pct <= 0.2:
                    wf_score = 1.0  # Very consistent
                elif diff_pct <= 0.4:
                    wf_score = 0.7  # Moderately consistent
                else:
                    wf_score = 0.4  # Less consistent
            else:
                wf_score = 0.5  # No walk-forward data
        else:
            wf_score = 0.5  # No walk-forward data

        score += wf_score * 0.1

        return score

    def set_initial_portfolio_value(self, value: float) -> None:
        """
        Set the initial portfolio value for stop-loss tracking.

        Args:
            value: Initial portfolio value in dollars
        """
        self.initial_portfolio_value = value
        self.daily_start_value = value
        self.daily_reset_date = datetime.now().date()
        logger.info(
            f"Portfolio tracking initialized: "
            f"Initial value=${value:,.2f}, "
            f"Stop-loss at {self.portfolio_stop_loss_pct:.0%} (${value * (1 - self.portfolio_stop_loss_pct):,.2f}), "
            f"Daily limit at {self.daily_loss_limit_pct:.0%}"
        )

    def reset_daily_tracking(self, current_value: float) -> None:
        """
        Reset daily loss tracking at start of new trading day.

        Args:
            current_value: Current portfolio value
        """
        today = datetime.now().date()
        if self.daily_reset_date != today:
            self.daily_start_value = current_value
            self.daily_reset_date = today
            logger.info(f"Daily tracking reset: Start value=${current_value:,.2f}")

    def check_portfolio_stop_loss(self, current_value: float) -> tuple[bool, Optional[str]]:
        """
        Check if portfolio-wide stop-loss or daily loss limit has been hit.

        Args:
            current_value: Current portfolio value in dollars

        Returns:
            Tuple of (should_pause, reason) where should_pause is True if trading should be paused
        """
        if self.initial_portfolio_value is None:
            logger.warning("Initial portfolio value not set, cannot check stop-loss")
            return (False, None)

        # Reset daily tracking if new day
        self.reset_daily_tracking(current_value)

        # Check portfolio-wide stop-loss (from initial value)
        portfolio_loss_pct = (self.initial_portfolio_value - current_value) / self.initial_portfolio_value
        if portfolio_loss_pct >= self.portfolio_stop_loss_pct:
            reason = (
                f"Portfolio stop-loss triggered: "
                f"Loss {portfolio_loss_pct:.2%} >= {self.portfolio_stop_loss_pct:.0%} "
                f"(${self.initial_portfolio_value:,.2f} → ${current_value:,.2f})"
            )
            logger.error(reason)
            return (True, reason)

        # Check daily loss limit (from daily start value)
        if self.daily_start_value is not None and self.daily_start_value > 0:
            daily_loss_pct = (self.daily_start_value - current_value) / self.daily_start_value
            if daily_loss_pct >= self.daily_loss_limit_pct:
                reason = (
                    f"Daily loss limit triggered: "
                    f"Loss {daily_loss_pct:.2%} >= {self.daily_loss_limit_pct:.0%} "
                    f"(${self.daily_start_value:,.2f} → ${current_value:,.2f})"
                )
                logger.error(reason)
                return (True, reason)

        return (False, None)

    def pause_trading(self, reason: str) -> None:
        """
        Pause all trading activity.

        Args:
            reason: Reason for pausing trading
        """
        self.trading_paused = True
        self.trading_paused_reason = reason
        logger.error(f"TRADING PAUSED: {reason}")

        # Close all open positions
        active_strategies = self.strategy_engine.get_active_strategies()
        for strategy in active_strategies:
            try:
                self._close_strategy_positions(strategy.id)
                logger.info(f"Closed positions for strategy {strategy.name}")
            except Exception as e:
                logger.error(f"Failed to close positions for {strategy.name}: {e}")

    def resume_trading(self) -> None:
        """Resume trading activity after pause."""
        self.trading_paused = False
        self.trading_paused_reason = None
        logger.info("Trading resumed")

    def is_trading_allowed(self, current_portfolio_value: Optional[float] = None) -> tuple[bool, Optional[str]]:
        """
        Check if trading is currently allowed.

        Args:
            current_portfolio_value: Optional current portfolio value for stop-loss check

        Returns:
            Tuple of (is_allowed, reason) where is_allowed is False if trading is paused
        """
        if self.trading_paused:
            return (False, self.trading_paused_reason)

        if current_portfolio_value is not None:
            should_pause, reason = self.check_portfolio_stop_loss(current_portfolio_value)
            if should_pause:
                self.pause_trading(reason)
                return (False, reason)

        return (True, None)

    def check_exposure_limits(
        self,
        new_trade_symbol: str,
        new_trade_value: float,
        new_trade_strategy_id: str,
        portfolio_value: float
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a new trade would violate exposure limits.

        Exposure limits:
        - Max total exposure: 100% of portfolio (no leverage)
        - Max per-symbol exposure: 20% of portfolio
        - Max per-strategy exposure: 30% of portfolio

        Args:
            new_trade_symbol: Symbol for the new trade
            new_trade_value: Dollar value of the new trade
            new_trade_strategy_id: Strategy ID for the new trade
            portfolio_value: Current portfolio value

        Returns:
            Tuple of (is_allowed, reason) where is_allowed is False if limits would be exceeded
        """
        session = self.strategy_engine.db.get_session()
        try:
            # Get all open positions
            open_positions = (
                session.query(PositionORM)
                .filter(PositionORM.closed_at.is_(None))
                .all()
            )

            # Calculate current exposures
            total_exposure = sum(abs(pos.quantity * pos.entry_price) for pos in open_positions)

            # Calculate per-symbol exposure
            symbol_exposure = {}
            for pos in open_positions:
                pos_value = abs(pos.quantity * pos.entry_price)
                symbol_exposure[pos.symbol] = symbol_exposure.get(pos.symbol, 0) + pos_value

            # Calculate per-strategy exposure
            strategy_exposure = {}
            for pos in open_positions:
                pos_value = abs(pos.quantity * pos.entry_price)
                strategy_exposure[pos.strategy_id] = strategy_exposure.get(pos.strategy_id, 0) + pos_value

            # Check total exposure limit (100%)
            new_total_exposure = total_exposure + new_trade_value
            max_total_exposure = portfolio_value * 1.0  # 100%
            if new_total_exposure > max_total_exposure:
                reason = (
                    f"Total exposure limit exceeded: "
                    f"${new_total_exposure:,.2f} > ${max_total_exposure:,.2f} (100% of portfolio). "
                    f"Current: ${total_exposure:,.2f}, New trade: ${new_trade_value:,.2f}"
                )
                logger.warning(reason)
                return (False, reason)

            # Check per-symbol exposure limit (20%)
            new_symbol_exposure = symbol_exposure.get(new_trade_symbol, 0) + new_trade_value
            max_symbol_exposure = portfolio_value * 0.20  # 20%
            if new_symbol_exposure > max_symbol_exposure:
                reason = (
                    f"Per-symbol exposure limit exceeded for {new_trade_symbol}: "
                    f"${new_symbol_exposure:,.2f} > ${max_symbol_exposure:,.2f} (20% of portfolio). "
                    f"Current: ${symbol_exposure.get(new_trade_symbol, 0):,.2f}, New trade: ${new_trade_value:,.2f}"
                )
                logger.warning(reason)
                return (False, reason)

            # Check per-strategy exposure limit (30%)
            new_strategy_exposure = strategy_exposure.get(new_trade_strategy_id, 0) + new_trade_value
            max_strategy_exposure = portfolio_value * 0.30  # 30%
            if new_strategy_exposure > max_strategy_exposure:
                reason = (
                    f"Per-strategy exposure limit exceeded for strategy {new_trade_strategy_id}: "
                    f"${new_strategy_exposure:,.2f} > ${max_strategy_exposure:,.2f} (30% of portfolio). "
                    f"Current: ${strategy_exposure.get(new_trade_strategy_id, 0):,.2f}, New trade: ${new_trade_value:,.2f}"
                )
                logger.warning(reason)
                return (False, reason)

            # All checks passed
            logger.info(
                f"Exposure check passed for {new_trade_symbol}: "
                f"Total={new_total_exposure/portfolio_value:.1%}, "
                f"Symbol={new_symbol_exposure/portfolio_value:.1%}, "
                f"Strategy={new_strategy_exposure/portfolio_value:.1%}"
            )
            return (True, None)

        finally:
            session.close()

    def get_current_exposures(self, portfolio_value: float) -> Dict:
        """
        Get current portfolio exposures.

        Args:
            portfolio_value: Current portfolio value

        Returns:
            Dict with exposure information
        """
        session = self.strategy_engine.db.get_session()
        try:
            # Get all open positions
            open_positions = (
                session.query(PositionORM)
                .filter(PositionORM.closed_at.is_(None))
                .all()
            )

            # Calculate exposures
            total_exposure = sum(abs(pos.quantity * pos.entry_price) for pos in open_positions)

            symbol_exposure = {}
            for pos in open_positions:
                pos_value = abs(pos.quantity * pos.entry_price)
                symbol_exposure[pos.symbol] = symbol_exposure.get(pos.symbol, 0) + pos_value

            strategy_exposure = {}
            for pos in open_positions:
                pos_value = abs(pos.quantity * pos.entry_price)
                strategy_exposure[pos.strategy_id] = strategy_exposure.get(pos.strategy_id, 0) + pos_value

            return {
                'total_exposure': total_exposure,
                'total_exposure_pct': total_exposure / portfolio_value if portfolio_value > 0 else 0,
                'symbol_exposure': symbol_exposure,
                'symbol_exposure_pct': {
                    symbol: value / portfolio_value if portfolio_value > 0 else 0
                    for symbol, value in symbol_exposure.items()
                },
                'strategy_exposure': strategy_exposure,
                'strategy_exposure_pct': {
                    strategy_id: value / portfolio_value if portfolio_value > 0 else 0
                    for strategy_id, value in strategy_exposure.items()
                },
                'num_positions': len(open_positions)
            }

        finally:
            session.close()

    def calculate_strategy_correlation(
        self,
        strategies: List[Strategy],
        returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix between active strategies.

        Args:
            strategies: List of strategies to analyze
            returns_data: Optional dict mapping strategy_id -> daily returns Series

        Returns:
            Correlation matrix as DataFrame
        """
        if not strategies or len(strategies) < 2:
            logger.info("Not enough strategies for correlation analysis")
            return pd.DataFrame()

        # Use risk manager to calculate correlation
        portfolio_metrics = self.risk_manager.calculate_portfolio_metrics(strategies, returns_data or {})
        correlation_matrix = portfolio_metrics.get('correlation_matrix', pd.DataFrame())

        return correlation_matrix

    def get_correlated_positions(
        self,
        new_trade_symbol: str,
        new_trade_strategy_id: str,
        correlation_threshold: float = 0.7
    ) -> List[Dict]:
        """
        Find existing positions that are highly correlated with a new trade.

        Correlation is determined by:
        1. Same symbol (correlation = 1.0)
        2. Strategy correlation from returns data

        Args:
            new_trade_symbol: Symbol for the new trade
            new_trade_strategy_id: Strategy ID for the new trade
            correlation_threshold: Threshold for high correlation (default 0.7)

        Returns:
            List of dicts with correlated position info
        """
        session = self.strategy_engine.db.get_session()
        try:
            # Get all open positions
            open_positions = (
                session.query(PositionORM)
                .filter(PositionORM.closed_at.is_(None))
                .all()
            )

            correlated_positions = []

            # Check for same symbol (perfect correlation)
            for pos in open_positions:
                if pos.symbol == new_trade_symbol:
                    correlated_positions.append({
                        'position_id': pos.id,
                        'symbol': pos.symbol,
                        'strategy_id': pos.strategy_id,
                        'value': abs(pos.quantity * pos.entry_price),
                        'correlation': 1.0,
                        'reason': 'Same symbol'
                    })

            # Get active strategies for correlation analysis
            active_strategies = self.strategy_engine.get_active_strategies()
            if len(active_strategies) >= 2:
                # Calculate strategy correlation
                correlation_matrix = self.calculate_strategy_correlation(active_strategies)

                if not correlation_matrix.empty and new_trade_strategy_id in correlation_matrix.index:
                    # Check correlation with other strategies
                    for pos in open_positions:
                        if pos.strategy_id != new_trade_strategy_id and pos.symbol != new_trade_symbol:
                            # Get correlation between strategies
                            if pos.strategy_id in correlation_matrix.columns:
                                correlation = correlation_matrix.loc[new_trade_strategy_id, pos.strategy_id]

                                if abs(correlation) >= correlation_threshold:
                                    correlated_positions.append({
                                        'position_id': pos.id,
                                        'symbol': pos.symbol,
                                        'strategy_id': pos.strategy_id,
                                        'value': abs(pos.quantity * pos.entry_price),
                                        'correlation': correlation,
                                        'reason': f'Strategy correlation {correlation:.2f}'
                                    })

            return correlated_positions

        finally:
            session.close()

    def calculate_correlation_adjusted_size(
        self,
        base_position_size: float,
        new_trade_symbol: str,
        new_trade_strategy_id: str,
        correlation_threshold: float = 0.7
    ) -> tuple[float, str]:
        """
        Adjust position size based on correlation with existing positions.

        If multiple strategies hold correlated positions, reduce the new position size
        to avoid over-concentration.

        Adjustment rules:
        - 1 correlated position: 75% of base size
        - 2 correlated positions: 50% of base size
        - 3+ correlated positions: 33% of base size

        Args:
            base_position_size: Base position size before adjustment
            new_trade_symbol: Symbol for the new trade
            new_trade_strategy_id: Strategy ID for the new trade
            correlation_threshold: Threshold for high correlation (default 0.7)

        Returns:
            Tuple of (adjusted_size, reason)
        """
        correlated_positions = self.get_correlated_positions(
            new_trade_symbol,
            new_trade_strategy_id,
            correlation_threshold
        )

        if not correlated_positions:
            return (base_position_size, "No correlated positions")

        num_correlated = len(correlated_positions)

        # Calculate adjustment factor
        if num_correlated == 1:
            adjustment_factor = 0.75  # 75% of base size
        elif num_correlated == 2:
            adjustment_factor = 0.50  # 50% of base size
        else:
            adjustment_factor = 0.33  # 33% of base size

        adjusted_size = base_position_size * adjustment_factor

        # Build reason string
        correlated_symbols = [pos['symbol'] for pos in correlated_positions]
        reason = (
            f"Reduced to {adjustment_factor:.0%} due to {num_correlated} correlated position(s): "
            f"{', '.join(correlated_symbols)}"
        )

        logger.info(
            f"Correlation-based position sizing for {new_trade_symbol}: "
            f"${base_position_size:,.2f} → ${adjusted_size:,.2f} ({adjustment_factor:.0%}). "
            f"{reason}"
        )

        return (adjusted_size, reason)




    def get_activation_tier(
        self, backtest_results: BacktestResults, is_alpha_edge: bool = False
    ) -> tuple[int, float]:
        """
        Determine activation tier and max allocation based on Sharpe ratio.

        Tiers:
        - Tier 1 (High Confidence): Sharpe > 1.0, max 30% allocation
        - Tier 2 (Medium Confidence): Sharpe 0.5-1.0, max 15% allocation
        - Tier 3 (Low Confidence): Sharpe 0.3-0.5 (or 0.2-0.5 for Alpha Edge), max 10% allocation
        - Reject: Sharpe < 0.3 (or < 0.2 for Alpha Edge)

        Args:
            backtest_results: Backtest results for the strategy
            is_alpha_edge: Whether this is an Alpha Edge fundamental strategy

        Returns:
            Tuple of (tier, max_allocation_pct) or (0, 0.0) if rejected
        """
        sharpe = backtest_results.sharpe_ratio
        min_sharpe = 0.2 if is_alpha_edge else 0.3

        if sharpe >= 1.0:
            return (1, 30.0)  # Tier 1: High confidence
        elif sharpe >= 0.5:
            return (2, 15.0)  # Tier 2: Medium confidence
        elif sharpe >= min_sharpe:
            return (3, 10.0)  # Tier 3: Low confidence
        else:
            return (0, 0.0)  # Reject

    def evaluate_for_activation(
        self, strategy: Strategy, backtest_results: BacktestResults, market_context: Optional[Dict] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if strategy should be auto-activated using tiered system.

        Tiered Activation Criteria:
        - Tier 1 (High Confidence): Sharpe > 1.0, max 30% allocation
        - Tier 2 (Medium Confidence): Sharpe 0.5-1.0, max 15% allocation
        - Tier 3 (Low Confidence): Sharpe 0.3-0.5, max 10% allocation
        - Reject: Sharpe < 0.3

        Additional Requirements (all tiers):
        - Win rate > 45% (adjusted by macro regime)
        - Max drawdown < 20% (adjusted by macro regime)
        - Minimum 10 trades

        Macro Regime Adjustments:
        - Risk-Off (VIX > 25): Stricter thresholds
        - Risk-On (VIX < 15): Relaxed thresholds

        Args:
            strategy: Strategy to evaluate
            backtest_results: Backtest results for the strategy
            market_context: Optional market context for macro-aware thresholds

        Returns:
            True if strategy should be activated, False otherwise
        """
        # Detect if this is an Alpha Edge strategy (fundamental-based)
        is_alpha_edge = False
        if hasattr(strategy, 'metadata') and strategy.metadata:
            is_alpha_edge = strategy.metadata.get('strategy_category') == 'alpha_edge'
        
        # Detect strategy direction for regime-aware threshold adjustments
        strategy_direction = 'LONG'
        if hasattr(strategy, 'metadata') and strategy.metadata:
            stored_dir = strategy.metadata.get('direction', '')
            if stored_dir.upper() == 'SHORT':
                strategy_direction = 'SHORT'
        
        # Get base thresholds from config file (activation_thresholds section)
        # Falls back to hardcoded defaults if config not available
        config_thresholds = {}
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    config_thresholds = config.get('activation_thresholds', {})
        except Exception:
            pass

        if is_alpha_edge:
            # Alpha Edge uses the config thresholds but with relaxed floors
            # (fundamental strategies behave differently from DSL technical strategies)
            config_sharpe = config_thresholds.get('min_sharpe', 0.3)
            base_sharpe_threshold = max(0.2, config_sharpe * 0.5)  # Half of DSL threshold, floor 0.2
            base_win_rate_threshold = max(0.35, config_thresholds.get('min_win_rate', 0.40) - 0.10)
            base_drawdown_threshold = config_thresholds.get('max_drawdown', 0.20) + 0.10  # 10% more lenient
            logger.info(
                f"Alpha Edge strategy detected: Using relaxed thresholds - "
                f"Sharpe>{base_sharpe_threshold}, WinRate>{base_win_rate_threshold:.0%}, "
                f"Drawdown<{base_drawdown_threshold:.0%}"
            )
        else:
            base_sharpe_threshold = config_thresholds.get('min_sharpe', 0.3)
            base_win_rate_threshold = config_thresholds.get('min_win_rate', 0.40)
            base_drawdown_threshold = config_thresholds.get('max_drawdown', 0.20)
        
        # Per-asset-class Sharpe threshold: use min_sharpe_crypto for crypto symbols
        # instead of the generic min_sharpe. This gives explicit control from the Settings UI.
        if hasattr(strategy, 'symbols') and strategy.symbols:
            primary_symbol = strategy.symbols[0] if strategy.symbols else ''
            try:
                from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                if primary_symbol.upper() in set(DEMO_ALLOWED_CRYPTO):
                    crypto_sharpe = config_thresholds.get('min_sharpe_crypto')
                    if crypto_sharpe is not None:
                        base_sharpe_threshold = crypto_sharpe
                        logger.info(
                            f"Crypto asset class: Using min_sharpe_crypto={base_sharpe_threshold} "
                            f"(from config)"
                        )
                    crypto_wr = config_thresholds.get('min_win_rate_crypto')
                    if crypto_wr is not None:
                        base_win_rate_threshold = crypto_wr
                        logger.info(
                            f"Crypto asset class: Using min_win_rate_crypto={base_win_rate_threshold} "
                            f"(from config)"
                        )
                
                from src.core.tradeable_instruments import DEMO_ALLOWED_COMMODITIES
                if primary_symbol.upper() in set(DEMO_ALLOWED_COMMODITIES):
                    commodity_sharpe = config_thresholds.get('min_sharpe_commodity')
                    if commodity_sharpe is not None:
                        base_sharpe_threshold = commodity_sharpe
                        logger.info(
                            f"Commodity asset class: Using min_sharpe_commodity={base_sharpe_threshold} "
                            f"(from config)"
                        )
                    commodity_wr = config_thresholds.get('min_win_rate_commodity')
                    if commodity_wr is not None:
                        base_win_rate_threshold = commodity_wr
                        logger.info(
                            f"Commodity asset class: Using min_win_rate_commodity={base_win_rate_threshold} "
                            f"(from config)"
                        )
            except ImportError:
                pass
        
        # Detect strategy timeframe for timeframe-aware threshold adjustments
        # Check strategy.metadata first (intraday templates), then backtest_results.metadata
        interval = '1d'  # Default to daily if not specified
        if hasattr(strategy, 'metadata') and strategy.metadata:
            interval = strategy.metadata.get('interval', '1d')
        if interval == '1d' and hasattr(backtest_results, 'metadata') and backtest_results.metadata:
            interval = backtest_results.metadata.get('interval', '1d')
        
        # Normalize interval format (handle both '1h' and '1H')
        interval = interval.lower() if interval else '1d'
        
        # Store original thresholds for logging
        original_sharpe = base_sharpe_threshold
        original_win_rate = base_win_rate_threshold
        
        # Apply timeframe multipliers AFTER reading base thresholds
        # Hourly strategies naturally have lower Sharpe ratios due to more frequent sampling
        if interval in ['1h', '2h']:
            base_sharpe_threshold = base_sharpe_threshold * 0.67
            base_win_rate_threshold = base_win_rate_threshold - 0.05
            logger.info(
                f"Hourly strategy detected (interval={interval}): Adjusted thresholds - "
                f"Sharpe>{base_sharpe_threshold:.2f} (from {original_sharpe:.2f}), "
                f"WinRate>{base_win_rate_threshold:.1%} (from {original_win_rate:.1%})"
            )
        elif interval in ['4h']:
            base_sharpe_threshold = base_sharpe_threshold * 0.8
            base_win_rate_threshold = base_win_rate_threshold - 0.03
            logger.info(
                f"4H strategy detected: Adjusted thresholds - "
                f"Sharpe>{base_sharpe_threshold:.2f} (from {original_sharpe:.2f}), "
                f"WinRate>{base_win_rate_threshold:.1%} (from {original_win_rate:.1%})"
            )
        elif interval in ['15m', '30m']:
            base_sharpe_threshold = base_sharpe_threshold * 0.44
            base_win_rate_threshold = base_win_rate_threshold - 0.07
            logger.info(
                f"Intraday strategy detected (interval={interval}): Adjusted thresholds - "
                f"Sharpe>{base_sharpe_threshold:.2f} (from {original_sharpe:.2f}), "
                f"WinRate>{base_win_rate_threshold:.1%} (from {original_win_rate:.1%})"
            )
        # Daily strategies: no adjustment
        
        # Apply direction-aware relaxation based on market regime
        # This prevents systematically rejecting LONG strategies in ranging markets
        direction_relaxation_applied = False
        if market_context:
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                    da_config = config.get('backtest', {}).get('walk_forward', {}).get('direction_aware_thresholds', {})
                    
                    # Determine regime bucket from market context
                    macro_regime = market_context.get('macro_regime', 'unknown')
                    risk_regime = market_context.get('risk_regime', 'unknown')
                    
                    regime_key = None
                    if any(r in str(macro_regime).lower() for r in ['ranging', 'neutral', 'sideways']):
                        regime_key = 'ranging'
                    elif 'high_vol' in str(risk_regime).lower() or 'risk_off' in str(risk_regime).lower():
                        regime_key = 'high_vol'
                    elif any(r in str(macro_regime).lower() for r in ['bull', 'expansion', 'up']):
                        regime_key = 'trending_up'
                    elif any(r in str(macro_regime).lower() for r in ['bear', 'recession', 'down']):
                        regime_key = 'trending_down'
                    
                    if regime_key and da_config.get(regime_key):
                        dir_key = strategy_direction.lower()
                        dir_thresholds = da_config[regime_key].get(dir_key, {})
                        if dir_thresholds:
                            # Apply relaxation: use the more permissive of base vs direction-aware
                            relaxed_sharpe = dir_thresholds.get('min_sharpe', base_sharpe_threshold)
                            relaxed_win_rate = dir_thresholds.get('min_win_rate', base_win_rate_threshold)
                            
                            if relaxed_sharpe < base_sharpe_threshold or relaxed_win_rate < base_win_rate_threshold:
                                base_sharpe_threshold = min(base_sharpe_threshold, relaxed_sharpe)
                                base_win_rate_threshold = min(base_win_rate_threshold, relaxed_win_rate)
                                direction_relaxation_applied = True
                                logger.info(
                                    f"Direction-aware activation: Relaxed {strategy_direction} thresholds for "
                                    f"{regime_key} regime (Sharpe>{base_sharpe_threshold}, "
                                    f"WinRate>{base_win_rate_threshold:.0%})"
                                )
            except Exception as e:
                logger.warning(f"Failed to apply direction-aware activation thresholds: {e}")
        
        # Adjust thresholds based on macro regime
        # VIX adjustments use config values as the floor — never go below what the user configured
        if market_context:
            vix = market_context.get('vix', 20.0)
            macro_regime = market_context.get('macro_regime', 'transitional')
            
            # Risk-Off (VIX > 25): Stricter thresholds (scale up from config base)
            if vix > 25:
                sharpe_threshold = max(base_sharpe_threshold, base_sharpe_threshold * 1.4)
                win_rate_threshold = base_win_rate_threshold  # Don't inflate win rate — R:R check handles risk
                drawdown_threshold = min(base_drawdown_threshold, base_drawdown_threshold * 0.75)
                logger.info(
                    f"Risk-Off regime (VIX={vix:.1f}): Using stricter thresholds - "
                    f"Sharpe>{sharpe_threshold}, WinRate>{win_rate_threshold:.0%}, "
                    f"Drawdown<{drawdown_threshold:.0%}"
                )
            
            # Risk-On (VIX < 15): Use config thresholds (don't relax below config)
            elif vix < 15:
                sharpe_threshold = base_sharpe_threshold
                win_rate_threshold = base_win_rate_threshold
                drawdown_threshold = base_drawdown_threshold
                logger.info(
                    f"Risk-On regime (VIX={vix:.1f}): Using config thresholds - "
                    f"Sharpe>{sharpe_threshold}, WinRate>{win_rate_threshold:.0%}, "
                    f"Drawdown<{drawdown_threshold:.0%}"
                )
            
            # Normal conditions
            else:
                sharpe_threshold = base_sharpe_threshold
                win_rate_threshold = base_win_rate_threshold
                drawdown_threshold = base_drawdown_threshold
                logger.info(
                    f"Normal regime (VIX={vix:.1f}): Using standard thresholds - "
                    f"Sharpe>{sharpe_threshold}, WinRate>{win_rate_threshold:.0%}, "
                    f"Drawdown<{drawdown_threshold:.0%}"
                )
        else:
            # No market context, use base thresholds
            sharpe_threshold = base_sharpe_threshold
            win_rate_threshold = base_win_rate_threshold
            drawdown_threshold = base_drawdown_threshold
            logger.info("No market context: Using standard thresholds")
        
        # Get activation tier
        tier, max_allocation = self.get_activation_tier(backtest_results, is_alpha_edge=is_alpha_edge)

        if tier == 0 or backtest_results.sharpe_ratio < sharpe_threshold:
            reason = (
                f"Sharpe {backtest_results.sharpe_ratio:.2f} < {sharpe_threshold}"
            )
            logger.info(f"Strategy {strategy.name} rejected: {reason}")
            return False, reason

        # Check max drawdown (allow exactly at threshold)
        if backtest_results.max_drawdown > drawdown_threshold:
            reason = (
                f"Drawdown {backtest_results.max_drawdown:.1%} > {drawdown_threshold:.0%}"
            )
            logger.info(f"Strategy {strategy.name} failed activation: {reason}")
            return False, reason

        # Check win rate — but use EXPECTANCY as the primary gate for strategies
        # with enough trades. A 30% win-rate strategy with 3:1 R:R has positive
        # expectancy and should pass. Flat win-rate gates reject profitable
        # mean-reversion strategies — that's a software-engineer filter, not a
        # trader filter. A PM at a $100B fund cares about expected P&L per trade,
        # not how often you're right.
        min_win_rate = win_rate_threshold
        if hasattr(strategy, 'risk_params') and strategy.risk_params and strategy.risk_params.stop_loss_pct > 0:
            min_win_rate = win_rate_threshold
            logger.info(f"Strategy uses stop-loss, requiring win_rate >= {min_win_rate:.0%} (R:R checked separately)")
        
        # Expectancy gate: if we have enough trades, use expectancy instead of
        # raw win rate. Expectancy = (avg_win × WR) - (avg_loss × (1-WR)).
        # Positive expectancy = profitable system regardless of win rate.
        use_expectancy_gate = (
            backtest_results.total_trades >= 15
            and backtest_results.avg_win > 0
            and backtest_results.avg_loss != 0
        )
        
        if use_expectancy_gate:
            wr = backtest_results.win_rate
            expectancy = (backtest_results.avg_win * wr) - (abs(backtest_results.avg_loss) * (1 - wr))
            
            if expectancy > 0:
                # Positive expectancy — pass even if win rate is below threshold.
                # Still enforce a hard floor (25%) to filter out degenerate strategies
                # that "win" once with a huge outlier.
                hard_floor_wr = 0.25
                if wr < hard_floor_wr:
                    reason = (
                        f"WinRate {wr:.0%} < {hard_floor_wr:.0%} hard floor "
                        f"(expectancy ${expectancy:.2f} positive but WR too low for reliability)"
                    )
                    logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                    return False, reason
                
                logger.info(
                    f"Expectancy gate PASSED: ${expectancy:.2f}/trade "
                    f"(WR={wr:.0%}, avg_win=${backtest_results.avg_win:.2f}, "
                    f"avg_loss=${abs(backtest_results.avg_loss):.2f}) — "
                    f"win rate {wr:.0%} {'below' if wr < min_win_rate else 'above'} "
                    f"threshold {min_win_rate:.0%} but expectancy is positive"
                )
            else:
                # Negative expectancy — reject regardless of win rate
                reason = (
                    f"Negative expectancy ${expectancy:.2f}/trade "
                    f"(WR={wr:.0%}, avg_win=${backtest_results.avg_win:.2f}, "
                    f"avg_loss=${abs(backtest_results.avg_loss):.2f})"
                )
                logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                return False, reason
        else:
            # Not enough trades for reliable expectancy — fall back to win rate gate
            if backtest_results.win_rate < min_win_rate:
                reason = (
                    f"WinRate {backtest_results.win_rate:.0%} < {min_win_rate:.0%}"
                )
                logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                return False, reason
        
        # Check risk/reward ratio (avg_win / avg_loss)
        # Scale minimum R:R by win rate — high win-rate strategies are profitable
        # even with lower R:R. Formula: min_rr = max(0.4, 1.0 - win_rate)
        # Examples: 67% WR → min 0.4:1, 50% WR → min 0.5:1, 40% WR → min 0.6:1
        if hasattr(strategy, 'risk_params') and strategy.risk_params and strategy.risk_params.stop_loss_pct > 0:
            if backtest_results.avg_loss != 0:
                risk_reward_ratio = abs(backtest_results.avg_win / backtest_results.avg_loss)
                # Win-rate-adjusted minimum: high WR strategies need less R:R
                min_rr = max(0.4, 1.0 - backtest_results.win_rate)
                if risk_reward_ratio < min_rr:
                    reason = (
                        f"R:R {risk_reward_ratio:.2f} < {min_rr:.2f}:1 "
                        f"(WR={backtest_results.win_rate:.0%})"
                    )
                    logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                    return False, reason
                logger.info(f"Risk/reward ratio: {risk_reward_ratio:.2f} (meets {min_rr:.2f}:1 minimum for {backtest_results.win_rate:.0%} WR)")
            else:
                logger.debug(f"Cannot calculate risk/reward ratio (avg_loss=0) — strategy has no losing trades in backtest")
        

        # Check minimum number of trades — interval-aware and asset-class-aware thresholds
        # 4H strategies and commodities produce fewer trades by nature. Crypto
        # weekly/swing templates fire 3-7x in 120d due to thin bar counts — get
        # their own tier (4) paired with the min_sharpe_crypto floor.
        is_commodity = False
        is_crypto = False
        try:
            from src.core.tradeable_instruments import DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_CRYPTO
            if hasattr(strategy, 'symbols') and strategy.symbols:
                _primary = strategy.symbols[0].upper()
                is_commodity = _primary in set(DEMO_ALLOWED_COMMODITIES)
                is_crypto = _primary in set(DEMO_ALLOWED_CRYPTO)
        except ImportError:
            pass

        if is_commodity:
            min_trades_required = config_thresholds.get('min_trades_commodity', 2)
        elif is_crypto and interval == '4h':
            min_trades_required = config_thresholds.get('min_trades_crypto_4h', 4)
        elif is_crypto and interval in ('1h', '2h'):
            min_trades_required = config_thresholds.get('min_trades_crypto_1h', 15)
        elif is_crypto:
            min_trades_required = config_thresholds.get('min_trades_crypto_1d', 4)
        elif interval in ('4h',):
            min_trades_required = config_thresholds.get('min_trades_dsl_4h', config_thresholds.get('min_trades_4h', 3))
        elif interval in ('1h', '2h'):
            min_trades_required = config_thresholds.get('min_trades_dsl_1h', config_thresholds.get('min_trades_dsl', 5))
        elif is_alpha_edge:
            min_trades_required = config_thresholds.get('min_trades_alpha_edge', config_thresholds.get('min_trades', 5))
        else:
            min_trades_required = config_thresholds.get('min_trades_dsl', config_thresholds.get('min_trades', 5))
        
        # Relax min_trades for SHORT strategies — they fire less often in ranging/low-vol
        if strategy_direction == 'SHORT' and min_trades_required > 2:
            min_trades_required = max(2, min_trades_required - 1)
        
        if backtest_results.total_trades < min_trades_required:
            # Sharpe exception: high-conviction strategies (test Sharpe ≥ 2.0) with ≥ 3 trades
            # pass even if below the min_trades threshold. Mirrors the WF Sharpe exception so
            # strategies that passed WF on this basis don't get blocked again here.
            wf_test_sharpe = 0.0
            # strategy is a dataclass with .metadata dict (set by proposer after WF)
            if hasattr(strategy, 'metadata') and strategy.metadata:
                wf_test_sharpe = float(strategy.metadata.get('wf_test_sharpe', 0) or 0)
            if not wf_test_sharpe and hasattr(strategy, 'strategy_metadata') and strategy.strategy_metadata:
                wf_test_sharpe = float(strategy.strategy_metadata.get('wf_test_sharpe', 0) or 0)
            if backtest_results.total_trades >= 3 and wf_test_sharpe >= 2.0:
                logger.info(
                    f"Sharpe exception at activation: {strategy.name} — "
                    f"wf_sharpe={wf_test_sharpe:.2f} ≥ 2.0 with {backtest_results.total_trades} trades "
                    f"(below {min_trades_required} threshold but high conviction)"
                )
            else:
                reason = (
                    f"Trades {backtest_results.total_trades} < {min_trades_required} "
                    f"({'commodity' if is_commodity else '4H' if interval == '4h' else 'AE' if is_alpha_edge else 'DSL'})"
                )
                logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                return False, reason

        # Net-of-costs profitability check using per-asset-class cost model.
        # eToro charges zero commission on stocks/ETFs — the real cost is spread + slippage.
        # Each asset class has its own cost profile loaded from config.
        try:
            # Determine asset class for the primary symbol
            asset_class = 'stock'  # default
            primary_symbol = ''
            if hasattr(strategy, 'symbols') and strategy.symbols:
                primary_symbol = strategy.symbols[0].upper()
                try:
                    from src.core.tradeable_instruments import (
                        DEMO_ALLOWED_ETFS, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_CRYPTO,
                        DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES
                    )
                    if primary_symbol in set(DEMO_ALLOWED_FOREX):
                        asset_class = 'forex'
                    elif primary_symbol in set(DEMO_ALLOWED_CRYPTO):
                        asset_class = 'crypto'
                    elif primary_symbol in set(DEMO_ALLOWED_ETFS):
                        asset_class = 'etf'
                    elif primary_symbol in set(DEMO_ALLOWED_INDICES):
                        asset_class = 'index'
                    elif primary_symbol in set(DEMO_ALLOWED_COMMODITIES):
                        asset_class = 'commodity'
                except ImportError:
                    pass

            # Load per-asset-class transaction costs from config
            commission_pct = 0.0
            spread_pct = 0.0003
            slippage_pct = 0.0003
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        cfg = yaml.safe_load(f)
                        tx = cfg.get('backtest', {}).get('transaction_costs', {})
                        # Try per-asset-class costs first, fall back to global
                        ac_costs = tx.get('per_asset_class', {}).get(asset_class, {})
                        commission_pct = ac_costs.get('commission_percent', tx.get('commission_percent', 0.0))
                        spread_pct = ac_costs.get('spread_percent', tx.get('spread_percent', 0.0003))
                        slippage_pct = ac_costs.get('slippage_percent', tx.get('slippage_percent', 0.0003))
            except Exception:
                pass

            # The backtest engine (_run_vectorbt_backtest) already deducts transaction
            # costs from total_return using actual position sizes. The total_return in
            # BacktestResults is NET of costs. Do NOT deduct costs again here.
            # Just check if the net return is positive.
            net_return = backtest_results.total_return

            if net_return < 0:
                reason = (
                    f"Net return {net_return:.1%} < 0 "
                    f"(after costs, {backtest_results.total_trades} trades, "
                    f"asset_class={asset_class})"
                )
                logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                return False, reason

            # Minimum return-per-trade check: filters out strategies that churn
            # with tiny edge. A strategy with 10 trades and 0.5% total return
            # has 0.05% per trade — that's noise, not edge.
            # Interval-aware: 1h/4h/1d strategies have different hold periods and
            # per-trade return expectations — use interval-specific thresholds.
            # For crypto: crypto_1h=0.5%, crypto_4h=1.5%, crypto_1d=2.5%,
            # crypto=4% fallback for weekly/21d+ templates.
            min_rpt_config = config_thresholds.get('min_return_per_trade', {})
            if isinstance(min_rpt_config, dict):
                _strat_interval = ''
                if hasattr(strategy, 'metadata') and strategy.metadata:
                    _strat_interval = strategy.metadata.get('interval', '')
                if not _strat_interval and hasattr(strategy, 'rules') and isinstance(strategy.rules, dict):
                    _strat_interval = strategy.rules.get('interval', '')
                # Probe interval-specific key first; fall back to bare asset_class
                interval_key = f"{asset_class}_{_strat_interval}" if _strat_interval in ('1h', '2h', '4h', '1d') else None
                min_return_per_trade = (
                    min_rpt_config.get(interval_key, min_rpt_config.get(asset_class, 0.002))
                    if interval_key else min_rpt_config.get(asset_class, 0.002)
                )
                _rpt_source = interval_key if (interval_key and interval_key in min_rpt_config) else asset_class
            else:
                min_return_per_trade = 0.002
                _rpt_source = 'default'
            if backtest_results.total_trades > 0:
                return_per_trade = backtest_results.total_return / backtest_results.total_trades
                if return_per_trade < min_return_per_trade:
                    reason = (
                        f"Return/trade {return_per_trade:.3%} < {min_return_per_trade:.3%} min "
                        f"({_rpt_source}, {backtest_results.total_trades} trades, "
                        f"gross {backtest_results.total_return:.1%})"
                    )
                    logger.info(f"Strategy {strategy.name} failed activation: {reason}")
                    return False, reason

            logger.info(
                f"Cost check passed: net={net_return:.2%}, rpt={backtest_results.total_return/max(backtest_results.total_trades,1):.3%}, "
                f"asset_class={asset_class}, round_trip={round_trip_cost:.4%}"
            )
        except Exception as e:
            logger.debug(f"Could not check net-of-costs return: {e}")

        # Calculate confidence score
        confidence = self.calculate_confidence_score(strategy, backtest_results)

        logger.info(
            f"Strategy {strategy.name} passed activation criteria: "
            f"Tier={tier}, "
            f"Sharpe={backtest_results.sharpe_ratio:.2f} (threshold={sharpe_threshold}), "
            f"Drawdown={backtest_results.max_drawdown:.2%} (threshold={drawdown_threshold:.0%}), "
            f"WinRate={backtest_results.win_rate:.2%} (threshold={win_rate_threshold:.0%}), "
            f"Trades={backtest_results.total_trades}, "
            f"Confidence={confidence:.2f}, "
            f"MaxAllocation={max_allocation:.1f}%"
        )
        return True, None

    def auto_activate_strategy(
        self, strategy: Strategy, backtest_results: BacktestResults, allocation_pct: Optional[float] = None,
        market_context: Optional[Dict] = None
    ) -> None:
        """
        Automatically activate strategy in DEMO mode with tiered allocation.

        Uses tiered allocation based on Sharpe ratio and confidence score:
        - Tier 1 (Sharpe > 1.0): max 30% allocation
        - Tier 2 (Sharpe 0.5-1.0): max 15% allocation
        - Tier 3 (Sharpe 0.3-0.5): max 10% allocation

        Allocation is further adjusted by:
        - Confidence score (higher confidence = higher allocation)
        - Portfolio correlation (lower correlation = higher allocation)
        - Current portfolio allocation (ensure total <= 100%)
        - VIX level (higher VIX = lower allocation for risk management)

        Args:
            strategy: Strategy to activate
            backtest_results: Backtest results for the strategy
            allocation_pct: Optional custom allocation percentage. If None, calculates automatically.
            market_context: Optional market context with VIX data for position sizing

        Raises:
            ValueError: If activation fails or allocation exceeds 100%
        """
        # Get current active strategies
        active_strategies = self.strategy_engine.get_active_strategies()
        num_active = len(active_strategies)

        # Calculate allocation if not provided
        if allocation_pct is None:
            # Get tier and max allocation
            tier, max_allocation = self.get_activation_tier(backtest_results)

            if tier == 0:
                raise ValueError(
                    f"Cannot activate strategy {strategy.name}: "
                    f"Sharpe ratio {backtest_results.sharpe_ratio:.2f} < 0.3"
                )

            # Calculate confidence score
            confidence = self.calculate_confidence_score(strategy, backtest_results)

            # Conviction-based allocation: higher Sharpe/confidence = more capital
            # Tier 1 (Sharpe > 1.5): 3% allocation
            # Tier 2 (Sharpe 0.8-1.5): 2% allocation
            # Tier 3 (Sharpe 0.3-0.8): 1% allocation
            if backtest_results.sharpe_ratio > 1.5 and confidence > 0.7:
                allocation_pct = 3.0
            elif backtest_results.sharpe_ratio > 0.8:
                allocation_pct = 2.0
            else:
                allocation_pct = 1.0

            # Trade count confidence scaling: strategies with few test trades
            # get smaller allocations because the Sharpe is less reliable.
            # 10+ trades = full allocation, 2 trades = 20% of tier allocation.
            test_trades = backtest_results.total_trades if backtest_results.total_trades else 0
            trade_confidence = min(1.0, test_trades / 10.0)
            allocation_pct = max(0.5, allocation_pct * trade_confidence)  # Floor at 0.5%

            logger.info(
                f"Calculated allocation for {strategy.name}: "
                f"Tier={tier}, Confidence={confidence:.2f}, Sharpe={backtest_results.sharpe_ratio:.2f}, "
                f"Final={allocation_pct:.1f}% (conviction-based)"
            )
        
        # Adjust allocation based on VIX if market context provided
        if market_context:
            original_allocation = allocation_pct
            allocation_pct = self.adjust_allocation_for_vix(allocation_pct, market_context)
            logger.info(
                f"VIX-adjusted allocation for {strategy.name}: "
                f"{original_allocation:.1f}% → {allocation_pct:.1f}%"
            )

        logger.info(
            f"Auto-activating strategy {strategy.name} in DEMO mode "
            f"with {allocation_pct:.1f}% allocation "
            f"(current active strategies: {num_active})"
        )

        # Activate strategy in DEMO mode
        self.strategy_engine.activate_strategy(
            strategy_id=strategy.id, mode=TradingMode.DEMO, allocation_percent=allocation_pct
        )

        logger.info(
            f"Successfully activated strategy {strategy.name} "
            f"(total active: {num_active + 1})"
        )

    def check_retirement_triggers(self, strategy: Strategy) -> Optional[str]:
        """
        Check if a strategy should stop generating new signals.
        
        This is a lightweight check — it does NOT close positions.
        Positions are managed individually by trailing stops, SL/TP,
        and the position-level risk checks in the monitoring service.
        
        A strategy is retired only when it's clearly broken as a signal generator:
        - Regime mismatch (designed for trending, market is ranging for 30+ days)
        - Decay score hit 0 (accumulated penalties from multiple checks)
        
        Individual trade performance is handled at the position level.

        Args:
            strategy: Strategy to check

        Returns:
            Retirement reason if should retire, None otherwise
        """
        # Strategy-level retirement is now handled by:
        # 1. Decay score in monitoring service (gradual, multi-factor)
        # 2. Regime mismatch in autonomous cycle
        # 3. Idle demotion (no positions → BACKTESTED naturally)
        #
        # Position-level risk is handled by:
        # 1. Trailing stops (position_manager)
        # 2. SL/TP (eToro-side)
        # 3. Time-based exits (monitoring_service)
        # 4. Position health checks (monitoring_service._check_position_health)
        return None
    def detect_regime_changes_for_active_strategies(self) -> Dict[str, Dict]:
        """
        Detect regime changes for all active strategies.

        Runs daily to check if market conditions have changed significantly
        since strategy activation.

        Returns:
            Dict mapping strategy_id to regime change detection results
        """
        if not self.market_analyzer:
            logger.warning("MarketStatisticsAnalyzer not available, skipping regime detection")
            return {}

        logger.info("Detecting regime changes for active strategies...")

        # Get all active strategies
        session = self.strategy_engine.db.get_session()
        try:
            from src.models.orm import StrategyORM, RegimeHistoryORM

            active_strategies = session.query(StrategyORM).filter(
                StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
            ).all()

            results = {}

            for strategy_orm in active_strategies:
                try:
                    # Get activation regime and metrics from strategy metadata
                    metadata = strategy_orm.strategy_metadata or {}
                    activation_regime = metadata.get('activation_regime', 'UNKNOWN')
                    activation_metrics = metadata.get('activation_metrics', {})

                    if activation_regime == 'UNKNOWN' or not activation_metrics:
                        logger.warning(f"Strategy {strategy_orm.id} missing activation regime/metrics, skipping")
                        continue

                    # Detect regime change
                    change_result = self.market_analyzer.detect_regime_change(
                        strategy_id=strategy_orm.id,
                        activation_regime=activation_regime,
                        activation_metrics=activation_metrics,
                        symbols=strategy_orm.symbols
                    )

                    results[strategy_orm.id] = change_result

                    # Store in database
                    regime_history = RegimeHistoryORM(
                        strategy_id=strategy_orm.id,
                        detected_at=datetime.now(),
                        activation_regime=activation_regime,
                        current_regime=change_result['current_regime'],
                        regime_changed=1 if change_result['regime_changed'] else 0,
                        change_type=change_result['change_type'],
                        change_magnitude=change_result['change_magnitude'],
                        recommendation=change_result['recommendation'],
                        activation_metrics=activation_metrics,
                        current_metrics=change_result['current_metrics'],
                        details=change_result['details']
                    )
                    session.add(regime_history)

                    logger.info(f"Strategy {strategy_orm.name}: regime_changed={change_result['regime_changed']}")

                except Exception as e:
                    logger.error(f"Error detecting regime change for strategy {strategy_orm.id}: {e}")
                    continue

            session.commit()
            logger.info(f"Regime detection complete for {len(results)} strategies")
            return results

        except Exception as e:
            logger.error(f"Error in regime change detection: {e}")
            session.rollback()
            return {}
        finally:
            session.close()

    def apply_regime_based_adjustments(self, strategy: Strategy, regime_change: Dict) -> None:
        """
        Apply adjustments to strategy based on regime change.

        Adjustments:
        - Volatility spike (>50%): Reduce position sizes by 30%
        - Trend reversal: Pause trend-following strategies
        - Correlation spike: Reduce correlated strategy exposure

        Args:
            strategy: Strategy to adjust
            regime_change: Regime change detection result
        """
        # Check for manual override
        if self.regime_change_override.get(strategy.id, False):
            logger.info(f"Strategy {strategy.name} has manual override, skipping adjustments")
            return

        if not regime_change['regime_changed']:
            return

        change_type = regime_change['change_type']
        recommendation = regime_change['recommendation']

        logger.info(f"Applying regime-based adjustments for {strategy.name}")
        logger.info(f"  Change type: {change_type}")
        logger.info(f"  Recommendation: {recommendation}")

        session = self.strategy_engine.db.get_session()
        try:
            from src.models.orm import StrategyORM

            strategy_orm = session.query(StrategyORM).filter(
                StrategyORM.id == strategy.id
            ).first()

            if not strategy_orm:
                logger.error(f"Strategy {strategy.id} not found in database")
                return

            metadata = strategy_orm.strategy_metadata or {}
            adjustments = metadata.get('regime_adjustments', [])

            # Volatility spike: Reduce position sizes by 30%
            if change_type == 'volatility_spike':
                magnitude = regime_change['change_magnitude']
                reduction_pct = min(0.30, (magnitude - 1.0) * 0.20)  # Scale reduction with magnitude

                # Update allocation
                original_allocation = strategy_orm.allocation_percent
                new_allocation = original_allocation * (1.0 - reduction_pct)
                strategy_orm.allocation_percent = new_allocation

                adjustment = {
                    'timestamp': datetime.now().isoformat(),
                    'type': 'position_size_reduction',
                    'reason': f'Volatility increased {magnitude:.1f}x',
                    'original_allocation': original_allocation,
                    'new_allocation': new_allocation,
                    'reduction_pct': reduction_pct
                }
                adjustments.append(adjustment)

                logger.warning(f"  → Reduced allocation from {original_allocation:.1%} to {new_allocation:.1%}")

            # Trend reversal: Retire trend-following strategies
            elif change_type in ['trend_reversal_down', 'trend_reversal_up']:
                # Check if strategy is trend-following
                strategy_type = metadata.get('strategy_type', '')
                if 'momentum' in strategy_type.lower() or 'trend' in strategy_type.lower():
                    # Retire strategy (no PAUSED status available)
                    strategy_orm.status = StrategyStatus.RETIRED

                    adjustment = {
                        'timestamp': datetime.now().isoformat(),
                        'type': 'strategy_retired',
                        'reason': f'Trend reversal detected: {change_type}',
                        'original_status': 'DEMO'
                    }
                    adjustments.append(adjustment)

                    logger.warning(f"  → Retired trend-following strategy due to {change_type}")

            # Regime mismatch: Monitor for 30 days, then retire
            elif change_type == 'regime_mismatch':
                # Check how long mismatch has persisted
                mismatch_days = 0
                for adj in adjustments:
                    if adj.get('type') == 'regime_mismatch_detected':
                        first_detected = datetime.fromisoformat(adj['timestamp'])
                        mismatch_days = (datetime.now() - first_detected).days
                        break

                if mismatch_days == 0:
                    # First detection
                    adjustment = {
                        'timestamp': datetime.now().isoformat(),
                        'type': 'regime_mismatch_detected',
                        'reason': f"Strategy designed for {regime_change['activation_metrics'].get('regime', 'UNKNOWN')} but market is {regime_change['current_regime']}",
                        'days_elapsed': 0
                    }
                    adjustments.append(adjustment)
                    logger.info(f"  → Regime mismatch detected, monitoring for 30 days")

                elif mismatch_days >= 30:
                    # Retire strategy after 30 days of mismatch
                    logger.warning(f"  → Regime mismatch persisted for {mismatch_days} days, retiring strategy")
                    # Will be handled by check_retirement_triggers_with_regime

            # Save adjustments
            metadata['regime_adjustments'] = adjustments
            strategy_orm.strategy_metadata = metadata
            session.commit()

            logger.info(f"  ✓ Adjustments applied and saved")

        except Exception as e:
            logger.error(f"Error applying regime adjustments: {e}")
            session.rollback()
        finally:
            session.close()

    def check_retirement_triggers_with_regime(self, strategy: Strategy) -> Optional[str]:
        """
        Check retirement triggers including regime change criteria.

        Extends check_retirement_triggers with regime-based retirement:
        - Strategy designed for TRENDING but market RANGING for 30+ days
        - Strategy designed for LOW_VOL but volatility increased 2x for 14+ days

        Args:
            strategy: Strategy to check

        Returns:
            Retirement reason if should retire, None otherwise
        """
        # First check standard retirement triggers
        standard_reason = self.check_retirement_triggers(strategy)
        if standard_reason:
            return standard_reason

        # Check regime-based retirement
        if not self.market_analyzer:
            return None

        session = self.strategy_engine.db.get_session()
        try:
            from src.models.orm import StrategyORM, RegimeHistoryORM

            strategy_orm = session.query(StrategyORM).filter(
                StrategyORM.id == strategy.id
            ).first()

            if not strategy_orm:
                return None

            metadata = strategy_orm.strategy_metadata or {}
            activation_regime = metadata.get('activation_regime', 'UNKNOWN')

            # Get recent regime history (last 30 days)
            from datetime import timedelta
            thirty_days_ago = datetime.now() - timedelta(days=30)
            fourteen_days_ago = datetime.now() - timedelta(days=14)

            recent_history = session.query(RegimeHistoryORM).filter(
                RegimeHistoryORM.strategy_id == strategy.id,
                RegimeHistoryORM.detected_at >= thirty_days_ago
            ).order_by(RegimeHistoryORM.detected_at.desc()).all()

            if not recent_history:
                return None

            # Check for persistent regime mismatch (30+ days)
            if 'TRENDING' in activation_regime:
                # Count days where market was RANGING
                ranging_days = sum(
                    1 for h in recent_history
                    if 'RANGING' in h.current_regime and h.regime_changed
                )

                if ranging_days >= 30:
                    reason = (
                        f"Strategy designed for {activation_regime} but market has been "
                        f"RANGING for {ranging_days} days"
                    )
                    logger.info(f"Strategy {strategy.name} regime retirement trigger: {reason}")
                    return reason

            elif 'RANGING' in activation_regime:
                # Count days where market was TRENDING
                trending_days = sum(
                    1 for h in recent_history
                    if 'TRENDING' in h.current_regime and h.regime_changed
                )

                if trending_days >= 30:
                    reason = (
                        f"Strategy designed for {activation_regime} but market has been "
                        f"TRENDING for {trending_days} days"
                    )
                    logger.info(f"Strategy {strategy.name} regime retirement trigger: {reason}")
                    return reason

            # Check for persistent high volatility (14+ days with 2x increase)
            if 'LOW_VOL' in activation_regime:
                recent_14d = [h for h in recent_history if h.detected_at >= fourteen_days_ago]

                high_vol_days = sum(
                    1 for h in recent_14d
                    if h.change_type == 'volatility_spike' and h.change_magnitude >= 2.0
                )

                if high_vol_days >= 14:
                    reason = (
                        f"Strategy designed for LOW_VOL but volatility has been "
                        f"2x+ higher for {high_vol_days} days"
                    )
                    logger.info(f"Strategy {strategy.name} regime retirement trigger: {reason}")
                    return reason

            return None

        except Exception as e:
            logger.error(f"Error checking regime retirement triggers: {e}")
            return None
        finally:
            session.close()

    def set_regime_change_override(self, strategy_id: str, override: bool) -> None:
        """
        Set manual override for regime change adjustments.

        Args:
            strategy_id: Strategy identifier
            override: True to disable automatic adjustments, False to enable
        """
        self.regime_change_override[strategy_id] = override
        logger.info(f"Regime change override for {strategy_id}: {override}")

    def auto_retire_strategy(self, strategy: Strategy, reason: str) -> None:
        """
        Legacy method — kept for backward compatibility.
        
        Strategy-level retirement is no longer used. Risk management
        happens at the position level (trailing stops, SL/TP, position
        health checks). Strategies naturally cycle through DEMO → BACKTESTED
        when they have no open positions.

        Args:
            strategy: Strategy to retire
            reason: Reason (logged only)
        """
        logger.info(f"Strategy {strategy.name} flagged: {reason} (no action — risk managed at position level)")

    def _close_strategy_positions(self, strategy_id: str) -> None:
        """
        Close all open positions for a strategy and cancel pending/submitted orders.

        If an eToro client is available, submits close orders directly.
        Otherwise, falls back to setting pending_closure=True so that
        the monitoring service (11.8.1) will process them automatically.

        After submitting close orders, waits up to 30s to verify positions
        are closed or pending. If any fail, logs error but does NOT block
        strategy retirement — the monitoring service will handle stragglers.

        Args:
            strategy_id: ID of strategy whose positions should be closed
        """
        import uuid
        from src.models.orm import PositionORM, OrderORM
        from src.models.enums import (
            PositionSide, OrderSide, OrderType, OrderStatus,
        )

        session = self.strategy_engine.db.get_session()
        try:
            # ── Step 1: Cancel all PENDING and SUBMITTED orders for this strategy ──
            pending_orders = (
                session.query(OrderORM)
                .filter(
                    OrderORM.strategy_id == strategy_id,
                    OrderORM.status == OrderStatus.PENDING,
                )
                .all()
            )

            if pending_orders:
                logger.info(
                    f"Cancelling {len(pending_orders)} pending/submitted orders "
                    f"for retiring strategy {strategy_id}"
                )
                for order in pending_orders:
                    try:
                        if order.etoro_order_id and self.etoro_client:
                            try:
                                self.etoro_client.cancel_order(order.etoro_order_id)
                            except Exception as api_err:
                                logger.warning(
                                    f"Failed to cancel order {order.id} via eToro API: {api_err}"
                                )
                        order.status = OrderStatus.CANCELLED
                        logger.info(
                            f"Cancelled order {order.id} ({order.symbol} {order.side.value}) "
                            f"— strategy retiring"
                        )
                    except Exception as e:
                        logger.error(f"Error cancelling order {order.id}: {e}")
                session.commit()

            # ── Step 2: Query all open positions for this strategy ──
            open_positions = (
                session.query(PositionORM)
                .filter(
                    PositionORM.strategy_id == strategy_id,
                    PositionORM.closed_at.is_(None),
                )
                .all()
            )

            if not open_positions:
                logger.info(f"No open positions found for strategy {strategy_id}")
                return

            logger.info(
                f"Closing {len(open_positions)} open positions for strategy {strategy_id}"
            )

            # ── Step 3: Submit close orders or fall back to pending_closure ──
            submitted_order_ids: list[str] = []

            for position in open_positions:
                try:
                    if self.etoro_client:
                        # Direct close via eToro API
                        side = (
                            OrderSide.SELL
                            if position.side == PositionSide.LONG
                            else OrderSide.BUY
                        )
                        order_id = str(uuid.uuid4())

                        # Persist order record first
                        # Use invested_amount for the order quantity (dollar value).
                        # position.quantity is unreliable — for crypto it can be units,
                        # for stocks it can be shares. invested_amount is always dollars.
                        close_qty = getattr(position, 'invested_amount', None) or 0
                        if close_qty <= 0:
                            # Fallback: estimate, but sanity-check
                            if position.quantity and position.entry_price and position.entry_price > 0:
                                estimated = abs(position.quantity * position.entry_price)
                                if estimated > 150000:
                                    logger.warning(
                                        f"Close qty for {position.symbol} looks wrong: "
                                        f"qty={position.quantity} × price={position.entry_price} = ${estimated:,.0f}. "
                                        f"Falling back to unrealized_pnl-based estimate."
                                    )
                                    close_qty = 10000  # Safe default — eToro close_position ignores amount anyway
                                else:
                                    close_qty = estimated
                            else:
                                close_qty = 10000  # Safe default
                        order_orm = OrderORM(
                            id=order_id,
                            strategy_id=position.strategy_id,
                            symbol=position.symbol,
                            side=side,
                            order_type=OrderType.MARKET,
                            quantity=abs(close_qty),
                            status=OrderStatus.PENDING,
                            order_action='retirement',
                        )
                        session.add(order_orm)
                        session.flush()

                        try:
                            # Use close_position API — actually closes the position on eToro
                            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
                            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(position.symbol)
                            self.etoro_client.close_position(position.etoro_position_id, instrument_id=instrument_id)
                            order_orm.status = OrderStatus.FILLED
                            order_orm.submitted_at = datetime.now()
                            order_orm.filled_at = datetime.now()

                            # Mark position as closed
                            position.closed_at = datetime.now()
                            # Calculate realized PnL from price difference
                            entry = position.entry_price or 0
                            current = position.current_price or entry
                            invested = getattr(position, 'invested_amount', None) or close_qty or 0
                            if entry > 0 and invested > 0:
                                side_str = str(position.side).upper() if position.side else 'LONG'
                                if 'SHORT' in side_str or 'SELL' in side_str:
                                    calculated_pnl = invested * (entry - current) / entry
                                else:
                                    calculated_pnl = invested * (current - entry) / entry
                                position.realized_pnl = (position.realized_pnl or 0) + calculated_pnl
                            else:
                                position.realized_pnl = (position.realized_pnl or 0) + (position.unrealized_pnl or 0)
                            position.unrealized_pnl = 0.0
                            position.pending_closure = False

                            position.close_order_id = order_id
                            position.close_attempts = (position.close_attempts or 0) + 1
                            submitted_order_ids.append(order_id)

                            # Log to trade journal for performance feedback loop
                            try:
                                from src.analytics.trade_journal import TradeJournal
                                journal = TradeJournal(self.strategy_engine.db)
                                side_str = str(position.side).upper() if position.side else 'LONG'
                                is_long = 'LONG' in side_str or 'BUY' in side_str
                                journal.log_entry(
                                    trade_id=str(position.id),
                                    strategy_id=position.strategy_id or "unknown",
                                    symbol=position.symbol,
                                    entry_time=position.opened_at or position.closed_at,
                                    entry_price=position.entry_price or 0,
                                    entry_size=getattr(position, 'invested_amount', None) or close_qty or 0,
                                    entry_reason="autonomous_signal",
                                    order_side="BUY" if is_long else "SELL",
                                )
                                journal.log_exit(
                                    trade_id=str(position.id),
                                    exit_time=position.closed_at,
                                    exit_price=position.current_price,
                                    exit_reason="strategy_retired",
                                    symbol=position.symbol,
                                )
                            except Exception as je:
                                logger.debug(f"Could not log exit to trade journal for {position.symbol}: {je}")

                            logger.info(
                                f"Closed position {position.id} ({position.symbol} "
                                f"{position.side.value}) on eToro via close_position API"
                            )
                        except Exception as api_err:
                            order_orm.status = OrderStatus.FAILED
                            logger.error(
                                f"eToro API error closing position {position.id}: {api_err}"
                            )
                            # Fall back to pending_closure for this position
                            position.pending_closure = True
                            position.closure_reason = "Strategy retired (close order failed)"
                            logger.info(
                                f"Flagged position {position.id} as pending_closure "
                                f"(fallback after API error)"
                            )
                    else:
                        # No eToro client — flag for monitoring service (11.8.1)
                        position.pending_closure = True
                        position.closure_reason = "Strategy retired"
                        logger.info(
                            f"Flagged position {position.id} ({position.symbol}) as "
                            f"pending_closure — no eToro client available"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to close position {position.id}: {e}", exc_info=True
                    )
                    # Ensure the position is at least flagged for later processing
                    try:
                        position.pending_closure = True
                        position.closure_reason = "Strategy retired (error during closure)"
                    except Exception:
                        pass

            session.commit()

            # ── Step 4: Verification — wait up to 30s for submitted orders ──
            if submitted_order_ids:
                logger.info(
                    f"Verifying {len(submitted_order_ids)} close orders "
                    f"(waiting up to 30s)..."
                )
                deadline = time.time() + 30
                remaining_ids = set(submitted_order_ids)

                while remaining_ids and time.time() < deadline:
                    time.sleep(2)
                    for oid in list(remaining_ids):
                        order = session.query(OrderORM).filter_by(id=oid).first()
                        if order and order.status in (
                            OrderStatus.FILLED,
                            OrderStatus.CANCELLED,
                            OrderStatus.FAILED,
                        ):
                            remaining_ids.discard(oid)

                    # Refresh session to pick up external updates
                    session.expire_all()

                if remaining_ids:
                    logger.warning(
                        f"{len(remaining_ids)} close orders still pending after 30s "
                        f"for strategy {strategy_id}. "
                        f"Monitoring service will handle remaining positions."
                    )
                    # Flag any positions whose close orders are still pending
                    for oid in remaining_ids:
                        order = session.query(OrderORM).filter_by(id=oid).first()
                        if order:
                            pos = (
                                session.query(PositionORM)
                                .filter_by(close_order_id=oid)
                                .first()
                            )
                            if pos and not pos.pending_closure:
                                pos.pending_closure = True
                                pos.closure_reason = (
                                    "Strategy retired (close order still pending)"
                                )
                    session.commit()
                else:
                    logger.info(
                        f"All close orders resolved for strategy {strategy_id}"
                    )

        except Exception as e:
            logger.error(
                f"Error in _close_strategy_positions for {strategy_id}: {e}",
                exc_info=True,
            )
            session.rollback()
        finally:
            session.close()

    def calculate_portfolio_metrics(
        self, strategies: List[Strategy], returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> Dict:
        """
        Calculate portfolio-level performance metrics.

        Args:
            strategies: List of active strategies
            returns_data: Optional dict mapping strategy_id -> daily returns Series.
                         If None, metrics will be calculated from strategy performance only.

        Returns:
            Dict containing portfolio metrics (Sharpe, drawdown, correlation, diversification)
        """
        return self.risk_manager.calculate_portfolio_metrics(strategies, returns_data or {})

    def optimize_allocations(
        self, strategies: List[Strategy], returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> Dict[str, float]:
        """
        Optimize portfolio allocations for risk-adjusted returns.

        Args:
            strategies: List of strategies to allocate
            returns_data: Optional dict mapping strategy_id -> daily returns Series

        Returns:
            Dict mapping strategy_id -> allocation percentage (0-100)
        """
        return self.risk_manager.optimize_allocations(strategies, returns_data or {})

    def rebalance_portfolio(
        self, strategies: List[Strategy], returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> None:
        """
        Rebalance portfolio allocations based on optimized allocations.

        Args:
            strategies: List of active strategies
            returns_data: Optional dict mapping strategy_id -> daily returns Series
        """
        if not strategies:
            logger.info("No strategies to rebalance")
            return

        # Get optimized allocations
        optimized_allocations = self.optimize_allocations(strategies, returns_data)

        logger.info(f"Rebalancing portfolio with {len(strategies)} strategies")

        # Update each strategy's allocation
        for strategy in strategies:
            new_allocation = optimized_allocations.get(strategy.id, 0.0)

            if new_allocation != strategy.allocation_percent:
                logger.info(
                    f"Updating {strategy.name} allocation: "
                    f"{strategy.allocation_percent:.1f}% -> {new_allocation:.1f}%"
                )

                # Update allocation in database
                self.strategy_engine.update_strategy_allocation(strategy.id, new_allocation)

        logger.info("Portfolio rebalancing complete")

    def get_vix_position_size_multiplier(self, vix: float) -> float:
        """
        Calculate position size multiplier based on VIX level.
        
        VIX Levels:
        - VIX < 15 (Low fear): 100% of normal position size
        - VIX 15-20 (Moderate): 75% of normal position size
        - VIX 20-25 (Elevated): 50% of normal position size
        - VIX > 25 (High fear): 25% of normal position size
        
        Args:
            vix: Current VIX level
            
        Returns:
            Position size multiplier (0.25 to 1.0)
        """
        if vix < 15:
            multiplier = 1.0
            logger.info(f"VIX={vix:.1f} (low fear) → 100% position size")
        elif vix < 20:
            multiplier = 0.75
            logger.info(f"VIX={vix:.1f} (moderate) → 75% position size")
        elif vix < 25:
            multiplier = 0.50
            logger.info(f"VIX={vix:.1f} (elevated) → 50% position size")
        else:
            multiplier = 0.25
            logger.info(f"VIX={vix:.1f} (high fear) → 25% position size")
        
        return multiplier
    
    def adjust_allocation_for_vix(self, allocation_pct: float, market_context: Dict) -> float:
        """
        Adjust strategy allocation based on VIX level.
        
        Args:
            allocation_pct: Base allocation percentage
            market_context: Market context with VIX data
            
        Returns:
            Adjusted allocation percentage
        """
        vix = market_context.get('vix', 20.0)
        multiplier = self.get_vix_position_size_multiplier(vix)
        
        adjusted_allocation = allocation_pct * multiplier
        
        logger.info(
            f"Allocation adjustment: {allocation_pct:.1f}% × {multiplier:.2f} "
            f"(VIX={vix:.1f}) = {adjusted_allocation:.1f}%"
        )
        
        return adjusted_allocation

    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_pct: float,
        risk_per_trade_pct: float,
        atr: float
    ) -> float:
        """
        Calculate position size based on volatility (ATR) and risk per trade.

        Uses volatility-based position sizing to adjust for market conditions:
        - Base position size calculated from risk per trade and stop loss
        - Adjusted by ATR to reduce size in high volatility
        - Ensures consistent risk across different market conditions

        Formula:
        1. Risk amount = Portfolio * Risk%
        2. Risk per share = Entry * Stop%
        3. Number of shares = Risk amount / Risk per share
        4. Base position value = Number of shares * Entry price
        5. Volatility adjustment = 1.0 / (1.0 + ATR/Entry)
        6. Final position value = Base position value * Volatility adjustment

        Args:
            portfolio_value: Current portfolio value in dollars
            entry_price: Entry price for the position
            stop_loss_pct: Stop loss percentage (e.g., 0.02 for 2%)
            risk_per_trade_pct: Maximum risk per trade as percentage (e.g., 0.01 for 1%)
            atr: Average True Range value for volatility measurement

        Returns:
            Position size in dollars

        Example:
            >>> pm = PortfolioManager(strategy_engine)
            >>> # Portfolio: $100,000, Entry: $100, Stop: 2%, Risk: 1%, ATR: $2
            >>> size = pm.calculate_position_size(100000, 100, 0.02, 0.01, 2.0)
            >>> # Risk amount: $1,000
            >>> # Risk per share: $2 (2% of $100)
            >>> # Shares: 500 ($1,000 / $2)
            >>> # Base position: $50,000 (500 * $100)
            >>> # Volatility adj: 0.98 (1.0 / (1.0 + 2/100))
            >>> # Final: $49,000 ($50,000 * 0.98)
        """
        # Calculate risk amount in dollars
        risk_amount = portfolio_value * risk_per_trade_pct

        # Calculate risk per share based on stop loss
        risk_per_share = entry_price * stop_loss_pct

        # Prevent division by zero
        if risk_per_share <= 0:
            logger.warning(
                f"Invalid risk_per_share={risk_per_share:.4f} "
                f"(entry_price={entry_price:.2f}, stop_loss_pct={stop_loss_pct:.4f}). "
                f"Returning 0 position size."
            )
            return 0.0

        # Calculate number of shares based on risk
        num_shares = risk_amount / risk_per_share

        # Calculate base position value (in dollars)
        base_position_value = num_shares * entry_price

        # Adjust for volatility (reduce size in high volatility)
        # ATR as percentage of price
        atr_pct = atr / entry_price if entry_price > 0 else 0

        # Volatility adjustment factor: reduces size when ATR is high relative to price
        # When ATR = 0: adjustment = 1.0 (no reduction)
        # When ATR = entry_price: adjustment = 0.5 (50% reduction)
        # When ATR = 2*entry_price: adjustment = 0.33 (67% reduction)
        volatility_adjustment = 1.0 / (1.0 + atr_pct)

        # Calculate final adjusted position value
        adjusted_position_value = base_position_value * volatility_adjustment

        logger.info(
            f"Position size calculation: "
            f"portfolio=${portfolio_value:,.0f}, entry=${entry_price:.2f}, "
            f"stop={stop_loss_pct:.2%}, risk={risk_per_trade_pct:.2%}, ATR=${atr:.2f} ({atr_pct:.2%})"
        )
        logger.info(
            f"  Risk amount: ${risk_amount:,.0f}, Risk per share: ${risk_per_share:.2f}"
        )
        logger.info(
            f"  Number of shares: {num_shares:.0f}"
        )
        logger.info(
            f"  Base position value: ${base_position_value:,.0f} "
            f"({num_shares:.0f} shares × ${entry_price:.2f})"
        )
        logger.info(
            f"  Volatility adjustment: {volatility_adjustment:.3f} "
            f"(1.0 / (1.0 + {atr_pct:.3f}))"
        )
        logger.info(f"  Final adjusted position value: ${adjusted_position_value:,.0f}")

        return adjusted_position_value



    def check_performance_degradation(
        self,
        strategy: Strategy,
        trades_df: pd.DataFrame,
        equity_curve: pd.Series
    ) -> Optional[DegradationAlert]:
        """
        Check for performance degradation in an active strategy.
        
        Calculates rolling metrics and compares to backtest baseline to detect
        early warning signs of strategy failure.
        
        Args:
            strategy: Strategy to check
            trades_df: DataFrame with trade history
            equity_curve: Series with daily equity values
            
        Returns:
            DegradationAlert if degradation detected, None otherwise
        """
        # Check if manual override is set
        if self.degradation_overrides.get(strategy.id, False):
            logger.info(f"Degradation monitoring disabled for {strategy.name} (manual override)")
            return None
        
        # Need backtest results as baseline
        if not strategy.backtest_results:
            logger.warning(f"No backtest results for {strategy.name}, cannot check degradation")
            return None
        
        # Calculate rolling metrics
        try:
            rolling_metrics = self.degradation_monitor.calculate_rolling_metrics(
                strategy, trades_df, equity_curve
            )
            
            logger.info(
                f"Rolling metrics for {strategy.name}: "
                f"Sharpe 7d={rolling_metrics.sharpe_7d:.2f}, "
                f"14d={rolling_metrics.sharpe_14d:.2f}, "
                f"30d={rolling_metrics.sharpe_30d:.2f}"
            )
            
            # Detect degradation
            alert = self.degradation_monitor.detect_degradation(
                strategy, rolling_metrics, strategy.backtest_results
            )
            
            if alert:
                # Store in database
                self.degradation_monitor.store_degradation_event(
                    alert, rolling_metrics, action_taken=None
                )
            
            return alert
            
        except Exception as e:
            logger.error(f"Failed to check degradation for {strategy.name}: {e}")
            return None
    
    def apply_degradation_response(
        self,
        strategy: Strategy,
        alert: DegradationAlert
    ) -> str:
        """
        Apply graduated response to performance degradation.
        
        Tiered response based on severity:
        - Severity 0.3-0.5: Reduce position size by 50%
        - Severity 0.5-0.7: Pause strategy, monitor for 7 days
        - Severity 0.7+: Retire strategy immediately
        
        Args:
            strategy: Strategy with degradation
            alert: Degradation alert with severity and details
            
        Returns:
            Action taken as string
        """
        action_taken = None
        
        if alert.recommended_action == 'retire':
            # Severity 0.7+: Retire immediately
            logger.warning(
                f"CRITICAL degradation for {strategy.name} (severity={alert.severity:.2f}). "
                f"Retiring strategy immediately."
            )
            try:
                self.auto_retire_strategy(
                    strategy,
                    reason=f"Performance degradation: {alert.details}"
                )
                action_taken = 'retired'
            except ValueError as e:
                # Strategy not found in database (e.g., in tests)
                logger.warning(f"Could not retire strategy in database: {e}")
                # Still mark as retired in the strategy object
                strategy.status = StrategyStatus.RETIRED
                strategy.retired_at = datetime.now()
                action_taken = 'retired'
            
        elif alert.recommended_action == 'pause':
            # Severity 0.5-0.7: Pause for 7 days
            logger.warning(
                f"MODERATE degradation for {strategy.name} (severity={alert.severity:.2f}). "
                f"Pausing strategy for 7 days."
            )
            # Update strategy status to paused
            strategy.status = StrategyStatus.PAUSED
            strategy.metadata['paused_at'] = datetime.now().isoformat()
            strategy.metadata['pause_reason'] = f"Performance degradation: {alert.details}"
            strategy.metadata['pause_duration_days'] = 7
            
            # Save to database
            try:
                with self.strategy_engine.db.get_session() as session:
                    from src.models.orm import StrategyORM
                    strategy_orm = session.query(StrategyORM).filter_by(id=strategy.id).first()
                    if strategy_orm:
                        strategy_orm.status = StrategyStatus.PAUSED.value
                        strategy_orm.metadata = strategy.metadata
                        session.commit()
                        logger.info(f"Strategy {strategy.name} paused in database")
            except Exception as e:
                logger.error(f"Failed to pause strategy in database: {e}")
            
            action_taken = 'paused'
            
        elif alert.recommended_action == 'reduce_size':
            # Severity 0.3-0.5: Reduce position size by 50%
            logger.warning(
                f"MINOR degradation for {strategy.name} (severity={alert.severity:.2f}). "
                f"Reducing position size by 50%."
            )
            # Reduce allocation
            original_allocation = strategy.allocation_percent
            new_allocation = original_allocation * 0.5
            strategy.allocation_percent = new_allocation
            strategy.metadata['degradation_size_reduction'] = True
            strategy.metadata['original_allocation'] = original_allocation
            strategy.metadata['reduced_at'] = datetime.now().isoformat()
            
            # Save to database
            try:
                with self.strategy_engine.db.get_session() as session:
                    from src.models.orm import StrategyORM
                    strategy_orm = session.query(StrategyORM).filter_by(id=strategy.id).first()
                    if strategy_orm:
                        strategy_orm.allocation_percent = new_allocation
                        strategy_orm.metadata = strategy.metadata
                        session.commit()
                        logger.info(
                            f"Strategy {strategy.name} allocation reduced: "
                            f"{original_allocation:.1f}% → {new_allocation:.1f}%"
                        )
            except Exception as e:
                logger.error(f"Failed to reduce allocation in database: {e}")
            
            action_taken = 'reduced_size'
        
        # Update degradation event with action taken
        if action_taken:
            try:
                with self.strategy_engine.db.get_session() as session:
                    from src.strategy.performance_degradation_monitor import PerformanceDegradationHistoryORM
                    # Get most recent event for this strategy
                    event = session.query(PerformanceDegradationHistoryORM).filter_by(
                        strategy_id=strategy.id
                    ).order_by(PerformanceDegradationHistoryORM.detected_at.desc()).first()
                    
                    if event:
                        event.action_taken = action_taken
                        session.commit()
            except Exception as e:
                logger.error(f"Failed to update degradation event: {e}")
        
        return action_taken
    
    def monitor_all_active_strategies_for_degradation(self) -> Dict[str, DegradationAlert]:
        """
        Monitor all active strategies for performance degradation.
        
        Should be called periodically (e.g., daily) to check for early warning signs.
        
        Returns:
            Dictionary mapping strategy_id to DegradationAlert (if any)
        """
        logger.info("Checking all active strategies for performance degradation...")
        
        alerts = {}
        
        # Get all active strategies
        try:
            with self.strategy_engine.db.get_session() as session:
                from src.models.orm import StrategyORM
                active_strategies = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([
                        StrategyStatus.ACTIVE.value,
                        StrategyStatus.DEMO.value
                    ])
                ).all()
                
                logger.info(f"Found {len(active_strategies)} active strategies to monitor")
                
                for strategy_orm in active_strategies:
                    # Convert to Strategy dataclass
                    strategy = self.strategy_engine._orm_to_strategy(strategy_orm)
                    
                    # Get trade history and equity curve
                    # This would need to be implemented based on your data storage
                    # For now, we'll skip if we can't get the data
                    try:
                        # Get trades from backtest results or live trading
                        if strategy.backtest_results and strategy.backtest_results.trades is not None:
                            trades_df = strategy.backtest_results.trades
                            equity_curve = strategy.backtest_results.equity_curve
                            
                            # Check for degradation
                            alert = self.check_performance_degradation(
                                strategy, trades_df, equity_curve
                            )
                            
                            if alert:
                                alerts[strategy.id] = alert
                                
                                # Apply graduated response
                                action = self.apply_degradation_response(strategy, alert)
                                logger.warning(
                                    f"Degradation response for {strategy.name}: {action}"
                                )
                        else:
                            logger.debug(
                                f"No trade data available for {strategy.name}, skipping degradation check"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to check degradation for {strategy.name}: {e}"
                        )
                        continue
                
        except Exception as e:
            logger.error(f"Failed to monitor strategies for degradation: {e}")
        
        if alerts:
            logger.warning(
                f"Performance degradation detected in {len(alerts)} strategies"
            )
        else:
            logger.info("No performance degradation detected")
        
        return alerts
    
    def set_degradation_override(self, strategy_id: str, override: bool) -> None:
        """
        Set manual override for degradation monitoring.
        
        Args:
            strategy_id: Strategy ID
            override: True to disable monitoring, False to enable
        """
        self.degradation_overrides[strategy_id] = override
        logger.info(
            f"Degradation monitoring {'disabled' if override else 'enabled'} "
            f"for strategy {strategy_id}"
        )
