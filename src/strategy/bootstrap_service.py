"""Bootstrap Service for generating initial trading strategies."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import PerformanceMetrics, Strategy
from src.models.enums import StrategyStatus, TradingMode
from src.strategy.strategy_engine import BacktestResults, StrategyEngine

logger = logging.getLogger(__name__)


# Strategy templates for quick bootstrapping
STRATEGY_TEMPLATES = {
    "momentum": {
        "prompt": "Create a momentum strategy that buys stocks with strong upward price trends over the last 20 days and sells when momentum weakens",
        "symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
        "allocation": 30.0
    },
    "mean_reversion": {
        "prompt": "Create a mean reversion strategy that buys oversold stocks when RSI drops below 30 and sells when RSI rises above 70",
        "symbols": ["SPY", "QQQ", "IWM"],
        "allocation": 30.0
    },
    "breakout": {
        "prompt": "Create a breakout strategy that buys when price breaks above 52-week high with high volume and sells on stop loss",
        "symbols": ["NVDA", "AMD", "INTC"],
        "allocation": 30.0
    }
}


class BootstrapService:
    """Service for bootstrapping initial trading strategies."""
    
    def __init__(
        self,
        strategy_engine: StrategyEngine,
        llm_service: LLMService,
        market_data: MarketDataManager
    ):
        """
        Initialize BootstrapService.
        
        Args:
            strategy_engine: Strategy engine for creating and managing strategies
            llm_service: LLM service for strategy generation
            market_data: Market data manager for backtesting
        """
        self.strategy_engine = strategy_engine
        self.llm_service = llm_service
        self.market_data = market_data
        
        logger.info("BootstrapService initialized")
    
    def bootstrap_strategies(
        self,
        strategy_types: List[str] = None,
        auto_activate: bool = False,
        min_sharpe: float = 1.0,
        backtest_days: int = 90
    ) -> Dict[str, any]:
        """
        Bootstrap initial strategies with predefined templates.
        
        Generates 2-3 sample strategies with different trading approaches,
        automatically backtests each strategy, and optionally activates
        strategies that meet minimum performance thresholds.
        
        Args:
            strategy_types: List of strategy types to generate (default: all templates)
            auto_activate: Whether to automatically activate passing strategies
            min_sharpe: Minimum Sharpe ratio for auto-activation
            backtest_days: Number of days to backtest (default: 90)
        
        Returns:
            Dictionary with:
                - strategies: List of created Strategy objects
                - backtest_results: Dictionary mapping strategy_id to BacktestResults
                - activated: List of strategy_ids that were activated
                - summary: Summary statistics
        
        Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.6
        """
        logger.info(
            f"Starting bootstrap process: types={strategy_types}, "
            f"auto_activate={auto_activate}, min_sharpe={min_sharpe}"
        )
        
        # Default to all strategy types if none specified
        if strategy_types is None:
            strategy_types = list(STRATEGY_TEMPLATES.keys())
        
        # Validate strategy types
        invalid_types = [t for t in strategy_types if t not in STRATEGY_TEMPLATES]
        if invalid_types:
            logger.warning(f"Invalid strategy types: {invalid_types}")
            strategy_types = [t for t in strategy_types if t in STRATEGY_TEMPLATES]
        
        if not strategy_types:
            logger.error("No valid strategy types provided")
            return {
                "strategies": [],
                "backtest_results": {},
                "activated": [],
                "summary": {
                    "total_generated": 0,
                    "total_backtested": 0,
                    "total_activated": 0,
                    "errors": ["No valid strategy types provided"]
                }
            }
        
        strategies = []
        backtest_results = {}
        activated = []
        errors = []
        
        # Generate and backtest each strategy type
        for strategy_type in strategy_types:
            try:
                logger.info(f"Generating {strategy_type} strategy...")
                
                # Get template
                template = STRATEGY_TEMPLATES[strategy_type]
                
                # Generate strategy using LLM
                strategy = self._generate_strategy_from_template(template)
                strategies.append(strategy)
                
                logger.info(f"Generated strategy: {strategy.name} (ID: {strategy.id})")
                
                # Backtest strategy
                logger.info(f"Backtesting {strategy.name}...")
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=backtest_days)
                
                try:
                    results = self.strategy_engine.backtest_strategy(
                        strategy, start_date, end_date
                    )
                    backtest_results[strategy.id] = results

                    # Explicit strategy-state persistence (2026-05-04).
                    # backtest_strategy() is now a pure compute primitive —
                    # callers that want to persist results on the strategy
                    # object must do so explicitly. For the CLI bootstrap
                    # path we treat this backtest as the strategy's official
                    # backtest (it IS the only one run in this codepath).
                    strategy.status = StrategyStatus.BACKTESTED
                    strategy.performance = PerformanceMetrics(
                        total_return=results.total_return,
                        sharpe_ratio=results.sharpe_ratio,
                        sortino_ratio=results.sortino_ratio,
                        max_drawdown=results.max_drawdown,
                        win_rate=results.win_rate,
                        avg_win=results.avg_win,
                        avg_loss=results.avg_loss,
                        total_trades=results.total_trades,
                    )
                    strategy.backtest_results = results

                    logger.info(
                        f"Backtest complete for {strategy.name}: "
                        f"return={results.total_return:.2%}, "
                        f"sharpe={results.sharpe_ratio:.2f}, "
                        f"trades={results.total_trades}"
                    )
                    
                    # Auto-activate if enabled and meets threshold
                    if auto_activate and results.sharpe_ratio >= min_sharpe:
                        logger.info(
                            f"Auto-activating {strategy.name} "
                            f"(Sharpe {results.sharpe_ratio:.2f} >= {min_sharpe})"
                        )
                        
                        try:
                            # Use allocation from template
                            allocation = template.get("allocation", 0.0)
                            
                            self.strategy_engine.activate_strategy(
                                strategy.id, TradingMode.DEMO, allocation_percent=allocation
                            )
                            activated.append(strategy.id)
                            
                            logger.info(
                                f"Activated {strategy.name} in DEMO mode "
                                f"with {allocation:.1f}% allocation"
                            )
                        
                        except Exception as e:
                            error_msg = f"Failed to activate {strategy.name}: {e}"
                            logger.error(error_msg)
                            errors.append(error_msg)
                    
                    elif auto_activate:
                        logger.info(
                            f"Skipping activation for {strategy.name} "
                            f"(Sharpe {results.sharpe_ratio:.2f} < {min_sharpe})"
                        )
                
                except Exception as e:
                    error_msg = f"Backtest failed for {strategy.name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            except Exception as e:
                error_msg = f"Failed to generate {strategy_type} strategy: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Build summary
        summary = {
            "total_generated": len(strategies),
            "total_backtested": len(backtest_results),
            "total_activated": len(activated),
            "errors": errors
        }
        
        # Log summary
        logger.info(
            f"Bootstrap complete: generated={summary['total_generated']}, "
            f"backtested={summary['total_backtested']}, "
            f"activated={summary['total_activated']}"
        )
        
        if errors:
            logger.warning(f"Bootstrap completed with {len(errors)} errors")
        
        return {
            "strategies": strategies,
            "backtest_results": backtest_results,
            "activated": activated,
            "summary": summary
        }
    
    def _generate_strategy_from_template(self, template: Dict) -> Strategy:
        """
        Generate strategy from template using LLM.
        
        Args:
            template: Strategy template with prompt, symbols, and allocation
        
        Returns:
            Generated Strategy object
        
        Raises:
            ValueError: If strategy generation fails
        """
        from src.models import RiskConfig
        
        # Build market context from template
        market_context = {
            "available_symbols": template["symbols"],
            "risk_config": RiskConfig()  # Use default risk config
        }
        
        # Try to generate strategy using LLM
        try:
            strategy = self.strategy_engine.generate_strategy(
                template["prompt"],
                market_context
            )
            return strategy
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}. Using template fallback.")
            # Fallback: Create strategy directly from template
            return self._create_strategy_from_template_fallback(template)

    def _create_strategy_from_template_fallback(self, template: Dict) -> Strategy:
        """
        Create strategy directly from template when LLM fails.
        
        Args:
            template: Strategy template with prompt, symbols, and allocation
        
        Returns:
            Strategy object created from template
        """
        import uuid
        from src.models import RiskConfig, PerformanceMetrics
        
        # Determine strategy type from prompt
        prompt_lower = template["prompt"].lower()
        if "momentum" in prompt_lower:
            name = "Momentum Strategy"
            description = "Buys stocks with strong upward price trends and sells when momentum weakens"
            rules = {
                "entry_conditions": [
                    "Price above 20-period SMA",
                    "RSI above 50"
                ],
                "exit_conditions": [
                    "Price below 20-period SMA"
                ],
                "indicators": ["SMA", "RSI"],
                "timeframe": "1d"
            }
        elif "mean reversion" in prompt_lower or "rsi" in prompt_lower:
            name = "Mean Reversion Strategy"
            description = "Buys oversold stocks when RSI drops below 30 and sells when RSI rises above 70"
            rules = {
                "entry_conditions": [
                    "RSI < 30",
                    "Price below 20-day moving average",
                    "Volume confirmation"
                ],
                "exit_conditions": [
                    "RSI > 70",
                    "Price above 20-day moving average",
                    "Take profit triggered"
                ],
                "indicators": ["RSI_14", "SMA_20", "Volume"],
                "timeframe": "1d"
            }
        elif "breakout" in prompt_lower:
            name = "Breakout Strategy"
            description = "Buys when price breaks above 52-week high with high volume"
            rules = {
                "entry_conditions": [
                    "Price > 52-week high",
                    "Volume > 2x average volume",
                    "Price momentum positive"
                ],
                "exit_conditions": [
                    "Stop loss at 2% below entry",
                    "Take profit at 4% above entry",
                    "Volume drops below average"
                ],
                "indicators": ["High_52w", "Volume", "Price_Change"],
                "timeframe": "1d"
            }
        else:
            name = "Generic Strategy"
            description = template["prompt"]
            rules = {
                "entry_conditions": ["Price momentum positive", "Volume confirmation"],
                "exit_conditions": ["Stop loss triggered", "Take profit triggered"],
                "indicators": ["SMA_20", "Volume"],
                "timeframe": "1d"
            }
        
        # Create strategy object
        strategy = Strategy(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            status=StrategyStatus.PROPOSED,
            rules=rules,
            symbols=template["symbols"],
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics()
        )
        
        # Save to database
        self.strategy_engine._save_strategy(strategy)
        
        logger.info(f"Created fallback strategy: {name} (ID: {strategy.id})")
        return strategy
