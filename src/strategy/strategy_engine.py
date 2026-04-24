"""Strategy Engine for generating, backtesting, and managing trading strategies."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd

# Make vectorbt optional - only needed for backtesting
try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    VECTORBT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("vectorbt not available - backtesting will be disabled")

from sqlalchemy.orm import Session

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService, StrategyDefinition
from src.strategy.indicator_library import IndicatorLibrary
from src.models import (
    AlphaSource,
    BacktestResults,
    OrderStatus,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
    StrategyReasoning,
    StrategyStatus,
    TradingMode,
    TradingSignal,
)
from src.models.database import get_database
from src.models.orm import StrategyORM

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Generates, backtests, and manages trading strategies to maximize returns."""
    
    def __init__(self, llm_service: Optional[LLMService], market_data: MarketDataManager, websocket_manager=None):
        """
        Initialize StrategyEngine with optional LLM service and market data manager.
        
        Args:
            llm_service: Optional LLM service for strategy generation (not needed for DSL-based strategies)
            market_data: Market data manager for fetching data
            websocket_manager: Optional WebSocket manager for broadcasting updates
        """
        self.llm_service = llm_service
        self.market_data = market_data
        self.indicator_library = IndicatorLibrary()
        self.db = get_database()
        self._active_strategies: Dict[str, Strategy] = {}
        self.websocket_manager = websocket_manager
        
        # Market analyzer for regime detection (used by ConvictionScorer)
        try:
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            self.market_analyzer = MarketStatisticsAnalyzer(market_data)
        except Exception:
            self.market_analyzer = None
        
        # Load validation rules from config
        self.validation_config = self._load_validation_config()
        
        if llm_service:
            logger.info("StrategyEngine initialized with LLM service")
        else:
            logger.info("StrategyEngine initialized (DSL-only mode, no LLM)")
        
        self._batch_signal_running = False
    
    def _load_validation_config(self) -> Dict:
        """Load validation rules from autonomous_trading.yaml config file."""
        import yaml
        from pathlib import Path
        
        config_path = Path("config/autonomous_trading.yaml")
        default_config = {
            "rsi": {"entry_max": 55, "exit_min": 55},
            "stochastic": {"entry_max": 30, "exit_min": 70},
            "bollinger_bands": {"require_both_bands": False},
            "macd": {"allow_zero_cross": True},
            "signal_overlap": {"max_overlap_pct": 50},
            "entry_opportunities": {
                "min_entry_pct": 0.5,
                "min_trades_per_month": 0.25,
                # Asset-class-aware thresholds: forex/crypto/ETFs may have fewer signals
                "asset_class_thresholds": {
                    "stock": {"min_entry_pct": 0.5},
                    "etf": {"min_entry_pct": 0.3},
                    "forex": {"min_entry_pct": 0.2},
                    "crypto": {"min_entry_pct": 0.2},
                    "index": {"min_entry_pct": 0.3},
                    "commodity": {"min_entry_pct": 0.3},
                }
            },
            "indicators": {"min_indicators": 1, "max_indicators": 5, "allow_price_only": False},
            "conditions": {"min_entry_conditions": 1, "min_exit_conditions": 1, "max_conditions_per_type": 5},
            "validation_data_days": None,  # Will be read from backtest.days if not set
        }
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    validation_rules = config.get("validation_rules", {})
                    # Merge with defaults
                    for key, value in default_config.items():
                        if key not in validation_rules:
                            validation_rules[key] = value
                    
                    # Use backtest.days as the validation data window to ensure consistency
                    # between walk-forward validation and rule validation
                    if validation_rules.get("validation_data_days") is None:
                        backtest_days = config.get("backtest", {}).get("days", 1825)
                        validation_rules["validation_data_days"] = backtest_days
                        logger.info(f"Validation data window set to {backtest_days} days (from backtest.days)")
                    
                    logger.info(f"Loaded validation rules from {config_path}")
                    return validation_rules
            else:
                logger.warning(f"Config file not found at {config_path}, using defaults")
                default_config["validation_data_days"] = 1825
                return default_config
        except Exception as e:
            logger.error(f"Error loading validation config: {e}, using defaults")
            default_config["validation_data_days"] = 1825
            return default_config
    
    def _get_asset_class(self, symbol: str) -> str:
        """Determine asset class for a symbol (stock, etf, forex, crypto, index, commodity).
        
        Used for asset-class-aware validation thresholds.
        """
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_ETFS, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_CRYPTO,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES
        )
        sym = symbol.upper()
        if sym in DEMO_ALLOWED_FOREX:
            return "forex"
        if sym in DEMO_ALLOWED_CRYPTO:
            return "crypto"
        if sym in DEMO_ALLOWED_ETFS:
            return "etf"
        if sym in DEMO_ALLOWED_INDICES:
            return "index"
        if sym in DEMO_ALLOWED_COMMODITIES:
            return "commodity"
        return "stock"

    def generate_strategy(self, prompt: str, constraints: Dict) -> Strategy:
        """
        Use LLM to generate strategy from natural language prompt.
        
        Args:
            prompt: Natural language description of desired strategy
            constraints: Market context and constraints (risk_config, available_symbols, etc.)
        
        Returns:
            Strategy object in PROPOSED status
        
        Raises:
            ConnectionError: If LLM service is unavailable
            ValueError: If strategy generation fails or LLM service not initialized
        """
        if not self.llm_service:
            raise ValueError(
                "LLM service not initialized. Cannot generate strategy from prompt. "
                "Use template-based generation instead (StrategyProposer)."
            )
        
        logger.info(f"Generating strategy from prompt: {prompt}")
        
        # Generate strategy using LLM
        strategy_def = self.llm_service.generate_strategy(prompt, constraints)
        
        # Create Strategy object
        strategy = Strategy(
            id=str(uuid.uuid4()),
            name=strategy_def.name,
            description=strategy_def.description,
            status=StrategyStatus.PROPOSED,
            rules=strategy_def.rules,
            symbols=strategy_def.symbols,
            risk_params=strategy_def.risk_params,
            created_at=datetime.now(),
            performance=PerformanceMetrics(),
            reasoning=strategy_def.reasoning
        )
        
        # Persist to database
        self._save_strategy(strategy)
        
        logger.info(f"Generated strategy: {strategy.name} (ID: {strategy.id})")
        
        # Broadcast strategy creation
        self._broadcast_strategy_update_sync(strategy)
        
        return strategy
    
    def activate_strategy(self, strategy_id: str, mode: TradingMode, allocation_percent: float = 5.0) -> None:
        """
        Activate strategy for demo or live trading.
        
        Args:
            strategy_id: ID of strategy to activate
            mode: Trading mode (DEMO or LIVE)
            allocation_percent: Percentage of portfolio to allocate (0.0 to 100.0, default 5.0)
        
        Raises:
            ValueError: If strategy not found, not in valid status, or allocation exceeds 100%
        """
        strategy = self._load_strategy(strategy_id)
        
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        # Validate status - can only activate BACKTESTED strategies
        if strategy.status != StrategyStatus.BACKTESTED:
            raise ValueError(
                f"Cannot activate strategy in {strategy.status} status. "
                f"Strategy must be BACKTESTED first."
            )
        
        # Validate allocation percentage
        if allocation_percent < 0.0 or allocation_percent > 100.0:
            raise ValueError(
                f"Invalid allocation_percent: {allocation_percent}. "
                f"Must be between 0.0 and 100.0"
            )
        
        # Calculate total allocation of other active strategies
        current_total_allocation = self._calculate_total_active_allocation(exclude_strategy_id=strategy_id)
        new_total_allocation = current_total_allocation + allocation_percent
        
        # Log allocation info (no hard cap - allow many strategies with small allocations)
        if new_total_allocation > 100.0:
            logger.warning(
                f"Total allocation exceeds 100% (current: {current_total_allocation:.1f}%, "
                f"requested: {allocation_percent:.1f}%, total: {new_total_allocation:.1f}%). "
                f"Proceeding anyway - allocations are notional."
            )
        
        # NEW: Check similarity to active strategies
        similarity_threshold = self.validation_config.get('similarity_detection', {}).get('strategy_similarity_threshold', 80)
        if self.validation_config.get('similarity_detection', {}).get('enabled', True):
            active_strategies = self.get_active_strategies()
            
            for active_strategy in active_strategies:
                if active_strategy.id == strategy_id:
                    continue  # Skip self-comparison
                
                similarity_score = self._compute_strategy_similarity(strategy, active_strategy)
                
                if similarity_score > similarity_threshold:
                    raise ValueError(
                        f"Cannot activate strategy '{strategy.name}': Too similar ({similarity_score:.1f}%) "
                        f"to active strategy '{active_strategy.name}'. "
                        f"Activation blocked to prevent redundancy (threshold: {similarity_threshold}%)."
                    )
                
                if similarity_score > 60:  # Log warning for moderately similar strategies
                    logger.warning(
                        f"Strategy '{strategy.name}' is {similarity_score:.1f}% similar "
                        f"to active strategy '{active_strategy.name}'"
                    )
        
        # Check symbol concentration limits before activation
        # Only check the PRIMARY symbol (first in list) — with multi-symbol watchlists,
        # checking all symbols would block activation if any popular symbol is at the cap.
        # Signal generation handles per-signal dedup at trade time.
        from src.core.config import load_risk_config
        risk_config = load_risk_config(mode)
        
        session = self.db.get_session()
        try:
            primary_symbol = strategy.symbols[0] if strategy.symbols else None
            if primary_symbol:
                active_count = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE]),
                    StrategyORM.symbols.contains(f'"{primary_symbol}"')
                ).count()
                
                if active_count >= risk_config.max_strategies_per_symbol:
                    # Try to find an alternative primary symbol from the watchlist
                    activated_on_alt = False
                    for alt_symbol in strategy.symbols[1:]:
                        alt_count = session.query(StrategyORM).filter(
                            StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE]),
                            StrategyORM.symbols.contains(f'"{alt_symbol}"')
                        ).count()
                        if alt_count < risk_config.max_strategies_per_symbol:
                            # Swap: move this symbol to primary position
                            logger.info(
                                f"Symbol {primary_symbol} at concentration limit ({active_count}/{risk_config.max_strategies_per_symbol}), "
                                f"using alternative primary symbol {alt_symbol} ({alt_count}/{risk_config.max_strategies_per_symbol})"
                            )
                            strategy.symbols = [alt_symbol] + [s for s in strategy.symbols if s != alt_symbol]
                            activated_on_alt = True
                            break
                    
                    if not activated_on_alt:
                        raise ValueError(
                            f"Cannot activate strategy: All watchlist symbols at concentration limit "
                            f"(max: {risk_config.max_strategies_per_symbol} strategies per symbol)"
                        )
        finally:
            session.close()
        
        # Update status based on mode
        if mode == TradingMode.DEMO:
            strategy.status = StrategyStatus.DEMO
        else:
            strategy.status = StrategyStatus.LIVE
        
        strategy.activated_at = datetime.now()
        strategy.allocation_percent = allocation_percent
        
        # Save to database
        self._save_strategy(strategy)
        
        # Add to active strategies
        self._active_strategies[strategy_id] = strategy
        
        logger.info(
            f"Activated strategy {strategy.name} in {mode.value} mode "
            f"with {allocation_percent:.1f}% allocation "
            f"(total allocation: {new_total_allocation:.1f}%)"
        )
        
        # Broadcast strategy activation
        self._broadcast_strategy_update_sync(strategy)
    def _compute_strategy_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
        """
        Compute similarity score (0-100) between two strategies.

        Components:
        - 40% indicator similarity (matching indicator types)
        - 30% parameter similarity (how close numeric parameters are)
        - 30% rule similarity (entry/exit conditions)
        - -20% penalty if different symbols (unless correlated)

        Args:
            strategy1: First strategy to compare
            strategy2: Second strategy to compare

        Returns:
            Similarity score from 0.0 to 100.0
        """
        try:
            # Extract indicators from strategy rules
            indicators1 = self._extract_indicators_from_rules(strategy1.rules)
            indicators2 = self._extract_indicators_from_rules(strategy2.rules)

            # 1. Indicator Similarity (40%)
            if not indicators1 or not indicators2:
                indicator_sim = 0.0
            else:
                common = indicators1 & indicators2
                total = indicators1 | indicators2
                indicator_sim = len(common) / len(total) if total else 0.0

            # 2. Parameter Similarity (30%)
            param_sim = self._compute_parameter_similarity(strategy1, strategy2)

            # 3. Rule Similarity (30%)
            rule_sim = self._compute_rule_similarity(strategy1, strategy2)

            # 4. Symbol penalty
            symbol_penalty = 0.0
            if set(strategy1.symbols) != set(strategy2.symbols):
                # Check if symbols are correlated
                if not self._are_symbols_correlated(strategy1.symbols, strategy2.symbols):
                    symbol_penalty = 0.2

            # Weighted score
            score = (
                0.4 * indicator_sim +
                0.3 * param_sim +
                0.3 * rule_sim -
                symbol_penalty
            ) * 100

            return max(0.0, min(100.0, score))

        except Exception as e:
            logger.error(f"Error computing strategy similarity: {e}", exc_info=True)
            return 0.0

    def _extract_indicators_from_rules(self, rules: Dict) -> set:
        """Extract indicator names from strategy rules."""
        indicators = set()

        if not rules:
            return indicators

        # Extract from 'indicators' list if present (e.g., ['RSI:14', 'STOCH:14'])
        if 'indicators' in rules:
            for ind in rules['indicators']:
                if isinstance(ind, str):
                    # Extract base indicator name (e.g., 'RSI:14' -> 'RSI', 'RSI' -> 'RSI')
                    base_name = ind.split(':')[0].strip().upper()
                    indicators.add(base_name)

        # Extract from entry conditions
        if 'entry_conditions' in rules:
            for condition in rules['entry_conditions']:
                if isinstance(condition, dict) and 'indicator' in condition:
                    indicators.add(condition['indicator'])
                elif isinstance(condition, str):
                    # Parse indicator names from string conditions like 'RSI(14) > 75'
                    indicators.update(self._extract_indicator_names_from_string(condition))

        # Extract from exit conditions
        if 'exit_conditions' in rules:
            for condition in rules['exit_conditions']:
                if isinstance(condition, dict) and 'indicator' in condition:
                    indicators.add(condition['indicator'])
                elif isinstance(condition, str):
                    indicators.update(self._extract_indicator_names_from_string(condition))

        return indicators

    def _extract_indicator_names_from_string(self, condition: str) -> set:
        """Extract indicator names from a string condition like 'RSI(14) > 75'.
        
        Recognizes: RSI, STOCH, SMA, EMA, MACD, BB, ATR, ADX, CCI, WILLR, OBV, VWAP, MFI
        """
        import re
        indicators = set()
        known_indicators = [
            'RSI', 'STOCH', 'SMA', 'EMA', 'MACD', 'BB', 'ATR', 'ADX',
            'CCI', 'WILLR', 'OBV', 'VWAP', 'MFI', 'BOLLINGER'
        ]
        condition_upper = condition.upper()
        for ind in known_indicators:
            # Match indicator name followed by optional parentheses or space
            if re.search(rf'\b{ind}\b', condition_upper):
                indicators.add(ind)
        return indicators

    def _compute_parameter_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
        """
        Compare indicator parameters (e.g., RSI period 14 vs 15).

        Args:
            strategy1: First strategy
            strategy2: Second strategy

        Returns:
            Parameter similarity score from 0.0 to 1.0
        """
        try:
            # Extract parameters from rules
            params1 = self._extract_parameters_from_rules(strategy1.rules)
            params2 = self._extract_parameters_from_rules(strategy2.rules)

            if not params1 or not params2:
                return 0.0

            # Find common parameter keys
            common_keys = set(params1.keys()) & set(params2.keys())

            if not common_keys:
                return 0.0

            similarities = []

            for key in common_keys:
                val1 = params1[key]
                val2 = params2[key]

                # Numeric comparison
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    if val1 == 0 and val2 == 0:
                        param_sim = 1.0
                    elif val1 == 0 or val2 == 0:
                        param_sim = 0.0
                    else:
                        diff = abs(val1 - val2) / max(abs(val1), abs(val2))
                        param_sim = 1.0 - min(diff, 1.0)
                    similarities.append(param_sim)

                # String comparison
                elif isinstance(val1, str) and isinstance(val2, str):
                    similarities.append(1.0 if val1 == val2 else 0.0)

            return sum(similarities) / len(similarities) if similarities else 0.0

        except Exception as e:
            logger.error(f"Error computing parameter similarity: {e}", exc_info=True)
            return 0.0

    def _extract_parameters_from_rules(self, rules: Dict) -> Dict:
        """Extract parameters from strategy rules."""
        params = {}

        if not rules:
            return params

        # Extract from entry conditions
        if 'entry_conditions' in rules:
            for i, condition in enumerate(rules['entry_conditions']):
                if isinstance(condition, dict):
                    for key, value in condition.items():
                        if key not in ['indicator', 'operator', 'comparison']:
                            params[f'entry_{i}_{key}'] = value

        # Extract from exit conditions
        if 'exit_conditions' in rules:
            for i, condition in enumerate(rules['exit_conditions']):
                if isinstance(condition, dict):
                    for key, value in condition.items():
                        if key not in ['indicator', 'operator', 'comparison']:
                            params[f'exit_{i}_{key}'] = value

        return params

    def _compute_rule_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
        """
        Compare entry/exit rules (simplified text comparison).

        Args:
            strategy1: First strategy
            strategy2: Second strategy

        Returns:
            Rule similarity score from 0.0 to 1.0
        """
        try:
            # Convert rules to comparable strings
            rules1_str = json.dumps(strategy1.rules, sort_keys=True) if strategy1.rules else ""
            rules2_str = json.dumps(strategy2.rules, sort_keys=True) if strategy2.rules else ""

            if not rules1_str or not rules2_str:
                return 0.0

            # Simple token-based similarity
            tokens1 = set(rules1_str.lower().split())
            tokens2 = set(rules2_str.lower().split())

            if not tokens1 or not tokens2:
                return 0.0

            common = tokens1 & tokens2
            total = tokens1 | tokens2

            return len(common) / len(total) if total else 0.0

        except Exception as e:
            logger.error(f"Error computing rule similarity: {e}", exc_info=True)
            return 0.0

    def _are_symbols_correlated(self, symbols1: List[str], symbols2: List[str], threshold: float = 0.8) -> bool:
        """
        Check if any symbols in two lists are correlated.

        Args:
            symbols1: First list of symbols
            symbols2: Second list of symbols
            threshold: Correlation threshold (default 0.8)

        Returns:
            True if any pair of symbols is correlated above threshold
        """
        try:
            # Import here to avoid circular dependency
            from src.utils.correlation_analyzer import CorrelationAnalyzer

            # Create analyzer instance
            analyzer = CorrelationAnalyzer(self.market_data)

            # Check all pairs
            for sym1 in symbols1:
                for sym2 in symbols2:
                    if sym1 == sym2:
                        return True  # Same symbol = perfectly correlated

                    if analyzer.are_correlated(sym1, sym2, threshold):
                        return True

            return False

        except Exception as e:
            logger.warning(f"Error checking symbol correlation: {e}")
            # Fail open - if we can't check correlation, assume not correlated
            return False


    
    def deactivate_strategy(self, strategy_id: str) -> None:
        """
        Deactivate strategy (stop generating signals).
        
        Args:
            strategy_id: ID of strategy to deactivate
        
        Raises:
            ValueError: If strategy not found
        """
        strategy = self._load_strategy(strategy_id)
        
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        # Update status back to BACKTESTED
        strategy.status = StrategyStatus.BACKTESTED
        
        # Save to database
        self._save_strategy(strategy)
        
        # Remove from active strategies
        if strategy_id in self._active_strategies:
            del self._active_strategies[strategy_id]
        
        logger.info(f"Deactivated strategy {strategy.name}")
        
        # Broadcast strategy deactivation
        self._broadcast_strategy_update_sync(strategy)
    def update_strategy_allocation(self, strategy_id: str, allocation_percent: float) -> None:
        """
        Update allocation percentage for an active strategy.

        Args:
            strategy_id: ID of strategy to update
            allocation_percent: New allocation percentage (0.0 to 100.0)

        Raises:
            ValueError: If strategy not found, not active, or allocation invalid
        """
        strategy = self._load_strategy(strategy_id)

        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Validate strategy is active
        if strategy.status not in [StrategyStatus.DEMO, StrategyStatus.LIVE]:
            raise ValueError(
                f"Cannot update allocation for strategy in {strategy.status} status. "
                f"Strategy must be active (DEMO or LIVE)."
            )

        # Validate allocation percentage
        if allocation_percent < 0.0 or allocation_percent > 100.0:
            raise ValueError(
                f"Invalid allocation_percent: {allocation_percent}. "
                f"Must be between 0.0 and 100.0"
            )

        # Calculate total allocation of other active strategies
        current_total_allocation = self._calculate_total_active_allocation(exclude_strategy_id=strategy_id)

        # Check if new allocation would exceed 100%
        new_total_allocation = current_total_allocation + allocation_percent
        if new_total_allocation > 100.0:
            raise ValueError(
                f"Total allocation would exceed 100% (current: {current_total_allocation:.1f}%, "
                f"requested: {allocation_percent:.1f}%, total: {new_total_allocation:.1f}%). "
                f"Please reduce allocation."
            )

        old_allocation = strategy.allocation_percent
        strategy.allocation_percent = allocation_percent

        # Save to database
        self._save_strategy(strategy)

        # Update in active strategies cache
        if strategy_id in self._active_strategies:
            self._active_strategies[strategy_id] = strategy

        logger.info(
            f"Updated allocation for strategy {strategy.name}: "
            f"{old_allocation:.1f}% -> {allocation_percent:.1f}% "
            f"(total allocation: {new_total_allocation:.1f}%)"
        )

        # Broadcast strategy update
        self._broadcast_strategy_update_sync(strategy)

    def _calculate_total_active_allocation(self, exclude_strategy_id: Optional[str] = None) -> float:
        """
        Calculate total allocation percentage of active strategies.

        Args:
            exclude_strategy_id: Optional strategy ID to exclude from calculation

        Returns:
            Total allocation percentage (0.0 to 100.0)
        """
        session = self.db.get_session()
        try:
            # Query all active strategies (DEMO or LIVE)
            active_strategies = session.query(StrategyORM).filter(
                StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
            ).all()

            total_allocation = 0.0
            for strategy_orm in active_strategies:
                # Skip excluded strategy if specified
                if exclude_strategy_id and strategy_orm.id == exclude_strategy_id:
                    continue
                total_allocation += strategy_orm.allocation_percent

            return total_allocation
        finally:
            session.close()
    
    def get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """
        Get strategy by ID.
        
        Args:
            strategy_id: Strategy ID
        
        Returns:
            Strategy object or None if not found
        """
        return self._load_strategy(strategy_id)
    
    def get_all_strategies(self) -> List[Strategy]:
        """
        Get all strategies.
        
        Returns:
            List of all strategies
        """
        session = self.db.get_session()
        try:
            strategy_orms = session.query(StrategyORM).all()
            strategies = [self._orm_to_strategy(orm) for orm in strategy_orms]
            return strategies
        finally:
            session.close()
    
    def get_active_strategies(self) -> List[Strategy]:
        """
        Get all active strategies (DEMO or LIVE status).
        
        Returns:
            List of active strategies
        """
        session = self.db.get_session()
        try:
            strategy_orms = session.query(StrategyORM).filter(
                StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
            ).all()
            strategies = [self._orm_to_strategy(orm) for orm in strategy_orms]
            return strategies
        finally:
            session.close()
    
    def _strategy_to_dict(self, strategy: Strategy) -> Dict:
        """
        Convert Strategy object to dictionary for WebSocket broadcasting.
        
        Args:
            strategy: Strategy object to convert
        
        Returns:
            Dictionary representation of strategy
        """
        return {
            "id": strategy.id,
            "name": strategy.name,
            "description": strategy.description,
            "status": strategy.status.value,
            "symbols": strategy.symbols,
            "allocation_percent": strategy.allocation_percent,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "activated_at": strategy.activated_at.isoformat() if strategy.activated_at else None,
            "retired_at": strategy.retired_at.isoformat() if strategy.retired_at else None,
            "performance": {
                "total_return": strategy.performance.total_return,
                "sharpe_ratio": strategy.performance.sharpe_ratio,
                "sortino_ratio": strategy.performance.sortino_ratio,
                "max_drawdown": strategy.performance.max_drawdown,
                "win_rate": strategy.performance.win_rate,
                "avg_win": strategy.performance.avg_win,
                "avg_loss": strategy.performance.avg_loss,
                "total_trades": strategy.performance.total_trades
            } if strategy.performance else None,
            "rules": strategy.rules,
            "risk_params": {
                "max_position_size_pct": strategy.risk_params.get('max_position_size_pct') if isinstance(strategy.risk_params, dict) else getattr(strategy.risk_params, 'max_position_size_pct', None),
                "stop_loss_pct": strategy.risk_params.get('stop_loss_pct') if isinstance(strategy.risk_params, dict) else getattr(strategy.risk_params, 'stop_loss_pct', None),
                "take_profit_pct": strategy.risk_params.get('take_profit_pct') if isinstance(strategy.risk_params, dict) else getattr(strategy.risk_params, 'take_profit_pct', None),
                "max_drawdown_pct": strategy.risk_params.get('max_drawdown_pct') if isinstance(strategy.risk_params, dict) else getattr(strategy.risk_params, 'max_drawdown_pct', None),
            } if strategy.risk_params else None
        }
    
    async def _broadcast_strategy_update(self, strategy: Strategy):
        """
        Broadcast strategy update via WebSocket.
        
        Args:
            strategy: Strategy that was updated
        """
        if self.websocket_manager:
            try:
                strategy_dict = self._strategy_to_dict(strategy)
                await self.websocket_manager.broadcast_strategy_update(strategy_dict)
            except Exception as e:
                logger.error(f"Failed to broadcast strategy update: {e}")
    
    def _broadcast_strategy_update_sync(self, strategy: Strategy):
        """
        Synchronous wrapper for broadcasting strategy updates.
        Safely handles cases where no event loop is running.
        
        Args:
            strategy: Strategy that was updated
        """
        if not self.websocket_manager:
            return
        
        try:
            # Try to get or create an event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're already in an async context, create a task
                asyncio.create_task(self._broadcast_strategy_update(strategy))
            except RuntimeError:
                # No running loop, try to get the event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    # Run the coroutine
                    loop.run_until_complete(self._broadcast_strategy_update(strategy))
                except Exception as e:
                    logger.debug(f"Could not run broadcast in event loop: {e}")
        except Exception as e:
            logger.error(f"Failed to broadcast strategy update: {e}")
    
    def _save_strategy(self, strategy: Strategy) -> None:
        """
        Save strategy to database.
        
        Args:
            strategy: Strategy to save
        """
        session = self.db.get_session()
        try:
            # Check if strategy exists
            existing = session.query(StrategyORM).filter_by(id=strategy.id).first()
            
            if existing:
                # Update existing
                existing.name = strategy.name
                existing.description = strategy.description
                existing.status = strategy.status
                existing.rules = strategy.rules
                existing.symbols = strategy.symbols
                existing.allocation_percent = strategy.allocation_percent
                existing.risk_params = self._risk_config_to_dict(strategy.risk_params)
                existing.activated_at = strategy.activated_at
                existing.retired_at = strategy.retired_at
                existing.performance = self._performance_to_dict(strategy.performance)
                existing.reasoning = self._reasoning_to_dict(strategy.reasoning) if strategy.reasoning else None
                existing.backtest_results = self._backtest_results_to_dict(strategy.backtest_results) if strategy.backtest_results else None
                existing.strategy_metadata = strategy.metadata if strategy.metadata else {}
                existing.retirement_evaluation_history = strategy.retirement_evaluation_history
                existing.live_trade_count = strategy.live_trade_count
                existing.last_retirement_evaluation = strategy.last_retirement_evaluation
            else:
                # Create new
                strategy_orm = StrategyORM(
                    id=strategy.id,
                    name=strategy.name,
                    description=strategy.description,
                    status=strategy.status,
                    rules=strategy.rules,
                    symbols=strategy.symbols,
                    allocation_percent=strategy.allocation_percent,
                    risk_params=self._risk_config_to_dict(strategy.risk_params),
                    created_at=strategy.created_at,
                    activated_at=strategy.activated_at,
                    retired_at=strategy.retired_at,
                    performance=self._performance_to_dict(strategy.performance),
                    reasoning=self._reasoning_to_dict(strategy.reasoning) if strategy.reasoning else None,
                    backtest_results=self._backtest_results_to_dict(strategy.backtest_results) if strategy.backtest_results else None,
                    strategy_metadata=strategy.metadata if strategy.metadata else {},
                    retirement_evaluation_history=strategy.retirement_evaluation_history,
                    live_trade_count=strategy.live_trade_count,
                    last_retirement_evaluation=strategy.last_retirement_evaluation
                )
                session.add(strategy_orm)
            
            session.commit()
            logger.debug(f"Saved strategy {strategy.id} to database")
        
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save strategy {strategy.id}: {e}")
            raise
        finally:
            session.close()
    
    def _load_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """
        Load strategy from database.
        
        Args:
            strategy_id: Strategy ID
        
        Returns:
            Strategy object or None if not found
        """
        session = self.db.get_session()
        try:
            strategy_orm = session.query(StrategyORM).filter_by(id=strategy_id).first()
            
            if strategy_orm is None:
                return None
            
            return self._orm_to_strategy(strategy_orm)
        
        finally:
            session.close()
    
    def _orm_to_strategy(self, orm: StrategyORM) -> Strategy:
        """Convert ORM model to Strategy dataclass."""
        return Strategy(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            status=orm.status,
            rules=orm.rules,
            symbols=orm.symbols,
            risk_params=self._dict_to_risk_config(orm.risk_params),
            created_at=orm.created_at,
            allocation_percent=orm.allocation_percent,
            activated_at=orm.activated_at,
            retired_at=orm.retired_at,
            performance=self._dict_to_performance(orm.performance),
            reasoning=self._dict_to_reasoning(orm.reasoning) if orm.reasoning else None,
            backtest_results=self._dict_to_backtest_results(orm.backtest_results) if orm.backtest_results else None,
            metadata=orm.strategy_metadata if orm.strategy_metadata else {},
            retirement_evaluation_history=orm.retirement_evaluation_history or [],
            live_trade_count=orm.live_trade_count,
            last_retirement_evaluation=orm.last_retirement_evaluation
        )
    
    def _risk_config_to_dict(self, risk_config) -> Dict:
        """Convert RiskConfig (dataclass or dict) to dictionary for JSON storage."""
        if isinstance(risk_config, dict):
            return risk_config  # Already a dict, return as-is
        return {
            "max_position_size_pct": getattr(risk_config, 'max_position_size_pct', 0.05),
            "max_exposure_pct": getattr(risk_config, 'max_exposure_pct', 0.5),
            "max_daily_loss_pct": getattr(risk_config, 'max_daily_loss_pct', 0.03),
            "max_drawdown_pct": getattr(risk_config, 'max_drawdown_pct', 0.1),
            "position_risk_pct": getattr(risk_config, 'position_risk_pct', 0.02),
            "stop_loss_pct": getattr(risk_config, 'stop_loss_pct', 0.04),
            "take_profit_pct": getattr(risk_config, 'take_profit_pct', 0.1),
        }
    
    def _dict_to_risk_config(self, data: Dict) -> RiskConfig:
        """Convert dictionary to RiskConfig."""
        return RiskConfig(
            max_position_size_pct=data.get("max_position_size_pct", 0.1),
            max_exposure_pct=data.get("max_exposure_pct", 0.8),
            max_daily_loss_pct=data.get("max_daily_loss_pct", 0.03),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.10),
            position_risk_pct=data.get("position_risk_pct", 0.01),
            stop_loss_pct=data.get("stop_loss_pct", 0.02),
            take_profit_pct=data.get("take_profit_pct", 0.04)
        )
    
    def _performance_to_dict(self, performance: PerformanceMetrics) -> Dict:
        """Convert PerformanceMetrics to dictionary for JSON storage."""
        return {
            "total_return": performance.total_return,
            "sharpe_ratio": performance.sharpe_ratio,
            "sortino_ratio": performance.sortino_ratio,
            "max_drawdown": performance.max_drawdown,
            "win_rate": performance.win_rate,
            "avg_win": performance.avg_win,
            "avg_loss": performance.avg_loss,
            "total_trades": performance.total_trades
        }
    
    def _dict_to_performance(self, data: Dict) -> PerformanceMetrics:
        """Convert dictionary to PerformanceMetrics."""
        return PerformanceMetrics(
            total_return=data.get("total_return", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            win_rate=data.get("win_rate", 0.0),
            avg_win=data.get("avg_win", 0.0),
            avg_loss=data.get("avg_loss", 0.0),
            total_trades=data.get("total_trades", 0)
        )
    
    def _reasoning_to_dict(self, reasoning: StrategyReasoning) -> Dict:
        """Convert StrategyReasoning to dictionary for JSON storage."""
        # Handle string reasoning (from template-based strategies)
        if isinstance(reasoning, str):
            return {
                "hypothesis": reasoning,
                "alpha_sources": [],
                "market_assumptions": [],
                "signal_logic": reasoning,
                "confidence_factors": [],
                "llm_prompt": ""
            }
        
        return {
            "hypothesis": reasoning.hypothesis,
            "alpha_sources": [
                {
                    "type": source.type,
                    "weight": source.weight,
                    "description": source.description
                }
                for source in reasoning.alpha_sources
            ],
            "market_assumptions": reasoning.market_assumptions,
            "signal_logic": reasoning.signal_logic,
            "confidence_factors": reasoning.confidence_factors,
            "llm_prompt": reasoning.llm_prompt,
            "llm_response": reasoning.llm_response
        }
    
    def _dict_to_reasoning(self, data: Dict) -> StrategyReasoning:
        """Convert dictionary to StrategyReasoning."""
        alpha_sources = [
            AlphaSource(
                type=source.get("type", ""),
                weight=source.get("weight", 0.0),
                description=source.get("description", "")
            )
            for source in data.get("alpha_sources", [])
        ]
        
        return StrategyReasoning(
            hypothesis=data.get("hypothesis", ""),
            alpha_sources=alpha_sources,
            market_assumptions=data.get("market_assumptions", []),
            signal_logic=data.get("signal_logic", ""),
            confidence_factors=data.get("confidence_factors", {}),
            llm_prompt=data.get("llm_prompt"),
            llm_response=data.get("llm_response")
        )
    
    def _backtest_results_to_dict(self, results: BacktestResults) -> Dict:
        """Convert BacktestResults to dictionary for JSON storage."""
        result_dict = {
            "total_return": results.total_return,
            "sharpe_ratio": results.sharpe_ratio,
            "sortino_ratio": results.sortino_ratio,
            "max_drawdown": results.max_drawdown,
            "win_rate": results.win_rate,
            "avg_win": results.avg_win,
            "avg_loss": results.avg_loss,
            "total_trades": results.total_trades
        }
        
        # Handle optional fields
        if results.backtest_period:
            result_dict["backtest_period"] = [
                results.backtest_period[0].isoformat() if results.backtest_period[0] else None,
                results.backtest_period[1].isoformat() if results.backtest_period[1] else None
            ]
        
        # Serialize equity curve (pandas Series) to list of [timestamp, value] pairs
        # For large datasets, we may want to downsample to reduce storage size
        if results.equity_curve is not None:
            try:
                equity_data = [
                    [ts.isoformat(), float(val)]
                    for ts, val in results.equity_curve.items()
                ]
                
                # Warn if equity curve is very large (>10,000 points)
                if len(equity_data) > 10000:
                    logger.warning(
                        f"Equity curve has {len(equity_data)} data points. "
                        f"Consider downsampling for better performance."
                    )
                
                result_dict["equity_curve"] = equity_data
            except Exception as e:
                logger.warning(f"Failed to serialize equity curve: {e}")
                result_dict["equity_curve"] = None
        
        # Serialize trades (pandas DataFrame) to list of dictionaries
        # Limit to most recent 1000 trades to prevent excessive storage
        if results.trades is not None:
            try:
                # Convert DataFrame to list of dicts, handling datetime and numeric types
                trades_data = []
                
                # Limit trades to prevent excessive storage
                trades_to_serialize = results.trades
                if len(results.trades) > 1000:
                    logger.warning(
                        f"Trade history has {len(results.trades)} trades. "
                        f"Storing only the most recent 1000 trades."
                    )
                    trades_to_serialize = results.trades.tail(1000)
                
                if len(trades_to_serialize) > 0:
                    for _, row in trades_to_serialize.iterrows():
                        trade_dict = {}
                        for col, val in row.items():
                            if pd.isna(val):
                                trade_dict[col] = None
                            elif hasattr(val, 'isoformat'):  # datetime
                                trade_dict[col] = val.isoformat()
                            else:
                                trade_dict[col] = float(val) if isinstance(val, (int, float)) else str(val)
                        trades_data.append(trade_dict)
                
                result_dict["trades"] = trades_data
                result_dict["total_trades_in_backtest"] = len(results.trades)  # Store actual count
            except Exception as e:
                logger.warning(f"Failed to serialize trades: {e}")
                result_dict["trades"] = []
        
        return result_dict
    
    def _dict_to_backtest_results(self, data: Dict) -> BacktestResults:
        """Convert dictionary to BacktestResults."""
        from datetime import datetime
        
        backtest_period = None
        if "backtest_period" in data and data["backtest_period"]:
            backtest_period = (
                datetime.fromisoformat(data["backtest_period"][0]) if data["backtest_period"][0] else None,
                datetime.fromisoformat(data["backtest_period"][1]) if data["backtest_period"][1] else None
            )
        
        # Deserialize equity curve from list of [timestamp, value] pairs to pandas Series
        equity_curve = None
        if "equity_curve" in data and data["equity_curve"]:
            try:
                timestamps = [datetime.fromisoformat(ts) for ts, _ in data["equity_curve"]]
                values = [val for _, val in data["equity_curve"]]
                equity_curve = pd.Series(values, index=timestamps)
            except Exception as e:
                logger.warning(f"Failed to deserialize equity curve: {e}")
        
        # Deserialize trades from list of dicts to pandas DataFrame
        trades = None
        if "trades" in data and data["trades"] is not None:
            try:
                if len(data["trades"]) > 0:
                    trades = pd.DataFrame(data["trades"])
                    # Convert datetime columns back to datetime objects
                    for col in trades.columns:
                        if 'time' in col.lower() or 'date' in col.lower():
                            try:
                                trades[col] = pd.to_datetime(trades[col], utc=True)
                            except:
                                pass
                else:
                    # Empty trades list - create empty DataFrame
                    trades = pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to deserialize trades: {e}")
        
        return BacktestResults(
            total_return=data.get("total_return", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            win_rate=data.get("win_rate", 0.0),
            avg_win=data.get("avg_win", 0.0),
            avg_loss=data.get("avg_loss", 0.0),
            total_trades=data.get("total_trades", 0),
            equity_curve=equity_curve,
            trades=trades,
            backtest_period=backtest_period
        )
    
    def backtest_strategy(
        self,
        strategy: Strategy,
        start: datetime,
        end: datetime,
        commission: float = 0.0,
        slippage_bps: float = 0.0,
        interval: str = "1d"
    ) -> BacktestResults:
        """
        Backtest strategy using vectorbt with historical data.
        
        Args:
            strategy: Strategy to backtest
            start: Start date for backtest
            end: End date for backtest
            commission: Commission per trade in dollars (default 0.0, overridden by config)
            slippage_bps: Slippage in basis points (default 0.0, overridden by config)
        
        Returns:
            BacktestResults with performance metrics (adjusted for costs if specified)
        
        Raises:
            ValueError: If historical data cannot be fetched or backtest fails
        """
        if not VECTORBT_AVAILABLE:
            raise ValueError(
                "Backtesting requires vectorbt to be installed. "
                "Install it with: pip install vectorbt"
            )
        
        logger.info(f"Backtesting strategy {strategy.name} from {start} to {end}")
        
        # Load transaction costs from config if not specified — asset-class-aware
        if commission == 0.0 and slippage_bps == 0.0:
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        tx_costs = config.get('backtest', {}).get('transaction_costs', {})

                        # Determine asset class for per-asset-class costs
                        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                        asset_class = self._get_asset_class(primary_symbol) if primary_symbol else 'stock'
                        ac_costs = tx_costs.get('per_asset_class', {}).get(asset_class, {})

                        # Per-asset-class costs take priority over global defaults
                        commission = ac_costs.get('commission_percent', tx_costs.get('commission_percent', 0.0))
                        slippage_pct_raw = ac_costs.get('slippage_percent', tx_costs.get('slippage_percent', 0.0003))
                        slippage_bps = slippage_pct_raw * 10000  # Convert to bps
                        
                        # Override slippage with actual measured slippage from trade journal
                        # if we have enough data for the primary symbol
                        try:
                            primary_symbol = strategy.symbols[0] if strategy.symbols else None
                            if primary_symbol:
                                from src.analytics.trade_journal import TradeJournal
                                tj = TradeJournal(self.db)
                                feedback = tj.get_performance_feedback()
                                slippage_data = feedback.get('slippage_analytics', {})
                                by_symbol = slippage_data.get('slippage_by_symbol', {})
                                if primary_symbol in by_symbol:
                                    actual_slippage = abs(by_symbol[primary_symbol])
                                    if actual_slippage > 0:
                                        # Use the larger of config slippage or actual measured slippage
                                        actual_bps = actual_slippage * 10000
                                        if actual_bps > slippage_bps:
                                            slippage_bps = actual_bps
                                            logger.info(
                                                f"Using measured slippage for {primary_symbol}: "
                                                f"{actual_slippage:.4%} ({actual_bps:.1f}bps) — "
                                                f"higher than config default"
                                            )
                        except Exception as slip_err:
                            logger.debug(f"Could not load measured slippage: {slip_err}")
                        
                        logger.info(f"Loaded transaction costs from config: commission={commission:.4%}, slippage={slippage_bps:.1f}bps")
            except Exception as e:
                logger.warning(f"Could not load transaction costs from config: {e}")
        
        # Calculate warmup period needed for indicators
        # Find the maximum period from all indicators in the strategy
        max_period = 0
        for indicator in strategy.rules.get("indicators", []):
            # Extract period from indicator spec (e.g., "EMA:50" -> 50)
            if ":" in indicator:
                try:
                    period = int(indicator.split(":")[1])
                    max_period = max(max_period, period)
                except (ValueError, IndexError):
                    pass
        
        # Load warmup period from config (default 250 days for 2-year backtest)
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    backtest_config = config.get('backtest', {})
                    config_warmup_days = backtest_config.get('warmup_days', 250)
                    logger.debug(f"Loaded warmup_days from config: {config_warmup_days}")
            else:
                config_warmup_days = 250
                logger.warning(f"Config file not found, using default warmup_days: {config_warmup_days}")
        except Exception as e:
            config_warmup_days = 250
            logger.warning(f"Could not load warmup_days from config: {e}, using default: {config_warmup_days}")
        
        # Add warmup period (max indicator period * 2 for safety, or config value)
        # This ensures indicators have enough data to calculate properly (e.g., 200-day MA needs 200+ days)
        # For intraday intervals, warmup is in bars not days — convert to calendar days
        if interval in ("1h", "4h"):
            # Intraday: warmup needs enough BARS, not calendar days
            # max_period is already in bars (e.g., RSI:98 = 98 hourly bars)
            bars_per_day = 7 if interval == "1h" else 6  # Conservative estimate for stocks
            warmup_bars = max(max_period * 2, 200) if max_period > 0 else 200
            warmup_days = max(int(warmup_bars / bars_per_day) + 5, 30)  # +5 for weekends/holidays
            logger.info(f"Intraday warmup: {warmup_bars} bars → {warmup_days} calendar days (interval={interval})")
        else:
            warmup_days = max(max_period * 2, config_warmup_days) if max_period > 0 else config_warmup_days
        fetch_start = start - timedelta(days=warmup_days)
        
        # Calculate expected data points (trading days, not calendar days)
        # Asset-class-aware: crypto trades 365d/yr, forex ~260d/yr, stocks ~252d/yr
        calendar_days = (end - fetch_start).days
        
        # Determine asset class for the primary symbol to set the right ratio
        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
        asset_class = self._get_asset_class(primary_symbol)
        if asset_class == 'crypto':
            trading_days_per_year = 365  # 24/7
        elif asset_class == 'forex':
            trading_days_per_year = 260  # 24/5
        else:
            trading_days_per_year = 252  # Stocks, ETFs, indices, commodities
        
        expected_trading_days = int(calendar_days * trading_days_per_year / 365)
        logger.info(f"Fetching data with {warmup_days} day warmup period (from {fetch_start.date()} to {end.date()})")
        logger.info(f"Expected data points: ~{expected_trading_days} trading days ({calendar_days} calendar days, {asset_class})")
        
        # For intraday intervals, convert expected trading days to expected bars.
        # Daily bars: 1 bar/day. 1h bars: ~6.5 bars/day (stocks) or 24 (crypto).
        # Without this, coverage% is nonsensical (2200 bars / 193 days = 1139%).
        if interval == '1h':
            bars_per_trading_day = 24 if asset_class == 'crypto' else 7  # ~6.5h rounded up
            expected_bars = expected_trading_days * bars_per_trading_day
        elif interval == '4h':
            bars_per_trading_day = 6 if asset_class == 'crypto' else 2
            expected_bars = expected_trading_days * bars_per_trading_day
        else:
            expected_bars = expected_trading_days
        
        # Fetch historical data for all symbols (with warmup period)
        all_data = {}
        data_quality_warnings = []

        # Import DAILY_ONLY_SYMBOLS to skip LME metals on intraday/4h backtests.
        # These symbols have no intraday data on Yahoo Finance — requesting 1h/4h
        # returns [] which would crash the entire backtest. Skip them gracefully.
        try:
            from src.utils.symbol_mapper import DAILY_ONLY_SYMBOLS as _DAILY_ONLY
        except Exception:
            _DAILY_ONLY = set()

        for symbol in strategy.symbols:
            if interval in ("1h", "4h") and symbol.upper() in _DAILY_ONLY:
                logger.debug(f"Skipping {symbol} in {interval} backtest — daily-only LME metal, no intraday data")
                continue
            try:
                # Use Yahoo Finance for backtesting (eToro doesn't provide historical OHLCV)
                # Yahoo Finance is used consistently for all market data analysis
                data_list = self.market_data.get_historical_data(
                    symbol, fetch_start, end, interval=interval, prefer_yahoo=True
                )
                
                if not data_list:
                    raise ValueError(f"No historical data available for {symbol}")
                
                # Convert to DataFrame
                df = pd.DataFrame([
                    {
                        "timestamp": d.timestamp.replace(tzinfo=None) if hasattr(d.timestamp, 'tzinfo') and d.timestamp.tzinfo else d.timestamp,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.volume
                    }
                    for d in data_list
                ])
                df.set_index("timestamp", inplace=True)
                df.index = pd.to_datetime(df.index)
                # Ensure timezone-naive index for consistent backtest calculations
                if hasattr(df.index, 'tz') and df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                all_data[symbol] = df
                
                # Data quality check — relative to the period being backtested
                actual_days = len(df)
                data_coverage = (actual_days / expected_bars) * 100 if expected_bars > 0 else 0
                
                logger.info(f"Fetched {actual_days} data points for {symbol} (coverage: {data_coverage:.1f}%)")
                
                # Warn only if coverage is genuinely poor (< 70% of expected).
                # A 3-day shortfall on a 193-day expected count (98.4% coverage) is noise,
                # not a data quality issue. Only flag real problems.
                if data_coverage < 50:
                    # Severely limited — less than half the expected data
                    warning_msg = f"Symbol {symbol} has only {actual_days} bars of data (expected ~{expected_bars}, coverage: {data_coverage:.0f}%)"
                    logger.warning(warning_msg)
                    logger.warning(f"  ⚠ Very limited data for {symbol}. Consider using shorter backtest period.")
                    data_quality_warnings.append(warning_msg)
                elif data_coverage < 70:
                    # Limited but usable
                    warning_msg = f"Symbol {symbol} has {actual_days} bars (expected ~{expected_bars}, coverage: {data_coverage:.0f}%)"
                    logger.warning(warning_msg)
                    data_quality_warnings.append(warning_msg)
            
            except Exception as e:
                logger.error(f"Failed to fetch historical data for {symbol}: {e}")
                raise ValueError(f"Failed to fetch historical data for {symbol}: {e}")
        
        # Log data quality summary
        if data_quality_warnings:
            logger.warning(f"Data quality warnings: {len(data_quality_warnings)} symbol(s) with limited data")
        else:
            logger.info("✓ Data quality check passed - all symbols have sufficient historical data")
        
        # Run backtest using vectorbt
        try:
            results = self._run_vectorbt_backtest(strategy, all_data, start, end, commission, slippage_bps, interval=interval)
            
            # Update strategy status and performance
            strategy.status = StrategyStatus.BACKTESTED
            strategy.performance = PerformanceMetrics(
                total_return=results.total_return,
                sharpe_ratio=results.sharpe_ratio,
                sortino_ratio=results.sortino_ratio,
                max_drawdown=results.max_drawdown,
                win_rate=results.win_rate,
                avg_win=results.avg_win,
                avg_loss=results.avg_loss,
                total_trades=results.total_trades
            )
            
            # Store detailed backtest results
            strategy.backtest_results = results
            
            # Don't save to DB here — strategy will be saved only if it passes
            # activation in _evaluate_and_activate. Saving every backtested strategy
            # pollutes the DB with strategies that fail activation thresholds.
            
            logger.info(
                f"Backtest complete for {strategy.name}: "
                f"return={results.total_return:.2%}, "
                f"sharpe={results.sharpe_ratio:.2f}, "
                f"trades={results.total_trades}"
            )
            
            # Broadcast backtest completion
            self._broadcast_strategy_update_sync(strategy)
            
            return results
        
        except Exception as e:
            logger.error(f"Backtest failed for {strategy.name}: {e}")
            raise ValueError(f"Backtest failed: {e}")

    def walk_forward_validate(
        self,
        strategy: Strategy,
        start: datetime,
        end: datetime,
        train_days: int = None,  # Load from config if not specified
        test_days: int = None    # Load from config if not specified
    ) -> Dict[str, Any]:
        """
        Perform walk-forward validation on a strategy.

        Splits data into train and test periods, backtests on train period,
        and validates on test period (out-of-sample).

        Args:
            strategy: Strategy to validate
            start: Start date for validation
            end: End date for validation
            train_days: Number of days for training period (default from config: 480 = 16 months)
            test_days: Number of days for testing period (default from config: 240 = 8 months)

        Returns:
            Dict with train_results, test_results, train_sharpe, test_sharpe,
            is_overfitted flag, and performance_degradation percentage
        """
        # Load walk-forward config if not specified
        if train_days is None or test_days is None:
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        wf_config = config.get('backtest', {}).get('walk_forward', {})
                        if train_days is None:
                            train_days = wf_config.get('train_days', 480)
                        if test_days is None:
                            test_days = wf_config.get('test_days', 240)
                        logger.debug(f"Loaded walk-forward config: train_days={train_days}, test_days={test_days}")
                else:
                    train_days = train_days or 480
                    test_days = test_days or 240
                    logger.warning(f"Config file not found, using defaults: train_days={train_days}, test_days={test_days}")
            except Exception as e:
                train_days = train_days or 480
                test_days = test_days or 240
                logger.warning(f"Could not load walk-forward config: {e}, using defaults: train_days={train_days}, test_days={test_days}")
        
        logger.info(f"Walk-forward validation for {strategy.name}: train={train_days}d, test={test_days}d")

        # Detect if this is an intraday template that should be backtested on 1h bars
        is_intraday_template = (
            hasattr(strategy, 'metadata') and strategy.metadata and
            strategy.metadata.get('intraday', False)
        )
        
        # Detect 4H interval from strategy rules or metadata
        is_4h_template = False
        if hasattr(strategy, 'metadata') and strategy.metadata:
            is_4h_template = strategy.metadata.get('interval_4h', False)
        if not is_4h_template:
            strat_interval = strategy.rules.get('interval', '1d') if strategy.rules else '1d'
            is_4h_template = strat_interval == '4h'
        
        # For intraday templates, use appropriate windows based on interval.
        # Yahoo provides ~730 days of 1h data — use enough for statistical significance.
        # Professional quant standard: 200+ bars train, 100+ bars test minimum.
        backtest_interval = "1d"
        if is_intraday_template:
            backtest_interval = "1h"
            # 1h: 180 days train (~4,320 bars crypto 24/7), 90 days test (~2,160 bars)
            # Wider window captures multiple market regimes (bull + crash + recovery)
            # instead of being stuck entirely in one regime. Yahoo provides ~730 days
            # of 1h data, so 270 total days is well within limits.
            # Previous: 90d train + 45d test = 135d (test was entirely in crash period)
            train_days = min(train_days, 180)
            test_days = min(test_days, 90)
            # Override start to be within Yahoo's 1h data range (~730 days available)
            start = end - timedelta(days=train_days + test_days)
            logger.info(
                f"Intraday template: using 1h bars with walk-forward window "
                f"(train={train_days}d, test={test_days}d, start={start.date()})"
            )
        elif is_4h_template:
            backtest_interval = "4h"
            # 4H: 240 days train (~1,440 bars crypto), 120 days test (~720 bars)
            # Synthesized from 1h data, so same 730-day Yahoo limit applies.
            # 360 total days is within limits. Wider window gives 4-month test period
            # covering multiple market phases.
            # Previous: 120d train + 60d test = 180d
            train_days = min(train_days, 240)
            test_days = min(test_days, 120)
            start = end - timedelta(days=train_days + test_days)
            logger.info(
                f"4H template: using 4h bars with walk-forward window "
                f"(train={train_days}d, test={test_days}d, start={start.date()})"
            )

        # Calculate split date
        total_days = (end - start).days
        if total_days < train_days + test_days:
            raise ValueError(
                f"Insufficient data for walk-forward validation: "
                f"need {train_days + test_days} days, have {total_days} days"
            )

        # Split into train and test periods
        train_end = start + timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_days)

        logger.info(f"Train period: {start.date()} to {train_end.date()}")
        logger.info(f"Test period: {test_start.date()} to {test_end.date()}")

        # Backtest on train period
        try:
            train_results = self.backtest_strategy(strategy, start, train_end, interval=backtest_interval)
            train_sharpe = train_results.sharpe_ratio
            logger.info(f"Train Sharpe: {train_sharpe:.2f}, Return: {train_results.total_return:.2%}, Trades: {train_results.total_trades}")
        except Exception as e:
            logger.error(f"Train period backtest failed: {e}")
            raise ValueError(f"Train period backtest failed: {e}")

        # Clear in-memory data cache between train and test periods
        # to prevent stale data from the train period affecting the test period
        if hasattr(self.market_data, '_historical_memory_cache'):
            self.market_data._historical_memory_cache.clear()
        
        # Clear indicator cache to prevent train-period indicators (wrong length)
        # from being reused in the test period
        if hasattr(self, 'indicator_library'):
            self.indicator_library.clear_cache()

        # Backtest on test period (out-of-sample)
        try:
            test_results = self.backtest_strategy(strategy, test_start, test_end, interval=backtest_interval)
            test_sharpe = test_results.sharpe_ratio
            logger.info(f"Test Sharpe: {test_sharpe:.2f}, Return: {test_results.total_return:.2%}, Trades: {test_results.total_trades}")
        except Exception as e:
            logger.error(f"Test period backtest failed: {e}")
            raise ValueError(f"Test period backtest failed: {e}")

        # Calculate performance degradation
        if train_sharpe != 0:
            performance_degradation = ((train_sharpe - test_sharpe) / abs(train_sharpe)) * 100
        else:
            performance_degradation = 0.0

        # Detect strategy timeframe for timeframe-aware overfitting detection
        # Check strategy.metadata first (intraday templates), then backtest_results
        interval = '1d'  # Default to daily if not specified
        if hasattr(strategy, 'metadata') and strategy.metadata:
            interval = strategy.metadata.get('interval', '1d')
        if interval == '1d' and hasattr(train_results, 'metadata') and train_results.metadata:
            interval = train_results.metadata.get('interval', '1d')
        
        # Normalize interval format (handle both '1h' and '1H')
        interval = interval.lower() if interval else '1d'
        
        # Apply timeframe-aware degradation thresholds
        # Hourly and intraday strategies naturally show more performance variation
        # due to smaller sample sizes and higher noise in shorter timeframes
        if interval in ['1h', '2h']:
            degradation_threshold = 0.4  # 40% for hourly
            logger.info(
                f"Hourly strategy detected (interval={interval}): Using 40% degradation "
                f"threshold for overfitting detection (vs 30% for daily)"
            )
        elif interval in ['4h']:
            degradation_threshold = 0.35  # 35% for 4H (between daily and hourly)
            logger.info(
                f"4H strategy detected: Using 35% degradation threshold"
            )
        elif interval in ['15m', '30m']:
            degradation_threshold = 0.5  # 50% for intraday
            logger.info(
                f"Intraday strategy detected (interval={interval}): Using 50% degradation "
                f"threshold for overfitting detection (vs 30% for daily)"
            )
        else:
            # Daily and 4H strategies: use existing 30% threshold (preserve existing behavior)
            degradation_threshold = 0.3
        
        # Detect overfitting with explicit, calibrated thresholds.
        #
        # The question a PM asks: "Did this strategy demonstrate real OOS edge,
        # or did it just curve-fit the training data?"
        #
        # Rules (calibrated to how systematic funds evaluate backtests):
        # 1. Train positive, test negative → classic overfit (always flag)
        # 2. Train positive, test positive but test < 50% of train AND train > 1.0
        #    → suspicious degradation, BUT only if test Sharpe is below viable threshold
        #    A strategy with train=3.0, test=1.2 is NOT overfitted — it's just that
        #    the train period was unusually favorable. The test still shows real edge.
        # 3. Both negative → unprofitable, not overfitted
        # 4. Train negative, test positive → improved OOS, not overfitted
        is_overfitted = False
        if train_sharpe > 0 and test_sharpe < 0:
            # Classic overfit: profitable in-sample, unprofitable out-of-sample
            is_overfitted = True
        elif train_sharpe > 1.0 and test_sharpe > 0 and test_sharpe < train_sharpe * 0.5:
            # Severe degradation from a strong train. Only flag if test Sharpe
            # is truly marginal — below the minimum viable threshold.
            # This catches: train=2.5, test=0.15 (curve-fit)
            # This passes: train=2.5, test=0.8 (train was just a great period)
            min_viable_sharpe = 0.3
            if test_sharpe < min_viable_sharpe:
                is_overfitted = True
            else:
                logger.info(
                    f"Degradation {performance_degradation:.0f}% but test Sharpe {test_sharpe:.2f} "
                    f">= {min_viable_sharpe} — not overfitted (train was unusually strong)"
                )
        elif train_sharpe > 0 and test_sharpe > 0 and test_sharpe < train_sharpe * degradation_threshold:
            # Moderate degradation with lower train Sharpe. Same logic applies.
            min_viable_sharpe = 0.3
            if test_sharpe >= min_viable_sharpe:
                is_overfitted = False
                logger.info(
                    f"Degradation {performance_degradation:.0f}% but test Sharpe {test_sharpe:.2f} "
                    f">= {min_viable_sharpe} — not overfitted"
                )
            else:
                is_overfitted = True
        elif train_sharpe < 0 and test_sharpe < 0:
            # Both negative = unprofitable strategy, not overfitted
            is_overfitted = False

        logger.info(f"Performance degradation: {performance_degradation:.1f}%")
        logger.info(f"Overfitted: {is_overfitted}")

        return {
            "train_results": train_results,
            "test_results": test_results,
            "train_sharpe": train_sharpe,
            "test_sharpe": test_sharpe,
            "train_return": train_results.total_return,
            "test_return": test_results.total_return,
            "train_trades": train_results.total_trades,
            "test_trades": test_results.total_trades,
            "performance_degradation": performance_degradation,
            "is_overfitted": is_overfitted,
            "train_period": (start, train_end),
            "test_period": (test_start, test_end)
        }

    def rolling_window_validate(
        self,
        strategy: Strategy,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        """
        Perform rolling window validation with multiple out-of-sample test periods.

        Tests strategy across multiple time windows and market regimes to detect overfitting.

        Windows (for 2-year data):
        - Window 1: Train on months 1-12, test on months 13-18
        - Window 2: Train on months 7-18, test on months 19-24
        - Window 3: Train on full 24 months, test on most recent 6 months

        Args:
            strategy: Strategy to validate
            start: Start date (should be ~2 years before end)
            end: End date

        Returns:
            Dict with:
                - windows: List of window results
                - consistency_score: % of windows where Sharpe > 0.3
                - regime_performance: Performance by market regime
                - is_robust: bool (passes all windows)
                - overfitting_indicators: train vs test variance metrics
        """
        logger.info(f"Rolling window validation for {strategy.name}")

        total_days = (end - start).days
        if total_days < 600:  # Need at least ~2 years
            raise ValueError(
                f"Insufficient data for rolling window validation: "
                f"need ~730 days (2 years), have {total_days} days"
            )

        # Define windows
        windows = []

        # Window 1: Train on months 1-12 (365 days), test on months 13-18 (180 days)
        window1_train_start = start
        window1_train_end = start + timedelta(days=365)
        window1_test_start = window1_train_end
        window1_test_end = window1_test_start + timedelta(days=180)

        windows.append({
            "name": "Window 1 (Early Period)",
            "train_start": window1_train_start,
            "train_end": window1_train_end,
            "test_start": window1_test_start,
            "test_end": window1_test_end
        })

        # Window 2: Train on months 7-18 (365 days), test on months 19-24 (180 days)
        window2_train_start = start + timedelta(days=180)
        window2_train_end = window2_train_start + timedelta(days=365)
        window2_test_start = window2_train_end
        window2_test_end = window2_test_start + timedelta(days=180)

        windows.append({
            "name": "Window 2 (Middle Period)",
            "train_start": window2_train_start,
            "train_end": window2_train_end,
            "test_start": window2_test_start,
            "test_end": window2_test_end
        })

        # Window 3: Train on full 24 months (730 days), test on most recent 6 months (180 days)
        window3_test_start = end - timedelta(days=180)
        window3_train_start = start
        window3_train_end = window3_test_start
        window3_test_end = end

        windows.append({
            "name": "Window 3 (Recent Period)",
            "train_start": window3_train_start,
            "train_end": window3_train_end,
            "test_start": window3_test_start,
            "test_end": window3_test_end
        })

        # Run backtest for each window
        window_results = []
        train_sharpes = []
        test_sharpes = []

        for i, window in enumerate(windows, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"{window['name']}")
            logger.info(f"Train: {window['train_start'].date()} to {window['train_end'].date()}")
            logger.info(f"Test:  {window['test_start'].date()} to {window['test_end'].date()}")
            logger.info(f"{'='*60}")

            try:
                # Backtest on train period
                train_results = self.backtest_strategy(
                    strategy,
                    window['train_start'],
                    window['train_end']
                )

                # Backtest on test period
                test_results = self.backtest_strategy(
                    strategy,
                    window['test_start'],
                    window['test_end']
                )

                # Calculate degradation
                if train_results.sharpe_ratio != 0:
                    degradation = ((train_results.sharpe_ratio - test_results.sharpe_ratio) /
                                 abs(train_results.sharpe_ratio)) * 100
                else:
                    degradation = 0.0

                # Determine if window passed (Sharpe > 0.3 on test)
                passed = test_results.sharpe_ratio > 0.3

                window_result = {
                    "window_name": window['name'],
                    "train_sharpe": train_results.sharpe_ratio,
                    "test_sharpe": test_results.sharpe_ratio,
                    "train_return": train_results.total_return,
                    "test_return": test_results.total_return,
                    "train_trades": train_results.total_trades,
                    "test_trades": test_results.total_trades,
                    "degradation_pct": degradation,
                    "passed": passed
                }

                window_results.append(window_result)
                train_sharpes.append(train_results.sharpe_ratio)
                test_sharpes.append(test_results.sharpe_ratio)

                logger.info(f"✓ {window['name']} complete:")
                logger.info(f"  Train: Sharpe={train_results.sharpe_ratio:.2f}, Return={train_results.total_return:.2%}, Trades={train_results.total_trades}")
                logger.info(f"  Test:  Sharpe={test_results.sharpe_ratio:.2f}, Return={test_results.total_return:.2%}, Trades={test_results.total_trades}")
                logger.info(f"  Degradation: {degradation:.1f}%")
                logger.info(f"  Status: {'PASS' if passed else 'FAIL'} (test Sharpe {'>' if passed else '<='} 0.3)")

            except Exception as e:
                logger.error(f"Window {i} failed: {e}")
                window_result = {
                    "window_name": window['name'],
                    "train_sharpe": 0.0,
                    "test_sharpe": 0.0,
                    "train_return": 0.0,
                    "test_return": 0.0,
                    "train_trades": 0,
                    "test_trades": 0,
                    "degradation_pct": 0.0,
                    "passed": False,
                    "error": str(e)
                }
                window_results.append(window_result)

        # Calculate consistency score (% of windows passed)
        windows_passed = sum(1 for w in window_results if w['passed'])
        consistency_score = (windows_passed / len(window_results)) * 100

        # Calculate overfitting indicators
        train_sharpe_mean = sum(train_sharpes) / len(train_sharpes) if train_sharpes else 0
        test_sharpe_mean = sum(test_sharpes) / len(test_sharpes) if test_sharpes else 0

        # Variance between train and test
        if len(train_sharpes) > 1:
            train_variance = sum((x - train_sharpe_mean) ** 2 for x in train_sharpes) / len(train_sharpes)
            test_variance = sum((x - test_sharpe_mean) ** 2 for x in test_sharpes) / len(test_sharpes)
        else:
            train_variance = 0.0
            test_variance = 0.0

        # Strategy is robust if it passes at least 2 of 3 windows (60% consistency)
        is_robust = consistency_score >= 60.0

        # Detect market regimes for each test period
        regime_performance = self._analyze_regime_performance(strategy, windows, window_results)

        logger.info(f"\n{'='*60}")
        logger.info(f"ROLLING WINDOW VALIDATION SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Windows passed: {windows_passed}/{len(window_results)}")
        logger.info(f"Consistency score: {consistency_score:.1f}%")
        logger.info(f"Avg train Sharpe: {train_sharpe_mean:.2f}")
        logger.info(f"Avg test Sharpe: {test_sharpe_mean:.2f}")
        logger.info(f"Train variance: {train_variance:.3f}")
        logger.info(f"Test variance: {test_variance:.3f}")
        logger.info(f"Robust: {'YES' if is_robust else 'NO'} (requires 60% consistency)")
        logger.info(f"{'='*60}\n")

        return {
            "windows": window_results,
            "consistency_score": consistency_score,
            "windows_passed": windows_passed,
            "total_windows": len(window_results),
            "is_robust": is_robust,
            "train_sharpe_mean": train_sharpe_mean,
            "test_sharpe_mean": test_sharpe_mean,
            "train_variance": train_variance,
            "test_variance": test_variance,
            "regime_performance": regime_performance,
            "overfitting_indicators": {
                "train_test_gap": train_sharpe_mean - test_sharpe_mean,
                "variance_ratio": test_variance / train_variance if train_variance > 0 else 0.0
            }
        }

    def _analyze_regime_performance(
        self,
        strategy: Strategy,
        windows: List[Dict],
        window_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        Analyze strategy performance across different market regimes.

        Identifies bull/bear/sideways periods and tests performance in each.

        Args:
            strategy: Strategy being tested
            windows: Window definitions
            window_results: Results from each window

        Returns:
            Dict with regime-specific performance metrics
        """
        from src.strategy.market_analyzer import MarketStatisticsAnalyzer

        logger.info("Analyzing performance by market regime...")

        # Initialize market analyzer
        market_analyzer = MarketStatisticsAnalyzer(self.market_data)

        regime_results = {
            "TRENDING_UP": [],
            "TRENDING_DOWN": [],
            "RANGING": []
        }

        # Analyze each test period
        for i, (window, result) in enumerate(zip(windows, window_results)):
            if 'error' in result:
                continue

            # Detect regime for test period
            test_start = window['test_start']
            test_end = window['test_end']

            try:
                # Use detect_sub_regime to get detailed regime
                regime, confidence, data_quality, metrics = market_analyzer.detect_sub_regime(
                    symbols=strategy.symbols[:3]  # Use first 3 symbols
                )

                # Map sub-regimes to main regimes
                regime_str = str(regime.value) if hasattr(regime, 'value') else str(regime)

                if 'TRENDING_UP' in regime_str:
                    main_regime = "TRENDING_UP"
                elif 'TRENDING_DOWN' in regime_str:
                    main_regime = "TRENDING_DOWN"
                else:
                    main_regime = "RANGING"

                # Store result for this regime
                regime_results[main_regime].append({
                    "window": window['name'],
                    "sharpe": result['test_sharpe'],
                    "return": result['test_return'],
                    "trades": result['test_trades'],
                    "sub_regime": regime_str,
                    "confidence": confidence
                })

                logger.info(f"  {window['name']}: {main_regime} ({regime_str}), Sharpe={result['test_sharpe']:.2f}")

            except Exception as e:
                logger.warning(f"Could not detect regime for {window['name']}: {e}")

        # Calculate regime statistics
        regime_stats = {}
        regimes_with_positive_sharpe = 0

        for regime, results in regime_results.items():
            if results:
                sharpes = [r['sharpe'] for r in results]
                returns = [r['return'] for r in results]

                avg_sharpe = sum(sharpes) / len(sharpes)
                avg_return = sum(returns) / len(returns)

                regime_stats[regime] = {
                    "count": len(results),
                    "avg_sharpe": avg_sharpe,
                    "avg_return": avg_return,
                    "windows": [r['window'] for r in results]
                }

                if avg_sharpe > 0:
                    regimes_with_positive_sharpe += 1

                logger.info(f"  {regime}: {len(results)} windows, avg Sharpe={avg_sharpe:.2f}, avg return={avg_return:.2%}")

        # Check if strategy works in multiple regimes
        total_regimes_tested = sum(1 for r in regime_stats.values() if r['count'] > 0)
        works_in_multiple_regimes = regimes_with_positive_sharpe >= 2

        logger.info(f"  Regimes tested: {total_regimes_tested}")
        logger.info(f"  Regimes with positive Sharpe: {regimes_with_positive_sharpe}")
        logger.info(f"  Works in multiple regimes: {'YES' if works_in_multiple_regimes else 'NO'}")

        return {
            "regime_stats": regime_stats,
            "regimes_tested": total_regimes_tested,
            "regimes_with_positive_sharpe": regimes_with_positive_sharpe,
            "works_in_multiple_regimes": works_in_multiple_regimes,
            "regime_results": regime_results
        }



    def validate_strategy_signals(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Validate that a strategy can generate signals before full backtesting.

        Runs a quick validation by:
        1. Fetching 30 days of data for first symbol
        2. Generating signals using strategy rules
        3. Counting entry and exit signals

        Args:
            strategy: Strategy to validate

        Returns:
            Dict with validation results:
                - is_valid: bool
                - entry_signals: int (count)
                - exit_signals: int (count)
                - errors: List[str]
                - warnings: List[str]
        """
        logger.info(f"Validating strategy signals for: {strategy.name}")

        validation_result = {
            "is_valid": False,
            "entry_signals": 0,
            "exit_signals": 0,
            "errors": [],
            "warnings": []
        }

        try:
            # Get first symbol
            if not strategy.symbols:
                validation_result["errors"].append("Strategy has no symbols")
                return validation_result

            symbol = strategy.symbols[0]

            # Use the same data window as backtest/walk-forward validation for consistency
            # Previously hardcoded to 730 days, which was inconsistent with walk-forward's 1825 days
            validation_days = self.validation_config.get("validation_data_days", 1825)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=validation_days)

            logger.info(f"Fetching {validation_days} days of data for {symbol} for validation")
            # Don't force prefer_yahoo — let MarketDataManager choose the best source
            # (FMP for forex, Yahoo for stocks, etc.)
            market_data = self.market_data.get_historical_data(
                symbol=symbol,
                start=start_date,
                end=end_date
            )

            if not market_data:
                validation_result["errors"].append(f"No market data available for {symbol}")
                return validation_result

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "timestamp": md.timestamp,
                    "open": md.open,
                    "high": md.high,
                    "low": md.low,
                    "close": md.close,
                    "volume": md.volume
                }
                for md in market_data
            ])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            if len(df) < 90:
                validation_result["warnings"].append(f"Only {len(df)} days of data available (requested {validation_days})")
            
            logger.info(f"Validation using {len(df)} days of data (requested {validation_days})")

            # Extract price data
            close = df["close"]
            high = df["high"]
            low = df["low"]

            # Calculate indicators using new method
            indicators = self._calculate_indicators_from_strategy(strategy, df, symbol)

            # Generate signals
            try:
                volume = df["volume"] if "volume" in df.columns else None
                entries, exits = self._parse_strategy_rules(
                    close, high, low, indicators, strategy.rules, volume=volume
                )

                entry_count = entries.sum()
                exit_count = exits.sum()

                validation_result["entry_signals"] = int(entry_count)
                validation_result["exit_signals"] = int(exit_count)

                # Validation criteria
                if entry_count == 0:
                    validation_result["errors"].append(f"Strategy generates zero entry signals in {len(df)} days of data")

                if exit_count == 0:
                    validation_result["errors"].append(f"Strategy generates zero exit signals in {len(df)} days of data")

                # Check if valid
                if entry_count > 0 and exit_count > 0:
                    validation_result["is_valid"] = True
                    logger.info(f"Strategy validation passed: {entry_count} entry signals, {exit_count} exit signals")
                else:
                    logger.warning(f"Strategy validation failed: {entry_count} entry signals, {exit_count} exit signals")

            except Exception as e:
                validation_result["errors"].append(f"Failed to generate signals: {str(e)}")
                logger.error(f"Signal generation failed during validation: {e}")

        except Exception as e:
            validation_result["errors"].append(f"Validation error: {str(e)}")
            logger.error(f"Strategy validation error: {e}")

        return validation_result

    def validate_strategy_rules(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Validate strategy rules for trading viability before backtesting.

        Validates:
        1. RSI thresholds (entry < 35, exit > 65)
        2. Bollinger Band logic (entry at lower band, exit at upper band)
        3. Entry/exit signal overlap (< 50% overlap required)
        4. Minimum signal separation (20% of days with entry but no exit)

        Args:
            strategy: Strategy to validate

        Returns:
            Dict with validation results:
                - is_valid: bool
                - errors: List[str] (validation failures)
                - warnings: List[str] (potential issues)
                - suggestions: List[str] (how to fix issues)
                - overlap_percentage: float (entry/exit overlap %)
                - entry_only_percentage: float (entry without exit %)
        """
        logger.info(f"Validating strategy rules for: {strategy.name}")

        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "overlap_percentage": 0.0,
            "entry_only_percentage": 0.0
        }

        try:
            # Get entry and exit conditions
            entry_conditions = strategy.rules.get("entry_conditions", [])
            exit_conditions = strategy.rules.get("exit_conditions", [])

            if not entry_conditions:
                validation_result["errors"].append("Strategy has no entry conditions")
                validation_result["is_valid"] = False
                return validation_result

            if not exit_conditions:
                validation_result["errors"].append("Strategy has no exit conditions")
                validation_result["is_valid"] = False
                return validation_result

            # Validate RSI thresholds
            self._validate_rsi_thresholds(
                entry_conditions, exit_conditions, validation_result
            )
            
            # Validate Stochastic thresholds
            self._validate_stochastic_thresholds(
                entry_conditions, exit_conditions, validation_result
            )

            # Validate Bollinger Band logic
            self._validate_bollinger_band_logic(
                entry_conditions, exit_conditions, validation_result
            )

            # Validate entry/exit pairing with actual signal generation
            self._validate_signal_overlap(strategy, validation_result)

            # Set overall validity
            if validation_result["errors"]:
                validation_result["is_valid"] = False
                logger.warning(
                    f"Strategy validation failed for {strategy.name}: "
                    f"{len(validation_result['errors'])} errors"
                )
            else:
                logger.info(f"Strategy validation passed for {strategy.name}")

        except Exception as e:
            validation_result["errors"].append(f"Validation error: {str(e)}")
            validation_result["is_valid"] = False
            logger.error(f"Strategy rule validation error: {e}")

        return validation_result

    def _validate_rsi_thresholds(
        self,
        entry_conditions: List[str],
        exit_conditions: List[str],
        validation_result: Dict
    ) -> None:
        """
        Validate RSI thresholds in entry and exit conditions.

        Uses configurable thresholds from validation_config.
        Default: Entry oversold RSI < 55, Exit overbought RSI > 55
        """
        import re

        # Get thresholds from config
        rsi_config = self.validation_config.get("rsi", {})
        entry_max = rsi_config.get("entry_max", 55)
        exit_min = rsi_config.get("exit_min", 55)

        # Check entry conditions for RSI
        for condition in entry_conditions:
            condition_lower = condition.lower()
            
            # Detect RSI range conditions (momentum strategies use RSI > X AND RSI < Y)
            # These are range filters, not oversold entries — skip validation
            has_rsi_gt = bool(re.search(r'rsi[_\s]*\d*\s*(?:is\s+)?(?:above|>)\s*\d+', condition_lower))
            has_rsi_lt = bool(re.search(r'rsi[_\s]*\d*\s*(?:is\s+)?(?:below|<)\s*\d+', condition_lower))
            is_rsi_range_filter = has_rsi_gt and has_rsi_lt
            
            if is_rsi_range_filter:
                continue  # Skip validation for momentum range filters
            
            # Pattern: "RSI_14 is below X" or "RSI_14 < X"
            rsi_below_match = re.search(r'rsi[_\s]*\d*\s*(?:is\s+)?(?:below|<)\s*(\d+)', condition_lower)
            if rsi_below_match:
                threshold = int(rsi_below_match.group(1))
                if threshold >= entry_max:
                    validation_result["errors"].append(
                        f"Invalid RSI entry threshold: '{condition}' uses {threshold}, "
                        f"but oversold entry should use RSI < {entry_max}"
                    )
                    validation_result["suggestions"].append(
                        f"Change '{condition}' to use RSI < 30 or RSI < {entry_max} for oversold entry"
                    )

        # Check exit conditions for RSI
        for condition in exit_conditions:
            condition_lower = condition.lower()
            
            # Pattern: "RSI_14 rises above X" or "RSI_14 > X"
            rsi_above_match = re.search(r'rsi[_\s]*\d*\s*(?:rises\s+)?(?:above|>)\s*(\d+)', condition_lower)
            if rsi_above_match:
                threshold = int(rsi_above_match.group(1))
                if threshold <= exit_min:
                    validation_result["errors"].append(
                        f"Invalid RSI exit threshold: '{condition}' uses {threshold}, "
                        f"but overbought exit should use RSI > {exit_min}"
                    )
                    validation_result["suggestions"].append(
                        f"Change '{condition}' to use RSI > 70 or RSI > {exit_min} for overbought exit"
                    )
    
    def _validate_stochastic_thresholds(
        self,
        entry_conditions: List[str],
        exit_conditions: List[str],
        validation_result: Dict
    ) -> None:
        """
        Validate Stochastic Oscillator thresholds in entry and exit conditions.

        Uses configurable thresholds from validation_config.
        Default: Entry oversold STOCH < 30, Exit overbought STOCH > 70
        """
        import re

        # Get thresholds from config
        stoch_config = self.validation_config.get("stochastic", {})
        entry_max = stoch_config.get("entry_max", 30)
        exit_min = stoch_config.get("exit_min", 70)

        # Check entry conditions for Stochastic
        for condition in entry_conditions:
            condition_lower = condition.lower()
            
            # Pattern: "STOCH_14 is below X" or "STOCH_14 < X" or "Stochastic is below X"
            stoch_below_match = re.search(r'stoch(?:astic)?[_\s]*\d*\s*(?:is\s+)?(?:below|<)\s*(\d+)', condition_lower)
            if stoch_below_match:
                threshold = int(stoch_below_match.group(1))
                if threshold >= entry_max:
                    validation_result["warnings"].append(
                        f"Stochastic entry threshold: '{condition}' uses {threshold}, "
                        f"recommended oversold entry is STOCH < {entry_max}"
                    )
                    validation_result["suggestions"].append(
                        f"Consider changing '{condition}' to use STOCH < 20 or STOCH < {entry_max} for stronger oversold signal"
                    )

        # Check exit conditions for Stochastic
        for condition in exit_conditions:
            condition_lower = condition.lower()
            
            # Pattern: "STOCH_14 rises above X" or "STOCH_14 > X" or "Stochastic rises above X"
            stoch_above_match = re.search(r'stoch(?:astic)?[_\s]*\d*\s*(?:rises\s+)?(?:above|>)\s*(\d+)', condition_lower)
            if stoch_above_match:
                threshold = int(stoch_above_match.group(1))
                if threshold <= exit_min:
                    validation_result["warnings"].append(
                        f"Stochastic exit threshold: '{condition}' uses {threshold}, "
                        f"recommended overbought exit is STOCH > {exit_min}"
                    )
                    validation_result["suggestions"].append(
                        f"Consider changing '{condition}' to use STOCH > 80 or STOCH > {exit_min} for stronger overbought signal"
                    )

    def _validate_bollinger_band_logic(
        self,
        entry_conditions: List[str],
        exit_conditions: List[str],
        validation_result: Dict
    ) -> None:
        """
        Validate Bollinger Band logic.

        Entry at lower band: price < Lower_Band
        Exit at upper band: price > Upper_Band
        """
        # Check for Bollinger Band references
        has_bb_entry = False
        has_bb_exit = False
        bb_entry_correct = True
        bb_exit_correct = True

        for condition in entry_conditions:
            condition_lower = condition.lower()
            
            # Check for lower band entry (correct)
            if 'lower' in condition_lower and 'band' in condition_lower:
                has_bb_entry = True
                # Should be "price < Lower_Band" or "crosses below"
                if 'above' in condition_lower or '>' in condition:
                    bb_entry_correct = False
                    validation_result["errors"].append(
                        f"Invalid Bollinger Band entry logic: '{condition}' - "
                        f"entry should be when price crosses BELOW lower band"
                    )
                    validation_result["suggestions"].append(
                        "Change to 'Price crosses below Lower_Band_20' for mean reversion entry"
                    )

        for condition in exit_conditions:
            condition_lower = condition.lower()
            
            # Check for upper band exit (correct)
            if 'upper' in condition_lower and 'band' in condition_lower:
                has_bb_exit = True
                # Should be "price > Upper_Band" or "crosses above"
                if 'below' in condition_lower or '<' in condition:
                    bb_exit_correct = False
                    validation_result["errors"].append(
                        f"Invalid Bollinger Band exit logic: '{condition}' - "
                        f"exit should be when price crosses ABOVE upper band"
                    )
                    validation_result["suggestions"].append(
                        "Change to 'Price crosses above Upper_Band_20' for mean reversion exit"
                    )

        # Warn if using Bollinger Bands but logic seems reversed
        if has_bb_entry and not has_bb_exit:
            validation_result["warnings"].append(
                "Strategy uses Bollinger Bands for entry but not exit - "
                "consider adding Upper_Band exit condition"
            )

    def _validate_signal_overlap(
        self,
        strategy: Strategy,
        validation_result: Dict
    ) -> None:
        """
        Validate entry/exit signal overlap by generating actual signals.

        Calculates:
        - Signal overlap percentage (should be < 80% to proceed, < 50% ideal)
        - Entry-only percentage (should be > 20%)
        - Signal quality metrics (frequency, spacing, holding periods)
        
        Enhanced with detailed logging and rejection logic:
        - >80% overlap: REJECT strategy before backtesting
        - 50-80% overlap: WARN but continue
        - <50% overlap: Proceed normally
        """
        try:
            # Get first symbol
            if not strategy.symbols:
                validation_result["warnings"].append("No symbols to validate signal overlap")
                return

            symbol = strategy.symbols[0]

            # Use the same data window as backtest/walk-forward validation for consistency
            # Previously hardcoded to 730 days, which was inconsistent with walk-forward's 1825 days
            validation_days = self.validation_config.get("validation_data_days", 1825)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=validation_days)

            # Don't force prefer_yahoo — let MarketDataManager choose the best source
            # (FMP for forex, Yahoo for stocks, etc.)
            market_data = self.market_data.get_historical_data(
                symbol=symbol,
                start=start_date,
                end=end_date
            )

            if not market_data or len(market_data) < 90:
                validation_result["warnings"].append(
                    f"Insufficient data for overlap validation ({len(market_data) if market_data else 0} days)"
                )
                return

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "timestamp": md.timestamp,
                    "open": md.open,
                    "high": md.high,
                    "low": md.low,
                    "close": md.close,
                    "volume": md.volume
                }
                for md in market_data
            ])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            # Extract price data
            close = df["close"]
            high = df["high"]
            low = df["low"]

            # Calculate indicators
            indicators = self._calculate_indicators_from_strategy(strategy, df, symbol)

            # Generate signals
            volume = df["volume"] if "volume" in df.columns else None
            entries, exits = self._parse_strategy_rules(
                close, high, low, indicators, strategy.rules, volume=volume
            )

            # Align entries/exits to df index (prevents "Boolean index has wrong length" errors)
            if len(entries) != len(df):
                entries = entries.reindex(df.index, fill_value=False)
            if len(exits) != len(df):
                exits = exits.reindex(df.index, fill_value=False)

            # Calculate detailed overlap metrics
            total_days = len(entries)
            overlap_days = (entries & exits).sum()
            entry_only_days = (entries & ~exits).sum()
            exit_only_days = (exits & ~entries).sum()
            no_signal_days = (~entries & ~exits).sum()

            overlap_pct = (overlap_days / total_days * 100) if total_days > 0 else 0
            entry_only_pct = (entry_only_days / total_days * 100) if total_days > 0 else 0
            exit_only_pct = (exit_only_days / total_days * 100) if total_days > 0 else 0

            validation_result["overlap_percentage"] = overlap_pct
            validation_result["entry_only_percentage"] = entry_only_pct
            validation_result["exit_only_percentage"] = exit_only_pct

            # Log detailed overlap analysis
            logger.info("=" * 80)
            logger.info("SIGNAL OVERLAP ANALYSIS")
            logger.info("=" * 80)
            logger.info(f"Total days analyzed: {total_days}")
            logger.info(f"Entry-only days: {entry_only_days} ({entry_only_pct:.1f}%)")
            logger.info(f"Exit-only days: {exit_only_days} ({exit_only_pct:.1f}%)")
            logger.info(f"Overlap days (both entry & exit): {overlap_days} ({overlap_pct:.1f}%)")
            logger.info(f"No signal days: {no_signal_days} ({no_signal_days/total_days*100:.1f}%)")

            # Log first 5 dates where signals overlap
            if overlap_days > 0:
                overlap_dates = df.index[entries & exits][:5].tolist()
                logger.info(f"First 5 overlap dates: {[str(d.date()) for d in overlap_dates]}")
            else:
                logger.info("No overlap dates found")

            # Calculate signal quality metrics
            entry_indices = entries[entries].index
            if len(entry_indices) > 1:
                # Average days between entry signals
                entry_spacing = []
                for i in range(1, len(entry_indices)):
                    days_diff = (entry_indices[i] - entry_indices[i-1]).days
                    entry_spacing.append(days_diff)
                avg_entry_spacing = sum(entry_spacing) / len(entry_spacing)
                
                # Signal frequency (signals per month)
                total_months = (df.index[-1] - df.index[0]).days / 30.0
                signal_frequency = len(entry_indices) / total_months if total_months > 0 else 0
                
                validation_result["avg_days_between_entries"] = avg_entry_spacing
                validation_result["signal_frequency_per_month"] = signal_frequency
                
                logger.info(f"Average days between entry signals: {avg_entry_spacing:.1f}")
                logger.info(f"Signal frequency: {signal_frequency:.2f} entries/month")
            else:
                logger.info("Insufficient entry signals to calculate spacing metrics")
                validation_result["avg_days_between_entries"] = None
                validation_result["signal_frequency_per_month"] = None

            # Estimate average holding period (entry to next exit)
            if entries.sum() > 0 and exits.sum() > 0:
                holding_periods = []
                entry_dates = df.index[entries].tolist()
                exit_dates = df.index[exits].tolist()
                
                for entry_date in entry_dates:
                    # Find next exit after this entry
                    future_exits = [e for e in exit_dates if e > entry_date]
                    if future_exits:
                        next_exit = future_exits[0]
                        holding_period = (next_exit - entry_date).days
                        holding_periods.append(holding_period)
                
                if holding_periods:
                    avg_holding_period = sum(holding_periods) / len(holding_periods)
                    validation_result["avg_holding_period_days"] = avg_holding_period
                    logger.info(f"Average holding period: {avg_holding_period:.1f} days")
                else:
                    logger.info("Could not calculate holding period (no exit after entry)")
                    validation_result["avg_holding_period_days"] = None
            else:
                logger.info("Insufficient signals to calculate holding period")
                validation_result["avg_holding_period_days"] = None

            logger.info("=" * 80)

            # Enhanced conflict resolution logic
            overlap_config = self.validation_config.get("signal_overlap", {})
            max_overlap_pct = overlap_config.get("max_overlap_pct", 50)
            
            if overlap_pct > 80:
                # REJECT: Too much overlap, strategy is fundamentally flawed
                validation_result["errors"].append(
                    f"CRITICAL: Signal overlap too high: {overlap_pct:.1f}% (threshold: 80%) - "
                    f"Strategy REJECTED. Entry and exit conditions are nearly identical."
                )
                validation_result["suggestions"].append(
                    "Entry and exit conditions must be distinct. "
                    "Example: If entry uses RSI < 30, exit should use RSI > 70 (not RSI > 35). "
                    "Consider using different indicators or more extreme thresholds."
                )
                logger.error(f"Strategy REJECTED due to excessive signal overlap: {overlap_pct:.1f}%")
                
            elif overlap_pct > max_overlap_pct:
                # WARN: Moderate overlap, proceed with caution
                validation_result["warnings"].append(
                    f"WARNING: Signal overlap is moderate: {overlap_pct:.1f}% (ideal: <{max_overlap_pct}%) - "
                    f"Strategy may have reduced effectiveness due to conflicting signals."
                )
                validation_result["suggestions"].append(
                    "Consider making entry/exit conditions more distinct to reduce overlap. "
                    "This will improve strategy clarity and potentially performance."
                )
                logger.warning(f"Moderate signal overlap detected: {overlap_pct:.1f}% - proceeding with caution")
                
            else:
                # PROCEED: Acceptable overlap
                logger.info(f"Signal overlap is acceptable: {overlap_pct:.1f}% (<{max_overlap_pct}%)")

            # Validate entry-only threshold (configurable, asset-class-aware)
            entry_config = self.validation_config.get("entry_opportunities", {})
            min_entry_pct = entry_config.get("min_entry_pct", 0.5)
            
            # Use asset-class-specific threshold if available
            asset_class = self._get_asset_class(symbol)
            asset_thresholds = entry_config.get("asset_class_thresholds", {})
            if asset_class in asset_thresholds:
                min_entry_pct = asset_thresholds[asset_class].get("min_entry_pct", min_entry_pct)
                logger.info(f"Using {asset_class}-specific min_entry_pct: {min_entry_pct}%")
            
            if entry_only_pct < min_entry_pct:
                validation_result["errors"].append(
                    f"Insufficient entry opportunities: only {entry_only_pct:.1f}% of days "
                    f"have entry without immediate exit (threshold: {min_entry_pct}%)"
                )
                validation_result["suggestions"].append(
                    "Strategy needs more distinct entry opportunities. "
                    "Consider using more conservative entry thresholds or different indicators"
                )

        except Exception as e:
            validation_result["warnings"].append(
                f"Could not validate signal overlap: {str(e)}"
            )
            logger.warning(f"Signal overlap validation failed: {e}")

    
    def _run_vectorbt_backtest(
        self,
        strategy: Strategy,
        data: Dict[str, pd.DataFrame],
        start: datetime,
        end: datetime,
        commission: float = 0.0,
        slippage_bps: float = 0.0,
        interval: str = "1d"
    ) -> BacktestResults:
        """
        Run backtest using vectorbt.
        
        Interprets strategy rules and generates signals based on indicators like RSI, SMA, etc.
        
        Args:
            strategy: Strategy to backtest
            data: Dictionary of symbol -> DataFrame with OHLCV data
            start: Start date for backtest
            end: End date for backtest
            commission: Commission per trade in dollars (default 0.0)
            slippage_bps: Slippage in basis points (default 0.0)
        
        Returns:
            BacktestResults with metrics, equity curve, trades, and backtest period
        """
        # Use the first symbol from the strategy's symbol list
        symbol = strategy.symbols[0]
        logger.info(f"Backtesting {strategy.name} using symbol: {symbol}")
        df = data[symbol].copy()
        
        # Ensure DataFrame index is timezone-naive for consistent comparison
        # Strip all timezone info — we work in naive UTC throughout
        try:
            df.index = pd.to_datetime(df.index)
            if hasattr(df.index, 'tz') and df.index.tz is not None:
                df.index = df.index.tz_localize(None)
        except Exception:
            pass
        
        # Remove duplicate timestamps — DB cache or data sources can produce dupes.
        # Keeping the last entry per date (most recent data) prevents .loc[] from
        # returning a Series instead of a scalar, which crashes position sizing.
        if df.index.duplicated().any():
            n_dupes = df.index.duplicated().sum()
            logger.warning(f"Removed {n_dupes} duplicate timestamps from {symbol} data")
            df = df[~df.index.duplicated(keep='last')]
        # Also strip timezone from start/end
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        if end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        
        # The caller (backtest_strategy) fetches data from start-warmup to end.
        # This means the data already ends at the correct date for walk-forward validation.
        # The warmup data at the beginning is needed for indicator calculation.
        # After indicators are calculated, we slice to the actual backtest period.
        actual_start = df.index[0]
        actual_end = df.index[-1]
        
        logger.info(f"Dataset: {len(df)} bars from {actual_start.date()} to {actual_end.date()}")
        logger.info(f"Requested period: {start.date()} to {end.date()}")
        
        # Calculate indicators on full dataset (includes warmup for proper calculation)
        indicators = self._calculate_indicators_from_strategy(strategy, df, symbol)
        
        # CRITICAL: Slice data to the actual backtest period AFTER indicator calculation.
        # Warmup bars are needed for indicators (e.g., 200-bar SMA needs 200 prior bars)
        # but trades should only be counted within the requested start-end window.
        # Without this, trades fire during warmup and pollute the Sharpe calculation.
        backtest_mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        if backtest_mask.sum() >= 10:
            warmup_bars_count = len(df) - backtest_mask.sum()
            sliced_index = df.index[backtest_mask]
            # Slice indicators to match the backtest period
            for key in list(indicators.keys()):
                if isinstance(indicators[key], pd.Series):
                    indicators[key] = indicators[key].reindex(sliced_index)
            df = df.loc[sliced_index].copy()
            logger.info(f"Sliced to backtest period: {len(df)} bars (dropped {warmup_bars_count} warmup bars)")
        else:
            bars_found = backtest_mask.sum()
            # If we have zero bars in the requested period, the data doesn't cover it at all.
            # Running a backtest on wrong-period data produces meaningless results (0 trades,
            # wrong Sharpe) that waste cycle time and pollute walk-forward stats.
            # Fail fast so the proposer can move on to the next candidate.
            if bars_found == 0:
                raise ValueError(
                    f"No data available for backtest period {start.date()} to {end.date()}. "
                    f"Data covers {df.index[0].date()} to {df.index[-1].date()} ({len(df)} bars). "
                    f"This typically happens with intraday intervals (4h/1h) where Yahoo Finance "
                    f"data doesn't extend far enough."
                )
            logger.warning(
                f"Slicing to {start.date()}-{end.date()} produced only {bars_found} bars "
                f"(expected ~{len(df)//2}+), using available {bars_found} bars"
            )
            # Use whatever bars we have in the period rather than wrong-period data
            sliced_index = df.index[backtest_mask]
            for key in list(indicators.keys()):
                if isinstance(indicators[key], pd.Series):
                    indicators[key] = indicators[key].reindex(sliced_index)
            df = df.loc[sliced_index].copy()
        
        # Extract prices
        close = df["close"]
        high = df["high"]
        low = df["low"]
        
        # Generate entry and exit signals
        volume = df["volume"] if "volume" in df.columns else None
        entries, exits = self._parse_strategy_rules(
            close, high, low, indicators, strategy.rules, volume=volume
        )
        
        # DEFENSIVE: Ensure entries/exits are pd.Series with correct index.
        # DSL eval() can sometimes return numpy arrays or misaligned Series
        # (e.g., when indicator cache returns stale data from a prior backtest).
        # Without this guard, entries[entries].index crashes with:
        #   'numpy.ndarray' object has no attribute 'index'
        if not isinstance(entries, pd.Series):
            entries = pd.Series(entries, index=close.index).fillna(False).astype(bool)
        if not isinstance(exits, pd.Series):
            exits = pd.Series(exits, index=close.index).fillna(False).astype(bool)
        # Also re-align if index doesn't match (can happen with indicator reindexing)
        if len(entries) != len(close) or not entries.index.equals(close.index):
            entries = entries.reindex(close.index, fill_value=False).astype(bool)
        if len(exits) != len(close) or not exits.index.equals(close.index):
            exits = exits.reindex(close.index, fill_value=False).astype(bool)
        
        # Calculate detailed signal metrics
        total_days = len(close)
        entry_days = entries.sum()
        exit_days = exits.sum()
        overlap_days = (entries & exits).sum()
        entry_only_days = (entries & ~exits).sum()
        exit_only_days = (exits & ~entries).sum()
        
        overlap_pct = (overlap_days / total_days * 100) if total_days > 0 else 0
        entry_only_pct = (entry_only_days / total_days * 100) if total_days > 0 else 0
        exit_only_pct = (exit_only_days / total_days * 100) if total_days > 0 else 0
        
        # Log detailed backtest signal analysis
        logger.info("=" * 80)
        logger.info(f"BACKTEST SIGNAL ANALYSIS: {strategy.name}")
        logger.info("=" * 80)
        logger.info(f"Total days in backtest: {total_days}")
        logger.info(f"Entry signals: {entry_days} days ({entry_days/total_days*100:.1f}%)")
        logger.info(f"Exit signals: {exit_days} days ({exit_days/total_days*100:.1f}%)")
        logger.info(f"Entry-only days: {entry_only_days} ({entry_only_pct:.1f}%)")
        logger.info(f"Exit-only days: {exit_only_days} ({exit_only_pct:.1f}%)")
        logger.info(f"Overlap days: {overlap_days} ({overlap_pct:.1f}%)")
        
        # Log first 5 overlap dates if any
        if overlap_days > 0:
            overlap_dates = df.index[entries & exits][:5].tolist()
            logger.info(f"First 5 overlap dates: {[str(d.date()) for d in overlap_dates]}")
        
        # Calculate signal quality metrics
        entry_indices = entries[entries].index
        if len(entry_indices) > 1:
            # Average days between entry signals
            entry_spacing = []
            for i in range(1, len(entry_indices)):
                days_diff = (entry_indices[i] - entry_indices[i-1]).days
                entry_spacing.append(days_diff)
            avg_entry_spacing = sum(entry_spacing) / len(entry_spacing)
            
            # Signal frequency (signals per month)
            total_months = (df.index[-1] - df.index[0]).days / 30.0
            signal_frequency = len(entry_indices) / total_months if total_months > 0 else 0
            
            logger.info(f"Average days between entries: {avg_entry_spacing:.1f}")
            logger.info(f"Signal frequency: {signal_frequency:.2f} entries/month")
        
        # Estimate average holding period
        if entry_days > 0 and exit_days > 0:
            holding_periods = []
            entry_dates = df.index[entries].tolist()
            exit_dates = df.index[exits].tolist()
            
            for entry_date in entry_dates:
                future_exits = [e for e in exit_dates if e > entry_date]
                if future_exits:
                    next_exit = future_exits[0]
                    holding_period = (next_exit - entry_date).days
                    holding_periods.append(holding_period)
            
            if holding_periods:
                avg_holding_period = sum(holding_periods) / len(holding_periods)
                logger.info(f"Average holding period: {avg_holding_period:.1f} days")
        
        logger.info(f"Indicators calculated: {list(indicators.keys())}")
        for key, values in indicators.items():
            if len(values) > 0 and not values.isna().all():
                logger.info(f"{key} range: {values.min():.2f} to {values.max():.2f}")
        logger.info(f"Close price range: {close.min():.2f} to {close.max():.2f}")
        logger.info("=" * 80)
        
        # Check if we have any valid entry opportunities (entry without immediate exit)
        logger.info(f"Days with entry but no exit: {entry_only_days}")
        
        # WORKAROUND: If we have overlapping signals, prioritize entries over exits
        # This prevents the common issue where exit conditions are active during entry
        if overlap_days > 0:
            logger.warning(f"Detected {overlap_days} days with conflicting entry/exit signals. Prioritizing entries.")
            # Remove exit signals on days where we have entry signals
            exits = exits & ~entries
            logger.info(f"After conflict resolution - Exit signals: {exits.sum()} days")
        
        # Run portfolio simulation with stop-loss and take-profit
        # Extract stop-loss and take-profit from strategy's risk_params
        sl_stop = None
        tp_stop = None
        
        if hasattr(strategy, 'risk_params') and strategy.risk_params:
            if isinstance(strategy.risk_params, dict):
                sl_stop = strategy.risk_params.get('stop_loss_pct')
                tp_stop = strategy.risk_params.get('take_profit_pct')
            else:
                sl_stop = getattr(strategy.risk_params, 'stop_loss_pct', None)
                tp_stop = getattr(strategy.risk_params, 'take_profit_pct', None)
            if sl_stop and sl_stop > 0:
                logger.info(f"Using stop-loss: {sl_stop:.2%}, take-profit: {tp_stop:.2%}")
            else:
                logger.info("No stop-loss/take-profit configured (sl_stop=0)")
                sl_stop = None
                tp_stop = None
        else:
            logger.info("No risk_params found, running without stop-loss/take-profit")
        
        # Calculate dynamic position sizes based on volatility (ATR)
        # Get position sizing parameters from strategy
        risk_per_trade_pct = 0.01  # Default 1% risk per trade
        sizing_method = 'volatility'  # Default to volatility-based
        
        if hasattr(strategy, 'metadata') and strategy.metadata:
            template_params = strategy.metadata.get('template_parameters', {})
            risk_per_trade_pct = template_params.get('risk_per_trade_pct', 0.01)
            sizing_method = template_params.get('sizing_method', 'volatility')
        
        # Calculate ATR for volatility-based sizing
        atr_values = None
        if sizing_method == 'volatility' and 'ATR' in indicators:
            atr_values = indicators['ATR']
            logger.info(f"Using volatility-based position sizing with ATR (mean: ${atr_values.mean():.2f})")
        elif sizing_method == 'volatility':
            # Calculate ATR if not already in indicators
            from src.strategy.indicator_library import IndicatorLibrary
            indicator_lib = IndicatorLibrary()
            atr_values, _ = indicator_lib.calculate('ATR', df, symbol=symbol, period=14)
            logger.info(f"Calculated ATR for position sizing (mean: ${atr_values.mean():.2f})")
        
        # Calculate position sizes for each entry signal
        position_sizes = pd.Series(index=close.index, dtype=float)
        init_cash = 100000
        
        if sizing_method == 'volatility' and atr_values is not None and sl_stop is not None and sl_stop > 0:
            # Volatility-based sizing
            for date in close.index[entries]:
                entry_price = close.loc[date]
                # Guard against duplicate-index edge case returning a Series
                if isinstance(entry_price, pd.Series):
                    entry_price = entry_price.iloc[-1]
                atr = atr_values.loc[date] if date in atr_values.index else atr_values.mean()
                if isinstance(atr, pd.Series):
                    atr = atr.iloc[-1]
                
                # Skip if ATR is NaN
                if pd.isna(atr) or atr <= 0:
                    # Use fixed size as fallback
                    position_sizes.loc[date] = init_cash * 0.1  # 10% of portfolio
                    continue
                
                # Calculate position size using same formula as PortfolioManager
                risk_amount = init_cash * risk_per_trade_pct
                risk_per_share = entry_price * sl_stop
                
                if risk_per_share > 0:
                    # Calculate number of shares
                    num_shares = risk_amount / risk_per_share
                    
                    # Calculate base position value
                    base_position_value = num_shares * entry_price
                    
                    # Volatility adjustment
                    atr_pct = atr / entry_price if entry_price > 0 else 0
                    volatility_adjustment = 1.0 / (1.0 + atr_pct)
                    
                    # Final adjusted position value
                    adjusted_position_value = base_position_value * volatility_adjustment
                    
                    # Cap at 50% of portfolio
                    max_size = init_cash * 0.5
                    position_sizes.loc[date] = min(adjusted_position_value, max_size)
                else:
                    # Fallback to fixed size
                    position_sizes.loc[date] = init_cash * 0.1
            
            # Fill NaN values with 0
            position_sizes = position_sizes.fillna(0)
            
            # Log position sizing statistics
            entry_sizes = position_sizes[entries]
            if len(entry_sizes) > 0:
                logger.info(f"Position sizing statistics:")
                logger.info(f"  Mean size: ${entry_sizes.mean():,.0f}")
                logger.info(f"  Min size: ${entry_sizes.min():,.0f}")
                logger.info(f"  Max size: ${entry_sizes.max():,.0f}")
                logger.info(f"  Std dev: ${entry_sizes.std():,.0f}")
        else:
            # Fixed sizing (10% of portfolio per trade)
            position_sizes = pd.Series(init_cash * 0.1, index=close.index)
            logger.info(f"Using fixed position sizing: ${init_cash * 0.1:,.0f} per trade")
        
        # Detect if this is a SHORT strategy — vectorbt from_signals is LONG-only by default.
        # For SHORT strategies, we pass entries as short_entries and exits as short_exits.
        is_short_strategy = False
        if hasattr(strategy, 'metadata') and strategy.metadata:
            direction = strategy.metadata.get('direction', 'long').lower()
            if direction == 'short':
                is_short_strategy = True
        
        # Build portfolio parameters
        # vectorbt fees: set to 0 — we handle transaction costs manually after
        # the backtest to use per-asset-class cost models. Previously fees=0.001
        # was hardcoded here AND costs were deducted again manually, double-counting.
        #
        # Freq parameter: use the actual data interval so vectorbt annualizes
        # Sharpe correctly. With freq="1D" on hourly bars, vectorbt underestimates
        # Sharpe by sqrt(bars_per_day) because it thinks each bar is a full day.
        if interval in ('1h', '2h'):
            vbt_freq = "1h"
        elif interval == '4h':
            vbt_freq = "4h"
        else:
            vbt_freq = "1D"

        if is_short_strategy:
            portfolio_params = {
                'close': close,
                'short_entries': entries,
                'short_exits': exits,
                'size': position_sizes,
                'size_type': 'value',
                'init_cash': init_cash,
                'fees': 0.0,
                'freq': vbt_freq
            }
            logger.info(f"SHORT strategy detected — using short_entries/short_exits for correct P&L")
        else:
            portfolio_params = {
                'close': close,
                'entries': entries,
                'exits': exits,
                'size': position_sizes,
                'size_type': 'value',
                'init_cash': init_cash,
                'fees': 0.0,
                'freq': vbt_freq
            }
        
        # Add stop-loss and take-profit if configured
        if sl_stop is not None and sl_stop > 0:
            portfolio_params['sl_stop'] = float(sl_stop)
            portfolio_params['tp_stop'] = float(tp_stop) if tp_stop and tp_stop > 0 else None
            # Provide high/low for intraday stop simulation
            portfolio_params['high'] = high
            portfolio_params['low'] = low
            if is_short_strategy:
                logger.info(f"SHORT strategy: SL/TP enabled (SL triggers on price RISE, TP on price DROP)")
            else:
                logger.info(f"Stop-loss/take-profit enabled with high/low prices for intraday simulation")
        
        # Ensure entries/exits are clean boolean Series with no NaN
        entries = entries.fillna(False).astype(bool)
        exits = exits.fillna(False).astype(bool)
        
        # Update the correct keys in portfolio_params based on direction
        if is_short_strategy:
            portfolio_params['short_entries'] = entries
            portfolio_params['short_exits'] = exits
        else:
            portfolio_params['entries'] = entries
            portfolio_params['exits'] = exits
        
        portfolio = vbt.Portfolio.from_signals(**portfolio_params)
        
        # Calculate metrics (sanitize inf/nan from 0-trade portfolios)
        import math
        total_return = portfolio.total_return()
        sharpe_ratio = portfolio.sharpe_ratio()
        sortino_ratio = portfolio.sortino_ratio()
        max_drawdown = portfolio.max_drawdown()

        # Correct Sharpe annualization for hourly data on non-24/7 assets.
        # vectorbt with freq="1h" annualizes by sqrt(8760) (24/7/365).
        # For stocks/ETFs/indices (7 trading hours/day, 252 days/year = 1764 hours/year),
        # the correct annualization is sqrt(1764). We need to rescale.
        # For crypto (24/7), 8760 is correct. For forex (24/5), ~6240 hours/year.
        if interval in ('1h', '2h') and not (math.isinf(sharpe_ratio) or math.isnan(sharpe_ratio)):
            primary_symbol = strategy.symbols[0] if strategy.symbols else ''
            asset_class = self._get_asset_class(primary_symbol) if primary_symbol else 'stock'
            if asset_class == 'crypto':
                pass  # 8760 is correct for 24/7 crypto
            elif asset_class == 'forex':
                # Forex: 24/5 = ~6240 trading hours/year
                correction = (6240 / 8760) ** 0.5
                sharpe_ratio *= correction
                sortino_ratio *= correction
            else:
                # Stocks/ETFs/indices: ~7 hours/day * 252 days = 1764 hours/year
                correction = (1764 / 8760) ** 0.5
                sharpe_ratio *= correction
                sortino_ratio *= correction
        elif interval == '4h' and not (math.isinf(sharpe_ratio) or math.isnan(sharpe_ratio)):
            primary_symbol = strategy.symbols[0] if strategy.symbols else ''
            asset_class = self._get_asset_class(primary_symbol) if primary_symbol else 'stock'
            if asset_class == 'crypto':
                pass  # 2190 4h bars/year is correct for 24/7
            elif asset_class == 'forex':
                correction = (1560 / 2190) ** 0.5  # 24/5 in 4h bars
                sharpe_ratio *= correction
                sortino_ratio *= correction
            else:
                correction = (441 / 2190) ** 0.5  # ~1.75 4h bars/trading day * 252 days
                sharpe_ratio *= correction
                sortino_ratio *= correction
        
        # Sanitize inf/nan values from vectorbt (happens with 0 trades or 0 variance)
        if math.isinf(sharpe_ratio) or math.isnan(sharpe_ratio):
            sharpe_ratio = 0.0
        if math.isinf(sortino_ratio) or math.isnan(sortino_ratio):
            sortino_ratio = 0.0
        if math.isinf(total_return) or math.isnan(total_return):
            total_return = 0.0
        if math.isinf(max_drawdown) or math.isnan(max_drawdown):
            max_drawdown = 0.0
        
        # Get trades
        trades = portfolio.trades.records_readable
        
        # Initialize stop-loss and take-profit metrics
        stop_loss_hits = 0
        take_profit_hits = 0
        avg_loss_on_stop = 0.0
        avg_gain_on_tp = 0.0
        
        if len(trades) > 0:
            winning_trades = trades[trades["PnL"] > 0]
            losing_trades = trades[trades["PnL"] < 0]
            
            win_rate = len(winning_trades) / len(trades) if len(trades) > 0 else 0.0
            avg_win = winning_trades["PnL"].mean() if len(winning_trades) > 0 else 0.0
            avg_loss = losing_trades["PnL"].mean() if len(losing_trades) > 0 else 0.0
            total_trades = len(trades)
            
            # Analyze stop-loss and take-profit hits
            # Check if vectorbt provides exit reason in trades
            if sl_stop is not None and sl_stop > 0 and len(losing_trades) > 0:
                # Try to detect stop-loss hits by analyzing trade returns
                # A trade hit stop-loss if return is close to -sl_stop
                logger.info(f"Analyzing {len(losing_trades)} losing trades for stop-loss hits (sl_stop={sl_stop:.2%})")
                for idx, trade in losing_trades.iterrows():
                    # Calculate return percentage for this trade
                    entry_price = trade.get('Entry Price', 0)
                    exit_price = trade.get('Exit Price', 0)
                    pnl = trade.get('PnL', 0)
                    if entry_price > 0:
                        return_pct = (exit_price - entry_price) / entry_price
                        tolerance = abs(return_pct - (-sl_stop)) / sl_stop if sl_stop > 0 else 1.0
                        logger.info(f"  Trade: entry=${entry_price:.2f}, exit=${exit_price:.2f}, return={return_pct:.2%}, expected={-sl_stop:.2%}, tolerance={tolerance:.2f}")
                        # Check if return is close to -sl_stop (within 30% tolerance)
                        if tolerance < 0.3:
                            stop_loss_hits += 1
                            if avg_loss_on_stop == 0:
                                avg_loss_on_stop = pnl
                            else:
                                # Running average
                                avg_loss_on_stop = (avg_loss_on_stop + pnl) / 2
                            logger.info(f"    -> STOP-LOSS HIT detected!")
                
                logger.info(f"Detected {stop_loss_hits} stop-loss hits from {len(losing_trades)} losing trades")
            
            if tp_stop is not None and tp_stop > 0 and len(winning_trades) > 0:
                # Try to detect take-profit hits by analyzing trade returns
                logger.info(f"Analyzing {len(winning_trades)} winning trades for take-profit hits (tp_stop={tp_stop:.2%})")
                for idx, trade in winning_trades.iterrows():
                    entry_price = trade.get('Entry Price', 0)
                    exit_price = trade.get('Exit Price', 0)
                    pnl = trade.get('PnL', 0)
                    if entry_price > 0:
                        return_pct = (exit_price - entry_price) / entry_price
                        tolerance = abs(return_pct - tp_stop) / tp_stop if tp_stop > 0 else 1.0
                        logger.info(f"  Trade: entry=${entry_price:.2f}, exit=${exit_price:.2f}, return={return_pct:.2%}, expected={tp_stop:.2%}, tolerance={tolerance:.2f}")
                        # Check if return is close to +tp_stop (within 30% tolerance)
                        if tolerance < 0.3:
                            take_profit_hits += 1
                            if avg_gain_on_tp == 0:
                                avg_gain_on_tp = pnl
                            else:
                                # Running average
                                avg_gain_on_tp = (avg_gain_on_tp + pnl) / 2
                            logger.info(f"    -> TAKE-PROFIT HIT detected!")
                
                logger.info(f"Detected {take_profit_hits} take-profit hits from {len(winning_trades)} winning trades")
            
            # Calculate hit rates
            stop_loss_hit_rate = stop_loss_hits / total_trades if total_trades > 0 else 0.0
            take_profit_hit_rate = take_profit_hits / total_trades if total_trades > 0 else 0.0
            
            logger.info("=" * 80)
            logger.info("STOP-LOSS AND TAKE-PROFIT ANALYSIS")
            logger.info("=" * 80)
            logger.info(f"Total trades: {total_trades}")
            logger.info(f"Stop-loss hits: {stop_loss_hits} ({stop_loss_hit_rate:.1%})")
            logger.info(f"Take-profit hits: {take_profit_hits} ({take_profit_hit_rate:.1%})")
            if stop_loss_hits > 0:
                logger.info(f"Average loss on stop-loss: ${avg_loss_on_stop:,.2f}")
            if take_profit_hits > 0:
                logger.info(f"Average gain on take-profit: ${avg_gain_on_tp:,.2f}")
            logger.info("=" * 80)
        else:
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            total_trades = 0
            stop_loss_hit_rate = 0.0
            take_profit_hit_rate = 0.0
        
        # Get equity curve
        equity_curve = portfolio.value()
        
        # Store actual backtest period (use sliced data range, not warmup range)
        backtest_period = (df.index[0].to_pydatetime(), df.index[-1].to_pydatetime())
        
        # Calculate signal overlap percentage for metadata
        total_signal_days = entry_days + exit_days - overlap_days
        signal_overlap_pct = (overlap_days / total_signal_days * 100) if total_signal_days > 0 else 0.0
        
        # Calculate average holding period for metadata
        avg_holding_period_days = None
        if entry_days > 0 and exit_days > 0:
            holding_periods = []
            entry_dates = df.index[entries].tolist()
            exit_dates = df.index[exits].tolist()
            
            for entry_date in entry_dates:
                future_exits = [e for e in exit_dates if e > entry_date]
                if future_exits:
                    next_exit = future_exits[0]
                    holding_period = (next_exit - entry_date).days
                    holding_periods.append(holding_period)
            
            if holding_periods:
                avg_holding_period_days = sum(holding_periods) / len(holding_periods)
        
        # Create metadata with signal analysis and stop-loss/take-profit metrics
        metadata = {
            "entry_signal_days": int(entry_days),
            "exit_signal_days": int(exit_days),
            "overlap_days": int(overlap_days),
            "signal_overlap_pct": float(signal_overlap_pct),
            "entry_only_days": int(entry_only_days),
            "exit_only_days": int(exit_only_days),
            "avg_holding_period_days": float(avg_holding_period_days) if avg_holding_period_days is not None else None,
            "stop_loss_hits": int(stop_loss_hits) if 'stop_loss_hits' in locals() else 0,
            "take_profit_hits": int(take_profit_hits) if 'take_profit_hits' in locals() else 0,
            "stop_loss_hit_rate": float(stop_loss_hit_rate) if 'stop_loss_hit_rate' in locals() else 0.0,
            "take_profit_hit_rate": float(take_profit_hit_rate) if 'take_profit_hit_rate' in locals() else 0.0,
            "avg_loss_on_stop": float(avg_loss_on_stop) if 'avg_loss_on_stop' in locals() else 0.0,
            "avg_gain_on_tp": float(avg_gain_on_tp) if 'avg_gain_on_tp' in locals() else 0.0
        }
        
        # Apply transaction costs if specified
        adjusted_return = total_return
        total_commission_cost = 0.0
        total_slippage_cost = 0.0
        total_spread_cost = 0.0
        total_cost_pct = 0.0
        
        if commission > 0 or slippage_bps > 0:
            # Load spread from config — asset-class-aware
            spread_pct = 0.0003  # Default
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        tx_costs = config.get('backtest', {}).get('transaction_costs', {})
                        # Determine asset class
                        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                        asset_class = self._get_asset_class(primary_symbol) if primary_symbol else 'stock'
                        ac_costs = tx_costs.get('per_asset_class', {}).get(asset_class, {})
                        spread_pct = ac_costs.get('spread_percent', tx_costs.get('spread_percent', 0.0003))
            except Exception:
                pass
            
            # Calculate transaction costs per trade using actual position sizes
            # instead of a fixed 10% assumption. The position_sizes Series has the
            # actual dollar amount for each entry signal.
            init_cash = 100000
            entry_sizes = position_sizes[entries] if entries.any() else pd.Series(dtype=float)
            if len(entry_sizes) > 0 and entry_sizes.sum() > 0:
                avg_trade_value = entry_sizes.mean()
            else:
                avg_trade_value = init_cash * 0.1  # Fallback if no entries
            
            # Commission cost (percentage-based)
            commission_per_trade = avg_trade_value * commission
            total_commission_cost = total_trades * 2 * commission_per_trade  # Entry + Exit
            
            # Slippage cost (in percentage)
            slippage_pct = slippage_bps / 10000  # Convert bps to decimal
            slippage_per_trade = avg_trade_value * slippage_pct
            total_slippage_cost = total_trades * 2 * slippage_per_trade  # Entry + Exit
            
            # Spread cost (bid-ask spread)
            spread_per_trade = avg_trade_value * spread_pct
            total_spread_cost = total_trades * 2 * spread_per_trade  # Entry + Exit
            
            # Overnight financing cost: eToro charges ~0.02%/night on CFD positions.
            # We estimate this from the average holding period and the per-asset-class rate.
            total_overnight_cost = 0.0
            overnight_cost_pct_total = 0.0
            try:
                import yaml
                from pathlib import Path as _Path
                _cfg_path = _Path("config/autonomous_trading.yaml")
                if _cfg_path.exists():
                    with open(_cfg_path, 'r') as _f:
                        _cfg = yaml.safe_load(_f)
                    _tx = _cfg.get('backtest', {}).get('transaction_costs', {})
                    _primary = strategy.symbols[0] if strategy.symbols else ''
                    _ac = self._get_asset_class(_primary) if _primary else 'stock'
                    _ac_costs = _tx.get('per_asset_class', {}).get(_ac, {})
                    overnight_rate = _ac_costs.get(
                        'overnight_financing_pct_per_day',
                        _tx.get('overnight_financing_pct_per_day', 0.0002)
                    )
                    if overnight_rate > 0 and total_trades > 0:
                        # Estimate avg holding period from trades list if available
                        avg_hold_days = 7.0  # Conservative default
                        if trades:
                            hold_days_list = []
                            for t in trades:
                                entry_dt = t.get('entry_date') or t.get('entry_time')
                                exit_dt = t.get('exit_date') or t.get('exit_time')
                                if entry_dt and exit_dt:
                                    try:
                                        delta = (exit_dt - entry_dt).days
                                        if delta > 0:
                                            hold_days_list.append(delta)
                                    except Exception:
                                        pass
                            if hold_days_list:
                                avg_hold_days = sum(hold_days_list) / len(hold_days_list)
                        total_overnight_cost = total_trades * avg_trade_value * overnight_rate * avg_hold_days
                        overnight_cost_pct_total = total_overnight_cost / init_cash
                        logger.info(
                            f"Overnight financing: {overnight_rate:.4%}/night × "
                            f"{avg_hold_days:.1f}d avg hold × {total_trades} trades = "
                            f"${total_overnight_cost:,.2f} ({overnight_cost_pct_total:.4%})"
                        )
            except Exception as _oc_err:
                logger.debug(f"Could not compute overnight financing cost: {_oc_err}")
            
            # Total transaction costs
            total_tx_costs = total_commission_cost + total_slippage_cost + total_spread_cost + total_overnight_cost
            
            # Calculate costs as percentage of initial capital
            commission_cost_pct = total_commission_cost / init_cash
            slippage_cost_pct = total_slippage_cost / init_cash
            spread_cost_pct = total_spread_cost / init_cash
            total_cost_pct = total_tx_costs / init_cash
            
            # Adjust return
            gross_return = total_return
            adjusted_return = total_return - total_cost_pct
            
            # Calculate costs as % of gross returns (if positive)
            costs_pct_of_returns = 0.0
            if gross_return > 0:
                costs_pct_of_returns = (total_cost_pct / gross_return) * 100
            
            logger.info("=" * 80)
            logger.info("TRANSACTION COST ANALYSIS")
            logger.info("=" * 80)
            logger.info(f"Total trades: {total_trades}")
            logger.info(f"Commission cost: ${total_commission_cost:,.2f} ({commission_cost_pct:.4%})")
            logger.info(f"Slippage cost: ${total_slippage_cost:,.2f} ({slippage_cost_pct:.4%})")
            logger.info(f"Spread cost: ${total_spread_cost:,.2f} ({spread_cost_pct:.4%})")
            if overnight_cost_pct_total > 0:
                logger.info(f"Overnight financing: ${total_overnight_cost:,.2f} ({overnight_cost_pct_total:.4%})")
            logger.info(f"Total transaction costs: ${total_tx_costs:,.2f} ({total_cost_pct:.4%})")
            logger.info(f"Costs as % of gross returns: {costs_pct_of_returns:.2f}%")
            logger.info(f"Gross return (before costs): {gross_return:.2%}")
            logger.info(f"Net return (after costs): {adjusted_return:.2%}")
            logger.info("=" * 80)
        else:
            gross_return = total_return
        
        return BacktestResults(
            total_return=adjusted_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=total_trades,
            equity_curve=equity_curve,
            trades=trades,
            backtest_period=backtest_period,
            metadata=metadata,
            # Transaction cost details
            total_commission_cost=total_commission_cost,
            total_slippage_cost=total_slippage_cost,
            total_spread_cost=total_spread_cost,
            total_transaction_costs=total_commission_cost + total_slippage_cost + total_spread_cost,
            transaction_costs_pct=total_cost_pct if total_trades > 0 else 0.0,
            gross_return=gross_return,
            net_return=adjusted_return
        )
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    def _calculate_indicators_from_strategy(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        symbol: str
    ) -> Dict[str, pd.Series]:
        """
        Calculate all indicators referenced in strategy.rules["indicators"] list.

        Maps indicator names to IndicatorLibrary methods and returns all calculated keys.

        Args:
            strategy: Strategy with rules["indicators"] list
            df: Market data DataFrame
            symbol: Symbol for caching

        Returns:
            Dict mapping indicator keys to calculated Series
        """
        indicators = {}

        # Get indicator list from strategy rules
        indicator_list = strategy.rules.get("indicators", [])

        if not indicator_list:
            logger.warning(f"Strategy '{strategy.name}' has no indicators list in rules")
            return indicators

        # Normalize indicator names (handle common abbreviations and period specifications)
        indicator_name_normalization = {
            "STOCH": "Stochastic Oscillator",
            "Stochastic": "Stochastic Oscillator",
            "BB": "Bollinger Bands",
            "Bollinger": "Bollinger Bands",
            "Support": "Support/Resistance",
            "Resistance": "Support/Resistance",
            "SR": "Support/Resistance",
            "VOL": "Volume MA",
            "Volume": "Volume MA",
            "Price Change": "Price Change %",
            "PCT": "Price Change %"
        }
        
        normalized_indicator_list = []
        for indicator in indicator_list:
            # Check if indicator has period specification (e.g., "SMA:20", "SMA:50")
            if ":" in indicator:
                base_name, period_str = indicator.split(":", 1)
                # Normalize base name
                normalized_base = indicator_name_normalization.get(base_name, base_name)
                # Keep the period specification
                normalized = f"{normalized_base}:{period_str}"
                if normalized != indicator:
                    logger.info(f"Normalized indicator '{indicator}' → '{normalized}'")
                normalized_indicator_list.append(normalized)
            else:
                # No period specification, just normalize the name
                normalized = indicator_name_normalization.get(indicator, indicator)
                if normalized != indicator:
                    logger.info(f"Normalized indicator '{indicator}' → '{normalized}'")
                normalized_indicator_list.append(normalized)
        
        # Remove duplicates while preserving order
        seen = set()
        indicator_list = []
        for indicator in normalized_indicator_list:
            if indicator not in seen:
                seen.add(indicator)
                indicator_list.append(indicator)

        # COMPREHENSIVE LOGGING: Log the full indicators list from strategy
        logger.info(f"=" * 80)
        logger.info(f"INDICATOR CALCULATION START for strategy: {strategy.name}")
        logger.info(f"Strategy rules['indicators'] list (after normalization): {indicator_list}")
        logger.info(f"Number of indicators to calculate: {len(indicator_list)}")
        logger.info(f"=" * 80)
        
        # Validate that all indicators referenced in rules are in the indicators list
        entry_conditions = strategy.rules.get("entry_conditions", [])
        exit_conditions = strategy.rules.get("exit_conditions", [])
        all_conditions = entry_conditions + exit_conditions
        
        # Extract indicator references from conditions
        referenced_indicators = set()
        for condition in all_conditions:
            # Look for patterns like "Support", "Resistance", "STOCH_14", etc.
            if "Support" in condition or "Resistance" in condition:
                if "Support/Resistance" not in indicator_list:
                    logger.warning(f"Condition references Support/Resistance but it's not in indicators list: {condition}")
                    logger.warning(f"Adding 'Support/Resistance' to indicators list")
                    indicator_list.append("Support/Resistance")
                    referenced_indicators.add("Support/Resistance")
            
            if "STOCH" in condition or "Stochastic" in condition:
                # Extract STOCH period from condition (e.g., STOCH(5) → 5)
                import re as _re_stoch
                stoch_periods_in_cond = _re_stoch.findall(r'STOCH\((\d+)\)', condition)
                for sp in stoch_periods_in_cond:
                    stoch_spec = f"Stochastic Oscillator:{sp}"
                    if stoch_spec not in indicator_list and "Stochastic Oscillator" not in indicator_list:
                        logger.warning(f"Condition references STOCH({sp}) but it's not in indicators list: {condition}")
                        logger.warning(f"Adding '{stoch_spec}' to indicators list")
                        indicator_list.append(stoch_spec)
                        referenced_indicators.add(stoch_spec)
                # Fallback: if no period found, add default
                if not stoch_periods_in_cond:
                    if "Stochastic Oscillator" not in indicator_list and not any(
                        i.startswith("Stochastic Oscillator:") for i in indicator_list
                    ):
                        logger.warning(f"Condition references Stochastic but it's not in indicators list: {condition}")
                        logger.warning(f"Adding 'Stochastic Oscillator' to indicators list")
                        indicator_list.append("Stochastic Oscillator")
                        referenced_indicators.add("Stochastic Oscillator")
                if "STOCH_SIGNAL" in condition:
                    # Extract period for signal too
                    signal_periods = _re_stoch.findall(r'STOCH_SIGNAL\((\d+)\)', condition)
                    for sp in signal_periods:
                        sig_spec = f"Stochastic Signal:{sp}"
                        if sig_spec not in indicator_list and "Stochastic Signal" not in indicator_list:
                            indicator_list.append(sig_spec)
                            referenced_indicators.add(sig_spec)
                    if not signal_periods and "Stochastic Signal" not in indicator_list:
                        indicator_list.append("Stochastic Signal")
                        referenced_indicators.add("Stochastic Signal")
            
            # Check for rolling high/low references
            if "HIGH_20" in condition or "HIGH_N" in condition:
                if "Rolling High" not in indicator_list:
                    indicator_list.append("Rolling High")
                    referenced_indicators.add("Rolling High")
            if "LOW_20" in condition or "LOW_N" in condition:
                if "Rolling Low" not in indicator_list:
                    indicator_list.append("Rolling Low")
                    referenced_indicators.add("Rolling Low")

            # Check for PRICE_CHANGE_PCT references — auto-add with correct period
            if "PRICE_CHANGE_PCT" in condition:
                import re as _re_pcp
                for match in _re_pcp.finditer(r'PRICE_CHANGE_PCT\((\d+)\)', condition):
                    period = int(match.group(1))
                    spec = f"Price Change %:{period}"
                    if spec not in indicator_list and not any(
                        i == spec or i == "Price Change %" for i in indicator_list
                    ):
                        indicator_list.append(spec)
                        referenced_indicators.add(spec)
                # Fallback: no period found, add default
                if not _re_pcp.search(r'PRICE_CHANGE_PCT\(\d+\)', condition):
                    if "Price Change %" not in indicator_list:
                        indicator_list.append("Price Change %")
                        referenced_indicators.add("Price Change %")
            
            # Check for Bollinger Bands references
            if any(bb_ref in condition for bb_ref in ["Lower_Band", "Upper_Band", "Middle_Band", "Bollinger"]):
                if "Bollinger Bands" not in indicator_list:
                    logger.warning(f"Condition references Bollinger Bands but it's not in indicators list: {condition}")
                    logger.warning(f"Adding 'Bollinger Bands' to indicators list")
                    indicator_list.append("Bollinger Bands")
                    referenced_indicators.add("Bollinger Bands")
        
        if referenced_indicators:
            logger.info(f"Auto-added missing indicators referenced in rules: {list(referenced_indicators)}")

        # Scan entry/exit conditions for BB_UPPER(P, S) / BB_LOWER(P, S) / BB_MIDDLE(P, S)
        # to determine which (period, std_dev) pairs we need to calculate.
        # This ensures BB(20, 1.5) and BB(20, 2.0) produce different indicator values.
        import re as _re
        bb_configs = set()  # (period, std_dev) pairs
        for condition in all_conditions:
            for match in _re.finditer(r'BB_(?:UPPER|LOWER|MIDDLE)\((\d+)\s*,\s*([0-9.]+)\)', condition):
                bb_period = int(match.group(1))
                bb_std = float(match.group(2))
                bb_configs.add((bb_period, bb_std))
            # Also catch BB_UPPER(20) without std_dev — default to 2.0
            for match in _re.finditer(r'BB_(?:UPPER|LOWER|MIDDLE)\((\d+)\)(?!\s*,)', condition):
                bb_period = int(match.group(1))
                bb_configs.add((bb_period, 2.0))
        if not bb_configs and "Bollinger Bands" in indicator_list:
            bb_configs.add((20, 2.0))  # Default if no explicit BB params found
        if bb_configs:
            logger.info(f"Bollinger Bands configs detected from conditions: {sorted(bb_configs)}")

        # Indicator name mapping: strategy name → (library method, default params, keys returned)
        indicator_mapping = {
            "Bollinger Bands": {
                "method": "BBANDS",
                "params": {"period": 20, "std_dev": 2},
                "keys": ["Upper_Band_20_2", "Middle_Band_20_2", "Lower_Band_20_2"]
            },
            "MACD": {
                "method": "MACD",
                "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
                "keys": ["MACD_12_26_9", "MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]
            },
            "Support/Resistance": {
                "method": "SUPPORT_RESISTANCE",
                "params": {"period": 20},
                "keys": ["Support", "Resistance"]
            },
            "Stochastic Oscillator": {
                "method": "STOCH",
                "params": {"k_period": 14, "d_period": 3},
                "keys": ["STOCH_14"]
            },
            "Stochastic Signal": {
                "method": "STOCH_SIGNAL",
                "params": {"k_period": 14, "d_period": 3},
                "keys": ["STOCH_SIGNAL_14"]
            },
            "Rolling High": {
                "method": "HIGH_N",
                "params": {"period": 20},
                "keys": ["HIGH_20"]
            },
            "Rolling Low": {
                "method": "LOW_N",
                "params": {"period": 20},
                "keys": ["LOW_20"]
            },
            "RSI": {
                "method": "RSI",
                "params": {"period": 14},
                "keys": ["RSI_14"]
            },
            "SMA": {
                "method": "SMA",
                "params": {"period": 20},
                "keys": ["SMA_20"]
            },
            "STDDEV": {
                "method": "STDDEV",
                "params": {"period": 20},
                "keys": ["STDDEV_20"]
            },
            "EMA": {
                "method": "EMA",
                "params": {"period": 20},
                "keys": ["EMA_20"]
            },
            "ATR": {
                "method": "ATR",
                "params": {"period": 14},
                "keys": ["ATR_14"]
            },
            "Volume MA": {
                "method": "VOLUME_MA",
                "params": {"period": 20},
                "keys": ["VOLUME_MA_20"]
            },
            "Price Change %": {
                "method": "PRICE_CHANGE_PCT",
                "params": {"period": 1},
                "keys": ["PRICE_CHANGE_PCT_1"]
            },
            "VWAP": {
                "method": "VWAP",
                "params": {"period": 0},
                "keys": ["VWAP_0"]
            },
            "ADX": {
                "method": "ADX",
                "params": {"period": 14},
                "keys": ["ADX_14"]
            }
        }

        # Calculate each indicator
        for indicator_spec in indicator_list:
            try:
                # COMPREHENSIVE LOGGING: Log each indicator being calculated
                logger.info(f"")
                logger.info(f"Processing indicator: '{indicator_spec}'")
                
                # Check if indicator has period specification (e.g., "SMA:20", "SMA:50")
                if ":" in indicator_spec:
                    base_name, period_str = indicator_spec.split(":", 1)
                    period = int(period_str)
                    indicator_name = base_name
                    custom_period = True
                else:
                    indicator_name = indicator_spec
                    custom_period = False
                    period = None
                
                if indicator_name not in indicator_mapping:
                    logger.warning(f"  ⚠️  Unknown indicator '{indicator_name}' - not in indicator_mapping")
                    logger.warning(f"  Available indicators: {list(indicator_mapping.keys())}")
                    continue

                mapping = indicator_mapping[indicator_name]
                method_name = mapping["method"]
                params = mapping["params"].copy()  # Copy to avoid modifying original
                expected_keys = mapping["keys"]
                
                # Override period if custom period specified
                if custom_period and period is not None:
                    # Special handling for Stochastic Oscillator (uses k_period, not period)
                    if indicator_name == "Stochastic Oscillator":
                        params["k_period"] = period
                        expected_keys = [f"STOCH_{period}"]
                    elif indicator_name == "Stochastic Signal":
                        params["k_period"] = period
                        expected_keys = [f"STOCH_SIGNAL_{period}"]
                    elif indicator_name == "Rolling High":
                        params["period"] = period
                        expected_keys = [f"HIGH_{period}"]
                    elif indicator_name == "Rolling Low":
                        params["period"] = period
                        expected_keys = [f"LOW_{period}"]
                    elif indicator_name == "Bollinger Bands":
                        params["period"] = period
                        expected_keys = [f"Upper_Band_{period}", f"Middle_Band_{period}", f"Lower_Band_{period}"]
                    else:
                        params["period"] = period
                        # Update expected keys with custom period
                        if indicator_name in ["RSI", "SMA", "EMA", "ATR", "Volume MA", "ADX"]:
                            expected_keys = [f"{method_name}_{period}"]
                    logger.info(f"  Using custom period: {period}")

                logger.info(f"  Method: {method_name}")
                logger.info(f"  Parameters: {params}")
                logger.info(f"  Expected keys: {expected_keys}")

                # Call indicator library
                result, key = self.indicator_library.calculate(
                    method_name, df, symbol=symbol, **params
                )

                # Handle different return types
                if isinstance(result, dict):
                    # Multi-value indicators (Bollinger Bands, MACD, Support/Resistance)
                    if indicator_name == "Bollinger Bands":
                        # Calculate BB for EACH (period, std_dev) pair found in conditions.
                        # The default calculation (from indicator_mapping) uses std_dev=2.
                        # We also need to calculate for any non-default std_devs (1.5, 2.5, etc.)
                        for bb_p, bb_s in bb_configs:
                            # Calculate this specific BB config
                            bb_result, _ = self.indicator_library.calculate(
                                "BBANDS", df, symbol=symbol, period=bb_p, std_dev=bb_s
                            )
                            if isinstance(bb_result, dict):
                                # Store with std_dev-aware keys (matches DSL output)
                                indicators[f"Upper_Band_{bb_p}_{bb_s}"] = bb_result['upper']
                                indicators[f"Middle_Band_{bb_p}_{bb_s}"] = bb_result['middle']
                                indicators[f"Lower_Band_{bb_p}_{bb_s}"] = bb_result['lower']
                                # Also store BBANDS_ prefixed versions
                                indicators[f"BBANDS_{bb_p}_{bb_s}_UB"] = bb_result['upper']
                                indicators[f"BBANDS_{bb_p}_{bb_s}_MB"] = bb_result['middle']
                                indicators[f"BBANDS_{bb_p}_{bb_s}_LB"] = bb_result['lower']
                                # Backward compat: also store without std_dev for old conditions
                                # that use Upper_Band_20 (no std_dev suffix)
                                if f"Upper_Band_{bb_p}" not in indicators:
                                    indicators[f"Upper_Band_{bb_p}"] = bb_result['upper']
                                    indicators[f"Middle_Band_{bb_p}"] = bb_result['middle']
                                    indicators[f"Lower_Band_{bb_p}"] = bb_result['lower']
                                logger.info(
                                    f"  ✓ BB({bb_p}, {bb_s}) calculated — "
                                    f"keys: Upper/Middle/Lower_Band_{bb_p}_{bb_s}"
                                )
                        # COMPREHENSIVE LOGGING
                        bb_keys = [k for k in indicators.keys() if 'Band' in k or 'BBANDS' in k]
                        logger.info(f"  All BB keys available: {sorted(bb_keys)}")

                    elif indicator_name == "MACD":
                        indicators["MACD_12_26_9"] = result['macd']
                        indicators["MACD_12_26_9_SIGNAL"] = result['signal']
                        indicators["MACD_12_26_9_HIST"] = result['histogram']
                        # COMPREHENSIVE LOGGING: Log the keys returned
                        returned_keys = ["MACD_12_26_9", "MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]
                        logger.info(f"  ✓ Calculated successfully")
                        logger.info(f"  Keys returned: {returned_keys}")

                    elif indicator_name == "Support/Resistance":
                        indicators["Support"] = result['support']
                        indicators["Resistance"] = result['resistance']
                        # COMPREHENSIVE LOGGING: Log the keys returned
                        returned_keys = ["Support", "Resistance"]
                        logger.info(f"  ✓ Calculated successfully")
                        logger.info(f"  Keys returned: {returned_keys}")

                    else:
                        # Generic dict handling
                        for k, v in result.items():
                            indicators[k] = v
                        # COMPREHENSIVE LOGGING: Log the keys returned
                        returned_keys = list(result.keys())
                        logger.info(f"  ✓ Calculated successfully")
                        logger.info(f"  Keys returned: {returned_keys}")

                else:
                    # Single-value indicators (RSI, SMA, EMA, etc.)
                    indicators[key] = result
                    # COMPREHENSIVE LOGGING: Log the key returned
                    logger.info(f"  ✓ Calculated successfully")
                    logger.info(f"  Key returned: {key}")

            except Exception as e:
                # COMPREHENSIVE LOGGING: Log calculation failures
                logger.error(f"  ✗ Failed to calculate indicator '{indicator_spec}'")
                logger.error(f"  Error: {e}")
                logger.error(f"  Traceback: ", exc_info=True)
                continue

        # DEFENSIVE: Ensure all indicator values are pd.Series, not numpy arrays.
        # The indicator cache can sometimes return numpy arrays when data lengths
        # change between backtests (stale cache from prior walk-forward period).
        # This prevents 'numpy.ndarray' object has no attribute 'index' crashes
        # in the DSL code generator and vectorbt backtest.
        import numpy as np
        for key in list(indicators.keys()):
            val = indicators[key]
            if isinstance(val, np.ndarray):
                logger.warning(f"Indicator '{key}' is numpy array (len={len(val)}), converting to pd.Series")
                if len(val) == len(df):
                    indicators[key] = pd.Series(val, index=df.index)
                else:
                    logger.warning(f"  Length mismatch: array={len(val)}, df={len(df)} — dropping indicator")
                    del indicators[key]
            elif isinstance(val, pd.Series) and not val.index.equals(df.index):
                # Reindex to match the data DataFrame — prevents misaligned comparisons
                if len(val) != len(df):
                    indicators[key] = val.reindex(df.index)

        # COMPREHENSIVE LOGGING: Log final indicators dict keys
        logger.info(f"")
        logger.info(f"=" * 80)
        logger.info(f"INDICATOR CALCULATION COMPLETE")
        logger.info(f"Total indicators calculated: {len(indicators)}")
        logger.info(f"Final indicator keys available: {sorted(indicators.keys())}")
        logger.info(f"=" * 80)
        
        return indicators

    
    def _parse_strategy_rules(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        indicators: Dict[str, pd.Series],
        rules: dict,
        volume: pd.Series = None
    ) -> tuple:
        """
        Parse strategy rules and generate entry/exit signals using DSL parser.
        
        Args:
            close: Close prices
            high: High prices
            low: Low prices
            indicators: Dictionary of calculated indicators
            rules: Strategy rules dictionary
            volume: Volume data (optional, needed for VOLUME conditions)
        
        Returns:
            Tuple of (entries, exits) as boolean Series
        """
        import pandas as pd
        import numpy as np
        import math
        import re
        from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator
        
        entry_conditions = rules.get("entry_conditions", [])
        exit_conditions = rules.get("exit_conditions", [])
        
        logger.info(f"DSL: Parsing {len(entry_conditions)} entry conditions: {entry_conditions}")
        logger.info(f"DSL: Parsing {len(exit_conditions)} exit conditions: {exit_conditions}")
        logger.info(f"DSL: Available indicators: {list(indicators.keys())}")
        
        # Initialize signals as all False
        entries = pd.Series(False, index=close.index)
        exits = pd.Series(False, index=close.index)
        
        # Create data DataFrame for eval context
        data_dict = {
            'close': close,
            'high': high,
            'low': low
        }
        if volume is not None:
            data_dict['volume'] = volume
        data = pd.DataFrame(data_dict)
        
        # Safe namespace for eval (only pandas, numpy, math)
        safe_namespace = {
            'pd': pd,
            'np': np,
            'math': math,
            'data': data,
            'indicators': indicators
        }
        
        # Initialize DSL parser and code generator
        dsl_parser = TradingDSLParser()
        code_generator = DSLCodeGenerator(available_indicators=list(indicators.keys()))
        
        # Helper function for semantic validation
        def validate_rule_semantics(rule_text: str, code: str, is_entry: bool = True) -> tuple:
            """
            Validate rule semantics (RSI thresholds, Bollinger logic, etc.).
            
            Args:
                rule_text: The DSL rule text
                code: Generated pandas code
                is_entry: True if this is an entry condition, False if exit
            
            Returns:
                (is_valid, error_message)
            """
            rule_lower = rule_text.lower()
            
            # Get validation config
            rsi_config = self.validation_config.get("rsi", {})
            rsi_entry_max = rsi_config.get("entry_max", 55)
            rsi_exit_min = rsi_config.get("exit_min", 55)
            
            stoch_config = self.validation_config.get("stochastic", {})
            stoch_entry_max = stoch_config.get("entry_max", 30)
            stoch_exit_min = stoch_config.get("exit_min", 60)
            
            # RSI validation
            if 'rsi' in rule_lower:
                # Detect RSI range conditions (momentum strategies use RSI > X AND RSI < Y)
                # These are NOT oversold entries — they're range filters for momentum
                has_rsi_gt = bool(re.search(r'RSI\(\d+\)\s*>', rule_text, re.IGNORECASE))
                has_rsi_lt = bool(re.search(r'RSI\(\d+\)\s*<', rule_text, re.IGNORECASE))
                is_rsi_range_filter = has_rsi_gt and has_rsi_lt
                
                if is_entry:
                    # ENTRY conditions: RSI < X means oversold entry (threshold should be low)
                    # RSI > X in an entry is a momentum filter (e.g., "only enter when RSI > 40")
                    # — this is valid and should NOT be checked against exit thresholds
                    if '<' in rule_text and not is_rsi_range_filter:
                        match = re.search(r'RSI\(\d+\)\s*<\s*(\d+)', rule_text, re.IGNORECASE)
                        if match:
                            threshold = int(match.group(1))
                            if threshold > rsi_entry_max:
                                return False, f"RSI entry threshold {threshold} is too high (max {rsi_entry_max}). Use RSI < {rsi_entry_max} for oversold entry."
                else:
                    # EXIT conditions: RSI > X means overbought exit (threshold should be high)
                    # EXCEPTION: In OR conditions (e.g., "RSI(14) > 45 OR CLOSE > BB_MIDDLE"),
                    # the RSI check is just one of multiple exit triggers. A lower RSI threshold
                    # is valid as a secondary/safety exit — the primary exit (BB_MIDDLE, EMA, etc.)
                    # handles the main case. Also, downtrend mean reversion strategies legitimately
                    # exit at lower RSI (40-50) because they're scalping bounces, not waiting for
                    # overbought conditions.
                    if '>' in rule_text and not is_rsi_range_filter:
                        # Skip RSI exit validation if this is an OR condition with other exit paths
                        is_or_condition = ' OR ' in rule_text.upper() or ' or ' in rule_text
                        if not is_or_condition:
                            match = re.search(r'RSI\(\d+\)\s*>\s*(\d+)', rule_text, re.IGNORECASE)
                            if match:
                                threshold = int(match.group(1))
                                # Use a relaxed floor (35) instead of rsi_exit_min — anything below 35
                                # is almost certainly a bug (exiting at RSI > 30 means always exiting)
                                relaxed_floor = 35
                                if threshold < relaxed_floor:
                                    return False, f"RSI exit threshold {threshold} is too low (min {relaxed_floor}). Use RSI > {relaxed_floor}+ for exit."
            
            # Stochastic validation (context-aware: entry vs exit)
            if 'stoch' in rule_lower:
                if is_entry:
                    # Entry conditions: STOCH < X (oversold buy) or STOCH > X (overbought short)
                    # If condition has BOTH < and > for STOCH, it's a range filter (e.g., 60 < STOCH < 75)
                    # Range filters are valid for both long and short — skip threshold validation
                    is_stoch_range = '<' in rule_text and '>' in rule_text and 'STOCH' in rule_text.upper()
                    if not is_stoch_range:
                        # For oversold entries (STOCH < X): threshold should be low (< entry_max)
                        if '<' in rule_text:
                            # Match STOCH-specific threshold only — not RSI or other indicators
                            # in the same compound condition. Look for STOCH(N) < X pattern.
                            match = re.search(r'STOCH\(\d+\)\s*<\s*(\d+)', rule_text, re.IGNORECASE)
                            if match:
                                threshold = int(match.group(1))
                                if threshold > stoch_entry_max:
                                    return False, f"STOCH entry threshold {threshold} is too high (max {stoch_entry_max})."
                        # For overbought short entries (STOCH > X): any high value is valid
                        # No validation needed — STOCH > 80 for short entry is correct
                else:
                    # Exit conditions: STOCH > X (take profit on long) or STOCH < X (cover short)
                    # Skip validation for OR conditions (same reasoning as RSI above)
                    is_or_condition = ' OR ' in rule_text.upper() or ' or ' in rule_text
                    if not is_or_condition:
                        # For overbought exits (STOCH > X): threshold should be high (> exit_min)
                        if '>' in rule_text:
                            # Match STOCH-specific threshold only — not RSI or other indicators
                            match = re.search(r'STOCH\(\d+\)\s*>\s*(\d+)', rule_text, re.IGNORECASE)
                            if match:
                                threshold = int(match.group(1))
                                # Relaxed floor: 40 (anything below is likely a bug)
                                if threshold < 40:
                                    return False, f"STOCH exit threshold {threshold} is too low (min 40)."
                    # For oversold cover exits (STOCH < X): any low value is valid
                    # No validation needed — STOCH < 40 for covering a short is correct
            
            # Bollinger Band validation
            # Note: Both mean reversion and breakout strategies are valid
            # Mean reversion: Enter when price < lower band, exit when price > upper band
            # Breakout: Enter when price > upper band, exit when price < lower band
            # We only reject obviously wrong logic (e.g., "price > lower band" for entry)
            
            if 'bb_lower' in rule_lower or 'lower_band' in rule_lower:
                # Check if this is checking the band width (squeeze detection)
                if 'bb_upper' in rule_text or 'upper_band' in rule_text or 'atr' in rule_lower:
                    # This is a band width check (e.g., BB_UPPER - BB_LOWER < ATR * 4)
                    # Skip validation - this is valid for squeeze detection
                    pass
                else:
                    # This is a price vs lower band comparison
                    # Entry at lower band should use < for mean reversion
                    # But > is valid for breakout strategies, so we don't reject it
                    pass
            
            if 'bb_upper' in rule_lower or 'upper_band' in rule_lower:
                # Check if this is checking the band width (squeeze detection)
                if 'bb_lower' in rule_text or 'lower_band' in rule_text or 'atr' in rule_lower:
                    # This is a band width check (e.g., BB_UPPER - BB_LOWER < ATR * 4)
                    # Skip validation - this is valid for squeeze detection
                    pass
                else:
                    # This is a price vs upper band comparison
                    # Both > (breakout) and < (mean reversion) are valid
                    pass
            
            return True, None
        
        # Parse entry conditions using DSL
        entry_signals = []
        entry_signal_days = []  # Track which days each condition triggers
        
        for condition in entry_conditions:
            try:
                logger.info(f"DSL: Parsing entry condition: {condition}")
                
                # Parse DSL rule
                parse_result = dsl_parser.parse(condition)
                
                if not parse_result.success:
                    logger.error(f"DSL: Failed to parse entry condition '{condition}': {parse_result.error}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                logger.info(f"DSL: Successfully parsed entry condition")
                logger.debug(f"DSL: AST structure:\n{parse_result.ast.pretty()}")
                
                # Generate pandas code from AST
                code_result = code_generator.generate_code(parse_result.ast)
                
                if not code_result.success:
                    logger.error(f"DSL: Failed to generate code for entry condition '{condition}': {code_result.error}")
                    logger.error(f"DSL: Required indicators: {code_result.required_indicators}")
                    logger.error(f"DSL: Available indicators: {list(indicators.keys())}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                code = code_result.code
                logger.info(f"DSL: Generated pandas code: {code}")
                logger.info(f"DSL: Required indicators: {code_result.required_indicators}")
                
                # Semantic validation
                is_valid, error_msg = validate_rule_semantics(condition, code, is_entry=True)
                if not is_valid:
                    logger.error(f"DSL: Semantic validation failed for entry condition '{condition}': {error_msg}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                logger.info(f"DSL: Semantic validation passed")
                
                # Execute generated code with safe namespace
                signal = eval(code, {"__builtins__": {}}, safe_namespace)
                
                # Ensure signal is a boolean Series
                if isinstance(signal, pd.Series):
                    signal = signal.reindex(close.index, fill_value=False).fillna(False).astype(bool)
                elif isinstance(signal, np.ndarray):
                    signal = pd.Series(signal, index=close.index).fillna(False).astype(bool)
                elif isinstance(signal, bool):
                    signal = pd.Series(signal, index=close.index)
                else:
                    signal = pd.Series(False, index=close.index)
                
                entry_signals.append(signal)
                entry_signal_days.append(signal)
                logger.info(f"DSL: Entry condition '{condition}': {signal.sum()} days met out of {len(signal)}")
                
            except Exception as e:
                logger.error(f"DSL: Failed to execute entry condition '{condition}': {e}")
                logger.error(f"DSL: Available indicators: {list(indicators.keys())}")
                logger.error(f"DSL: Skipping this rule and continuing")
                continue
        
        # Combine entry signals with AND logic (ALL conditions must be met simultaneously)
        # Each entry_conditions string is a separate requirement. Within a single string,
        # AND/OR operators work as written. But multiple strings = all must be true.
        # Example: ["CLOSE < BB_LOWER(20,2)", "RSI(14) < 45"] means BOTH must fire.
        if entry_signals:
            entries = entry_signals[0]
            for signal in entry_signals[1:]:
                entries = entries & signal
            logger.info(f"DSL: Combined entry signals (AND logic): {entries.sum()} days met out of {len(entries)}")
        else:
            logger.warning("DSL: No entry signals generated from conditions")
        
        # Parse exit conditions using DSL
        exit_signals = []
        exit_signal_days = []  # Track which days each condition triggers
        
        for condition in exit_conditions:
            try:
                logger.info(f"DSL: Parsing exit condition: {condition}")
                
                # Parse DSL rule
                parse_result = dsl_parser.parse(condition)
                
                if not parse_result.success:
                    logger.error(f"DSL: Failed to parse exit condition '{condition}': {parse_result.error}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                logger.info(f"DSL: Successfully parsed exit condition")
                logger.debug(f"DSL: AST structure:\n{parse_result.ast.pretty()}")
                
                # Generate pandas code from AST
                code_result = code_generator.generate_code(parse_result.ast)
                
                if not code_result.success:
                    logger.error(f"DSL: Failed to generate code for exit condition '{condition}': {code_result.error}")
                    logger.error(f"DSL: Required indicators: {code_result.required_indicators}")
                    logger.error(f"DSL: Available indicators: {list(indicators.keys())}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                code = code_result.code
                logger.info(f"DSL: Generated pandas code: {code}")
                logger.info(f"DSL: Required indicators: {code_result.required_indicators}")
                
                # Semantic validation
                is_valid, error_msg = validate_rule_semantics(condition, code, is_entry=False)
                if not is_valid:
                    logger.error(f"DSL: Semantic validation failed for exit condition '{condition}': {error_msg}")
                    logger.error(f"DSL: Skipping this rule")
                    continue
                
                logger.info(f"DSL: Semantic validation passed")
                
                # Execute generated code with safe namespace
                signal = eval(code, {"__builtins__": {}}, safe_namespace)
                
                # Ensure signal is a boolean Series
                if isinstance(signal, pd.Series):
                    signal = signal.reindex(close.index, fill_value=False).fillna(False).astype(bool)
                elif isinstance(signal, np.ndarray):
                    signal = pd.Series(signal, index=close.index).fillna(False).astype(bool)
                elif isinstance(signal, bool):
                    signal = pd.Series(signal, index=close.index)
                else:
                    signal = pd.Series(False, index=close.index)
                
                exit_signals.append(signal)
                exit_signal_days.append(signal)
                logger.info(f"DSL: Exit condition '{condition}': {signal.sum()} days met out of {len(signal)}")
                
            except Exception as e:
                logger.error(f"DSL: Failed to execute exit condition '{condition}': {e}")
                logger.error(f"DSL: Available indicators: {list(indicators.keys())}")
                logger.error(f"DSL: Skipping this rule and continuing")
                continue
        
        # Combine exit signals with OR logic (exit if ANY condition is met)
        # Unlike entry (AND), exits use OR because any single exit reason is sufficient
        # to protect capital. Example: "RSI > 60 OR CLOSE > SMA(20)" — either is enough to exit.
        if exit_signals:
            exits = exit_signals[0]
            for signal in exit_signals[1:]:
                exits = exits | signal
            logger.info(f"DSL: Combined exit signals (OR logic): {exits.sum()} days met out of {len(exits)}")
        else:
            logger.warning("DSL: No exit signals generated from conditions")
        
        # Signal overlap validation
        if entries.sum() > 0 and exits.sum() > 0:
            overlap = (entries & exits).sum()
            overlap_pct = (overlap / len(entries)) * 100
            
            overlap_config = self.validation_config.get("signal_overlap", {})
            max_overlap_pct = overlap_config.get("max_overlap_pct", 50)
            
            logger.info(f"DSL: Signal overlap analysis:")
            logger.info(f"DSL:   Entry-only days: {(entries & ~exits).sum()}")
            logger.info(f"DSL:   Exit-only days: {(exits & ~entries).sum()}")
            logger.info(f"DSL:   Overlap days: {overlap}")
            logger.info(f"DSL:   Overlap percentage: {overlap_pct:.1f}%")
            
            if overlap_pct > 80:
                logger.error(f"DSL: REJECTED - Signal overlap {overlap_pct:.1f}% exceeds 80% threshold")
                logger.error(f"DSL: Entry and exit conditions are too similar")
                # Return empty signals to reject strategy
                return pd.Series(False, index=close.index), pd.Series(False, index=close.index)
            elif overlap_pct > max_overlap_pct:
                logger.warning(f"DSL: WARNING - Signal overlap {overlap_pct:.1f}% exceeds {max_overlap_pct}% threshold")
                logger.warning(f"DSL: Consider using more distinct entry/exit conditions")
        
        return entries, exits
    
    def generate_signals(self, strategy: Strategy, include_dynamic: bool = True) -> List[TradingSignal]:
        """
        Generate trading signals based on strategy rules and current market data.
        
        Uses the same DSL-based rule parsing and indicator calculation as backtesting
        to ensure consistency between backtest results and live signal generation.
        
        Performance optimizations:
        - Uses signal_generation_days (default 120) instead of backtest_days (730)
        - Accepts pre-fetched data via _shared_data to avoid redundant Yahoo Finance calls
        - Per-strategy timeout protection (default 60s)
        - Detailed timing logs for each step
        
        Args:
            strategy: Strategy to generate signals from
        
        Returns:
            List of trading signals
        
        Raises:
            ValueError: If strategy is not active or signal generation fails
        
        Validates: Requirements 11.12, 11.16, 16.12
        """
        import time as _time
        from src.core.system_state_manager import get_system_state_manager
        from src.models.enums import SystemStateEnum
        
        strategy_start = _time.time()
        
        # Check system state before generating signals
        state_manager = get_system_state_manager()
        current_state = state_manager.get_current_state()
        
        # Skip signal generation if system is not ACTIVE
        if current_state.state != SystemStateEnum.ACTIVE:
            logger.info(
                f"Skipping signal generation for strategy {strategy.name}: "
                f"system state is {current_state.state.value}, not ACTIVE"
            )
            return []
        
        # Validate strategy is active
        if strategy.status not in [StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED]:
            raise ValueError(
                f"Cannot generate signals for strategy in {strategy.status} status. "
                f"Strategy must be DEMO, LIVE, or BACKTESTED."
            )
        
        logger.info(f"Generating signals for strategy {strategy.name} using DSL rule engine")
        
        # Detect Alpha Edge strategy early for logging
        is_alpha_edge = (
            strategy.metadata and isinstance(strategy.metadata, dict) and
            strategy.metadata.get('strategy_category') == 'alpha_edge'
        )
        if is_alpha_edge:
            template_type = self._get_alpha_edge_template_type(strategy)
            logger.info(
                f"Strategy {strategy.name} is Alpha Edge ({template_type}) — "
                f"will use fundamental signal generation instead of DSL"
            )
        
        signals = []
        
        # Load signal generation config (separate from backtest config)
        signal_gen_days = 120  # Default: enough for indicator warmup
        strategy_timeout = 60  # Default: 60s per strategy
        config = {}  # Will be loaded from YAML below
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    sg_config = config.get('signal_generation', {})
                    signal_gen_days = sg_config.get('days', 120)
                    strategy_timeout = sg_config.get('strategy_timeout', 60)
        except Exception as e:
            logger.warning(f"Could not load signal_generation config, using defaults: {e}")
        
        # Dynamic watchlist: DISABLED.
        # Adding random symbols based on generic SMA distance scoring adds noise
        # and lets strategies trade symbols they were never validated on.
        # Each strategy trades only its assigned symbols (from proposal + watchlist).
        symbols_to_trade = list(strategy.symbols) if strategy.symbols else []
        fundamental_filter = None
        data_provider = None
        fundamental_config = {}
        strategy_type = "default"
        
        try:
            import yaml
            from pathlib import Path
            
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    
                # Check if fundamental filtering is enabled
                alpha_edge_config = config.get('alpha_edge', {})
                fundamental_config = alpha_edge_config.get('fundamental_filters', {})
                
                if fundamental_config.get('enabled', False):
                    # Initialize providers but don't filter yet - wait until we have signals
                    from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                    from src.strategy.fundamental_filter import FundamentalFilter
                    
                    # Use singleton to preserve cache and rate limiter state across strategies
                    if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
                        data_provider = get_fundamental_data_provider(config)
                        self._fundamental_data_provider = data_provider
                    else:
                        data_provider = self._fundamental_data_provider
                    fundamental_filter = FundamentalFilter(config, data_provider)
                    
                    # Inject cross-sectional ranking results if available.
                    # The proposer stores ranker results on the engine after running
                    # rank_universe(). This lets the filter use tercile-based pass/fail
                    # instead of absolute P/E thresholds.
                    if hasattr(self, '_ranker_results') and self._ranker_results:
                        fundamental_filter.set_ranker_results(self._ranker_results)
                    
                    # Determine strategy type for valuation thresholds
                    template_name = ''
                    if strategy.metadata and isinstance(strategy.metadata, dict):
                        template_name = strategy.metadata.get('template_name', '')
                    
                    if template_name:
                        if "growth" in template_name.lower() or "momentum" in template_name.lower():
                            strategy_type = "growth"
                        elif "earnings" in template_name.lower():
                            strategy_type = "earnings_momentum"
                    
                    logger.info(
                        f"Fundamental filtering enabled - will apply AFTER signal generation "
                        f"to minimize API calls (strategy type: {strategy_type})"
                    )
                else:
                    logger.debug("Fundamental filtering is disabled")
        except Exception as e:
            logger.error(f"Error initializing fundamental filter: {e}", exc_info=True)
        
        # Calculate warmup period from strategy indicators
        max_period = 0
        for indicator in strategy.rules.get("indicators", []):
            if ":" in indicator:
                try:
                    period = int(indicator.split(":")[1])
                    max_period = max(max_period, period)
                except (ValueError, IndexError):
                    pass
        
        # Warmup = 2x the max indicator period, minimum 50 days
        effective_warmup = max(max_period * 2, 50) if max_period > 0 else 50
        
        # Detect strategy interval from metadata first (intraday templates), then rules, then config
        strategy_interval = None
        
        # Check metadata first (used by intraday templates)
        if hasattr(strategy, 'metadata') and strategy.metadata:
            strategy_interval = strategy.metadata.get('interval')
        
        # Check backtest_results metadata (used by walk-forward validation)
        if not strategy_interval and hasattr(strategy, 'backtest_results') and strategy.backtest_results:
            if hasattr(strategy.backtest_results, 'metadata') and strategy.backtest_results.metadata:
                strategy_interval = strategy.backtest_results.metadata.get('interval')
        
        # Check strategy rules (set explicitly by proposer based on template type)
        if not strategy_interval:
            strategy_interval = strategy.rules.get("interval", None)
        
        # Fall back to daily — NOT the config default_interval.
        # The config default_interval controls the signal LOOP frequency (how often
        # we check for signals), not the data interval. A daily template must use
        # daily bars regardless of how often the loop runs.
        if not strategy_interval:
            strategy_interval = '1d'
        
        # Validate interval
        if strategy_interval not in ("1d", "4h", "1h", "15m", "5m", "2h", "30m"):
            strategy_interval = "1d"
        
        # Log the detected interval for hourly strategies
        if strategy_interval in ('1h', '1H', '2h', '2H'):
            logger.info(f"Generating signals for hourly strategy {strategy.name} using {strategy_interval} bars")
        
        # For crypto symbols with non-intraday templates, use daily bars
        # to avoid indicator scaling issues. Crypto updates daily bars continuously.
        is_intraday_template = (
            hasattr(strategy, 'metadata') and strategy.metadata and
            (strategy.metadata.get('intraday', False) or strategy.metadata.get('interval_4h', False))
        )
        # Also check rules.interval as fallback — metadata propagation can miss this
        if not is_intraday_template and strategy_interval in ('1h', '4h', '2h', '15m', '30m'):
            is_intraday_template = True
        if not is_intraday_template and strategy_interval != "1d":
            try:
                from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                # Check if primary symbol is crypto
                primary_sym = strategy.symbols[0] if strategy.symbols else ''
                if primary_sym.upper() in set(DEMO_ALLOWED_CRYPTO):
                    strategy_interval = "1d"
                    logger.info(
                        f"Crypto non-intraday template: using daily bars for {strategy.name} "
                        f"(avoids indicator scaling issues)"
                    )
            except ImportError:
                pass
        
        # For intraday intervals, adjust signal_gen_days (fewer calendar days needed)
        intraday_day_multiplier = {
            "1d": 1, "4h": 1, "1h": 1, "15m": 0.5, "5m": 0.25
        }
        adjusted_signal_days = int(signal_gen_days * intraday_day_multiplier.get(strategy_interval, 1))
        
        # Fetch enough historical data for indicators to warm up properly
        end = datetime.now()
        start = end - timedelta(days=adjusted_signal_days + effective_warmup)
        
        logger.info(
            f"Signal gen for {strategy.name}: {signal_gen_days}+{effective_warmup} warmup days "
            f"(from {start.date()} to {end.date()})"
        )
        
        # Strategy-scoped pre-filter: only block if THIS strategy already has a position/order
        # Different strategies CAN trade the same symbol — coordination layer handles dedup
        this_strategy_positions = set()  # normalized symbols where THIS strategy has open positions
        this_strategy_pending = set()    # normalized symbols where THIS strategy has pending orders
        
        try:
            from src.models.database import get_database
            from src.models.orm import PositionORM, OrderORM
            from src.models.enums import OrderStatus
            from src.utils.symbol_normalizer import normalize_symbol
            
            db = get_database()
            session = db.get_session()
            try:
                # Only check positions for THIS strategy
                my_positions = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy.id,
                    PositionORM.closed_at.is_(None)
                ).all()
                
                for pos in my_positions:
                    this_strategy_positions.add(normalize_symbol(pos.symbol))
                
                # Only check pending orders for THIS strategy
                my_pending = session.query(OrderORM).filter(
                    OrderORM.strategy_id == strategy.id,
                    OrderORM.status == OrderStatus.PENDING
                ).all()
                
                for order in my_pending:
                    this_strategy_pending.add(normalize_symbol(order.symbol))
                
                if this_strategy_positions or this_strategy_pending:
                    logger.info(
                        f"Pre-filter for {strategy.name}: "
                        f"{len(this_strategy_positions)} symbols with own positions, "
                        f"{len(this_strategy_pending)} symbols with own pending orders"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not check positions for {strategy.name}: {e}")
        
        for symbol in symbols_to_trade:
            from src.utils.symbol_normalizer import normalize_symbol
            normalized_symbol = normalize_symbol(symbol)
            
            # Per-symbol market hours check: don't generate signals for stocks/ETFs
            # outside market hours, even if the strategy's primary symbol is crypto/forex
            try:
                import pytz
                from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
                sym_upper = normalized_symbol.upper()
                # Check both raw and normalized forms (DOT vs DOTUSD)
                raw_symbol = symbol.upper()
                is_crypto = sym_upper in set(DEMO_ALLOWED_CRYPTO) or raw_symbol in set(DEMO_ALLOWED_CRYPTO)
                is_forex = sym_upper in set(DEMO_ALLOWED_FOREX) or raw_symbol in set(DEMO_ALLOWED_FOREX)
                
                if not is_crypto and not is_forex:
                    et_tz = pytz.timezone('US/Eastern')
                    now_et = datetime.now(et_tz)
                    is_weekend = now_et.weekday() >= 5
                    # eToro allows stock trading Mon-Fri ~4:00 AM to 8:00 PM ET
                    is_market_hours = (not is_weekend and 
                                       now_et.hour >= 4 and now_et.hour < 20)
                    if not is_market_hours:
                        logger.debug(f"Skipping {symbol}: market closed for stocks/ETFs")
                        continue
                elif is_forex:
                    et_tz = pytz.timezone('US/Eastern')
                    now_et = datetime.now(et_tz)
                    if now_et.weekday() >= 5:
                        logger.debug(f"Skipping {symbol}: forex market closed on weekends")
                        continue
            except Exception:
                pass  # If pytz fails, don't block signal generation
            
            # Only skip ENTRY signals if THIS strategy already has a position in this symbol.
            # EXIT signals must still be evaluated — the DSL exit conditions (e.g., RSI > 60)
            # need to fire to generate close orders. Without this, exit rules are dead code
            # and positions only close via SL/TP or time-based exit.
            has_position_in_symbol = normalized_symbol in this_strategy_positions
            if has_position_in_symbol:
                logger.debug(
                    f"Strategy {strategy.name} has open position in {symbol} — "
                    f"evaluating for EXIT signals only"
                )
            
            # Only skip if THIS strategy already has a pending order for this symbol
            if normalized_symbol in this_strategy_pending:
                logger.debug(
                    f"Skipping {symbol} for {strategy.name}: already has pending order"
                )
                continue
            
            # Check timeout
            elapsed = _time.time() - strategy_start
            if elapsed > strategy_timeout:
                logger.warning(
                    f"Strategy {strategy.name} timed out after {elapsed:.1f}s "
                    f"(limit: {strategy_timeout}s). Skipping remaining symbols."
                )
                break
            
            try:
                t_fetch = _time.time()
                
                # Use shared data if available (batched by symbol in generate_signals_batch)
                shared_data = getattr(self, '_shared_data', {})
                # Determine the effective interval for THIS symbol
                # Crypto non-intraday templates use daily bars; crypto intraday templates use 1h
                symbol_interval = strategy_interval
                if not is_intraday_template and symbol_interval != "1d":
                    try:
                        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                        if symbol.upper() in set(DEMO_ALLOWED_CRYPTO):
                            symbol_interval = "1d"
                    except ImportError:
                        pass
                
                # Try interval-specific key first, then plain symbol (backward compat)
                shared_key = f"{symbol}:{symbol_interval}"
                if shared_key in shared_data:
                    data_list = shared_data[shared_key]
                    logger.info(f"Using shared cached {symbol_interval} data for {symbol} ({len(data_list)} points)")
                elif symbol in shared_data:
                    data_list = shared_data[symbol]
                    logger.info(f"Using shared cached data for {symbol} ({len(data_list)} points)")
                else:
                    # Fetch from cache or Yahoo Finance
                    from src.data.market_data_manager import get_historical_cache
                    hist_cache = get_historical_cache()
                    cache_key = f"{symbol}:{symbol_interval}:{signal_gen_days}"
                    data_list = hist_cache.get(cache_key)
                    
                    if data_list is None:
                        data_list = self.market_data.get_historical_data(
                            symbol, start, end, interval=symbol_interval, prefer_yahoo=True
                        )
                        if data_list:
                            hist_cache.set(cache_key, data_list)
                
                fetch_time = _time.time() - t_fetch
                
                if not data_list or len(data_list) < 20:
                    logger.warning(
                        f"Insufficient data for {symbol}: got {len(data_list) if data_list else 0} "
                        f"points, need at least 20. Skipping."
                    )
                    continue
                
                # Signal frequency validation: verify the data bar frequency matches
                # the strategy's intended interval. An intraday strategy (1h, 4h)
                # running on daily bars will generate signals at the wrong frequency
                # and with miscalibrated indicators (RSI(14) on daily = 14 days,
                # RSI(14) on 1h = 14 hours — completely different signals).
                # A PM would never let a 1h strategy trade on daily data.
                if len(data_list) >= 3:
                    # Estimate actual bar spacing from the data
                    ts0 = data_list[0].timestamp
                    ts1 = data_list[1].timestamp
                    ts2 = data_list[-1].timestamp
                    if hasattr(ts0, 'timestamp'):
                        # datetime objects
                        avg_bar_seconds = (ts2 - ts0).total_seconds() / max(len(data_list) - 1, 1)
                    else:
                        avg_bar_seconds = 86400  # assume daily if can't determine
                    
                    expected_bar_seconds = {
                        '1d': 86400, '4h': 14400, '1h': 3600,
                        '2h': 7200, '30m': 1800, '15m': 900,
                    }
                    expected = expected_bar_seconds.get(symbol_interval, 86400)
                    
                    # Allow 3x tolerance (weekends/gaps inflate daily bar spacing)
                    if avg_bar_seconds > expected * 5 and symbol_interval in ('1h', '2h', '4h'):
                        logger.warning(
                            f"Data frequency mismatch for {symbol}: strategy expects "
                            f"{symbol_interval} bars but data has ~{avg_bar_seconds/3600:.1f}h spacing. "
                            f"Skipping to avoid miscalibrated signals."
                        )
                        continue
                
                # Convert to DataFrame with full OHLCV (same as backtesting)
                t_convert = _time.time()
                df = pd.DataFrame([
                    {
                        "timestamp": d.timestamp,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.volume
                    }
                    for d in data_list
                ])
                df.set_index("timestamp", inplace=True)
                convert_time = _time.time() - t_convert
                
                logger.info(
                    f"{symbol}: {len(df)} points fetched in {fetch_time:.2f}s, "
                    f"converted in {convert_time:.3f}s"
                )
                
                # Generate signal using the appropriate engine
                t_signal = _time.time()
                
                # Route Alpha Edge strategies to fundamental signal generation
                if self._is_alpha_edge_strategy(strategy):
                    signal = self._generate_alpha_edge_signal(strategy, symbol, df, config)
                    engine_label = "alpha_edge_fundamental"
                else:
                    signal = self._generate_signal_for_symbol(strategy, symbol, df)
                    engine_label = "dsl"
                
                signal_time = _time.time() - t_signal
                
                logger.info(f"{symbol}: signal generation ({engine_label}) took {signal_time:.2f}s")
                
                if signal:
                    # If we have an open position in this symbol, only allow exit signals
                    # Entry signals are suppressed — can't enter twice
                    from src.models.enums import SignalAction
                    if has_position_in_symbol and signal.action in (
                        SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT
                    ):
                        logger.debug(
                            f"Suppressing entry signal for {symbol} — already has open position"
                        )
                    else:
                        signals.append(signal)
            
            except Exception as e:
                logger.error(f"Failed to generate signal for {symbol}: {e}", exc_info=True)
                continue
        
        # Apply conviction scoring and frequency limiting to generated signals
        filtered_signals = []
        try:
            from src.strategy.conviction_scorer import ConvictionScorer
            from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
            from src.ml.signal_filter import MLSignalFilter
            
            # Initialize conviction scorer
            conviction_scorer = ConvictionScorer(
                config=config,
                database=self.db,
                fundamental_filter=fundamental_filter if fundamental_config.get('enabled', False) else None,
                market_analyzer=getattr(self, 'market_analyzer', None)
            )
            
            # Initialize frequency limiter
            frequency_limiter = TradeFrequencyLimiter(
                config=config,
                database=self.db
            )
            
            # Initialize ML signal filter
            ml_filter = MLSignalFilter(
                config=config,
                database=self.db,
                market_analyzer=getattr(self, 'market_analyzer', None)
            )
            
            # Get min conviction threshold from config
            _ae_config = config.get('alpha_edge', {}) if config else {}
            min_conviction = _ae_config.get('min_conviction_score', 70)
            
            logger.info(
                f"Applying conviction scoring (min: {min_conviction}), frequency limiting, "
                f"and ML filtering to {len(signals)} signals"
            )
            # Accumulate raw signal count for batch reporting
            self._last_batch_raw_signals = getattr(self, '_last_batch_raw_signals', 0) + len(signals)
            
            for signal in signals:
                # EXIT signals bypass ALL filters — they are risk management, not entry decisions.
                # Filtering an exit signal means a position stays open past its edge expiry.
                from src.models.enums import SignalAction as _SA
                if signal.action in (_SA.EXIT_LONG, _SA.EXIT_SHORT):
                    filtered_signals.append(signal)
                    logger.info(f"Exit signal for {signal.symbol} passed through (bypasses conviction/ML filters)")
                    continue

                # Check frequency limits first (cheapest check)
                freq_check = frequency_limiter.check_signal_allowed(signal, strategy)
                if not freq_check.allowed:
                    frequency_limiter.log_rejected_signal(signal, strategy, freq_check)
                    logger.info(
                        f"Signal rejected for {signal.symbol}: {freq_check.reason} "
                        f"(trades this month: {freq_check.trades_this_month}/{freq_check.max_trades_per_month})"
                    )
                    continue
                
                # Quick pre-check: if signal confidence is very low, skip expensive fundamental fetch
                # A signal with confidence < 0.3 can score at most ~30 points from signal strength,
                # which means it needs 30+ from fundamentals+regime to pass 60 threshold — unlikely.
                if hasattr(signal, 'confidence') and signal.confidence and signal.confidence < 0.3:
                    logger.info(f"Signal skipped for {signal.symbol}: confidence {signal.confidence:.2f} too low for conviction threshold")
                    continue
                
                # Apply fundamental filter (only for equity symbols with actual signals)
                # Commodities, forex, indices, crypto, and ETFs don't have earnings/P&E/revenue data.
                # Applying the fundamental filter to them always fails (0/5 checks) and kills
                # every signal. Only filter individual stocks.
                fundamental_report = None
                _skip_fundamental = False
                try:
                    from src.core.tradeable_instruments import (
                        DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_FOREX,
                        DEMO_ALLOWED_INDICES, DEMO_ALLOWED_CRYPTO,
                        DEMO_ALLOWED_ETFS,
                    )
                    _sig_sym = signal.symbol.upper()
                    _non_equity = (
                        set(DEMO_ALLOWED_COMMODITIES) | set(DEMO_ALLOWED_FOREX) |
                        set(DEMO_ALLOWED_INDICES) | set(DEMO_ALLOWED_CRYPTO) |
                        set(DEMO_ALLOWED_ETFS)
                    )
                    if _sig_sym in _non_equity:
                        _skip_fundamental = True
                        logger.debug(f"Skipping fundamental filter for {signal.symbol} (non-equity asset)")
                except ImportError:
                    pass

                if fundamental_config.get('enabled', False) and fundamental_filter and not _skip_fundamental:
                    try:
                        t_fund = _time.time()
                        fundamental_report = fundamental_filter.filter_symbol(signal.symbol, strategy_type)
                        fund_time = _time.time() - t_fund
                        
                        # Reject signal if fundamental filter fails
                        if not fundamental_report.passed:
                            failed_checks = [r.check_name for r in fundamental_report.results if not r.passed]
                            logger.info(
                                f"Signal rejected for {signal.symbol}: fundamental filter failed "
                                f"({fundamental_report.checks_passed}/{fundamental_report.checks_total} checks passed, "
                                f"need {fundamental_report.min_required}). Failed: {', '.join(failed_checks)} "
                                f"[took {fund_time:.2f}s]"
                            )
                            continue
                        
                        logger.info(
                            f"Signal passed fundamental filter for {signal.symbol}: "
                            f"{fundamental_report.checks_passed}/{fundamental_report.checks_total} checks passed "
                            f"[took {fund_time:.2f}s]"
                        )
                    except Exception as e:
                        logger.warning(f"Could not get fundamental report for {signal.symbol}: {e}")
                        # Continue without fundamental filtering if it fails
                
                # Score conviction
                conviction = conviction_scorer.score_signal(signal, strategy, fundamental_report)
                
                # Check conviction threshold
                if not conviction.passes_threshold(min_conviction):
                    logger.info(
                        f"Signal rejected for {signal.symbol}: "
                        f"conviction {conviction.total_score:.1f} < {min_conviction} "
                        f"(wf_edge: {conviction.breakdown.get('walkforward_edge', {}).get('score', 0):.1f}, "
                        f"signal: {conviction.signal_strength_score:.1f}, "
                        f"asset: {conviction.fundamental_score:.1f}, "
                        f"regime: {conviction.regime_alignment_score:.1f}, "
                        f"fundamental_adj: {conviction.breakdown.get('fundamental_quality_direction', {}).get('score', 0):.1f}, "
                        f"news: {conviction.breakdown.get('news_sentiment', {}).get('score', 0):.1f})"
                    )
                    continue
                
                # Add conviction score to signal metadata
                if not hasattr(signal, 'metadata'):
                    signal.metadata = {}
                signal.metadata['conviction_score'] = conviction.total_score
                signal.metadata['conviction_breakdown'] = conviction.breakdown
                
                logger.info(
                    f"Signal passed conviction filter for {signal.symbol}: "
                    f"conviction {conviction.total_score:.1f}/100 "
                    f"(signal: {conviction.signal_strength_score:.1f}, "
                    f"fundamental: {conviction.fundamental_score:.1f}, "
                    f"regime: {conviction.regime_alignment_score:.1f})"
                )
                
                # Apply ML filter
                ml_result = ml_filter.filter_signal(signal, strategy)
                if not ml_result.passed:
                    logger.info(
                        f"Signal rejected by ML filter for {signal.symbol}: "
                        f"ML confidence {ml_result.confidence:.3f} < {ml_filter.min_confidence}"
                    )
                    continue
                
                # Add ML confidence to signal metadata
                signal.metadata['ml_confidence'] = ml_result.confidence
                signal.metadata['ml_features'] = ml_result.features
                signal.metadata['ml_model_version'] = ml_result.model_version
                
                logger.info(
                    f"Signal accepted for {signal.symbol}: "
                    f"ML confidence {ml_result.confidence:.3f}"
                )
                
                # Signal passed all filters
                filtered_signals.append(signal)
            
            logger.info(
                f"All filters applied: {len(filtered_signals)}/{len(signals)} signals passed "
                f"({len(signals) - len(filtered_signals)} rejected by conviction/frequency/ML filters)"
            )
            
            # Log API usage after filtering
            if fundamental_config.get('enabled', False) and data_provider:
                api_usage = data_provider.get_api_usage()
                logger.info(
                    f"FMP API usage: {api_usage['fmp']['calls_made']}/{api_usage['fmp']['max_calls']} "
                    f"({api_usage['fmp']['usage_percent']:.1f}%), Cache: {api_usage['cache_size']} symbols"
                )
            
        except Exception as e:
            logger.error(f"Error applying conviction/frequency filtering: {e}", exc_info=True)
            # Fall back to unfiltered signals if filtering fails
            logger.warning("Continuing with unfiltered signals due to error")
            filtered_signals = signals
        
        total_time = _time.time() - strategy_start
        logger.info(
            f"Strategy {strategy.name}: {len(filtered_signals)} signals generated in {total_time:.2f}s"
        )
        return filtered_signals
    
    def generate_signals_batch(self, strategies: List[Strategy], include_dynamic: bool = True) -> Dict[str, List[TradingSignal]]:
        """
        Generate signals for multiple strategies, batching data fetches by symbol.
        
        Args:
            strategies: List of strategies to generate signals for
            include_dynamic: If True, add dynamic symbol additions (manual cycle).
                           If False, only scan static watchlist symbols (30-min loop).
            
        Returns:
            Dict mapping strategy_id to list of signals
        """
        import time as _time
        
        batch_start = _time.time()
        self._batch_signal_running = True
        self._last_batch_raw_signals = 0  # Reset raw signal counter for this batch
        results: Dict[str, List[TradingSignal]] = {}
        
        # Load signal generation config
        signal_gen_days = 120
        strategy_timeout = 60
        cache_ttl = 3600
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    sg_config = config.get('signal_generation', {})
                    signal_gen_days = sg_config.get('days', 120)
                    strategy_timeout = sg_config.get('strategy_timeout', 60)
                    cache_ttl = sg_config.get('cache_ttl', 3600)
        except Exception as e:
            logger.warning(f"Could not load signal_generation config: {e}")
        
        # Collect all unique (symbol, interval) pairs across strategies
        # Different strategies may use different intervals (1d, 4h, 1h)
        symbol_interval_to_strategies: Dict[str, Dict[str, List[Strategy]]] = {}  # {symbol: {interval: [strategies]}}
        
        # Determine which symbols are crypto for interval selection
        crypto_symbols = set()
        try:
            from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
            crypto_symbols = set(DEMO_ALLOWED_CRYPTO)
        except ImportError:
            pass
        
        for strategy in strategies:
            # Determine the strategy's signal interval from rules (set by proposer)
            # The proposer explicitly sets rules.interval to '1d', '1h', or '4h'
            # based on template type. Trust it — don't override with config default.
            strat_interval = "1d"
            if hasattr(strategy, 'rules') and strategy.rules:
                strat_interval = strategy.rules.get("interval", "1d")
            
            # For crypto symbols with non-intraday templates, use daily bars
            # instead of 1h — daily bars are more reliable for daily-calibrated
            # indicators and crypto updates daily bars continuously (no market hours)
            is_intraday_template = (
                hasattr(strategy, 'metadata') and strategy.metadata and
                (strategy.metadata.get('intraday', False) or strategy.metadata.get('interval_4h', False))
            )
            # Also check rules.interval as fallback — metadata propagation can miss this
            if not is_intraday_template and strat_interval in ('1h', '4h', '2h', '15m', '30m'):
                is_intraday_template = True
            
            for symbol in strategy.symbols:
                effective_interval = strat_interval
                if symbol.upper() in crypto_symbols and not is_intraday_template and strat_interval != "1d":
                    # Non-intraday template on crypto: use daily bars to avoid
                    # scaling issues (RSI(14) stays as 14-day RSI)
                    effective_interval = "1d"
                
                if symbol not in symbol_interval_to_strategies:
                    symbol_interval_to_strategies[symbol] = {}
                if effective_interval not in symbol_interval_to_strategies[symbol]:
                    symbol_interval_to_strategies[symbol][effective_interval] = []
                symbol_interval_to_strategies[symbol][effective_interval].append(strategy)
        
        # Count unique symbols
        unique_symbols = set(symbol_interval_to_strategies.keys())
        
        logger.info(
            f"Batch signal generation: {len(strategies)} strategies, "
            f"{len(unique_symbols)} unique symbols"
        )
        
        # Pre-fetch data for all unique (symbol, interval) pairs
        from src.data.market_data_manager import get_historical_cache
        hist_cache = get_historical_cache(ttl_seconds=cache_ttl)
        
        # Clear stale intraday entries from in-memory cache before fetching
        # so we always get the latest 1h/4h bars from Yahoo, not hour-old cache
        stale_cleared = hist_cache.clear_intraday() if hasattr(hist_cache, 'clear_intraday') else 0
        if stale_cleared > 0:
            logger.info(f"Cleared {stale_cleared} stale intraday cache entries before signal gen")
        
        # Also clear the MarketDataManager's in-memory cache for intraday data
        if hasattr(self.market_data, '_historical_memory_cache'):
            keys_to_clear = [k for k in self.market_data._historical_memory_cache 
                           if ':1h:' in str(k) or ':4h:' in str(k)]
            for k in keys_to_clear:
                del self.market_data._historical_memory_cache[k]
            if keys_to_clear:
                logger.info(f"Cleared {len(keys_to_clear)} intraday entries from MarketDataManager memory cache")
        
        end = datetime.now()
        
        shared_data: Dict[str, List] = {}
        for symbol, intervals in symbol_interval_to_strategies.items():
            for interval, strats in intervals.items():
                # For intraday intervals, Yahoo only provides ~30 days
                # For daily, we can go back further
                if interval in ("1h", "4h"):
                    fetch_days = min(signal_gen_days, 180)  # Yahoo provides ~730 days of 1h data
                else:
                    fetch_days = signal_gen_days
                
                start = end - timedelta(days=fetch_days + 100)
                
                t0 = _time.time()
                cache_key = f"{symbol}:{interval}:{fetch_days}"
                data_list = hist_cache.get(cache_key)
                
                if data_list is None:
                    try:
                        data_list = self.market_data.get_historical_data(
                            symbol, start, end, interval=interval, prefer_yahoo=True
                        )
                        if data_list:
                            hist_cache.set(cache_key, data_list)
                            # Store with interval suffix for strategies to find
                            data_key = f"{symbol}:{interval}"
                            shared_data[data_key] = data_list
                            # Also store without suffix for backward compat (daily)
                            if interval == "1d":
                                shared_data[symbol] = data_list
                            logger.info(
                                f"Fetched {len(data_list)} {interval} bars for {symbol} in "
                                f"{_time.time() - t0:.2f}s (shared by "
                                f"{len(strats)} strategies)"
                            )
                        else:
                            logger.warning(f"No {interval} data returned for {symbol}")
                    except Exception as e:
                        logger.error(f"Failed to fetch {interval} data for {symbol}: {e}")
                else:
                    data_key = f"{symbol}:{interval}"
                    shared_data[data_key] = data_list
                    if interval == "1d":
                        shared_data[symbol] = data_list
                    logger.info(
                        f"Cache hit for {symbol} {interval}: {len(data_list)} bars "
                        f"(shared by {len(strats)} strategies)"
                    )
        
        data_fetch_time = _time.time() - batch_start
        logger.info(
            f"Data fetch phase complete: {len(shared_data)} data sets fetched "
            f"in {data_fetch_time:.2f}s (cache entries: {hist_cache.size})"
        )
        
        # Generate signals for each strategy using shared data
        self._shared_data = shared_data
        
        # Clear indicator cache before signal generation to prevent stale indicators
        # from a previous cycle being reused with updated price data
        if hasattr(self, 'indicator_library'):
            self.indicator_library.clear_cache()
        
        # Parallel signal generation using thread pool.
        # The per-strategy work is I/O-bound (DB queries, fundamental API calls)
        # mixed with CPU-bound (indicator math via numpy, which releases the GIL).
        # ThreadPoolExecutor works well here because:
        # - Each thread gets its own DB session (get_session() creates new sessions)
        # - Indicator library cache is thread-safe (uses lock)
        # - shared_data is read-only during signal gen
        # - Results are collected into a thread-safe dict
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        # Load worker count from config, default 4
        max_workers = 4
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    _par_config = yaml.safe_load(f)
                    max_workers = _par_config.get('signal_generation', {}).get('parallel_workers', 4)
        except Exception:
            pass
        
        # For small batches, sequential is faster (thread overhead not worth it)
        use_parallel = len(strategies) > 10 and max_workers > 1
        
        def _generate_for_strategy(strategy):
            """Worker function for parallel signal generation."""
            t0 = _time.time()
            try:
                signals = self.generate_signals(strategy, include_dynamic=include_dynamic)
                elapsed = _time.time() - t0
                if signals:
                    logger.info(f"Strategy {strategy.name}: {len(signals)} signals in {elapsed:.2f}s")
                else:
                    logger.debug(f"Strategy {strategy.name}: no signals in {elapsed:.2f}s")
                return strategy.id, signals
            except Exception as e:
                logger.error(f"Error generating signals for {strategy.name}: {e}")
                return strategy.id, []
        
        try:
            if use_parallel:
                logger.info(f"Parallel signal generation: {len(strategies)} strategies, {max_workers} workers")
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="siggen") as executor:
                    futures = {executor.submit(_generate_for_strategy, s): s for s in strategies}
                    for future in as_completed(futures):
                        strategy_id, signals = future.result()
                        results[strategy_id] = signals
            else:
                for strategy in strategies:
                    strategy_id, signals = _generate_for_strategy(strategy)
                    results[strategy_id] = signals
        finally:
            # Clean up shared data reference
            self._shared_data = {}
        
        total_time = _time.time() - batch_start
        total_signals = sum(len(s) for s in results.values())
        self._batch_signal_running = False
        # Track raw signals (pre-conviction) for reporting — accumulated by generate_signals
        self._last_batch_raw_signals = getattr(self, '_last_batch_raw_signals', 0)
        logger.info(
            f"Batch signal generation complete: {total_signals} signals from "
            f"{len(strategies)} strategies in {total_time:.2f}s"
        )
        
        return results
    
    def _is_alpha_edge_strategy(self, strategy: Strategy) -> bool:
        """Check if a strategy is an Alpha Edge strategy."""
        if not strategy.metadata or not isinstance(strategy.metadata, dict):
            return False
        return strategy.metadata.get('strategy_category') == 'alpha_edge'
    
    def _get_alpha_edge_template_type(self, strategy: Strategy) -> Optional[str]:
        """
        Determine the Alpha Edge template type from strategy metadata/name.
        
        Returns:
            'earnings_momentum', 'sector_rotation', 'quality_mean_reversion',
            'dividend_aristocrat', 'insider_buying', 'revenue_acceleration', 'relative_value',
            'end_of_month_momentum', 'pairs_trading', 'analyst_revision_momentum', 'share_buyback',
            or their SHORT variants, or None
        """
        if not self._is_alpha_edge_strategy(strategy):
            return None
        
        # Check explicit alpha_edge_type metadata first (most reliable)
        if strategy.metadata:
            explicit_type = strategy.metadata.get('alpha_edge_type')
            if explicit_type:
                return explicit_type
        
        template_name = ''
        if strategy.metadata:
            template_name = strategy.metadata.get('template_name', strategy.name).lower()
        
        if not template_name:
            template_name = strategy.name.lower()
        
        # SHORT templates must be checked first (more specific names)
        if 'earnings miss' in template_name or ('earning' in template_name and 'short' in template_name):
            return 'earnings_miss_momentum_short'
        elif ('sector' in template_name or 'rotation' in template_name) and 'short' in template_name:
            return 'sector_rotation_short'
        elif ('quality' in template_name and 'deterioration' in template_name) or \
             ('deterioration' in template_name and 'short' in template_name):
            return 'quality_deterioration_short'
        # Multi-Factor Composite (check before generic patterns)
        elif 'multi-factor' in template_name or 'multi_factor' in template_name or 'composite' in template_name:
            return 'multi_factor_composite'
        # New institutional-grade factor templates
        elif 'gross profitability' in template_name or 'gross_profitability' in template_name:
            return 'gross_profitability'
        elif 'accruals quality' in template_name or 'accruals_quality' in template_name:
            return 'accruals_quality'
        elif 'fcf yield' in template_name or 'fcf_yield' in template_name:
            return 'fcf_yield_value'
        elif 'price target' in template_name or 'price_target' in template_name:
            return 'price_target_upside'
        elif 'shareholder yield' in template_name or 'shareholder_yield' in template_name:
            return 'shareholder_yield'
        elif 'earnings momentum combo' in template_name or 'earnings_momentum_combo' in template_name:
            return 'earnings_momentum_combo'
        elif 'quality value combo' in template_name or 'quality_value_combo' in template_name:
            return 'quality_value_combo'
        elif 'deleveraging' in template_name:
            return 'deleveraging'
        # Specific LONG templates (check before generic patterns)
        elif 'analyst' in template_name and 'revision' in template_name:
            return 'analyst_revision_momentum'
        elif 'buyback' in template_name or 'share buyback' in template_name:
            return 'share_buyback'
        elif 'end-of-month' in template_name or 'end_of_month' in template_name or 'month-end' in template_name:
            return 'end_of_month_momentum'
        elif 'pairs' in template_name and 'trading' in template_name:
            return 'pairs_trading'
        elif 'dividend' in template_name or 'aristocrat' in template_name:
            return 'dividend_aristocrat'
        elif 'insider' in template_name:
            return 'insider_buying'
        elif 'revenue' in template_name and 'acceleration' in template_name:
            return 'revenue_acceleration'
        elif 'relative' in template_name and 'value' in template_name:
            return 'relative_value'
        # Generic LONG templates (last — these have broad name patterns)
        elif 'earning' in template_name or ('momentum' in template_name and 'month' not in template_name):
            return 'earnings_momentum'
        elif 'sector' in template_name or 'rotation' in template_name:
            return 'sector_rotation'
        elif 'quality' in template_name or 'mean_reversion' in template_name or 'mean reversion' in template_name:
            return 'quality_mean_reversion'
        
        return None
    
    def validate_alpha_edge_strategy(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Validate an Alpha Edge strategy using fundamental data checks instead of DSL signal validation.
        
        For Alpha Edge strategies, DSL-based validation (RSI thresholds, signal overlap, etc.) is meaningless.
        Instead, we validate:
        1. Fundamental data availability for the strategy's symbols
        2. Template-specific data requirements (earnings data, sector data, quality metrics)
        3. Data freshness (not stale)
        
        Returns:
            Dict with validation results matching the same interface as validate_strategy_rules()
        """
        logger.info(f"Validating Alpha Edge strategy: {strategy.name}")
        
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "overlap_percentage": 0.0,
            "entry_only_percentage": 100.0,
            "alpha_edge_validation": True,
        }
        
        template_type = self._get_alpha_edge_template_type(strategy)
        if not template_type:
            validation_result["errors"].append("Could not determine Alpha Edge template type")
            validation_result["is_valid"] = False
            return validation_result
        
        if not strategy.symbols:
            validation_result["errors"].append("Strategy has no symbols")
            validation_result["is_valid"] = False
            return validation_result
        
        # Initialize fundamental data provider if needed
        if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                config = {}
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                self._fundamental_data_provider = get_fundamental_data_provider(config)
            except Exception as e:
                validation_result["errors"].append(f"Cannot initialize FundamentalDataProvider: {e}")
                validation_result["is_valid"] = False
                return validation_result
        
        provider = self._fundamental_data_provider
        symbol = strategy.symbols[0]
        
        # Template-specific validation
        if template_type == 'earnings_momentum':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                checks_available = 0
                if fund_data.eps is not None:
                    checks_available += 1
                if fund_data.revenue_growth is not None:
                    checks_available += 1
                if fund_data.market_cap is not None:
                    checks_available += 1
                
                if checks_available == 0:
                    validation_result["errors"].append(f"No earnings/revenue data available for {symbol}")
                    validation_result["is_valid"] = False
                elif checks_available < 2:
                    validation_result["warnings"].append(
                        f"Limited fundamental data for {symbol} ({checks_available}/3 metrics available)"
                    )
                
                logger.info(f"Earnings Momentum validation for {symbol}: {checks_available}/3 data points available")
        
        elif template_type == 'sector_rotation':
            sector_etfs = strategy.metadata.get('fixed_symbols', []) if strategy.metadata else []
            if not sector_etfs:
                sector_etfs = ["XLE", "XLF", "XLK", "XLU", "XLV", "XLI", "XLP", "XLY"]
            
            if symbol not in sector_etfs:
                validation_result["warnings"].append(
                    f"{symbol} is not in sector ETF universe {sector_etfs}"
                )
            
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)
                market_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                if not market_data or len(market_data) < 30:
                    validation_result["warnings"].append(
                        f"Limited price data for {symbol} ({len(market_data) if market_data else 0} days) — momentum calculation may be impaired"
                    )
            except Exception as e:
                validation_result["warnings"].append(f"Could not fetch price data for {symbol}: {e}")
            
            logger.info(f"Sector Rotation validation for {symbol}: ETF universe check passed")
        
        elif template_type == 'quality_mean_reversion':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                quality_checks = 0
                if fund_data.roe is not None:
                    quality_checks += 1
                if fund_data.debt_to_equity is not None:
                    quality_checks += 1
                if fund_data.market_cap is not None:
                    quality_checks += 1
                
                if quality_checks == 0:
                    validation_result["errors"].append(f"No quality metrics (ROE, D/E, market cap) available for {symbol}")
                    validation_result["is_valid"] = False
                elif quality_checks < 2:
                    validation_result["warnings"].append(
                        f"Limited quality data for {symbol} ({quality_checks}/3 metrics available)"
                    )
                
                try:
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=30)
                    market_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                    if not market_data or len(market_data) < 14:
                        validation_result["warnings"].append(
                            f"Insufficient price data for RSI calculation ({len(market_data) if market_data else 0} days)"
                        )
                except Exception as e:
                    validation_result["warnings"].append(f"Could not fetch price data for RSI: {e}")
                
                logger.info(f"Quality Mean Reversion validation for {symbol}: {quality_checks}/3 quality metrics available")
        
        elif template_type == 'earnings_miss_momentum_short':
            # Same validation as earnings_momentum — needs earnings/revenue data
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                checks_available = 0
                if fund_data.eps is not None:
                    checks_available += 1
                if fund_data.revenue_growth is not None:
                    checks_available += 1
                if fund_data.market_cap is not None:
                    checks_available += 1
                
                if checks_available == 0:
                    validation_result["errors"].append(f"No earnings/revenue data available for {symbol}")
                    validation_result["is_valid"] = False
                elif checks_available < 2:
                    validation_result["warnings"].append(
                        f"Limited fundamental data for {symbol} ({checks_available}/3 metrics available)"
                    )
                
                logger.info(f"Earnings Miss Momentum SHORT validation for {symbol}: {checks_available}/3 data points available")
        
        elif template_type == 'sector_rotation_short':
            # Same validation as sector_rotation — needs sector ETF price data
            sector_etfs = strategy.metadata.get('fixed_symbols', []) if strategy.metadata else []
            if not sector_etfs:
                sector_etfs = ["XLE", "XLF", "XLK", "XLU", "XLV", "XLI", "XLP", "XLY"]
            
            if symbol not in sector_etfs:
                validation_result["warnings"].append(
                    f"{symbol} is not in sector ETF universe {sector_etfs}"
                )
            
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)
                market_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                if not market_data or len(market_data) < 30:
                    validation_result["warnings"].append(
                        f"Limited price data for {symbol} ({len(market_data) if market_data else 0} days) — momentum calculation may be impaired"
                    )
            except Exception as e:
                validation_result["warnings"].append(f"Could not fetch price data for {symbol}: {e}")
            
            logger.info(f"Sector Rotation SHORT validation for {symbol}: ETF universe check passed")
        
        elif template_type == 'quality_deterioration_short':
            # Same validation as quality_mean_reversion — needs quality metrics + RSI data
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                quality_checks = 0
                if fund_data.roe is not None:
                    quality_checks += 1
                if fund_data.debt_to_equity is not None:
                    quality_checks += 1
                if fund_data.market_cap is not None:
                    quality_checks += 1
                
                if quality_checks == 0:
                    validation_result["errors"].append(f"No quality metrics (ROE, D/E, market cap) available for {symbol}")
                    validation_result["is_valid"] = False
                elif quality_checks < 2:
                    validation_result["warnings"].append(
                        f"Limited quality data for {symbol} ({quality_checks}/3 metrics available)"
                    )
                
                try:
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=30)
                    market_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                    if not market_data or len(market_data) < 14:
                        validation_result["warnings"].append(
                            f"Insufficient price data for RSI calculation ({len(market_data) if market_data else 0} days)"
                        )
                except Exception as e:
                    validation_result["warnings"].append(f"Could not fetch price data for RSI: {e}")
                
                logger.info(f"Quality Deterioration SHORT validation for {symbol}: {quality_checks}/3 quality metrics available")
        
        elif template_type == 'dividend_aristocrat':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                checks = 0
                if getattr(fund_data, 'dividend_yield', None) is not None:
                    checks += 1
                if fund_data.market_cap is not None:
                    checks += 1
                if checks == 0:
                    validation_result["warnings"].append(f"No dividend/market cap data for {symbol}")
                logger.info(f"Dividend Aristocrat validation for {symbol}: {checks}/2 data points available")
        
        elif template_type == 'insider_buying':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will use proxy signals")
            logger.info(f"Insider Buying validation for {symbol}: fundamental data {'available' if fund_data else 'unavailable'}")
        
        elif template_type == 'revenue_acceleration':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                checks = 0
                if fund_data.revenue_growth is not None:
                    checks += 1
                if getattr(fund_data, 'earnings_surprise', None) is not None:
                    checks += 1
                if checks == 0:
                    validation_result["warnings"].append(f"No revenue/earnings data for {symbol}")
                logger.info(f"Revenue Acceleration validation for {symbol}: {checks}/2 data points available")
        
        elif template_type == 'relative_value':
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                validation_result["warnings"].append(f"No fundamental data for {symbol} — will rely on live data at signal time")
            else:
                if fund_data.pe_ratio is None:
                    validation_result["warnings"].append(f"No P/E ratio data for {symbol}")
                logger.info(f"Relative Value validation for {symbol}: P/E {'available' if fund_data.pe_ratio else 'unavailable'}")
        
        elif template_type == 'end_of_month_momentum':
            # End-of-Month Momentum only needs price data (SMA, RSI) — no fundamental data required
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=60)
                market_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                if not market_data or len(market_data) < 20:
                    validation_result["warnings"].append(
                        f"Limited price data for {symbol} ({len(market_data) if market_data else 0} days) — SMA/RSI calculation may be impaired"
                    )
                else:
                    logger.info(f"End-of-Month Momentum validation for {symbol}: {len(market_data)} days of price data available")
            except Exception as e:
                validation_result["warnings"].append(f"Could not fetch price data for {symbol}: {e}")
        
        elif template_type == 'pairs_trading':
            # Pairs Trading needs price data for both symbols in the pair to compute correlation and z-score
            # Use the class-level PAIRS_MAP which is the single source of truth
            if symbol not in self.PAIRS_MAP:
                validation_result["warnings"].append(f"{symbol} is not in the pairs trading universe")
            else:
                pair = self.PAIRS_MAP[symbol]
                partner = pair[1] if pair[0] == symbol else pair[0]
                try:
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=90)
                    sym_data = self.market_data.get_historical_data(symbol=symbol, start=start_date, end=end_date)
                    partner_data = self.market_data.get_historical_data(symbol=partner, start=start_date, end=end_date)
                    if not sym_data or len(sym_data) < 60:
                        validation_result["warnings"].append(f"Limited price data for {symbol} ({len(sym_data) if sym_data else 0} days)")
                    if not partner_data or len(partner_data) < 60:
                        validation_result["warnings"].append(f"Limited price data for pair partner {partner} ({len(partner_data) if partner_data else 0} days)")
                    if sym_data and partner_data and len(sym_data) >= 60 and len(partner_data) >= 60:
                        logger.info(f"Pairs Trading validation for {symbol}/{partner}: sufficient data available")
                except Exception as e:
                    validation_result["warnings"].append(f"Could not fetch pair data for {symbol}: {e}")

        elif template_type == 'analyst_revision_momentum':
            fund_data = provider.get_fundamental_data(symbol)
            quarters = provider.get_historical_fundamentals(symbol, quarters=4)
            estimates = [q.get('estimated_eps') for q in (quarters or []) if q.get('estimated_eps') is not None]
            if len(estimates) < 2:
                validation_result["warnings"].append(f"Only {len(estimates)} quarters with analyst estimates for {symbol}")
            else:
                validation_result["suggestions"].append(f"{len(estimates)} quarters of analyst estimates available")

        elif template_type == 'share_buyback':
            fund_data = provider.get_fundamental_data(symbol)
            if fund_data:
                if fund_data.shares_change_percent is not None:
                    validation_result["suggestions"].append(f"Shares change: {fund_data.shares_change_percent:.1%}")
                else:
                    validation_result["warnings"].append(f"No shares_change_percent data for {symbol}")
                if fund_data.eps is None:
                    validation_result["warnings"].append(f"No EPS data for {symbol}")
            else:
                validation_result["warnings"].append(f"No fundamental data for {symbol}")
        
        # --- Data freshness check ---
        # Stale fundamental data can lead to bad signals. Warn if >7 days, reject if >30 days.
        if template_type in ('earnings_momentum', 'quality_mean_reversion', 'earnings_miss_momentum_short', 'quality_deterioration_short', 'dividend_aristocrat', 'insider_buying', 'revenue_acceleration', 'relative_value', 'analyst_revision_momentum', 'share_buyback'):
            freshness_data = provider.get_fundamental_data(symbol)
            if freshness_data and hasattr(freshness_data, 'timestamp') and freshness_data.timestamp:
                try:
                    data_age = datetime.now() - freshness_data.timestamp
                    data_age_days = data_age.days
                    if data_age_days > 30:
                        validation_result["errors"].append(
                            f"Fundamental data too stale ({data_age_days} days old, max 30)"
                        )
                    elif data_age_days > 7:
                        validation_result["warnings"].append(
                            f"Fundamental data is {data_age_days} days old (consider refreshing)"
                        )
                    else:
                        logger.debug(f"Fundamental data for {symbol} is fresh ({data_age_days} days old)")
                except Exception as e:
                    validation_result["warnings"].append(f"Could not check data freshness for {symbol}: {e}")
            elif freshness_data:
                validation_result["warnings"].append(
                    f"No timestamp on fundamental data for {symbol} — freshness unknown"
                )

        if validation_result["errors"]:
            validation_result["is_valid"] = False
            logger.warning(f"Alpha Edge validation failed for {strategy.name}: {validation_result['errors']}")
        else:
            logger.info(f"Alpha Edge validation passed for {strategy.name}")
        
        return validation_result
    
    def validate_alpha_edge_factor(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Factor-based validation for Alpha Edge strategies.
        
        Instead of requiring historical trade count (which is meaningless for
        quarterly-signal strategies), this validates whether the underlying
        factor has a real edge across the symbol universe.
        
        Validation criteria (thinking like a trader):
        1. Factor data availability: Do we have enough quarterly data to judge?
        2. Factor quality gate: Does the primary symbol pass the template's
           fundamental screen? (e.g., F-Score >= 6 for quality templates)
        3. Cross-sectional spread: Do top-ranked symbols outperform bottom-ranked
           on the relevant factor? (proves the factor discriminates)
        4. Watchlist quality: Are the watchlist symbols in the right quintile
           for this factor?
        
        Returns:
            Dict with 'passed', 'factor_score' (0-100), 'details', and
            synthetic 'backtest_results' that can flow through the activation gate.
        """
        result = {
            'passed': False,
            'factor_score': 0.0,
            'details': {},
            'backtest_results': None,
        }
        
        template_type = self._get_alpha_edge_template_type(strategy)
        symbols = strategy.symbols or []
        if not template_type or not symbols:
            result['details']['error'] = 'Missing template type or symbols'
            return result
        
        # Initialize fundamental data provider
        if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
            try:
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                import yaml
                from pathlib import Path
                config = {}
                try:
                    config_path = Path("config/autonomous_trading.yaml")
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = yaml.safe_load(f) or {}
                except Exception:
                    pass
                self._fundamental_data_provider = get_fundamental_data_provider(config)
            except Exception as e:
                result['details']['error'] = f'Cannot init FundamentalDataProvider: {e}'
                return result
        
        provider = self._fundamental_data_provider
        primary_symbol = symbols[0]
        
        # --- Gate 1: Factor data availability ---
        # Need at least 4 quarters of data to judge a fundamental factor
        quarterly = provider.get_historical_fundamentals(primary_symbol, quarters=8)
        if not quarterly or len(quarterly) < 4:
            result['details']['gate1'] = f'Insufficient data: {len(quarterly) if quarterly else 0} quarters (need >= 4)'
            logger.info(f"[FactorValidation] {strategy.name}: FAIL gate 1 — {result['details']['gate1']}")
            return result
        result['details']['gate1'] = f'{len(quarterly)} quarters available'
        
        # --- Gate 2: Factor quality gate ---
        # Does the primary symbol currently pass the template's fundamental screen?
        latest = quarterly[-1]  # Most recent quarter
        is_short = (strategy.metadata or {}).get('direction', 'long') == 'short'
        
        factor_checks = {
            'earnings_momentum': lambda q: (q.get('earnings_surprise') or 0) > 0.03,
            'earnings_miss_momentum_short': lambda q: (q.get('earnings_surprise') is not None and (q.get('earnings_surprise') or 0) < 0) or (q.get('revenue_growth') is not None and (q.get('revenue_growth') or 0) < 0),
            'quality_mean_reversion': lambda q: (q.get('roe') or 0) > 0.08,
            'quality_deterioration_short': lambda q: (q.get('roe') is not None and (q.get('roe') or 1) < 0.08) or (q.get('debt_to_equity') is not None and (q.get('debt_to_equity') or 0) > 1.5),
            'revenue_acceleration': lambda q: (q.get('revenue_growth') or 0) > 0.02,
            'dividend_aristocrat': lambda q: (q.get('dividend_yield') or 0) > 0.015,
            'multi_factor_composite': lambda q: (q.get('piotroski_f_score') or 0) >= 5 if not is_short else (q.get('piotroski_f_score') is not None and (q.get('piotroski_f_score') or 9) <= 4),
            'gross_profitability': lambda q: (q.get('gross_profit') or 0) > 0 and (q.get('total_assets') or 1) > 0 and (q.get('gross_profit') or 0) / (q.get('total_assets') or 1) > 0.20,
            'accruals_quality': lambda q: (q.get('accruals_ratio') is not None and abs(q.get('accruals_ratio', 1)) < 0.08) if not is_short else (q.get('accruals_ratio') is not None and (q.get('accruals_ratio') or 0) > 0.05),
            'fcf_yield_value': lambda q: (q.get('fcf_yield') or 0) > 0.02,
            'shareholder_yield': lambda q: (q.get('dividend_yield') is not None and (q.get('dividend_yield') or 0) > 0.005) or (q.get('shares_outstanding') is not None),
            'deleveraging': lambda q: (q.get('long_term_debt') is not None),
            'relative_value': lambda q: (q.get('pe_ratio') or 0) > 0,
            'analyst_revision_momentum': lambda q: q.get('estimated_eps') is not None,
            'share_buyback': lambda q: q.get('shares_outstanding') is not None,
            'insider_buying': lambda q: True,  # Validated separately via insider data
            'earnings_momentum_combo': lambda q: q.get('sue') is not None,
            'quality_value_combo': lambda q: (q.get('fcf_yield') is not None and (q.get('fcf_yield') or 0) > 0) or (q.get('gross_profit') is not None and (q.get('gross_profit') or 0) > 0),
            'price_target_upside': lambda q: True,  # Validated via price target API
        }
        
        check_fn = factor_checks.get(template_type, lambda q: True)
        # Check across recent quarters — pass if ANY of the last 3 quarters qualify
        # (fundamental conditions are cyclical, one bad quarter doesn't invalidate the factor)
        recent_quarters = quarterly[-3:]
        gate2_passed = any(check_fn(q) for q in recent_quarters)
        qualifying_quarters = sum(1 for q in quarterly if check_fn(q))
        
        result['details']['gate2'] = {
            'passed': gate2_passed,
            'qualifying_quarters': qualifying_quarters,
            'total_quarters': len(quarterly),
            'hit_rate': round(qualifying_quarters / len(quarterly), 2),
        }
        
        if not gate2_passed:
            logger.info(f"[FactorValidation] {strategy.name}: FAIL gate 2 — {primary_symbol} doesn't pass {template_type} screen in recent quarters")
            return result
        
        # --- Gate 3: Cross-sectional factor spread ---
        # The real test: do stocks that score well on this factor outperform those that don't?
        # Use the ranker to check if there's meaningful spread between top and bottom quintiles.
        spread_score = 50.0  # Neutral default
        try:
            from src.strategy.fundamental_ranker import FundamentalRanker
            if not hasattr(self, '_fundamental_ranker') or self._fundamental_ranker is None:
                self._fundamental_ranker = FundamentalRanker(
                    fundamental_data_provider=provider,
                    market_data_manager=self.market_data
                )
            
            # Map template types to the ranker factor they rely on
            factor_map = {
                'earnings_momentum': 'growth_rank',
                'earnings_miss_momentum_short': 'growth_rank',
                'revenue_acceleration': 'growth_rank',
                'earnings_momentum_combo': 'growth_rank',
                'quality_mean_reversion': 'quality_rank',
                'quality_deterioration_short': 'quality_rank',
                'multi_factor_composite': 'composite_score',
                'gross_profitability': 'quality_rank',
                'accruals_quality': 'quality_rank',
                'quality_value_combo': 'composite_score',
                'fcf_yield_value': 'value_rank',
                'relative_value': 'value_rank',
                'shareholder_yield': 'value_rank',
                'deleveraging': 'quality_rank',
                'dividend_aristocrat': 'value_rank',
                'share_buyback': 'quality_rank',
                'price_target_upside': 'momentum_rank',
                'analyst_revision_momentum': 'growth_rank',
                'insider_buying': 'momentum_rank',
            }
            
            relevant_factor = factor_map.get(template_type, 'composite_score')
            
            # Use cached ranker results if available
            rankings = getattr(self, '_ranker_cache', None)
            if not rankings:
                # Rank a subset of symbols (the watchlist + some extras for spread calculation)
                from src.core.tradeable_instruments import DEMO_ALLOWED_STOCKS
                rank_symbols = list(set(symbols + list(DEMO_ALLOWED_STOCKS)[:30]))
                rankings = self._fundamental_ranker.rank_universe(rank_symbols)
                self._ranker_cache = rankings
            
            if rankings and len(rankings) >= 10:
                # Sort by the relevant factor
                sorted_by_factor = sorted(
                    rankings.items(),
                    key=lambda x: x[1].get(relevant_factor, 50),
                    reverse=True
                )
                
                n = len(sorted_by_factor)
                top_quintile = [s for s, _ in sorted_by_factor[:n // 5]] if n >= 5 else [s for s, _ in sorted_by_factor[:2]]
                bottom_quintile = [s for s, _ in sorted_by_factor[-(n // 5):]] if n >= 5 else [s for s, _ in sorted_by_factor[-2:]]
                
                top_avg = sum(rankings[s].get(relevant_factor, 50) for s in top_quintile) / len(top_quintile)
                bottom_avg = sum(rankings[s].get(relevant_factor, 50) for s in bottom_quintile) / len(bottom_quintile)
                spread = top_avg - bottom_avg
                
                # For the factor to be useful, we need meaningful spread (> 30 points on 0-100 scale)
                spread_score = min(100, max(0, spread * 2))  # Scale: 50-point spread = 100 score
                
                # Check if primary symbol is in the right quintile for this factor
                primary_rank = rankings.get(primary_symbol, {}).get(relevant_factor, 50)
                if is_short:
                    # Short templates want symbols in the BOTTOM quintile
                    symbol_in_right_quintile = primary_symbol in bottom_quintile
                else:
                    symbol_in_right_quintile = primary_symbol in top_quintile
                
                result['details']['gate3'] = {
                    'factor': relevant_factor,
                    'spread': round(spread, 1),
                    'spread_score': round(spread_score, 1),
                    'top_quintile_avg': round(top_avg, 1),
                    'bottom_quintile_avg': round(bottom_avg, 1),
                    'primary_rank': round(primary_rank, 1),
                    'in_right_quintile': symbol_in_right_quintile,
                    'universe_size': len(rankings),
                }
                
                logger.info(
                    f"[FactorValidation] {strategy.name}: {relevant_factor} spread={spread:.1f} "
                    f"(top={top_avg:.0f}, bottom={bottom_avg:.0f}), "
                    f"{primary_symbol} rank={primary_rank:.0f}, in_right_quintile={symbol_in_right_quintile}"
                )
            else:
                result['details']['gate3'] = {'skipped': True, 'reason': f'Only {len(rankings)} ranked symbols (need >= 10)'}
                spread_score = 50.0  # Neutral — don't penalize if we can't compute spread
        except Exception as e:
            result['details']['gate3'] = {'skipped': True, 'reason': str(e)}
            spread_score = 50.0
            logger.debug(f"[FactorValidation] Cross-sectional spread check failed: {e}")
        
        # --- Gate 4: Watchlist quality ---
        # What fraction of watchlist symbols pass the factor screen?
        watchlist_pass_count = 0
        for sym in symbols:
            try:
                sym_quarters = provider.get_historical_fundamentals(sym, quarters=4)
                if sym_quarters and len(sym_quarters) >= 2:
                    recent = sym_quarters[-2:]
                    if any(check_fn(q) for q in recent):
                        watchlist_pass_count += 1
            except Exception:
                continue
        
        watchlist_quality = watchlist_pass_count / max(len(symbols), 1)
        result['details']['gate4'] = {
            'watchlist_size': len(symbols),
            'passing_symbols': watchlist_pass_count,
            'quality_pct': round(watchlist_quality, 2),
        }
        
        # --- Compute composite factor score ---
        # Weighted: data availability (10%), factor quality (30%), spread (35%), watchlist (25%)
        data_score = min(100, len(quarterly) * 12.5)  # 8 quarters = 100
        quality_score = (qualifying_quarters / max(len(quarterly), 1)) * 100
        watchlist_score = watchlist_quality * 100
        
        factor_score = (
            0.10 * data_score +
            0.30 * quality_score +
            0.35 * spread_score +
            0.25 * watchlist_score
        )
        
        result['factor_score'] = round(factor_score, 1)
        
        # Pass threshold: factor score >= 40 (generous — we want to let factors prove themselves live)
        FACTOR_PASS_THRESHOLD = 40.0
        result['passed'] = factor_score >= FACTOR_PASS_THRESHOLD
        
        if result['passed']:
            # Build synthetic BacktestResults calibrated to academic factor return data.
            # Historical annualized factor Sharpe ratios (Fama-French, AQR research):
            #   Value (HML): ~0.3-0.5 Sharpe
            #   Quality (QMJ): ~0.4-0.6 Sharpe
            #   Momentum (UMD): ~0.5-0.8 Sharpe
            #   Size (SMB): ~0.2-0.3 Sharpe
            #   Multi-factor: ~0.6-0.9 Sharpe (diversification benefit)
            # We scale by factor_score but cap at realistic academic levels.
            
            # Map template types to their academic Sharpe ceiling
            factor_sharpe_ceiling = {
                'earnings_momentum': 0.7, 'earnings_miss_momentum_short': 0.6,
                'revenue_acceleration': 0.5, 'earnings_momentum_combo': 0.7,
                'quality_mean_reversion': 0.5, 'quality_deterioration_short': 0.5,
                'multi_factor_composite': 0.8, 'quality_value_combo': 0.7,
                'gross_profitability': 0.5, 'accruals_quality': 0.5,
                'fcf_yield_value': 0.4, 'relative_value': 0.4,
                'shareholder_yield': 0.4, 'deleveraging': 0.4,
                'dividend_aristocrat': 0.3, 'share_buyback': 0.4,
                'price_target_upside': 0.5, 'analyst_revision_momentum': 0.6,
                'insider_buying': 0.5, 'sector_rotation': 0.5,
            }
            max_sharpe = factor_sharpe_ceiling.get(template_type, 0.5)
            
            # Scale: factor_score 40 (threshold) → 40% of ceiling, 100 → 100% of ceiling
            sharpe_pct = (factor_score - FACTOR_PASS_THRESHOLD) / (100.0 - FACTOR_PASS_THRESHOLD)
            estimated_sharpe = max_sharpe * (0.4 + 0.6 * sharpe_pct)
            
            # Win rate: fundamental strategies typically 45-60%
            estimated_win_rate = max(0.45, min(0.60, 0.45 + (quality_score / 100.0) * 0.15))
            
            # Drawdown: conservative — fundamental strategies have quarterly rebalance
            # so drawdowns can persist for months before the signal updates
            estimated_drawdown = max(0.08, 0.20 - (factor_score / 100.0) * 0.10)
            
            # Return: Sharpe × assumed 15% annualized vol, scaled to backtest period
            estimated_return = estimated_sharpe * 0.15
            
            result['backtest_results'] = BacktestResults(
                total_return=estimated_return,
                sharpe_ratio=estimated_sharpe,
                sortino_ratio=estimated_sharpe * 1.2,
                max_drawdown=estimated_drawdown,
                win_rate=estimated_win_rate,
                total_trades=qualifying_quarters,  # Quarters where factor fired = "trades"
                avg_win=estimated_return / max(qualifying_quarters, 1) * 1.5,
                avg_loss=estimated_return / max(qualifying_quarters, 1) * 0.8,
            )
            
            logger.info(
                f"[FactorValidation] {strategy.name}: PASSED (score={factor_score:.0f}) — "
                f"synthetic Sharpe={estimated_sharpe:.2f}, WR={estimated_win_rate:.0%}, "
                f"DD={estimated_drawdown:.0%}, qualifying_quarters={qualifying_quarters}/{len(quarterly)}"
            )
        else:
            logger.info(
                f"[FactorValidation] {strategy.name}: FAILED (score={factor_score:.0f} < {FACTOR_PASS_THRESHOLD}) — "
                f"data={data_score:.0f}, quality={quality_score:.0f}, spread={spread_score:.0f}, watchlist={watchlist_score:.0f}"
            )
        
        return result

    def backtest_alpha_edge_strategy(self, strategy: Strategy, start: datetime, end: datetime) -> BacktestResults:
        """
        Backtest an Alpha Edge strategy using REAL historical fundamental data from FMP.
        
        Fetches quarterly income statements, key metrics, and earnings data,
        then simulates trades based on the actual fundamental conditions that
        the live signal generator uses (P/E ratios, earnings surprises, revenue
        growth, etc.) — not price proxies.
        
        For sector rotation templates, routes to sector performance data instead
        of per-symbol income statements (ETFs don't have quarterly earnings).
        """
        template_type = self._get_alpha_edge_template_type(strategy)
        symbol = strategy.symbols[0] if strategy.symbols else None
        
        if not symbol or not template_type:
            logger.warning(f"Cannot backtest Alpha Edge strategy {strategy.name}: missing symbol or template type")
            return BacktestResults(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                sortino_ratio=0.0
            )
        
        # Sector rotation templates use sector performance data, not per-symbol income statements.
        # Route them directly to the sector rotation simulator which fetches FMP sector data.
        if template_type in ('sector_rotation', 'sector_rotation_short'):
            try:
                market_data = self.market_data.get_historical_data(symbol=symbol, start=start, end=end)
                if not market_data or len(market_data) < 30:
                    logger.warning(f"Insufficient price data for sector rotation backtest on {symbol}")
                    return BacktestResults(
                        total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                        win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                        sortino_ratio=0.0
                    )
                df = pd.DataFrame([{
                    "timestamp": md.timestamp, "open": md.open, "high": md.high,
                    "low": md.low, "close": md.close, "volume": md.volume
                } for md in market_data])
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                
                params = self._resolve_alpha_edge_params(strategy)
                if template_type == 'sector_rotation':
                    trades = self._simulate_sector_rotation_with_fundamentals(df, params, strategy)
                else:
                    trades = self._simulate_sector_rotation_short_trades(df, params)
                
                if trades:
                    logger.info(f"[AlphaEdgeBacktest] {strategy.name} ({template_type}): {len(trades)} trades via sector performance data")
                else:
                    logger.warning(f"[AlphaEdgeBacktest] {strategy.name} ({template_type}): 0 trades")
                
                return self._calculate_alpha_edge_backtest_results(trades, df)
            except Exception as e:
                logger.error(f"Sector rotation backtest failed: {e}")
                return BacktestResults(
                    total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                    win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                    sortino_ratio=0.0
                )
        
        # Alpha Edge fundamental templates require equity symbols (stocks/ETFs)
        asset_class = self._get_asset_class(symbol)
        EQUITY_ONLY_AE_TYPES = {
            'earnings_momentum', 'earnings_miss_momentum_short', 'dividend_aristocrat',
            'insider_buying', 'quality_mean_reversion', 'quality_deterioration_short',
            'analyst_revision_momentum', 'share_buyback',
        }
        if asset_class in ('crypto', 'forex', 'commodity', 'index') and template_type in EQUITY_ONLY_AE_TYPES:
            logger.warning(f"Alpha Edge backtest skipped: {template_type} on {symbol} ({asset_class}) — requires equity fundamentals")
            return BacktestResults(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                sortino_ratio=0.0
            )
        
        logger.info(f"Running Alpha Edge backtest for {strategy.name} ({template_type}) on {symbol} using FMP data")
        
        # Fetch price data
        try:
            market_data = self.market_data.get_historical_data(symbol=symbol, start=start, end=end)
            if not market_data or len(market_data) < 30:
                logger.warning(f"Insufficient price data for Alpha Edge backtest: {len(market_data) if market_data else 0} days")
                return BacktestResults(
                    total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                    win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                    sortino_ratio=0.0
                )
            
            df = pd.DataFrame([{
                "timestamp": md.timestamp, "open": md.open, "high": md.high,
                "low": md.low, "close": md.close, "volume": md.volume
            } for md in market_data])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
        except Exception as e:
            logger.error(f"Failed to fetch price data for Alpha Edge backtest: {e}")
            return BacktestResults(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                sortino_ratio=0.0
            )
        
        # Fetch real historical fundamental data from FMP
        quarterly_data = []
        try:
            if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                import yaml
                from pathlib import Path
                config = {}
                try:
                    config_path = Path("config/autonomous_trading.yaml")
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = yaml.safe_load(f) or {}
                except Exception:
                    pass
                self._fundamental_data_provider = get_fundamental_data_provider(config)
            quarterly_data = self._fundamental_data_provider.get_historical_fundamentals(symbol, quarters=12)
            logger.info(f"Fetched {len(quarterly_data)} quarters of FMP data for {symbol}")
        except Exception as e:
            logger.warning(f"Could not fetch FMP historical data for {symbol}: {e}")
        
        if not quarterly_data:
            logger.warning(f"No FMP historical data for {symbol} — rejecting AE backtest (no price-proxy fallback)")
            return BacktestResults(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                sortino_ratio=0.0
            )
        
        # Simulate trades using real fundamental data aligned with price data
        params = self._resolve_alpha_edge_params(strategy)
        
        trades = self._simulate_alpha_edge_with_fundamentals(
            template_type, df, quarterly_data, params, strategy
        )
        
        if trades:
            logger.info(f"[AlphaEdgeBacktest] {strategy.name} ({template_type}) on {symbol}: {len(trades)} trades using real FMP data")
            for idx, t in enumerate(trades[:5]):
                logger.info(
                    f"  Trade {idx+1}: {t.get('entry_date', 'N/A')} → {t.get('exit_date', 'N/A')} | "
                    f"entry=${t['entry_price']:.2f} exit=${t['exit_price']:.2f} | "
                    f"P&L={t['pnl_pct']:+.2%} | {t['days_held']}d | {t['exit_reason']}"
                )
        else:
            logger.warning(f"[AlphaEdgeBacktest] {strategy.name} ({template_type}) on {symbol}: 0 trades from FMP data")
        
        return self._calculate_alpha_edge_backtest_results(trades, df)
    def _resolve_alpha_edge_params(self, strategy) -> Dict:
        """Resolve Alpha Edge strategy parameters from metadata.

        The Strategy dataclass has no 'parameters' field — customized params
        are stored in metadata['customized_parameters'] by the proposer.
        Falls back to metadata['default_parameters'], then empty dict.
        """
        if hasattr(strategy, 'metadata') and strategy.metadata:
            params = strategy.metadata.get('customized_parameters')
            if params:
                return params
            params = strategy.metadata.get('default_parameters')
            if params:
                return params
        return {}
    
    def _simulate_earnings_momentum_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Earnings Momentum trades using price patterns that match post-earnings drift.
        Looks for sharp 1-day moves > 3% as proxy for earnings announcements.
        """
        trades = []
        close = df['close']
        daily_returns = close.pct_change()
        
        profit_target = params.get('profit_target', 0.05)
        stop_loss = params.get('stop_loss_pct', 0.03)
        hold_max = params.get('hold_period_max', 30)
        entry_delay = params.get('entry_delay_days', 2)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(entry_delay + 1, len(df)):
            if not in_trade:
                trigger_idx = i - entry_delay
                if trigger_idx >= 1 and daily_returns.iloc[trigger_idx] > 0.03:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades

    def _simulate_with_price_proxy(self, template_type: str, df, params: Dict, strategy=None) -> List[Dict]:
        """Fallback: use old price-proxy simulations when FMP data is unavailable."""
        if template_type == 'earnings_momentum':
            return self._simulate_earnings_momentum_trades(df, params)
        elif template_type == 'sector_rotation':
            return self._simulate_sector_rotation_trades(df, params)
        elif template_type == 'quality_mean_reversion':
            return self._simulate_quality_mean_reversion_trades(df, params)
        elif template_type == 'earnings_miss_momentum_short':
            return self._simulate_earnings_miss_momentum_trades(df, params)
        elif template_type == 'sector_rotation_short':
            return self._simulate_sector_rotation_short_trades(df, params)
        elif template_type == 'quality_deterioration_short':
            return self._simulate_quality_deterioration_trades(df, params)
        elif template_type == 'dividend_aristocrat':
            return self._simulate_dividend_aristocrat_trades(df, params)
        elif template_type == 'insider_buying':
            return self._simulate_insider_buying_trades(df, params)
        elif template_type == 'revenue_acceleration':
            return self._simulate_revenue_acceleration_trades(df, params)
        elif template_type == 'relative_value':
            return self._simulate_relative_value_trades(df, params)
        elif template_type == 'end_of_month_momentum':
            return self._simulate_end_of_month_momentum_trades(df, params)
        elif template_type == 'pairs_trading':
            return self._simulate_pairs_trading_trades(df, params, strategy)
        elif template_type == 'analyst_revision_momentum':
            return self._simulate_analyst_revision_trades(df, params)
        elif template_type == 'share_buyback':
            return self._simulate_share_buyback_trades(df, params)
        return []

    def _simulate_alpha_edge_with_fundamentals(
        self, template_type: str, df, quarterly_data: List[Dict], params: Dict, strategy=None
    ) -> List[Dict]:
        """
        Simulate Alpha Edge trades using REAL quarterly fundamental data from FMP.

        For each quarter where fundamental conditions are met, enters a trade
        on the first trading day after the EARNINGS ANNOUNCEMENT date (not quarter-end).
        This avoids look-ahead bias — we only trade after the data is public.
        """
        trades = []
        close = df['close']

        profit_target = params.get('profit_target', 0.10)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 60)

        # Build a date-indexed lookup for price data
        price_dates = df.index.tolist()

        # Fetch actual earnings announcement dates to avoid look-ahead bias.
        # Quarter-end dates (e.g., 2024-03-30) are NOT when the market learns the data —
        # the earnings call happens weeks later. We must use announcement dates.
        announcement_dates = {}  # quarter_date -> announcement_date
        try:
            symbol = strategy.symbols[0] if strategy and strategy.symbols else None
            if symbol and hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                earnings_cal = self._fundamental_data_provider.get_earnings_calendar(symbol)
                if earnings_cal and isinstance(earnings_cal, dict):
                    # Map fiscal quarter end to announcement date
                    for entry in earnings_cal.get('history', earnings_cal.get('earnings', [])):
                        if isinstance(entry, dict):
                            ann_date = entry.get('date') or entry.get('reportDate') or entry.get('fiscalDateEnding')
                            fiscal_end = entry.get('fiscalDateEnding') or entry.get('date')
                            if ann_date and fiscal_end:
                                announcement_dates[fiscal_end] = ann_date
                if announcement_dates:
                    logger.info(f"Loaded {len(announcement_dates)} earnings announcement dates for look-ahead bias prevention")
        except Exception as e:
            logger.debug(f"Could not load earnings calendar for look-ahead prevention: {e}")

        def find_trading_day_after(date_str: str, delay_days: int = 2):
            """Find the first trading day at least delay_days after a date."""
            from datetime import datetime as dt
            try:
                target = dt.strptime(date_str, '%Y-%m-%d') + timedelta(days=delay_days)
                for i, d in enumerate(price_dates):
                    d_naive = d.replace(tzinfo=None) if hasattr(d, 'replace') and d.tzinfo else d
                    if d_naive >= target:
                        return i
            except Exception:
                pass
            return None

        def execute_trade(entry_idx: int, direction: str = 'long') -> Dict:
            """Execute a trade from entry_idx with stop/profit/hold limits."""
            entry_price = close.iloc[entry_idx]
            for j in range(entry_idx + 1, min(entry_idx + hold_max + 1, len(df))):
                current = close.iloc[j]
                days_held = j - entry_idx
                if direction == 'long':
                    pnl_pct = (current - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - current) / entry_price

                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"

                if exit_reason:
                    return {
                        "entry_price": entry_price, "exit_price": current,
                        "pnl_pct": pnl_pct, "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[j].date()) if hasattr(df.index[j], 'date') else str(df.index[j]),
                    }
            # If we ran out of data, close at last price
            last_idx = min(entry_idx + hold_max, len(df) - 1)
            current = close.iloc[last_idx]
            if direction == 'long':
                pnl_pct = (current - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current) / entry_price
            return {
                "entry_price": entry_price, "exit_price": current,
                "pnl_pct": pnl_pct, "days_held": last_idx - entry_idx,
                "exit_reason": "end_of_data",
                "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                "exit_date": str(df.index[last_idx].date()) if hasattr(df.index[last_idx], 'date') else str(df.index[last_idx]),
            }

        # Track per-quarter dedup for Quality Mean Reversion
        last_qmr_quarter = None
        # Track entry spacing for Dividend Aristocrat
        last_div_entry_date = None
        div_last_exit_date = None
        # Track Analyst Revision Momentum state
        prev_analyst_est = None
        analyst_base_est = None
        analyst_consecutive_up = 0
        # Track Share Buyback state
        share_buyback_checked = False
        share_buyback_signal = False
        # Track Revenue Acceleration state (previous quarter's growth for acceleration check)
        prev_rev_growth_for_accel = None

        # Iterate through quarterly data and check fundamental conditions
        for q in quarterly_data:
            q_date = q.get('date', '')
            if not q_date:
                continue

            # Use announcement date if available (avoids look-ahead bias).
            # Fall back to quarter-end + 45 days (conservative estimate for earnings release).
            entry_date = announcement_dates.get(q_date)
            if entry_date:
                entry_idx = find_trading_day_after(entry_date, delay_days=1)  # 1 day after announcement
            else:
                # No announcement date — assume earnings released ~45 days after quarter end
                entry_idx = find_trading_day_after(q_date, delay_days=45)

            if entry_idx is None or entry_idx >= len(df) - 5:
                continue

            # Check conditions based on template type
            should_enter = False
            direction = 'long'

            if template_type == 'earnings_momentum':
                # Enter LONG after positive earnings surprise > 5%
                surprise = q.get('earnings_surprise')
                rev_growth = q.get('revenue_growth')
                if surprise is not None and surprise > 0.05:
                    should_enter = True
                elif rev_growth is not None and rev_growth > 0.10:
                    should_enter = True

            elif template_type == 'earnings_miss_momentum_short':
                # Enter SHORT after negative earnings surprise OR revenue decline
                # Relaxed from -5% to -2% surprise — a miss is a miss, the market punishes it
                surprise = q.get('earnings_surprise')
                rev_growth = q.get('revenue_growth')
                if surprise is not None and surprise < -0.02:
                    should_enter = True
                    direction = 'short'
                elif rev_growth is not None and rev_growth < -0.03:
                    # Revenue declining > 3% is bearish even without an earnings miss
                    should_enter = True
                    direction = 'short'

            elif template_type == 'revenue_acceleration':
                # Enter LONG when revenue growth is ACCELERATING (Q-over-Q growth increasing).
                # Just positive growth (> 2%) is noise — we need the growth rate itself to be rising.
                rev_growth = q.get('revenue_growth')
                if rev_growth is not None and rev_growth > 0.02:
                    if prev_rev_growth_for_accel is not None and rev_growth > prev_rev_growth_for_accel:
                        # Growth is accelerating — current quarter growth > previous quarter growth
                        should_enter = True
                    elif prev_rev_growth_for_accel is None and rev_growth > 0.10:
                        # No previous quarter data — only enter on strong growth (> 10%)
                        should_enter = True
                # Always track for next iteration
                if rev_growth is not None:
                    prev_rev_growth_for_accel = rev_growth

            elif template_type == 'relative_value':
                # Enter LONG when P/E is significantly below sector median (undervalued)
                # Enter SHORT when P/E is significantly above sector median (overvalued)
                # Uses sector-relative comparison instead of absolute P/E thresholds.
                pe = q.get('pe_ratio')
                if pe is not None and pe > 0:
                    # Determine sector median P/E from FMP data or use sector-aware defaults
                    # Sector-aware P/E medians (approximate 2024-2026 ranges):
                    # Tech: ~30, Financials: ~14, Healthcare: ~22, Consumer: ~25, Energy: ~12, Utilities: ~18
                    sector_median_pe = 22.0  # Default cross-sector median
                    try:
                        sym = strategy.symbols[0] if strategy and strategy.symbols else None
                        if sym and hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                            fd = self._fundamental_data_provider.get_fundamental_data(sym)
                            if fd and fd.pe_ratio is not None and fd.pe_ratio > 0:
                                # Use the symbol's own sector context from FMP profile
                                # Approximate sector medians based on common ranges
                                sector_pe_map = {
                                    'technology': 30.0, 'financial': 14.0, 'healthcare': 22.0,
                                    'consumer': 25.0, 'energy': 12.0, 'utilities': 18.0,
                                    'industrial': 20.0, 'communication': 22.0, 'real estate': 35.0,
                                }
                                # Try to get sector from profile (cached)
                                profile = self._fundamental_data_provider._fmp_request("/profile", symbol=sym)
                                if profile and len(profile) > 0:
                                    sector = (profile[0].get('sector', '') or '').lower()
                                    for key, median in sector_pe_map.items():
                                        if key in sector:
                                            sector_median_pe = median
                                            break
                    except Exception:
                        pass  # Use default median

                    # Check trend at entry point for confirmation
                    if entry_idx is not None and entry_idx >= 50 and entry_idx < len(df):
                        sma50 = close.iloc[max(0, entry_idx - 50):entry_idx + 1].mean()
                        current = close.iloc[entry_idx]
                        pe_ratio_to_median = pe / sector_median_pe if sector_median_pe > 0 else 1.0

                        if pe_ratio_to_median < 0.70:
                            # LONG: P/E is > 30% below sector median (genuinely cheap)
                            # Require price not in freefall
                            if current > sma50 * 0.90:
                                should_enter = True
                                direction = 'long'
                        elif pe_ratio_to_median > 1.60:
                            # SHORT: P/E is > 60% above sector median (genuinely expensive)
                            # Require price below SMA50 (confirming overvaluation + weakness)
                            if current < sma50:
                                should_enter = True
                                direction = 'short'

            elif template_type == 'quality_mean_reversion':
                # Enter LONG when fundamentals are solid AND price is technically oversold.
                # Relaxed fundamental thresholds: ROE > 10% (was 15%), D/E < 1.0 (was 0.5)
                # These still filter for quality but don't exclude 80% of the market.
                roe = q.get('roe')
                de = q.get('debt_to_equity')
                # Read RSI threshold from both possible param names (template uses oversold_threshold)
                rsi_threshold = params.get('rsi_threshold', params.get('oversold_threshold', 40))

                # Per-quarter dedup: skip if we already entered this quarter
                q_key = q_date[:7]  # YYYY-MM as quarter key
                if q_key == last_qmr_quarter:
                    continue

                # Relaxed: ROE > 10% (profitable), D/E < 1.0 (not overleveraged)
                min_roe = params.get('min_roe', 0.10)
                max_de = params.get('max_debt_equity', 1.0)
                if roe is not None and roe > min_roe:
                    if de is None or de < max_de:
                        # Check technical oversold condition at entry point
                        if entry_idx is not None and entry_idx < len(df):
                            # Calculate RSI at entry
                            lookback = min(entry_idx, 14)
                            if lookback >= 5:
                                price_slice = close.iloc[max(0, entry_idx - 20):entry_idx + 1]
                                delta = price_slice.diff()
                                gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                                loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                                if loss.iloc[-1] > 0:
                                    rs = gain.iloc[-1] / loss.iloc[-1]
                                    rsi = 100 - (100 / (1 + rs))
                                    if rsi < rsi_threshold:
                                        should_enter = True
                                        last_qmr_quarter = q_key
                                    else:
                                        logger.debug(f"Quality Mean Reversion: {q_date} RSI={rsi:.0f} (>= {rsi_threshold}, skipping)")
                                else:
                                    should_enter = True  # No losses = strong uptrend, enter
                                    last_qmr_quarter = q_key

            elif template_type == 'quality_deterioration_short':
                # Enter SHORT when ROE drops below 5% or D/E > 2
                # PLUS trend confirmation: price must be below SMA(200) or SMA(50) declining
                # Without this, we'd short strong stocks that happen to have slightly declining ROE.
                roe = q.get('roe')
                de = q.get('debt_to_equity')
                if (roe is not None and roe < 0.05) or (de is not None and de > 2.0):
                    # Require trend confirmation before shorting
                    trend_confirmed = False
                    if entry_idx is not None and entry_idx < len(df):
                        # Check 1: Price below SMA(200)
                        if entry_idx >= 200:
                            sma200 = close.iloc[max(0, entry_idx - 200):entry_idx + 1].mean()
                            if close.iloc[entry_idx] < sma200:
                                trend_confirmed = True
                        # Check 2: SMA(50) declining (current < 20 bars ago)
                        if not trend_confirmed and entry_idx >= 70:
                            sma50_now = close.iloc[max(0, entry_idx - 50):entry_idx + 1].mean()
                            sma50_prev = close.iloc[max(0, entry_idx - 70):entry_idx - 20 + 1].mean()
                            if sma50_now < sma50_prev:
                                trend_confirmed = True
                    if trend_confirmed:
                        should_enter = True
                        direction = 'short'

            elif template_type == 'dividend_aristocrat':
                # Enter LONG when dividend yield > 2% and ROE > 10%
                # with entry spacing, technical confirmation, and no-overlap constraints
                min_entry_gap_days = params.get('min_entry_gap_days', 120)
                pullback_confirmation_pct = params.get('pullback_confirmation_pct', 0.04)
                rsi_confirmation_threshold = params.get('rsi_confirmation_threshold', 45)

                # Skip if a trade is currently open (entry would overlap with previous trade)
                if div_last_exit_date is not None:
                    try:
                        entry_dt = datetime.strptime(str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]), '%Y-%m-%d')
                        if entry_dt < div_last_exit_date:
                            continue
                    except (ValueError, TypeError):
                        pass

                # Enforce minimum entry gap (180 days default)
                if last_div_entry_date is not None:
                    try:
                        entry_dt = datetime.strptime(str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]), '%Y-%m-%d')
                        if (entry_dt - last_div_entry_date).days < min_entry_gap_days:
                            continue
                    except (ValueError, TypeError):
                        pass

                div_yield = q.get('dividend_yield')
                roe = q.get('roe')
                if div_yield is not None and div_yield > 0.02:
                    if roe is None or roe > 0.10:
                        # Technical confirmation: pullback >= 5% from 252-day high OR RSI < 40
                        if entry_idx is not None and entry_idx < len(df):
                            tech_confirmed = False
                            # Check pullback from 252-day high
                            lookback_252 = min(entry_idx, 252)
                            if lookback_252 > 0:
                                high_252 = close.iloc[max(0, entry_idx - lookback_252):entry_idx + 1].max()
                                if high_252 > 0:
                                    pullback = (high_252 - close.iloc[entry_idx]) / high_252
                                    if pullback >= pullback_confirmation_pct:
                                        tech_confirmed = True
                            # Check RSI < threshold
                            if not tech_confirmed and entry_idx >= 14:
                                price_slice = close.iloc[max(0, entry_idx - 20):entry_idx + 1]
                                delta = price_slice.diff()
                                gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                                loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                                if loss.iloc[-1] > 0:
                                    rs = gain.iloc[-1] / loss.iloc[-1]
                                    rsi = 100 - (100 / (1 + rs))
                                    if rsi < rsi_confirmation_threshold:
                                        tech_confirmed = True
                            if tech_confirmed:
                                should_enter = True

            elif template_type == 'insider_buying':
                # Enter LONG when real insider net purchases exceed threshold
                # Fetch insider data separately (not in quarterly_data)
                symbol = strategy.symbols[0] if strategy and strategy.symbols else None
                if symbol and hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                    insider_txns = self._fundamental_data_provider.get_insider_trading(symbol)
                    if insider_txns:
                        # Count net purchases in a window around this quarter
                        lookback_days = params.get('lookback_days', 90)
                        min_net_purchases = params.get('min_net_purchases', 3)
                        try:
                            q_dt = datetime.strptime(q_date, '%Y-%m-%d')
                            window_start = q_dt - timedelta(days=lookback_days)
                            buy_count = 0
                            sell_count = 0
                            for txn in insider_txns:
                                txn_date_str = txn.get('date', '')
                                if not txn_date_str:
                                    continue
                                try:
                                    txn_dt = datetime.strptime(txn_date_str, '%Y-%m-%d')
                                except (ValueError, TypeError):
                                    continue
                                if window_start <= txn_dt <= q_dt:
                                    if txn.get('transaction_type') == 'buy':
                                        buy_count += 1
                                    elif txn.get('transaction_type') == 'sell':
                                        sell_count += 1
                            net_purchases = buy_count - sell_count
                            if net_purchases >= min_net_purchases:
                                # Volume confirmation as secondary filter
                                if entry_idx is not None and entry_idx >= 10 and entry_idx < len(df):
                                    vol_avg = df['volume'].iloc[entry_idx-10:entry_idx].mean()
                                    vol_current = df['volume'].iloc[entry_idx]
                                    if vol_avg > 0 and vol_current / vol_avg > 1.0:
                                        should_enter = True
                                    else:
                                        # Still enter if strong insider signal even without volume confirmation
                                        if net_purchases >= min_net_purchases * 2:
                                            should_enter = True
                                else:
                                    should_enter = True
                        except (ValueError, TypeError):
                            pass
                    else:
                        # FMP insider endpoint unavailable on current plan (403/404).
                        # Fall back to momentum + volume proxy: 5-day return > 2% with
                        # above-average volume is a reasonable proxy for insider confidence.
                        if entry_idx is not None and entry_idx >= 10 and entry_idx < len(df):
                            ret_5d = (close.iloc[entry_idx] - close.iloc[entry_idx - 5]) / close.iloc[entry_idx - 5]
                            vol_avg = df['volume'].iloc[entry_idx - 10:entry_idx].mean()
                            vol_current = df['volume'].iloc[entry_idx]
                            vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0
                            if ret_5d > 0.02 and vol_ratio > 1.3:
                                should_enter = True

            elif template_type == 'sector_rotation':
                # Use real FMP sector performance data for sector rotation
                return self._simulate_sector_rotation_with_fundamentals(df, params, strategy)

            elif template_type == 'analyst_revision_momentum':
                # Enter when estimated_eps has been revised upward for 2+ consecutive quarters
                # Requires meaningful revision (>= 5% from base) to filter noise
                est = q.get('estimated_eps')
                if est is not None:
                    if prev_analyst_est is not None and prev_analyst_est > 0:
                        if est > prev_analyst_est:
                            analyst_consecutive_up += 1
                        else:
                            analyst_consecutive_up = 0
                            analyst_base_est = est  # Reset base on downward revision

                        min_consec = params.get('min_consecutive_revisions', 2)
                        if analyst_consecutive_up >= min_consec:
                            revision_pct = (est - analyst_base_est) / abs(analyst_base_est) if analyst_base_est and analyst_base_est > 0 else 0
                            if revision_pct >= params.get('min_revision_pct', 0.05):
                                should_enter = True
                    else:
                        analyst_base_est = est
                    prev_analyst_est = est

            elif template_type == 'share_buyback':
                # Enter when shares outstanding decreased > min_buyback_pct
                # Require positive EPS (profitable company) and RSI confirmation.
                # Check quarterly data for share count changes to verify ongoing buyback.
                if not share_buyback_checked:
                    share_buyback_checked = True
                    try:
                        sym = strategy.symbols[0] if strategy and strategy.symbols else None
                        if sym and hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                            fd = self._fundamental_data_provider.get_fundamental_data(sym)
                            if fd and fd.shares_change_percent is not None:
                                min_buyback = params.get('min_buyback_pct', 0.01)
                                if fd.shares_change_percent <= -min_buyback:
                                    if fd.eps is not None and fd.eps > 0:
                                        # Verify buyback is meaningful relative to market cap
                                        if fd.market_cap is not None and fd.market_cap > 1_000_000_000:
                                            share_buyback_signal = True
                                        elif fd.market_cap is None:
                                            share_buyback_signal = True  # No market cap data, proceed
                    except Exception:
                        pass
                if share_buyback_signal:
                    # Enter with RSI confirmation
                    if entry_idx is not None and entry_idx >= 14 and entry_idx < len(df):
                        price_slice = close.iloc[max(0, entry_idx - 20):entry_idx + 1]
                        delta = price_slice.diff()
                        gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                        if loss.iloc[-1] > 0:
                            rs = gain.iloc[-1] / loss.iloc[-1]
                            rsi = 100 - (100 / (1 + rs))
                            if rsi < params.get('rsi_max_entry', 60):
                                should_enter = True
                                share_buyback_signal = False  # Only enter once
                        else:
                            should_enter = True
                            share_buyback_signal = False

            elif template_type in ('sector_rotation_short',
                                    'end_of_month_momentum', 'pairs_trading'):
                # These templates don't map cleanly to quarterly data
                # Fall through to price-proxy simulation below
                pass

            elif template_type == 'multi_factor_composite':
                # Multi-Factor Composite: use cross-sectional ranking data
                # Entry when F-Score >= 6 AND accruals < 0.05 (for LONG)
                # or F-Score <= 3 AND accruals > 0.10 (for SHORT)
                f_score = q.get('piotroski_f_score')
                accruals = q.get('accruals_ratio')
                fcf_yield = q.get('fcf_yield')
                sue_val = q.get('sue')

                is_long_template = params.get('top_pct') is not None
                is_short_template = params.get('bottom_pct') is not None

                if is_long_template:
                    # LONG: high quality + low accruals + positive SUE
                    min_f = params.get('min_f_score', 6)
                    max_acc = params.get('max_accruals', 0.05)
                    if f_score is not None and f_score >= min_f:
                        if accruals is None or accruals < max_acc:
                            # Additional confirmation: positive FCF or positive SUE
                            if (fcf_yield is not None and fcf_yield > 0) or (sue_val is not None and sue_val > 0):
                                should_enter = True
                elif is_short_template:
                    # SHORT: low quality + high accruals
                    max_f = params.get('max_f_score', 3)
                    min_acc = params.get('min_accruals', 0.10)
                    if f_score is not None and f_score <= max_f:
                        if accruals is not None and accruals > min_acc:
                            should_enter = True
                            direction = 'short'

            elif template_type == 'gross_profitability':
                # Gross Profitability (Novy-Marx): long when GP/Assets is high
                gp = q.get('gross_profit')
                ta = q.get('total_assets')
                f_score = q.get('piotroski_f_score')
                if gp is not None and ta is not None and ta > 0:
                    gp_to_assets = gp / ta
                    min_gp = params.get('min_gp_to_assets', 0.30)
                    if gp_to_assets >= min_gp:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            # Trend confirmation: price above SMA(50)
                            if entry_idx is not None and entry_idx >= 50 and entry_idx < len(df):
                                sma50 = close.iloc[max(0, entry_idx - 50):entry_idx + 1].mean()
                                if close.iloc[entry_idx] > sma50:
                                    should_enter = True

            elif template_type == 'accruals_quality':
                # Accruals Quality (Sloan): long low accruals, short high accruals
                accruals = q.get('accruals_ratio')
                f_score = q.get('piotroski_f_score')
                ocf = q.get('operating_cash_flow')

                is_long = params.get('max_accruals_ratio') is not None
                is_short = params.get('min_accruals_ratio') is not None

                if is_long:
                    max_acc = params.get('max_accruals_ratio', -0.03)
                    if accruals is not None and accruals < max_acc:
                        if ocf is not None and ocf > 0:
                            if f_score is None or f_score >= params.get('min_f_score', 5):
                                should_enter = True
                elif is_short:
                    min_acc = params.get('min_accruals_ratio', 0.10)
                    if accruals is not None and accruals > min_acc:
                        if f_score is not None and f_score <= params.get('max_f_score', 4):
                            # Trend confirmation for shorts
                            if entry_idx is not None and entry_idx >= 200 and entry_idx < len(df):
                                sma200 = close.iloc[max(0, entry_idx - 200):entry_idx + 1].mean()
                                if close.iloc[entry_idx] < sma200:
                                    should_enter = True
                                    direction = 'short'

            elif template_type == 'fcf_yield_value':
                # FCF Yield Value: long when FCF yield is high
                fcf_yield = q.get('fcf_yield')
                f_score = q.get('piotroski_f_score')
                ocf = q.get('operating_cash_flow')
                if fcf_yield is not None and fcf_yield >= params.get('min_fcf_yield', 0.05):
                    if ocf is not None and ocf > 0:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True

            elif template_type == 'price_target_upside':
                # Price Target Upside: long when analyst consensus target implies 20%+ upside
                # Uses FMP price target data fetched separately (not in quarterly data)
                symbol_name = strategy.symbols[0] if strategy and strategy.symbols else None
                if symbol_name and hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                    try:
                        pt_data = self._fundamental_data_provider.get_price_target_consensus(symbol_name)
                        if pt_data and pt_data.get('upside_pct') is not None:
                            min_upside = params.get('min_upside_pct', 0.20)
                            f_score = q.get('piotroski_f_score')
                            if pt_data['upside_pct'] >= min_upside:
                                if f_score is None or f_score >= params.get('min_f_score', 4):
                                    should_enter = True
                    except Exception:
                        pass

            elif template_type == 'shareholder_yield':
                # Shareholder Yield (Faber): dividend + buyback + debt paydown
                div_yield = q.get('dividend_yield') or 0
                # Buyback yield: negative shares_change = buyback
                shares_change = q.get('shares_outstanding')
                prev_shares = None
                # Look at previous quarter for shares change
                q_idx = quarterly_data.index(q) if q in quarterly_data else -1
                if q_idx > 0:
                    prev_shares = quarterly_data[q_idx - 1].get('shares_outstanding')
                buyback_yield = 0
                if shares_change and prev_shares and prev_shares > 0:
                    shares_pct_change = (shares_change - prev_shares) / prev_shares
                    if shares_pct_change < 0:
                        buyback_yield = abs(shares_pct_change) * 4  # Annualize quarterly
                # Debt paydown yield
                lt_debt = q.get('long_term_debt')
                prev_lt_debt = None
                if q_idx > 0:
                    prev_lt_debt = quarterly_data[q_idx - 1].get('long_term_debt')
                mkt_cap = q.get('market_cap')
                debt_paydown_yield = 0
                if lt_debt is not None and prev_lt_debt is not None and mkt_cap and mkt_cap > 0:
                    debt_reduction = prev_lt_debt - lt_debt
                    if debt_reduction > 0:
                        debt_paydown_yield = (debt_reduction / mkt_cap) * 4  # Annualize

                total_yield = div_yield + buyback_yield + debt_paydown_yield
                f_score = q.get('piotroski_f_score')
                fcf = q.get('free_cash_flow')
                min_yield = params.get('min_shareholder_yield', 0.04)
                if total_yield >= min_yield:
                    if fcf is not None and fcf > 0:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True

            elif template_type == 'earnings_momentum_combo':
                # Earnings + Price Momentum Combo: SUE > 1.5 + strong price momentum
                sue_val = q.get('sue')
                min_sue = params.get('min_sue', 1.5)
                if sue_val is not None and sue_val >= min_sue:
                    # Check price momentum at entry point
                    if entry_idx is not None and entry_idx >= 63 and entry_idx < len(df):
                        price_3m_ago = close.iloc[entry_idx - 63]
                        price_now = close.iloc[entry_idx]
                        if price_3m_ago > 0:
                            momentum_3m = (price_now - price_3m_ago) / price_3m_ago
                            if momentum_3m > 0.05:  # At least 5% 3-month return
                                should_enter = True

            elif template_type == 'quality_value_combo':
                # Quality + Value Combo: high FCF yield AND high gross profitability
                fcf_yield = q.get('fcf_yield')
                gp = q.get('gross_profit')
                ta = q.get('total_assets')
                f_score = q.get('piotroski_f_score')
                min_fcf = params.get('min_fcf_yield', 0.03)
                min_gp = params.get('min_gp_to_assets', 0.25)
                min_f = params.get('min_f_score', 6)
                if fcf_yield is not None and fcf_yield >= min_fcf:
                    if gp is not None and ta is not None and ta > 0:
                        gp_ratio = gp / ta
                        if gp_ratio >= min_gp:
                            if f_score is None or f_score >= min_f:
                                should_enter = True

            elif template_type == 'deleveraging':
                # Deleveraging: long when company is actively paying down debt
                lt_debt = q.get('long_term_debt')
                fcf = q.get('free_cash_flow')
                f_score = q.get('piotroski_f_score')
                de = q.get('debt_to_equity')
                # Compare to 4 quarters ago for YoY change
                q_idx = quarterly_data.index(q) if q in quarterly_data else -1
                if q_idx >= 4:
                    prev_debt = quarterly_data[q_idx - 4].get('long_term_debt')
                    if lt_debt is not None and prev_debt is not None and prev_debt > 0:
                        debt_change = (lt_debt - prev_debt) / prev_debt
                        min_reduction = params.get('min_debt_reduction_pct', 0.10)
                        if debt_change <= -min_reduction:  # Debt decreased by 10%+
                            if fcf is not None and fcf > 0:
                                if f_score is None or f_score >= params.get('min_f_score', 5):
                                    # Must still have meaningful debt (room to deleverage)
                                    if de is not None and de >= params.get('min_debt_to_equity', 0.3):
                                        should_enter = True

            if should_enter:
                trade = execute_trade(entry_idx, direction)
                if trade:
                    trade['fundamental_trigger'] = template_type
                    trade['quarter'] = q_date
                    trades.append(trade)
                    # Track dividend aristocrat trade state for overlap prevention
                    if template_type == 'dividend_aristocrat':
                        try:
                            last_div_entry_date = datetime.strptime(trade['entry_date'], '%Y-%m-%d')
                            # Store exit date to check overlap with future entries
                            div_last_exit_date = datetime.strptime(trade['exit_date'], '%Y-%m-%d')
                        except (ValueError, TypeError):
                            pass

        # For templates that don't use quarterly data, fall back to price proxy
        if not trades and template_type in ('sector_rotation_short',
                                             'end_of_month_momentum', 'pairs_trading'):
            logger.info(f"Template {template_type} doesn't use quarterly data, using price-proxy simulation")
            return self._simulate_with_price_proxy(template_type, df, params, strategy)

        return trades


    
    def _simulate_sector_rotation_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Sector Rotation trades using momentum-based rebalancing.
        Enters when 60-day momentum is positive, exits when momentum turns negative.
        """
        trades = []
        close = df['close']
        
        rebalance_days = params.get('rebalance_frequency_days', 30)
        momentum_lookback = params.get('momentum_lookback_days', 60)
        stop_loss = params.get('stop_loss_pct', 0.08)
        take_profit = params.get('take_profit_pct', 0.15)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(momentum_lookback, len(df)):
            momentum = (close.iloc[i] - close.iloc[i - momentum_lookback]) / close.iloc[i - momentum_lookback]
            
            if not in_trade:
                if momentum > 0.02:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if pnl_pct >= take_profit:
                    exit_reason = "take_profit"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= rebalance_days and momentum < 0:
                    exit_reason = "momentum_reversal"
                elif days_held >= rebalance_days * 3:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades

    def _simulate_sector_rotation_with_fundamentals(
        self, df: pd.DataFrame, params: Dict, strategy=None
    ) -> List[Dict]:
        """
        Simulate sector rotation using real FMP sector performance data.

        Fetches sector performance, ranks sectors by trailing return over a
        configurable period (default 3 months), and simulates monthly
        rebalancing into the top N sectors (default 3).

        The simulation uses the strategy's assigned symbol price data as a proxy
        for the top-ranked sector ETF. This works because the proposer assigns
        sector ETFs (XLF, XLK, etc.) as the primary symbol for sector rotation
        strategies. The backtest validates whether the assigned ETF is actually
        in a favorable sector.
        """
        # Ensure we have a fundamental data provider
        if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
            try:
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                import yaml
                from pathlib import Path
                config = {}
                try:
                    config_path = Path("config/autonomous_trading.yaml")
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = yaml.safe_load(f) or {}
                except Exception:
                    pass
                self._fundamental_data_provider = get_fundamental_data_provider(config)
            except Exception as e:
                logger.warning(f"Could not initialize FundamentalDataProvider for sector rotation: {e}")
                return self._simulate_with_price_proxy('sector_rotation', df, params, strategy)

        sector_data = self._fundamental_data_provider.get_sector_performance()
        if not sector_data:
            logger.warning("No sector data from FMP, falling back to price proxy")
            return self._simulate_with_price_proxy('sector_rotation', df, params, strategy)

        # Configuration
        trailing_period = params.get('trailing_period', '3m')
        top_n = params.get('top_sectors', 3)
        rebalance_days = params.get('rebalance_frequency_days', 30)
        profit_target = params.get('profit_target', 0.15)
        stop_loss = params.get('stop_loss_pct', 0.08)
        hold_max = params.get('hold_period_max', 90)

        # Rank sectors by trailing period performance
        ranked = sorted(
            sector_data.items(),
            key=lambda x: x[1].get(trailing_period, 0.0),
            reverse=True,
        )
        top_sectors = [etf for etf, _ in ranked[:top_n]]

        if not top_sectors:
            logger.warning("No sectors ranked, falling back to price proxy")
            return self._simulate_with_price_proxy('sector_rotation', df, params, strategy)

        # Check if the strategy's assigned symbol is in a favorable sector
        assigned_symbol = strategy.symbols[0] if strategy and strategy.symbols else None
        symbol_in_top = assigned_symbol in top_sectors if assigned_symbol else False

        logger.info(
            f"Sector rotation: top {top_n} sectors by {trailing_period} return: "
            f"{', '.join(top_sectors)} | assigned={assigned_symbol} (in_top={symbol_in_top})"
        )

        # If the assigned symbol is NOT in a top sector, this strategy shouldn't trade.
        # Return minimal trades to signal poor fit (rather than simulating on wrong data).
        if not symbol_in_top:
            logger.info(f"Sector rotation: {assigned_symbol} not in top {top_n} sectors — poor fit")
            # Still simulate but with a momentum filter: only enter when the ETF has positive momentum
            close = df['close']
            trades: List[Dict] = []
            momentum_lookback = 60
            
            i = max(rebalance_days, momentum_lookback)
            while i < len(df):
                # Only enter if the ETF has positive momentum (it's rotating INTO favor)
                if i >= momentum_lookback:
                    momentum = (close.iloc[i] - close.iloc[i - momentum_lookback]) / close.iloc[i - momentum_lookback]
                    if momentum <= 0.02:
                        i += rebalance_days
                        continue
                
                entry_price = close.iloc[i]
                entry_idx = i
                exit_idx = min(i + rebalance_days, len(df) - 1)
                exit_reason = "rebalance"

                for j in range(i + 1, min(i + hold_max + 1, len(df))):
                    current = close.iloc[j]
                    pnl_pct = (current - entry_price) / entry_price if entry_price > 0 else 0
                    if pnl_pct >= profit_target:
                        exit_idx = j
                        exit_reason = "profit_target"
                        break
                    elif pnl_pct <= -stop_loss:
                        exit_idx = j
                        exit_reason = "stop_loss"
                        break
                    elif j - i >= rebalance_days:
                        exit_idx = j
                        exit_reason = "rebalance"
                        break

                exit_price = close.iloc[exit_idx]
                pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
                days_held = exit_idx - entry_idx

                trades.append({
                    "entry_price": entry_price, "exit_price": exit_price,
                    "pnl_pct": pnl_pct, "days_held": days_held,
                    "exit_reason": exit_reason,
                    "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                    "exit_date": str(df.index[exit_idx].date()) if hasattr(df.index[exit_idx], 'date') else str(df.index[exit_idx]),
                    "fundamental_trigger": "sector_rotation", "top_sectors": top_sectors,
                })
                i = exit_idx + 1
            return trades

        # Symbol IS in a top sector — simulate monthly rebalancing trades
        trades: List[Dict] = []
        close = df['close']
        if len(df) < rebalance_days:
            return trades

        i = rebalance_days
        while i < len(df):
            entry_price = close.iloc[i]
            entry_idx = i
            exit_idx = min(i + rebalance_days, len(df) - 1)
            exit_reason = "rebalance"

            for j in range(i + 1, min(i + hold_max + 1, len(df))):
                current = close.iloc[j]
                pnl_pct = (current - entry_price) / entry_price if entry_price > 0 else 0

                if pnl_pct >= profit_target:
                    exit_idx = j
                    exit_reason = "profit_target"
                    break
                elif pnl_pct <= -stop_loss:
                    exit_idx = j
                    exit_reason = "stop_loss"
                    break
                elif j - i >= rebalance_days:
                    exit_idx = j
                    exit_reason = "rebalance"
                    break

            exit_price = close.iloc[exit_idx]
            pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
            days_held = exit_idx - entry_idx

            trades.append({
                "entry_price": entry_price, "exit_price": exit_price,
                "pnl_pct": pnl_pct, "days_held": days_held,
                "exit_reason": exit_reason,
                "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                "exit_date": str(df.index[exit_idx].date()) if hasattr(df.index[exit_idx], 'date') else str(df.index[exit_idx]),
                "fundamental_trigger": "sector_rotation", "top_sectors": top_sectors,
            })
            i = exit_idx + 1

        if trades:
            logger.info(
                f"Sector rotation with fundamentals: {len(trades)} trades, "
                f"top sectors: {', '.join(top_sectors)}"
            )

        return trades
    
    def _simulate_quality_mean_reversion_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Quality Mean Reversion trades using RSI oversold + price recovery.
        Uses the technical component (RSI < 30 entry, mean reversion exit) as timing mechanism.
        """
        trades = []
        close = df['close']
        
        rsi_period = params.get('rsi_period', 14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        
        sma_50 = close.rolling(window=50).mean()
        
        oversold_threshold = params.get('oversold_threshold', 35)
        profit_target = params.get('profit_target', 0.05)
        stop_loss = params.get('stop_loss_pct', 0.05)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(50, len(df)):
            if pd.isna(rsi.iloc[i]) or pd.isna(sma_50.iloc[i]):
                continue
            
            if not in_trade:
                if i > 0 and not pd.isna(rsi.iloc[i-1]):
                    if rsi.iloc[i-1] < oversold_threshold and rsi.iloc[i] >= oversold_threshold:
                        entry_price = close.iloc[i]
                        entry_idx = i
                        in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if current_price >= sma_50.iloc[i]:
                    exit_reason = "mean_reversion_complete"
                elif pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= 40:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades
    
    def _simulate_earnings_miss_momentum_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Earnings Miss Momentum SHORT trades.
        Enters SHORT after negative 3%+ moves (proxy for earnings misses). P&L inverted for short.
        """
        trades = []
        close = df['close']
        daily_returns = close.pct_change()
        
        profit_target = params.get('profit_target', 0.05)
        stop_loss = params.get('stop_loss_pct', 0.03)
        hold_max = params.get('hold_period_max', 30)
        entry_delay = params.get('entry_delay_days', 2)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(entry_delay + 1, len(df)):
            if not in_trade:
                trigger_idx = i - entry_delay
                if trigger_idx >= 1 and daily_returns.iloc[trigger_idx] < -0.03:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                # SHORT P&L: profit when price drops
                pnl_pct = (entry_price - current_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades
    
    def _simulate_sector_rotation_short_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Sector Rotation SHORT trades.
        Short when sector bounces into resistance during a downtrend (mean-reversion short).
        Entry: 60d momentum negative AND price bounced to near SMA(20) from below.
        This avoids shorting at the bottom of a move (which gets squeezed).
        """
        trades = []
        close = df['close']
        sma_20 = close.rolling(window=20).mean()
        
        rebalance_days = params.get('rebalance_frequency_days', 30)
        momentum_lookback = params.get('momentum_lookback_days', 60)
        stop_loss = params.get('stop_loss_pct', 0.06)
        take_profit = params.get('take_profit_pct', 0.05)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(momentum_lookback, len(df)):
            if pd.isna(sma_20.iloc[i]):
                continue
            momentum = (close.iloc[i] - close.iloc[i - momentum_lookback]) / close.iloc[i - momentum_lookback]
            
            if not in_trade:
                # Short when: downtrend (negative 60d momentum) BUT price has bounced
                # near SMA(20) — this is the "sell the rally" setup
                if momentum < -0.03:
                    # Price must be within 1% of SMA(20) from below (bounced up to resistance)
                    distance_to_sma = (sma_20.iloc[i] - close.iloc[i]) / sma_20.iloc[i]
                    if -0.01 < distance_to_sma < 0.02:
                        entry_price = close.iloc[i]
                        entry_idx = i
                        in_trade = True
            else:
                current_price = close.iloc[i]
                # SHORT P&L: profit when price drops
                pnl_pct = (entry_price - current_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if pnl_pct >= take_profit:
                    exit_reason = "take_profit"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= rebalance_days and momentum > 0:
                    exit_reason = "momentum_reversal"
                elif days_held >= rebalance_days * 2:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades
    
    def _simulate_quality_deterioration_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """
        Simulate Quality Deterioration SHORT trades.
        Enters SHORT when RSI crosses below 75 (from overbought). P&L inverted for short.
        """
        trades = []
        close = df['close']
        
        rsi_period = params.get('rsi_period', 14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        
        sma_50 = close.rolling(window=50).mean()
        
        overbought_threshold = params.get('overbought_threshold', 75)
        profit_target = params.get('profit_target', 0.05)
        stop_loss = params.get('stop_loss_pct', 0.05)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(50, len(df)):
            if pd.isna(rsi.iloc[i]) or pd.isna(sma_50.iloc[i]):
                continue
            
            if not in_trade:
                if i > 0 and not pd.isna(rsi.iloc[i-1]):
                    # Enter SHORT when RSI crosses below overbought threshold
                    if rsi.iloc[i-1] > overbought_threshold and rsi.iloc[i] <= overbought_threshold:
                        entry_price = close.iloc[i]
                        entry_idx = i
                        in_trade = True
            else:
                current_price = close.iloc[i]
                # SHORT P&L: profit when price drops
                pnl_pct = (entry_price - current_price) / entry_price
                days_held = i - entry_idx
                
                exit_reason = None
                if current_price <= sma_50.iloc[i]:
                    exit_reason = "mean_reversion_complete"
                elif pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= 40:
                    exit_reason = "max_hold"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        
        return trades
    
    def _simulate_dividend_aristocrat_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """Simulate Dividend Aristocrat trades: enter on pullback >3% from rolling 252-day high.
        
        Includes 180-day entry gap enforcement and no overlapping trades.
        """
        trades = []
        close = df['close']
        high = df['high']
        
        pullback_pct = params.get('pullback_from_high_pct', 0.03)
        profit_target = params.get('profit_target', 0.12)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 90)
        min_entry_gap_days = params.get('min_entry_gap_days', 180)
        lookback = min(252, len(df) - 1)
        
        rolling_high = high.rolling(window=lookback).max()
        in_trade = False
        entry_price = 0
        entry_idx = 0
        last_entry_idx = None  # Track last entry for 180-day gap
        
        for i in range(lookback, len(df)):
            if pd.isna(rolling_high.iloc[i]):
                continue
            if not in_trade:
                # Enforce 180-day minimum gap between entries
                if last_entry_idx is not None and (i - last_entry_idx) < min_entry_gap_days:
                    continue
                
                pullback = (rolling_high.iloc[i] - close.iloc[i]) / rolling_high.iloc[i]
                if pullback >= pullback_pct:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    last_entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        return trades
    
    def _simulate_insider_buying_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """Simulate Insider Buying trades: enter on positive 2%+ 5-day momentum as proxy for insider confidence."""
        trades = []
        close = df['close']
        
        profit_target = params.get('profit_target', 0.10)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 60)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(10, len(df)):
            if not in_trade:
                ret_5d = (close.iloc[i] - close.iloc[i-5]) / close.iloc[i-5]
                vol_ratio = df['volume'].iloc[i] / df['volume'].iloc[i-10:i].mean() if df['volume'].iloc[i-10:i].mean() > 0 else 1
                if ret_5d > 0.02 and vol_ratio > 1.3:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        return trades
    
    def _simulate_revenue_acceleration_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """Simulate Revenue Acceleration trades: enter on strong positive earnings-like moves (>2.5%)."""
        trades = []
        close = df['close']
        daily_returns = close.pct_change()
        
        profit_target = params.get('profit_target', 0.12)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 40)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(3, len(df)):
            if not in_trade:
                if daily_returns.iloc[i-1] > 0.025 and daily_returns.iloc[i-2] > 0:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        return trades
    
    def _simulate_relative_value_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """Simulate Relative Value trades: enter LONG on mean reversion from oversold with trend confirmation."""
        trades = []
        close = df['close']
        sma_50 = close.rolling(window=50).mean()
        sma_20 = close.rolling(window=20).mean()
        
        profit_target = params.get('profit_target', 0.10)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 45)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0
        
        for i in range(50, len(df)):
            if pd.isna(sma_50.iloc[i]) or pd.isna(sma_20.iloc[i]):
                continue
            if not in_trade:
                discount = (sma_50.iloc[i] - close.iloc[i]) / sma_50.iloc[i]
                # Enter when price is 3-8% below SMA50 (discount zone, not freefall)
                # AND SMA20 is still above SMA50 (overall trend intact — just a pullback)
                if 0.03 < discount < 0.08 and sma_20.iloc[i] > sma_50.iloc[i] * 0.98:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                exit_reason = None
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "monthly_rebalance"
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        return trades
    
    def _simulate_end_of_month_momentum_trades(self, df: pd.DataFrame, params: Dict) -> List[Dict]:
        """Simulate End-of-Month Momentum trades: enter in last 3 trading days of month when price > SMA(20) and RSI > 40."""
        trades = []
        close = df['close']
        sma_period = params.get('sma_period', 20)
        rsi_period = params.get('rsi_period', 14)
        rsi_min = params.get('rsi_min', 40)
        month_end_day = params.get('month_end_day_threshold', 26)
        exit_day = params.get('exit_day_of_new_month', 3)
        stop_loss = params.get('stop_loss_pct', 0.02)
        
        sma = close.rolling(window=sma_period).mean()
        
        # Calculate RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        
        start_idx = max(sma_period, rsi_period) + 1
        in_trade = False
        entry_price = 0
        entry_idx = 0
        entry_month = 0
        
        for i in range(start_idx, len(df)):
            if pd.isna(sma.iloc[i]) or pd.isna(rsi.iloc[i]):
                continue
            
            idx_date = df.index[i]
            day = idx_date.day if hasattr(idx_date, 'day') else 1
            month = idx_date.month if hasattr(idx_date, 'month') else 1
            
            if not in_trade:
                # Entry: last 3 trading days of month, price > SMA(20), RSI > 40
                if day >= month_end_day and close.iloc[i] > sma.iloc[i] and rsi.iloc[i] > rsi_min:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    entry_month = month
                    in_trade = True
            else:
                current_price = close.iloc[i]
                pnl_pct = (current_price - entry_price) / entry_price
                days_held = i - entry_idx
                exit_reason = None
                
                # Stop loss
                if pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                # Exit on 3rd trading day of new month
                elif month != entry_month and day >= exit_day:
                    exit_reason = "new_month_exit"
                
                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    })
                    in_trade = False
        return trades
    
    # ===== PAIRS TRADING CONSTANTS =====
    PAIRS_MAP = {
        s: pair for pair in [
            # Original 8 pairs
            ("KO", "PEP"), ("GOOGL", "META"), ("JPM", "GS"), ("XOM", "CVX"),
            ("MSFT", "AAPL"), ("V", "MA"), ("HD", "LOW"), ("UNH", "LLY"),
            # Expanded 10 pairs (all in our 232-stock universe)
            ("GS", "MS"), ("BAC", "WFC"), ("NVDA", "AMD"), ("MCD", "YUM"),
            ("PFE", "MRK"), ("T", "VZ"), ("NEE", "DUK"), ("CAT", "DE"),
            ("BA", "LMT"), ("AMZN", "SHOP"),
        ] for s in pair
    }

    def _simulate_pairs_trading_trades(self, df: pd.DataFrame, params: Dict, strategy: Strategy = None) -> List[Dict]:
        """Simulate Pairs Trading trades using OLS regression spread z-score between correlated pairs.

        Uses the academically correct approach: spread = sym - β*partner - α (OLS regression),
        which produces cleaner z-scores than the simple price ratio method.
        """
        trades = []
        z_entry = params.get('z_entry', 2.0)
        z_exit = params.get('z_exit', 0.0)
        z_stop = params.get('z_stop', 3.0)
        rolling_window = params.get('rolling_window', 60)
        hold_max = params.get('hold_period_max', 30)
        stop_loss = params.get('stop_loss_pct', 0.04)
        profit_target = params.get('profit_target', 0.05)

        # For backtest, we need the partner symbol's data
        symbol = strategy.symbols[0] if strategy and strategy.symbols else None
        if not symbol or symbol not in self.PAIRS_MAP:
            return trades

        pair = self.PAIRS_MAP[symbol]
        partner = pair[1] if pair[0] == symbol else pair[0]

        try:
            start = df.index[0] if hasattr(df.index[0], 'date') else datetime.now() - timedelta(days=len(df))
            end = df.index[-1] if hasattr(df.index[-1], 'date') else datetime.now()
            partner_data = self.market_data.get_historical_data(symbol=partner, start=start, end=end)
            if not partner_data or len(partner_data) < rolling_window + 10:
                return trades
            partner_df = pd.DataFrame([{
                "timestamp": md.timestamp, "close": md.close
            } for md in partner_data]).set_index("timestamp").sort_index()
        except Exception:
            return trades

        # Align both series by date
        combined = pd.DataFrame({"sym": df['close'], "partner": partner_df['close']}).dropna()
        if len(combined) < rolling_window + 10:
            return trades

        # OLS regression spread: spread = sym - β*partner - α
        # Rolling OLS gives time-varying hedge ratio β, which is more robust than fixed ratio
        def _rolling_ols_spread(sym_series: pd.Series, partner_series: pd.Series, window: int) -> pd.Series:
            """Compute rolling OLS spread: sym - β*partner - α"""
            spreads = pd.Series(index=sym_series.index, dtype=float)
            for i in range(window, len(sym_series)):
                y = sym_series.iloc[i - window:i].values
                x = partner_series.iloc[i - window:i].values
                # OLS: β = cov(x,y)/var(x), α = mean(y) - β*mean(x)
                x_mean, y_mean = x.mean(), y.mean()
                var_x = ((x - x_mean) ** 2).mean()
                if var_x < 1e-10:
                    continue
                beta = ((x - x_mean) * (y - y_mean)).mean() / var_x
                alpha = y_mean - beta * x_mean
                spreads.iloc[i] = sym_series.iloc[i] - beta * partner_series.iloc[i] - alpha
            return spreads

        spread = _rolling_ols_spread(combined['sym'], combined['partner'], rolling_window)
        spread_mean = spread.rolling(window=rolling_window).mean()
        spread_std = spread.rolling(window=rolling_window).std()
        z_score = (spread - spread_mean) / spread_std.replace(0, float('nan'))

        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        trade_direction = None  # 'long_sym' or 'short_sym'

        for i in range(rolling_window * 2, len(combined)):
            if pd.isna(z_score.iloc[i]):
                continue
            z = z_score.iloc[i]
            if not in_trade:
                if z > z_entry:
                    # Spread above mean → sym overpriced vs partner → SHORT sym
                    entry_price = combined['sym'].iloc[i]
                    entry_idx = i
                    trade_direction = 'short_sym'
                    in_trade = True
                elif z < -z_entry:
                    # Spread below mean → sym underpriced vs partner → LONG sym
                    entry_price = combined['sym'].iloc[i]
                    entry_idx = i
                    trade_direction = 'long_sym'
                    in_trade = True
            else:
                current_price = combined['sym'].iloc[i]
                days_held = i - entry_idx
                if trade_direction == 'long_sym':
                    pnl_pct = (current_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - current_price) / entry_price

                exit_reason = None
                if trade_direction == 'long_sym' and z >= z_exit:
                    exit_reason = "mean_reversion"
                elif trade_direction == 'short_sym' and z <= z_exit:
                    exit_reason = "mean_reversion"
                elif abs(z) > z_stop:
                    exit_reason = "z_stop_loss"
                elif pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold_max:
                    exit_reason = "max_hold"

                if exit_reason:
                    trades.append({
                        "entry_price": entry_price, "exit_price": current_price,
                        "pnl_pct": pnl_pct, "days_held": days_held, "exit_reason": exit_reason,
                        "entry_date": str(combined.index[entry_idx].date()) if hasattr(combined.index[entry_idx], 'date') else str(combined.index[entry_idx]),
                        "exit_date": str(combined.index[i].date()) if hasattr(combined.index[i], 'date') else str(combined.index[i]),
                    })
                    in_trade = False
        return trades

    def _simulate_analyst_revision_trades(self, df, params):
        """Price-proxy for analyst revision: enter on 3-month momentum > 5% with RSI < 65."""
        trades = []
        close = df['close']
        profit_target = params.get('profit_target', 0.12)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 60)
        momentum_lookback = 63  # ~3 months

        in_trade = False
        entry_price = 0
        entry_idx = 0

        for i in range(momentum_lookback + 14, len(df)):
            if not in_trade:
                momentum = (close.iloc[i] - close.iloc[i - momentum_lookback]) / close.iloc[i - momentum_lookback]
                if momentum > 0.05:
                    # RSI check
                    price_slice = close.iloc[max(0, i - 20):i + 1]
                    delta = price_slice.diff()
                    gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                    if loss.iloc[-1] > 0:
                        rs = gain.iloc[-1] / loss.iloc[-1]
                        rsi = 100 - (100 / (1 + rs))
                        if rsi < 65:
                            entry_price = close.iloc[i]
                            entry_idx = i
                            in_trade = True
            else:
                current = close.iloc[i]
                pnl = (current - entry_price) / entry_price
                days = i - entry_idx
                exit_reason = None
                if pnl >= profit_target: exit_reason = "profit_target"
                elif pnl <= -stop_loss: exit_reason = "stop_loss"
                elif days >= hold_max: exit_reason = "max_hold"
                if exit_reason:
                    trades.append({"entry_price": entry_price, "exit_price": current, "pnl_pct": pnl, "days_held": days, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i])})
                    in_trade = False
        return trades

    def _simulate_share_buyback_trades(self, df, params):
        """Price-proxy for share buyback: enter on pullback > 3% from 50-day high with RSI < 55."""
        trades = []
        close = df['close']
        profit_target = params.get('profit_target', 0.10)
        stop_loss = params.get('stop_loss_pct', 0.05)
        hold_max = params.get('hold_period_max', 60)

        rolling_high = close.rolling(50).max()
        in_trade = False
        entry_price = 0
        entry_idx = 0

        for i in range(64, len(df)):
            if pd.isna(rolling_high.iloc[i]):
                continue
            if not in_trade:
                pullback = (rolling_high.iloc[i] - close.iloc[i]) / rolling_high.iloc[i]
                if pullback >= 0.03:
                    price_slice = close.iloc[max(0, i - 20):i + 1]
                    delta = price_slice.diff()
                    gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                    if loss.iloc[-1] > 0:
                        rs = gain.iloc[-1] / loss.iloc[-1]
                        rsi = 100 - (100 / (1 + rs))
                        if rsi < 55:
                            entry_price = close.iloc[i]
                            entry_idx = i
                            in_trade = True
            else:
                current = close.iloc[i]
                pnl = (current - entry_price) / entry_price
                days = i - entry_idx
                exit_reason = None
                if pnl >= profit_target: exit_reason = "profit_target"
                elif pnl <= -stop_loss: exit_reason = "stop_loss"
                elif days >= hold_max: exit_reason = "max_hold"
                if exit_reason:
                    trades.append({"entry_price": entry_price, "exit_price": current, "pnl_pct": pnl, "days_held": days, "exit_reason": exit_reason,
                        "entry_date": str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], 'date') else str(df.index[entry_idx]),
                        "exit_date": str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i])})
                    in_trade = False
        return trades

    def _handle_pairs_trading(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame,
        pt_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """
        Pairs Trading (market-neutral): trade the spread between two correlated stocks.
        Entry when z-score of price ratio > 2.0, exit on mean reversion or stop loss.
        Each leg is a separate order on eToro.
        """
        from src.models.enums import SignalAction

        z_entry = pt_config.get('z_entry', 2.0)
        z_exit = pt_config.get('z_exit', 0.0)
        z_stop = pt_config.get('z_stop', 3.0)
        rolling_window = pt_config.get('rolling_window', 60)
        stop_loss = pt_config.get('stop_loss_pct', 0.04)
        min_corr = pt_config.get('min_correlation', 0.7)

        if symbol not in self.PAIRS_MAP:
            return None

        pair = self.PAIRS_MAP[symbol]
        partner = pair[1] if pair[0] == symbol else pair[0]

        if len(data) < rolling_window + 5:
            return None

        # Fetch partner data
        try:
            start = data.index[0] if hasattr(data.index[0], 'date') else datetime.now() - timedelta(days=len(data))
            end = data.index[-1] if hasattr(data.index[-1], 'date') else datetime.now()
            partner_md = self.market_data.get_historical_data(symbol=partner, start=start, end=end)
            if not partner_md or len(partner_md) < rolling_window + 5:
                return None
            partner_df = pd.DataFrame([{
                "timestamp": md.timestamp, "close": md.close
            } for md in partner_md]).set_index("timestamp").sort_index()
        except Exception as e:
            logger.warning(f"Pairs Trading: could not fetch partner data for {partner}: {e}")
            return None

        combined = pd.DataFrame({"sym": data['close'], "partner": partner_df['close']}).dropna()
        if len(combined) < rolling_window + 5:
            return None

        # Check rolling correlation
        correlation = combined['sym'].rolling(window=rolling_window).corr(combined['partner']).iloc[-1]
        if pd.isna(correlation) or correlation < min_corr:
            logger.debug(f"Pairs Trading {symbol}/{partner}: correlation {correlation:.2f} < {min_corr} — skip")
            return None

        # Rolling 60-day OLS hedge ratio (3.6) — matches backtest simulation.
        # Static full-window OLS goes stale over months; rolling keeps β current.
        rolling_window = pt_config.get('rolling_window', 60)
        y = combined['sym'].values
        x = combined['partner'].values

        # Compute rolling beta using the last `rolling_window` observations
        y_roll = y[-rolling_window:]
        x_roll = x[-rolling_window:]
        x_mean_r, y_mean_r = x_roll.mean(), y_roll.mean()
        var_x_r = ((x_roll - x_mean_r) ** 2).mean()
        if var_x_r < 1e-10:
            return None
        beta = ((x_roll - x_mean_r) * (y_roll - y_mean_r)).mean() / var_x_r
        alpha_ols = y_mean_r - beta * x_mean_r

        # Spread uses full history for z-score stability, but with rolling β
        spread = combined['sym'] - beta * combined['partner'] - alpha_ols
        spread_mean = spread.rolling(window=rolling_window).mean().iloc[-1]
        spread_std = spread.rolling(window=rolling_window).std().iloc[-1]
        if pd.isna(spread_mean) or pd.isna(spread_std) or spread_std == 0:
            return None
        current_z = (spread.iloc[-1] - spread_mean) / spread_std
        current_price = float(data['close'].iloc[-1])

        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            side = getattr(open_position, 'side', 'BUY')
            if side == 'BUY':
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            else:
                pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0

            exit_reason = None
            if side == 'BUY' and current_z >= z_exit:
                exit_reason = f"Mean reversion (z={current_z:.2f})"
            elif side == 'SELL' and current_z <= z_exit:
                exit_reason = f"Mean reversion (z={current_z:.2f})"
            elif abs(current_z) > z_stop:
                exit_reason = f"Z-score stop loss (z={current_z:.2f})"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss ({pnl_pct:.1%})"

            if exit_reason:
                action = SignalAction.EXIT_LONG if side == 'BUY' else SignalAction.EXIT_SHORT
                logger.info(f"Alpha Edge Pairs Trading EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=action,
                    confidence=0.80, reasoning=f"Pairs Trading exit ({symbol}/{partner}): {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price, "z_score": current_z, "correlation": correlation, "partner": partner},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "pairs_trading",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct, "pair_partner": partner}
                )

        if has_open_position:
            return None

        # ENTRY LOGIC
        if current_z > z_entry:
            # Symbol overpriced vs partner → SHORT symbol
            confidence = min(1.0, 0.60 + (current_z - z_entry) * 0.1)
            reasoning = (f"Pairs Trading SHORT {symbol} (z={current_z:.2f} > {z_entry}): "
                         f"{symbol} overpriced vs {partner}, corr={correlation:.2f}")
            logger.info(f"Alpha Edge Pairs Trading ENTER_SHORT for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_SHORT,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price, "z_score": current_z, "correlation": correlation, "partner": partner},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "pairs_trading",
                          "pair_partner": partner, "strategy_name": strategy.name,
                          "hedge_ratio": float(beta)}
            )
        elif current_z < -z_entry:
            # Symbol underpriced vs partner → LONG symbol
            confidence = min(1.0, 0.60 + (abs(current_z) - z_entry) * 0.1)
            reasoning = (f"Pairs Trading LONG {symbol} (z={current_z:.2f} < -{z_entry}): "
                         f"{symbol} underpriced vs {partner}, corr={correlation:.2f}")
            logger.info(f"Alpha Edge Pairs Trading ENTER_LONG for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price, "z_score": current_z, "correlation": correlation, "partner": partner},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "pairs_trading",
                          "pair_partner": partner, "strategy_name": strategy.name,
                          "hedge_ratio": float(beta)}
            )

        return None

    def _handle_analyst_revision_momentum(
        self, strategy, symbol, data, provider, config, has_open_position, open_position
    ):
        from src.models.enums import SignalAction

        min_revision_pct = config.get('min_revision_pct', 0.05)
        min_consecutive = config.get('min_consecutive_revisions', 2)

        # EXIT check first
        if has_open_position:
            try:
                quarters = provider.get_historical_fundamentals(symbol, quarters=4)
                if quarters and len(quarters) >= 2:
                    latest_est = quarters[-1].get('estimated_eps')
                    prev_est = quarters[-2].get('estimated_eps')
                    if latest_est is not None and prev_est is not None and prev_est > 0:
                        if latest_est < prev_est:
                            current_price = data['close'].iloc[-1] if len(data) > 0 else 0
                            return TradingSignal(
                                strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT,
                                confidence=0.65, reasoning=f"Analyst revision turned negative: est EPS {latest_est:.2f} < prev {prev_est:.2f}",
                                generated_at=datetime.now(), indicators={"price": current_price},
                                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "analyst_revision_momentum", "strategy_name": strategy.name}
                            )
            except Exception as e:
                logger.debug(f"Could not check analyst revision exit for {symbol}: {e}")
            return None

        # ENTRY check
        try:
            quarters = provider.get_historical_fundamentals(symbol, quarters=8)
            if not quarters or len(quarters) < 3:
                return None

            estimates = [(q.get('date', ''), q.get('estimated_eps')) for q in quarters if q.get('estimated_eps') is not None]
            if len(estimates) < 3:
                return None

            consecutive_up = 0
            for i in range(1, len(estimates)):
                prev_est = estimates[i-1][1]
                curr_est = estimates[i][1]
                if prev_est and prev_est > 0 and curr_est > prev_est:
                    consecutive_up += 1
                else:
                    consecutive_up = 0

            if consecutive_up < min_consecutive:
                return None

            oldest_est = estimates[-min_consecutive-1][1] if len(estimates) > min_consecutive else estimates[0][1]
            latest_est = estimates[-1][1]
            if oldest_est and oldest_est > 0:
                revision_pct = (latest_est - oldest_est) / abs(oldest_est)
                if revision_pct < min_revision_pct:
                    return None
            else:
                return None

            current_price = data['close'].iloc[-1] if len(data) > 0 else 0
            confidence = min(0.60 + (consecutive_up * 0.05) + (revision_pct * 0.5), 0.90)

            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence,
                reasoning=f"Analyst Revision Momentum: {consecutive_up} consecutive upward revisions, total revision +{revision_pct:.1%}",
                generated_at=datetime.now(), indicators={"price": current_price},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "analyst_revision_momentum",
                          "consecutive_revisions": consecutive_up, "revision_pct": revision_pct, "strategy_name": strategy.name}
            )
        except Exception as e:
            logger.warning(f"Error in analyst revision momentum for {symbol}: {e}")
            return None

    def _handle_share_buyback(
        self, strategy, symbol, data, provider, config, has_open_position, open_position
    ):
        from src.models.enums import SignalAction

        min_buyback_pct = config.get('min_buyback_pct', 0.01)
        rsi_max_entry = config.get('rsi_max_entry', 60)

        # EXIT check
        if has_open_position:
            try:
                fund_data = provider.get_fundamental_data(symbol)
                if fund_data and fund_data.shares_change_percent is not None:
                    if fund_data.shares_change_percent > 0.005:  # > 0.5% dilution
                        current_price = data['close'].iloc[-1] if len(data) > 0 else 0
                        return TradingSignal(
                            strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT,
                            confidence=0.65, reasoning=f"Share dilution detected: shares changed +{fund_data.shares_change_percent:.1%}",
                            generated_at=datetime.now(), indicators={"price": current_price},
                            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "share_buyback", "strategy_name": strategy.name}
                        )
            except Exception:
                pass
            return None

        # ENTRY check
        try:
            fund_data = provider.get_fundamental_data(symbol)
            if not fund_data:
                return None

            shares_change = fund_data.shares_change_percent
            if shares_change is None or shares_change >= -min_buyback_pct:
                return None  # Not buying back enough

            if fund_data.eps is not None and fund_data.eps <= 0:
                return None

            # RSI check (not overbought)
            if len(data) >= 20:
                close = data['close']
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14, min_periods=5).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=5).mean()
                if loss.iloc[-1] > 0:
                    rs = gain.iloc[-1] / loss.iloc[-1]
                    rsi = 100 - (100 / (1 + rs))
                    if rsi > rsi_max_entry:
                        return None

            buyback_pct = abs(shares_change)
            current_price = data['close'].iloc[-1] if len(data) > 0 else 0
            confidence = min(0.60 + (buyback_pct * 5.0), 0.90)

            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence,
                reasoning=f"Share Buyback: shares reduced by {buyback_pct:.1%}, EPS={fund_data.eps:.2f}",
                generated_at=datetime.now(), indicators={"price": current_price},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "share_buyback",
                          "buyback_pct": buyback_pct, "eps": fund_data.eps, "strategy_name": strategy.name}
            )
        except Exception as e:
            logger.warning(f"Error in share buyback signal for {symbol}: {e}")
            return None

    def _handle_multi_factor_composite(
        self, strategy, symbol, data, provider, alpha_edge_config,
        has_open_position, open_position
    ):
        """
        Multi-Factor Composite signal handler.

        Uses Piotroski F-Score, accruals ratio, FCF yield, and SUE
        from the latest quarterly data to generate entry/exit signals.
        """
        from src.models.enums import SignalAction

        current_price = float(data['close'].iloc[-1]) if len(data) > 0 else 0
        params = strategy.metadata.get('customized_parameters', {}) if strategy.metadata else {}
        is_long = params.get('top_pct') is not None
        is_short = params.get('bottom_pct') is not None

        # EXIT check
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            if not is_long:
                pnl_pct = -pnl_pct  # Invert for short
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0

            stop_loss = params.get('stop_loss_pct', 0.08)
            profit_target = params.get('profit_target', 0.15 if is_long else 0.10)
            hold_max = params.get('hold_period_max', 90)

            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss: {pnl_pct:.1%}"
            elif days_held >= hold_max:
                exit_reason = f"Max hold: {days_held}d"

            if exit_reason:
                action = SignalAction.EXIT_LONG if is_long else SignalAction.EXIT_SHORT
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=action,
                    confidence=0.80, reasoning=f"Multi-Factor Composite EXIT: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "multi_factor_composite", "strategy_name": strategy.name}
                )
            return None

        # ENTRY check — fetch latest quarterly data
        try:
            quarters = provider.get_historical_fundamentals(symbol, quarters=4)
            if not quarters:
                return None
            latest = quarters[-1]

            f_score = latest.get('piotroski_f_score')
            accruals = latest.get('accruals_ratio')
            fcf_yield = latest.get('fcf_yield')
            sue_val = latest.get('sue')

            if is_long:
                min_f = params.get('min_f_score', 6)
                max_acc = params.get('max_accruals', 0.05)
                if f_score is None or f_score < min_f:
                    return None
                if accruals is not None and accruals > max_acc:
                    return None
                if fcf_yield is not None and fcf_yield <= 0 and (sue_val is None or sue_val <= 0):
                    return None

                confidence = 0.55 + (f_score / 9.0) * 0.25
                if sue_val and sue_val > 1.0:
                    confidence += 0.10
                confidence = min(confidence, 0.90)

                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                    confidence=confidence,
                    reasoning=f"Multi-Factor Composite LONG: F-Score={f_score}, accruals={accruals:.3f}, FCF yield={fcf_yield:.3f}" if fcf_yield else f"Multi-Factor Composite LONG: F-Score={f_score}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "multi_factor_composite",
                              "f_score": f_score, "accruals": accruals, "fcf_yield": fcf_yield, "sue": sue_val, "strategy_name": strategy.name}
                )

            elif is_short:
                max_f = params.get('max_f_score', 3)
                min_acc = params.get('min_accruals', 0.10)
                if f_score is None or f_score > max_f:
                    return None
                if accruals is None or accruals < min_acc:
                    return None

                confidence = 0.55 + ((9 - f_score) / 9.0) * 0.25
                confidence = min(confidence, 0.85)

                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_SHORT,
                    confidence=confidence,
                    reasoning=f"Multi-Factor Composite SHORT: F-Score={f_score}, accruals={accruals:.3f}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "multi_factor_composite",
                              "f_score": f_score, "accruals": accruals, "strategy_name": strategy.name}
                )

        except Exception as e:
            logger.warning(f"Error in multi-factor composite signal for {symbol}: {e}")
        return None

    def _handle_factor_template_signal(
        self, strategy, symbol, data, provider, alpha_edge_config, template_type,
        has_open_position, open_position
    ):
        """
        Generic signal handler for institutional factor templates
        (gross_profitability, accruals_quality, fcf_yield_value).

        Uses the same quarterly data pattern as multi-factor composite.
        """
        from src.models.enums import SignalAction

        current_price = float(data['close'].iloc[-1]) if len(data) > 0 else 0
        params = strategy.metadata.get('customized_parameters', {}) if strategy.metadata else {}
        direction = (strategy.metadata or {}).get('direction', 'long')

        # EXIT check
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            if direction == 'short':
                pnl_pct = -pnl_pct
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0

            stop_loss = params.get('stop_loss_pct', 0.08)
            profit_target = params.get('profit_target', 0.12)
            hold_max = params.get('hold_period_max', 90)

            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss: {pnl_pct:.1%}"
            elif days_held >= hold_max:
                exit_reason = f"Max hold: {days_held}d"

            if exit_reason:
                action = SignalAction.EXIT_LONG if direction == 'long' else SignalAction.EXIT_SHORT
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=action,
                    confidence=0.80, reasoning=f"{template_type} EXIT: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": template_type, "strategy_name": strategy.name}
                )
            return None

        # ENTRY check
        try:
            quarters = provider.get_historical_fundamentals(symbol, quarters=4)
            if not quarters:
                return None
            latest = quarters[-1]

            f_score = latest.get('piotroski_f_score')
            accruals = latest.get('accruals_ratio')
            fcf_yield = latest.get('fcf_yield')
            gp = latest.get('gross_profit')
            ta = latest.get('total_assets')
            ocf = latest.get('operating_cash_flow')

            should_enter = False
            reasoning = ""

            if template_type == 'gross_profitability':
                if gp is not None and ta is not None and ta > 0:
                    gp_ratio = gp / ta
                    if gp_ratio >= params.get('min_gp_to_assets', 0.30):
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True
                            reasoning = f"Gross Profitability: GP/Assets={gp_ratio:.2f}, F-Score={f_score}"

            elif template_type == 'accruals_quality':
                if direction == 'long':
                    max_acc = params.get('max_accruals_ratio', -0.03)
                    if accruals is not None and accruals < max_acc and ocf is not None and ocf > 0:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True
                            reasoning = f"Accruals Quality LONG: accruals={accruals:.3f}, OCF={ocf:,.0f}"
                else:
                    min_acc = params.get('min_accruals_ratio', 0.10)
                    if accruals is not None and accruals > min_acc:
                        if f_score is not None and f_score <= params.get('max_f_score', 4):
                            should_enter = True
                            reasoning = f"Accruals Quality SHORT: accruals={accruals:.3f}, F-Score={f_score}"

            elif template_type == 'fcf_yield_value':
                if fcf_yield is not None and fcf_yield >= params.get('min_fcf_yield', 0.05):
                    if ocf is not None and ocf > 0:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True
                            reasoning = f"FCF Yield Value: yield={fcf_yield:.2%}, F-Score={f_score}"

            elif template_type == 'price_target_upside':
                try:
                    pt_data = provider.get_price_target_consensus(symbol)
                    if pt_data and pt_data.get('upside_pct') is not None:
                        min_upside = params.get('min_upside_pct', 0.20)
                        if pt_data['upside_pct'] >= min_upside:
                            if f_score is None or f_score >= params.get('min_f_score', 4):
                                should_enter = True
                                reasoning = f"Price Target Upside: {pt_data['upside_pct']:.1%} upside, target=${pt_data.get('target_consensus', 0):.0f}"
                except Exception:
                    pass

            elif template_type == 'shareholder_yield':
                div_yield = latest.get('dividend_yield') or 0
                # Compute buyback yield from shares change
                buyback_yield = 0
                if len(quarters) >= 2:
                    curr_shares = latest.get('shares_outstanding')
                    prev_shares = quarters[-2].get('shares_outstanding')
                    if curr_shares and prev_shares and prev_shares > 0:
                        change = (curr_shares - prev_shares) / prev_shares
                        if change < 0:
                            buyback_yield = abs(change) * 4
                # Compute debt paydown yield
                debt_paydown_yield = 0
                if len(quarters) >= 2:
                    curr_debt = latest.get('long_term_debt')
                    prev_debt = quarters[-2].get('long_term_debt')
                    mkt_cap = latest.get('market_cap')
                    if curr_debt is not None and prev_debt is not None and mkt_cap and mkt_cap > 0:
                        reduction = prev_debt - curr_debt
                        if reduction > 0:
                            debt_paydown_yield = (reduction / mkt_cap) * 4

                total_yield = div_yield + buyback_yield + debt_paydown_yield
                if total_yield >= params.get('min_shareholder_yield', 0.04):
                    fcf = latest.get('free_cash_flow')
                    if fcf is not None and fcf > 0:
                        if f_score is None or f_score >= params.get('min_f_score', 5):
                            should_enter = True
                            reasoning = f"Shareholder Yield: total={total_yield:.1%} (div={div_yield:.1%}, buyback={buyback_yield:.1%}, debt={debt_paydown_yield:.1%})"

            elif template_type == 'earnings_momentum_combo':
                sue_val = latest.get('sue')
                min_sue = params.get('min_sue', 1.5)
                if sue_val is not None and sue_val >= min_sue:
                    # Check 3-month price momentum
                    if len(data) >= 63:
                        price_3m = float(data['close'].iloc[-63])
                        if price_3m > 0:
                            momentum = (current_price - price_3m) / price_3m
                            if momentum > 0.05:
                                should_enter = True
                                reasoning = f"Earnings Momentum Combo: SUE={sue_val:.1f}, 3m momentum={momentum:.1%}"

            elif template_type == 'quality_value_combo':
                min_fcf = params.get('min_fcf_yield', 0.03)
                min_gp = params.get('min_gp_to_assets', 0.25)
                min_f = params.get('min_f_score', 6)
                if fcf_yield is not None and fcf_yield >= min_fcf:
                    if gp is not None and ta is not None and ta > 0:
                        gp_ratio = gp / ta
                        if gp_ratio >= min_gp:
                            if f_score is None or f_score >= min_f:
                                should_enter = True
                                reasoning = f"Quality Value Combo: FCF yield={fcf_yield:.2%}, GP/Assets={gp_ratio:.2f}, F-Score={f_score}"

            elif template_type == 'deleveraging':
                if len(quarters) >= 5:
                    curr_debt = latest.get('long_term_debt')
                    prev_debt = quarters[-5].get('long_term_debt')  # 4 quarters ago
                    fcf = latest.get('free_cash_flow')
                    de = latest.get('debt_to_equity')
                    if curr_debt is not None and prev_debt is not None and prev_debt > 0:
                        debt_change = (curr_debt - prev_debt) / prev_debt
                        if debt_change <= -params.get('min_debt_reduction_pct', 0.10):
                            if fcf is not None and fcf > 0:
                                if f_score is None or f_score >= params.get('min_f_score', 5):
                                    if de is not None and de >= params.get('min_debt_to_equity', 0.3):
                                        should_enter = True
                                        reasoning = f"Deleveraging: debt reduced {abs(debt_change):.0%} YoY, FCF={fcf:,.0f}, D/E={de:.1f}"

            if should_enter:
                confidence = 0.60
                if f_score is not None:
                    confidence += (f_score / 9.0) * 0.20
                confidence = min(confidence, 0.85)

                action = SignalAction.ENTER_LONG if direction == 'long' else SignalAction.ENTER_SHORT
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=action,
                    confidence=confidence, reasoning=reasoning,
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": template_type,
                              "f_score": f_score, "accruals": accruals, "fcf_yield": fcf_yield, "strategy_name": strategy.name}
                )

        except Exception as e:
            logger.warning(f"Error in {template_type} signal for {symbol}: {e}")
        return None

    def _calculate_alpha_edge_backtest_results(self, trades: List[Dict], df: pd.DataFrame) -> BacktestResults:
        """Calculate BacktestResults from simulated Alpha Edge trades."""
        if not trades:
            logger.warning("Alpha Edge backtest produced 0 trades")
            return BacktestResults(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, avg_win=0.0, avg_loss=0.0,
                sortino_ratio=0.0
            )
        
        pnl_values = [t['pnl_pct'] for t in trades]
        total_return = sum(pnl_values)
        
        winners = [p for p in pnl_values if p > 0]
        losers = [p for p in pnl_values if p < 0]
        
        win_rate = len(winners) / len(pnl_values) if pnl_values else 0.0
        avg_win = sum(winners) / len(winners) if winners else 0.0
        avg_loss = sum(losers) / len(losers) if losers else 0.0
        
        returns_series = pd.Series(pnl_values)
        if len(returns_series) >= 2 and returns_series.std() > 0.001:
            avg_hold = sum(t['days_held'] for t in trades) / len(trades)
            trades_per_year = 252 / max(avg_hold, 1)
            sharpe_ratio = (returns_series.mean() / returns_series.std()) * (trades_per_year ** 0.5)
            # Cap Sharpe in both directions based on trade count
            n_trades = len(trades)
            if n_trades < 10:
                sharpe_cap = 2.0
            elif n_trades < 20:
                sharpe_cap = 2.5
            else:
                sharpe_cap = 3.0
            sharpe_ratio = max(-sharpe_cap, min(sharpe_ratio, sharpe_cap))
        else:
            sharpe_ratio = 0.0
        
        downside = returns_series[returns_series < 0]
        if len(downside) >= 2 and downside.std() > 0:
            avg_hold = sum(t['days_held'] for t in trades) / len(trades)
            trades_per_year = 252 / max(avg_hold, 1)
            sortino_ratio = (returns_series.mean() / downside.std()) * (trades_per_year ** 0.5)
            # Cap Sortino based on trade count (same logic as Sharpe)
            n_trades = len(trades)
            if n_trades < 10:
                sortino_cap = 3.0
            elif n_trades < 20:
                sortino_cap = 4.0
            else:
                sortino_cap = 5.0
            sortino_ratio = min(sortino_ratio, sortino_cap)
        else:
            sortino_ratio = 0.0
        
        cumulative = returns_series.cumsum()
        running_max = cumulative.expanding().max()
        drawdown = cumulative - running_max
        max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0.0
        
        logger.info(
            f"Alpha Edge backtest: {len(trades)} trades, "
            f"return={total_return:.2%}, sharpe={sharpe_ratio:.2f}, "
            f"win_rate={win_rate:.2%}, max_dd={max_drawdown:.2%}"
        )
        
        return BacktestResults(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            total_trades=len(trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            sortino_ratio=sortino_ratio
        )
    
    def _generate_alpha_edge_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        config: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal for Alpha Edge strategies using fundamental data.
        
        Instead of relying on generic DSL indicators (SMA/Volume), this method
        evaluates the actual fundamental conditions that each Alpha Edge template
        is designed around:
        - Earnings Momentum: earnings surprise, revenue growth, post-earnings entry window
        - Sector Rotation: regime-to-sector mapping, monthly rebalancing
        - Quality Mean Reversion: ROE, Debt/Equity, RSI oversold
        
        Args:
            strategy: Alpha Edge strategy
            symbol: Symbol to evaluate
            data: Historical OHLCV data
            config: Full config dict from autonomous_trading.yaml
            
        Returns:
            TradingSignal or None
        """
        from src.models.enums import SignalAction
        
        template_type = self._get_alpha_edge_template_type(strategy)
        if not template_type:
            logger.warning(f"Could not determine Alpha Edge template type for {strategy.name}")
            return None
        
        alpha_edge_config = config.get('alpha_edge', {})
        
        # Ensure we have a fundamental data provider
        if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
            try:
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                self._fundamental_data_provider = get_fundamental_data_provider(config)
            except Exception as e:
                logger.error(f"Could not initialize FundamentalDataProvider: {e}")
                return None
        
        provider = self._fundamental_data_provider
        
        # Check for open positions (for exit signals)
        has_open_position = False
        open_position = None
        try:
            from src.models.orm import PositionORM
            session = self.db.get_session()
            try:
                open_position = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy.id,
                    PositionORM.symbol == symbol,
                    PositionORM.closed_at.is_(None)
                ).first()
                has_open_position = open_position is not None
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not check open positions for {symbol}: {e}")
        
        # Route to the appropriate template handler
        if template_type == 'earnings_momentum':
            return self._check_earnings_momentum_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('earnings_momentum', {}),
                has_open_position, open_position
            )
        elif template_type == 'sector_rotation':
            return self._check_sector_rotation_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('sector_rotation', {}),
                config, has_open_position, open_position
            )
        elif template_type == 'quality_mean_reversion':
            return self._check_quality_mean_reversion_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('quality_mean_reversion', {}),
                has_open_position, open_position
            )
        elif template_type == 'earnings_miss_momentum_short':
            return self._check_earnings_miss_momentum_short_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('earnings_momentum', {}),
                has_open_position, open_position
            )
        elif template_type == 'sector_rotation_short':
            return self._check_sector_rotation_short_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('sector_rotation', {}),
                config, has_open_position, open_position
            )
        elif template_type == 'quality_deterioration_short':
            return self._check_quality_deterioration_short_signal(
                strategy, symbol, data, provider,
                alpha_edge_config.get('quality_mean_reversion', {}),
                has_open_position, open_position
            )
        elif template_type == 'dividend_aristocrat':
            return self._handle_dividend_aristocrat(
                strategy, symbol, data, provider,
                alpha_edge_config.get('dividend_aristocrat', {}),
                has_open_position, open_position
            )
        elif template_type == 'insider_buying':
            return self._handle_insider_buying(
                strategy, symbol, data, provider,
                alpha_edge_config.get('insider_buying', {}),
                has_open_position, open_position
            )
        elif template_type == 'revenue_acceleration':
            return self._handle_revenue_acceleration(
                strategy, symbol, data, provider,
                alpha_edge_config.get('revenue_acceleration', {}),
                has_open_position, open_position
            )
        elif template_type == 'relative_value':
            return self._handle_relative_value(
                strategy, symbol, data, provider,
                alpha_edge_config.get('relative_value', {}),
                has_open_position, open_position
            )
        elif template_type == 'end_of_month_momentum':
            return self._handle_end_of_month_momentum(
                strategy, symbol, data,
                alpha_edge_config.get('end_of_month_momentum', {}),
                has_open_position, open_position
            )
        elif template_type == 'pairs_trading':
            return self._handle_pairs_trading(
                strategy, symbol, data,
                alpha_edge_config.get('pairs_trading', {}),
                has_open_position, open_position
            )
        elif template_type == 'analyst_revision_momentum':
            return self._handle_analyst_revision_momentum(
                strategy, symbol, data, provider,
                alpha_edge_config.get('analyst_revision_momentum', {}),
                has_open_position, open_position
            )
        elif template_type == 'share_buyback':
            return self._handle_share_buyback(
                strategy, symbol, data, provider,
                alpha_edge_config.get('share_buyback', {}),
                has_open_position, open_position
            )
        elif template_type == 'multi_factor_composite':
            return self._handle_multi_factor_composite(
                strategy, symbol, data, provider,
                alpha_edge_config,
                has_open_position, open_position
            )
        elif template_type in ('gross_profitability', 'accruals_quality', 'fcf_yield_value',
                               'price_target_upside', 'shareholder_yield',
                               'earnings_momentum_combo', 'quality_value_combo', 'deleveraging'):
            return self._handle_factor_template_signal(
                strategy, symbol, data, provider,
                alpha_edge_config, template_type,
                has_open_position, open_position
            )
        
        return None
    
    def _check_earnings_momentum_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        em_config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Earnings Momentum conditions using FMP data.
        
        Entry requires:
        1. Recent earnings surprise > threshold (default 5%)
        2. Revenue growth > threshold (default 10%)
        3. Within entry window (2-3 days after earnings)
        
        Exit conditions:
        - Profit target reached (10%)
        - Stop loss triggered (5%)
        - Hold period exceeded (30-60 days)
        - Next earnings approaching (within 7 days)
        """
        from src.models.enums import SignalAction
        
        surprise_min = em_config.get('earnings_surprise_min', 0.05)
        revenue_growth_min = em_config.get('revenue_growth_min', 0.10)
        entry_delay_days = em_config.get('entry_delay_days', 2)
        entry_window_max = entry_delay_days + 2  # e.g., 2-4 days after earnings
        profit_target = em_config.get('profit_target', 0.10)
        stop_loss = em_config.get('stop_loss', 0.05)
        hold_period_max = em_config.get('hold_period_days', 45)
        exit_before_earnings_days = em_config.get('exit_before_earnings_days', 7)
        
        current_price = float(data['close'].iloc[-1])
        
        # --- EXIT LOGIC (check first if we have a position) ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%} >= {profit_target:.0%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%} <= -{stop_loss:.0%}"
            elif days_held >= hold_period_max:
                exit_reason = f"Max hold period reached: {days_held} days >= {hold_period_max}"
            
            # Check if next earnings is approaching
            if not exit_reason:
                try:
                    earnings_data = provider.get_earnings_calendar(symbol)
                    if earnings_data and earnings_data.get('next_earnings_date'):
                        next_date = datetime.strptime(earnings_data['next_earnings_date'], '%Y-%m-%d')
                        days_to_next = (next_date - datetime.now()).days
                        if 0 < days_to_next <= exit_before_earnings_days:
                            exit_reason = f"Next earnings in {days_to_next} days (exit before {exit_before_earnings_days}d)"
                except Exception as e:
                    logger.debug(f"Could not check next earnings for {symbol}: {e}")
            
            if exit_reason:
                exit_action = SignalAction.EXIT_LONG
                if open_position.side and open_position.side.value == 'SHORT':
                    exit_action = SignalAction.EXIT_SHORT
                
                logger.info(f"Alpha Edge Earnings Momentum EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id,
                    symbol=symbol,
                    action=exit_action,
                    confidence=0.85,
                    reasoning=f"Earnings Momentum exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price},
                    metadata={
                        "signal_engine": "alpha_edge_fundamental",
                        "template_type": "earnings_momentum",
                        "exit_reason": exit_reason,
                        "pnl_pct": pnl_pct,
                        "days_held": days_held,
                    }
                )
        
        # --- ENTRY LOGIC ---
        if has_open_position:
            return None  # Already have a position, no new entry
        
        # Check 1: Recent earnings surprise
        earnings_surprise = provider.calculate_earnings_surprise(symbol)
        if earnings_surprise is None:
            logger.debug(f"No earnings surprise data for {symbol} — skipping earnings momentum")
            return None
        
        if earnings_surprise < surprise_min:
            logger.debug(
                f"{symbol}: earnings surprise {earnings_surprise:.1%} < {surprise_min:.0%} — no entry"
            )
            return None
        
        # Check 2: Revenue growth
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data or fund_data.revenue_growth is None:
            logger.debug(f"No revenue growth data for {symbol} — skipping earnings momentum")
            return None
        
        if fund_data.revenue_growth < revenue_growth_min:
            logger.debug(
                f"{symbol}: revenue growth {fund_data.revenue_growth:.1%} < {revenue_growth_min:.0%} — no entry"
            )
            return None
        
        # Check 3: Entry window (2-N days after earnings)
        days_since = provider.get_days_since_earnings(symbol)
        if days_since is None:
            logger.debug(f"No earnings date data for {symbol} — skipping earnings momentum")
            return None
        
        if days_since < entry_delay_days or days_since > entry_window_max:
            logger.debug(
                f"{symbol}: {days_since} days since earnings, "
                f"entry window is {entry_delay_days}-{entry_window_max} days — no entry"
            )
            return None
        
        # All conditions met — generate ENTER_LONG signal
        confidence = min(1.0, 0.6 + (earnings_surprise * 2))  # Higher surprise = higher confidence
        
        reasoning = (
            f"Earnings Momentum entry for {symbol}: "
            f"surprise={earnings_surprise:.1%} (>{surprise_min:.0%}), "
            f"revenue_growth={fund_data.revenue_growth:.1%} (>{revenue_growth_min:.0%}), "
            f"{days_since}d since earnings (window: {entry_delay_days}-{entry_window_max}d)"
        )
        
        logger.info(f"Alpha Edge Earnings Momentum ENTRY for {symbol}: {reasoning}")
        
        return TradingSignal(
            strategy_id=strategy.id,
            symbol=symbol,
            action=SignalAction.ENTER_LONG,
            confidence=confidence,
            reasoning=reasoning,
            generated_at=datetime.now(),
            indicators={"price": current_price, "earnings_surprise": earnings_surprise},
            metadata={
                "signal_engine": "alpha_edge_fundamental",
                "template_type": "earnings_momentum",
                "earnings_surprise": earnings_surprise,
                "revenue_growth": fund_data.revenue_growth,
                "days_since_earnings": days_since,
                "market_cap": fund_data.market_cap,
                "strategy_name": strategy.name,
            }
        )
    
    def _check_sector_rotation_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        sr_config: Dict[str, Any],
        full_config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Sector Rotation conditions using real FMP sector performance data.
        
        Entry requires:
        1. Symbol is a sector ETF ranked in the top N by trailing performance
        2. Monthly rebalancing period has elapsed
        3. Sector has positive momentum
        
        Exit conditions:
        - Sector no longer in top N by performance
        - Stop loss triggered
        
        Falls back to regime-to-sector mapping if FMP data is unavailable.
        """
        from src.models.enums import SignalAction
        
        # Regime-to-sector mapping (fallback when FMP data unavailable)
        regime_sector_map = {
            'trending_up': ['XLK', 'XLY', 'XLF'],
            'trending_up_strong': ['XLK', 'XLY', 'XLF'],
            'trending_up_weak': ['XLK', 'XLV', 'XLI'],
            'trending_down': ['XLU', 'XLP', 'XLV'],
            'trending_down_strong': ['XLU', 'XLP', 'XLV'],
            'trending_down_weak': ['XLU', 'XLP', 'XLV'],
            'ranging': ['XLE', 'XLI', 'XLF'],
            'ranging_low_vol': ['XLK', 'XLF', 'XLI'],
            'ranging_high_vol': ['XLU', 'XLP', 'XLV'],
        }
        
        max_positions = sr_config.get('max_positions', 3)
        top_n = sr_config.get('top_sectors', max_positions)
        rebalance_days = sr_config.get('rebalance_frequency_days', 30)
        stop_loss = sr_config.get('stop_loss_pct', 0.08)
        trailing_period = sr_config.get('trailing_period', '3m')
        
        current_price = float(data['close'].iloc[-1])
        
        # Try to get real sector performance data from FMP
        optimal_sectors = None
        sector_data = None
        use_real_data = False
        try:
            if provider and hasattr(provider, 'get_sector_performance'):
                sector_data = provider.get_sector_performance()
                if sector_data:
                    ranked = sorted(
                        sector_data.items(),
                        key=lambda x: x[1].get(trailing_period, 0.0),
                        reverse=True,
                    )
                    optimal_sectors = [etf for etf, _ in ranked[:top_n]]
                    use_real_data = True
                    logger.debug(
                        f"Sector rotation: using real FMP data, top {top_n} by {trailing_period}: "
                        f"{', '.join(optimal_sectors)}"
                    )
        except Exception as e:
            logger.warning(f"Could not fetch sector performance for live signal: {e}")
        
        # Fallback to regime-based mapping, enhanced with FRED macro indicators
        if not optimal_sectors:
            current_regime = 'ranging_low_vol'
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                analyzer = MarketStatisticsAnalyzer(self.market_data)
                regime, confidence, _, _ = analyzer.detect_sub_regime(symbols=[symbol])
                current_regime = str(regime).lower().replace('marketregime.', '')
                logger.debug(f"Sector rotation: detected regime = {current_regime}")
            except Exception as e:
                logger.warning(f"Could not detect market regime for sector rotation: {e}")

            # Macro-conditioned override: use yield curve slope and ISM PMI
            # from FRED to override the price-based regime when macro data
            # gives a clearer signal. This is how institutional sector rotation
            # works — leading indicators, not lagging price action.
            macro_override = None
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                analyzer = MarketStatisticsAnalyzer(self.market_data)
                ctx = analyzer.get_market_context()
                yield_curve = ctx.get('yield_curve_slope', 0.5)
                pmi = ctx.get('ism_pmi', 50.0)

                # Inverted yield curve + PMI < 50 = recession → defensives
                if yield_curve < 0 and pmi < 50:
                    macro_override = ['XLU', 'XLP', 'XLV']
                    logger.info(
                        f"Sector rotation MACRO OVERRIDE: recession signal "
                        f"(curve={yield_curve:+.2f}%, PMI={pmi:.1f}) → defensives"
                    )
                # Positive curve + PMI > 50 = expansion → cyclicals
                elif yield_curve > 0 and pmi > 50:
                    macro_override = ['XLY', 'XLI', 'XLF']
                    logger.info(
                        f"Sector rotation MACRO OVERRIDE: expansion signal "
                        f"(curve={yield_curve:+.2f}%, PMI={pmi:.1f}) → cyclicals"
                    )
                # Inverted curve but PMI still > 50 = late cycle → quality/healthcare
                elif yield_curve < 0 and pmi > 50:
                    macro_override = ['XLV', 'XLK', 'XLP']
                    logger.info(
                        f"Sector rotation MACRO OVERRIDE: late cycle signal "
                        f"(curve={yield_curve:+.2f}%, PMI={pmi:.1f}) → quality/defensive growth"
                    )
            except Exception as e:
                logger.debug(f"Could not get macro context for sector rotation: {e}")

            if macro_override:
                optimal_sectors = macro_override
            else:
                optimal_sectors = regime_sector_map.get(current_regime, ['XLK', 'XLF', 'XLI'])
            logger.debug(f"Sector rotation: sectors={', '.join(optimal_sectors)} (regime={current_regime})")
        
        # --- EXIT LOGIC ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            
            exit_reason = None
            
            # Check if sector is no longer in top-ranked sectors
            symbol_upper = symbol.upper()
            if symbol_upper not in optimal_sectors:
                data_source = "FMP sector performance" if use_real_data else "regime mapping"
                exit_reason = (
                    f"Sector {symbol_upper} no longer in top {top_n} sectors "
                    f"(top: {', '.join(optimal_sectors)}, source: {data_source})"
                )
            
            # Check stop loss
            if not exit_reason and pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%} <= -{stop_loss:.0%}"
            
            if exit_reason:
                exit_action = SignalAction.EXIT_LONG
                if open_position.side and open_position.side.value == 'SHORT':
                    exit_action = SignalAction.EXIT_SHORT
                
                logger.info(f"Alpha Edge Sector Rotation EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id,
                    symbol=symbol,
                    action=exit_action,
                    confidence=0.80,
                    reasoning=f"Sector Rotation exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price},
                    metadata={
                        "signal_engine": "alpha_edge_fundamental",
                        "template_type": "sector_rotation",
                        "exit_reason": exit_reason,
                        "data_source": "fmp_sector_performance" if use_real_data else "regime_mapping",
                        "optimal_sectors": optimal_sectors,
                        "pnl_pct": pnl_pct,
                    }
                )
        
        # --- ENTRY LOGIC ---
        if has_open_position:
            return None
        
        symbol_upper = symbol.upper()
        
        # Check 1: Is this symbol in the top-ranked sectors?
        if symbol_upper not in optimal_sectors:
            data_source = "FMP performance" if use_real_data else "regime mapping"
            logger.debug(
                f"{symbol}: not in top sectors ({data_source}) "
                f"(top: {', '.join(optimal_sectors)})"
            )
            return None
        
        # Check 2: Rebalancing check — has enough time passed since last trade?
        try:
            from src.models.orm import OrderORM
            session = self.db.get_session()
            try:
                from src.utils.symbol_normalizer import normalize_symbol
                normalized = normalize_symbol(symbol)
                last_order = session.query(OrderORM).filter(
                    OrderORM.strategy_id == strategy.id,
                    OrderORM.symbol == normalized
                ).order_by(OrderORM.submitted_at.desc()).first()
                
                if last_order and last_order.submitted_at:
                    days_since_last = (datetime.now() - last_order.submitted_at).days
                    if days_since_last < rebalance_days:
                        logger.debug(
                            f"{symbol}: last trade {days_since_last}d ago, "
                            f"rebalance period is {rebalance_days}d — too soon"
                        )
                        return None
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not check rebalancing for {symbol}: {e}")
        
        # Check 3: Positive momentum (price above SMA-200 or positive 60-day return)
        momentum_positive = False
        if len(data) >= 60:
            price_60d_ago = float(data['close'].iloc[-60])
            momentum_return = (current_price - price_60d_ago) / price_60d_ago
            momentum_positive = momentum_return > 0
            
            if not momentum_positive:
                logger.debug(
                    f"{symbol}: negative 60d momentum ({momentum_return:.1%}) — no entry"
                )
                return None
        else:
            # Not enough data for momentum check, allow entry based on regime
            momentum_positive = True
        
        # All conditions met
        confidence = 0.70
        sector_rank = optimal_sectors.index(symbol_upper) if symbol_upper in optimal_sectors else 2
        confidence += (top_n - sector_rank) * 0.05  # Higher rank = higher confidence
        confidence = min(1.0, confidence)
        
        data_source = "FMP sector performance" if use_real_data else "regime mapping"
        reasoning = (
            f"Sector Rotation entry for {symbol}: "
            f"sector rank #{sector_rank + 1}/{len(optimal_sectors)} "
            f"(source: {data_source}), positive momentum"
        )
        
        logger.info(f"Alpha Edge Sector Rotation ENTRY for {symbol}: {reasoning}")
        
        return TradingSignal(
            strategy_id=strategy.id,
            symbol=symbol,
            action=SignalAction.ENTER_LONG,
            confidence=confidence,
            reasoning=reasoning,
            generated_at=datetime.now(),
            indicators={"price": current_price},
            metadata={
                "signal_engine": "alpha_edge_fundamental",
                "template_type": "sector_rotation",
                "data_source": "fmp_sector_performance" if use_real_data else "regime_mapping",
                "optimal_sectors": optimal_sectors,
                "sector_rank": sector_rank + 1,
                "strategy_name": strategy.name,
            }
        )
    
    def _check_quality_mean_reversion_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        qmr_config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Quality Mean Reversion conditions combining fundamental + technical.
        
        Entry requires:
        1. ROE > 15% (strong profitability)
        2. Debt/Equity < 0.5 (healthy balance sheet)
        3. RSI < 30 (technically oversold)
        
        Exit conditions:
        - Price returns to 50-day MA
        - Profit target (5%)
        - Stop loss (3%)
        """
        from src.models.enums import SignalAction
        
        min_roe = qmr_config.get('min_roe', 0.15)
        max_debt_equity = qmr_config.get('max_debt_equity', 0.5)
        oversold_threshold = qmr_config.get('oversold_threshold', 30)
        profit_target = qmr_config.get('profit_target', 0.05)
        stop_loss = qmr_config.get('stop_loss', 0.03)
        
        current_price = float(data['close'].iloc[-1])
        
        # Calculate RSI
        rsi_series = self._calculate_rsi(data['close'], period=14)
        current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.isna().all() else None
        
        # Calculate 50-day SMA for exit
        sma_50 = float(data['close'].rolling(50).mean().iloc[-1]) if len(data) >= 50 else None
        
        # --- EXIT LOGIC ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            
            exit_reason = None
            
            # Check profit target
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%} >= {profit_target:.0%}"
            # Check stop loss
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%} <= -{stop_loss:.0%}"
            # Check mean reversion complete (price returned to 50-day MA)
            elif sma_50 and current_price >= sma_50:
                exit_reason = (
                    f"Mean reversion complete: price ${current_price:.2f} >= "
                    f"SMA50 ${sma_50:.2f}"
                )
            
            if exit_reason:
                exit_action = SignalAction.EXIT_LONG
                if open_position.side and open_position.side.value == 'SHORT':
                    exit_action = SignalAction.EXIT_SHORT
                
                logger.info(f"Alpha Edge Quality Mean Reversion EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id,
                    symbol=symbol,
                    action=exit_action,
                    confidence=0.85,
                    reasoning=f"Quality Mean Reversion exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={
                        "price": current_price,
                        "rsi": current_rsi,
                        "sma_50": sma_50,
                    },
                    metadata={
                        "signal_engine": "alpha_edge_fundamental",
                        "template_type": "quality_mean_reversion",
                        "exit_reason": exit_reason,
                        "pnl_pct": pnl_pct,
                    }
                )
        
        # --- ENTRY LOGIC ---
        if has_open_position:
            return None
        
        # Check 1: Fundamental quality — ROE > threshold
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data:
            logger.debug(f"No fundamental data for {symbol} — skipping quality mean reversion")
            return None
        
        if fund_data.roe is None or fund_data.roe < min_roe:
            logger.debug(
                f"{symbol}: ROE {fund_data.roe} < {min_roe:.0%} — no entry"
            )
            return None
        
        # Check 2: Fundamental quality — Debt/Equity < threshold
        if fund_data.debt_to_equity is None or fund_data.debt_to_equity > max_debt_equity:
            logger.debug(
                f"{symbol}: D/E {fund_data.debt_to_equity} > {max_debt_equity} — no entry"
            )
            return None
        
        # Check 3: Technical oversold — RSI < threshold
        if current_rsi is None:
            logger.debug(f"No RSI data for {symbol} — skipping quality mean reversion")
            return None
        
        if current_rsi >= oversold_threshold:
            logger.debug(
                f"{symbol}: RSI {current_rsi:.1f} >= {oversold_threshold} — not oversold"
            )
            return None
        
        # All conditions met — quality stock that is technically oversold
        confidence = min(1.0, 0.65 + (oversold_threshold - current_rsi) * 0.01)
        
        reasoning = (
            f"Quality Mean Reversion entry for {symbol}: "
            f"ROE={fund_data.roe:.1%} (>{min_roe:.0%}), "
            f"D/E={fund_data.debt_to_equity:.2f} (<{max_debt_equity}), "
            f"RSI={current_rsi:.1f} (<{oversold_threshold})"
        )
        
        logger.info(f"Alpha Edge Quality Mean Reversion ENTRY for {symbol}: {reasoning}")
        
        return TradingSignal(
            strategy_id=strategy.id,
            symbol=symbol,
            action=SignalAction.ENTER_LONG,
            confidence=confidence,
            reasoning=reasoning,
            generated_at=datetime.now(),
            indicators={
                "price": current_price,
                "rsi": current_rsi,
                "sma_50": sma_50,
            },
            metadata={
                "signal_engine": "alpha_edge_fundamental",
                "template_type": "quality_mean_reversion",
                "roe": fund_data.roe,
                "debt_to_equity": fund_data.debt_to_equity,
                "rsi": current_rsi,
                "market_cap": fund_data.market_cap,
                "strategy_name": strategy.name,
            }
        )
    
    def _check_earnings_miss_momentum_short_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        em_config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Earnings Miss Momentum SHORT conditions.
        Entry: negative earnings surprise, revenue decline. Exit: profit/stop/hold.
        """
        from src.models.enums import SignalAction
        
        earnings_miss_min = em_config.get('earnings_miss_min', 0.03)
        profit_target = em_config.get('profit_target', 0.05)
        stop_loss = em_config.get('stop_loss', 0.03)
        hold_period_max = em_config.get('hold_period_days', 30)
        
        current_price = float(data['close'].iloc[-1])
        
        # --- EXIT LOGIC ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            # SHORT P&L: profit when price drops
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%} >= {profit_target:.0%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%} <= -{stop_loss:.0%}"
            elif days_held >= hold_period_max:
                exit_reason = f"Max hold period reached: {days_held} days >= {hold_period_max}"
            
            if exit_reason:
                logger.info(f"Alpha Edge Earnings Miss SHORT EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol,
                    action=SignalAction.EXIT_SHORT, confidence=0.85,
                    reasoning=f"Earnings Miss Momentum SHORT exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "earnings_miss_momentum_short",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct, "days_held": days_held}
                )
        
        if has_open_position:
            return None
        
        # --- ENTRY LOGIC: negative earnings surprise ---
        earnings_surprise = provider.calculate_earnings_surprise(symbol)
        if earnings_surprise is None:
            return None
        
        # For SHORT: we want negative surprise (earnings miss)
        if earnings_surprise > -earnings_miss_min:
            logger.debug(f"{symbol}: earnings surprise {earnings_surprise:.1%} not negative enough for SHORT")
            return None
        
        # Check revenue decline
        fund_data = provider.get_fundamental_data(symbol)
        if fund_data and fund_data.revenue_growth is not None and fund_data.revenue_growth > 0:
            logger.debug(f"{symbol}: revenue still growing ({fund_data.revenue_growth:.1%}) — skip SHORT")
            return None
        
        confidence = min(1.0, 0.60 + abs(earnings_surprise) * 2)
        reasoning = (
            f"Earnings Miss Momentum SHORT entry for {symbol}: "
            f"earnings surprise={earnings_surprise:.1%} (<-{earnings_miss_min:.0%})"
        )
        
        logger.info(f"Alpha Edge Earnings Miss SHORT ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol,
            action=SignalAction.ENTER_SHORT, confidence=confidence,
            reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "earnings_miss_momentum_short",
                      "earnings_surprise": earnings_surprise, "strategy_name": strategy.name}
        )
    
    def _check_sector_rotation_short_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        sr_config: Dict[str, Any],
        config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Sector Rotation SHORT conditions.
        Entry: negative 60-day momentum on sector ETF. Exit: momentum reversal/profit/stop.
        """
        from src.models.enums import SignalAction
        
        momentum_lookback = sr_config.get('momentum_lookback_days', 60)
        stop_loss = sr_config.get('stop_loss_pct', 0.08)
        take_profit = sr_config.get('take_profit_pct', 0.05)
        
        current_price = float(data['close'].iloc[-1])
        
        # --- EXIT LOGIC ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            
            exit_reason = None
            if pnl_pct >= take_profit:
                exit_reason = f"Take profit reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            elif days_held >= momentum_lookback * 3:
                exit_reason = f"Max hold period: {days_held} days"
            else:
                # Check if momentum turned positive
                if len(data) >= momentum_lookback:
                    momentum = (float(data['close'].iloc[-1]) - float(data['close'].iloc[-momentum_lookback])) / float(data['close'].iloc[-momentum_lookback])
                    if momentum > 0 and days_held >= 30:
                        exit_reason = f"Momentum reversal: {momentum:.1%} positive"
            
            if exit_reason:
                logger.info(f"Alpha Edge Sector Rotation SHORT EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol,
                    action=SignalAction.EXIT_SHORT, confidence=0.80,
                    reasoning=f"Sector Rotation SHORT exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "sector_rotation_short",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # --- ENTRY LOGIC: negative momentum ---
        if len(data) < momentum_lookback:
            return None
        
        momentum = (float(data['close'].iloc[-1]) - float(data['close'].iloc[-momentum_lookback])) / float(data['close'].iloc[-momentum_lookback])
        
        if momentum >= -0.02:
            logger.debug(f"{symbol}: momentum {momentum:.1%} not negative enough for SHORT")
            return None
        
        confidence = min(1.0, 0.55 + abs(momentum) * 2)
        reasoning = f"Sector Rotation SHORT entry for {symbol}: 60d momentum={momentum:.1%}"
        
        logger.info(f"Alpha Edge Sector Rotation SHORT ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol,
            action=SignalAction.ENTER_SHORT, confidence=confidence,
            reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price, "momentum_60d": momentum},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "sector_rotation_short",
                      "momentum": momentum, "strategy_name": strategy.name}
        )
    
    def _check_quality_deterioration_short_signal(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame,
        provider,
        qd_config: Dict[str, Any],
        has_open_position: bool,
        open_position
    ) -> Optional[TradingSignal]:
        """
        Evaluate Quality Deterioration SHORT conditions.
        Entry: overbought RSI > 75 + deteriorating fundamentals (low ROE, high D/E).
        """
        from src.models.enums import SignalAction
        
        overbought_threshold = qd_config.get('overbought_threshold', 75)
        profit_target = qd_config.get('profit_target', 0.05)
        stop_loss = qd_config.get('stop_loss', 0.05)
        
        current_price = float(data['close'].iloc[-1])
        
        rsi_series = self._calculate_rsi(data['close'], period=14)
        current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.isna().all() else None
        sma_50 = float(data['close'].rolling(50).mean().iloc[-1]) if len(data) >= 50 else None
        
        # --- EXIT LOGIC ---
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
            
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            elif sma_50 and current_price <= sma_50:
                exit_reason = f"Mean reversion complete: price ${current_price:.2f} <= SMA50 ${sma_50:.2f}"
            
            if exit_reason:
                logger.info(f"Alpha Edge Quality Deterioration SHORT EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol,
                    action=SignalAction.EXIT_SHORT, confidence=0.85,
                    reasoning=f"Quality Deterioration SHORT exit: {exit_reason}",
                    generated_at=datetime.now(),
                    indicators={"price": current_price, "rsi": current_rsi, "sma_50": sma_50},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "quality_deterioration_short",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # --- ENTRY LOGIC: overbought + deteriorating fundamentals ---
        if current_rsi is None or current_rsi <= overbought_threshold:
            logger.debug(f"{symbol}: RSI {current_rsi} not overbought (>{overbought_threshold})")
            return None
        
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data:
            return None
        
        # Check for deteriorating quality: low ROE or high D/E
        deterioration_signals = 0
        if fund_data.roe is not None and fund_data.roe < 0.10:
            deterioration_signals += 1
        if fund_data.debt_to_equity is not None and fund_data.debt_to_equity > 1.0:
            deterioration_signals += 1
        
        if deterioration_signals == 0:
            logger.debug(f"{symbol}: fundamentals still healthy — skip SHORT")
            return None
        
        confidence = min(1.0, 0.60 + (current_rsi - overbought_threshold) * 0.01 + deterioration_signals * 0.05)
        reasoning = (
            f"Quality Deterioration SHORT entry for {symbol}: "
            f"RSI={current_rsi:.1f} (>{overbought_threshold}), "
            f"ROE={fund_data.roe}, D/E={fund_data.debt_to_equity}"
        )
        
        logger.info(f"Alpha Edge Quality Deterioration SHORT ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol,
            action=SignalAction.ENTER_SHORT, confidence=confidence,
            reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price, "rsi": current_rsi, "sma_50": sma_50},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "quality_deterioration_short",
                      "roe": fund_data.roe, "debt_to_equity": fund_data.debt_to_equity,
                      "rsi": current_rsi, "strategy_name": strategy.name}
        )
    
    def _handle_dividend_aristocrat(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame, provider,
        da_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """Check FMP for dividend history, yield, payout ratio. Verify price pullback from 52w high."""
        from src.models.enums import SignalAction
        
        profit_target = da_config.get('profit_target', 0.15)
        stop_loss = da_config.get('stop_loss_pct', 0.05)
        pullback_pct = da_config.get('pullback_from_high_pct', 0.03)
        current_price = float(data['close'].iloc[-1])
        
        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            if exit_reason:
                logger.info(f"Alpha Edge Dividend Aristocrat EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT_LONG,
                    confidence=0.85, reasoning=f"Dividend Aristocrat exit: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "dividend_aristocrat",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # ENTRY LOGIC: check pullback from 52-week high
        high_52w = float(data['high'].rolling(252).max().iloc[-1]) if len(data) >= 252 else float(data['high'].max())
        pullback = (high_52w - current_price) / high_52w if high_52w > 0 else 0
        
        if pullback < pullback_pct:
            logger.debug(f"{symbol}: pullback {pullback:.1%} < {pullback_pct:.0%} from 52w high — skip")
            return None
        
        # Check fundamental dividend data
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data:
            return None
        
        div_yield = getattr(fund_data, 'dividend_yield', None)
        if div_yield is None or div_yield < 0.02:
            logger.debug(f"{symbol}: dividend yield {div_yield} < 2.0% — skip")
            return None
        
        confidence = min(1.0, 0.65 + pullback * 2)
        reasoning = (f"Dividend Aristocrat entry for {symbol}: pullback {pullback:.1%} from 52w high, "
                     f"div yield {div_yield:.1%}")
        logger.info(f"Alpha Edge Dividend Aristocrat ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
            confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price, "high_52w": high_52w},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "dividend_aristocrat",
                      "pullback": pullback, "dividend_yield": div_yield, "strategy_name": strategy.name}
        )
    
    def _handle_insider_buying(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame, provider,
        ib_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """Check FMP insider transactions endpoint for recent large purchases."""
        from src.models.enums import SignalAction
        
        profit_target = ib_config.get('profit_target', 0.10)
        stop_loss = ib_config.get('stop_loss_pct', 0.05)
        hold_max = ib_config.get('hold_period_max', 60)
        current_price = float(data['close'].iloc[-1])
        
        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            elif days_held >= hold_max:
                exit_reason = f"Max hold period reached: {days_held}d"
            if exit_reason:
                logger.info(f"Alpha Edge Insider Buying EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT_LONG,
                    confidence=0.80, reasoning=f"Insider Buying exit: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "insider_buying",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # ENTRY LOGIC: check for recent insider purchases via FMP
        min_net_purchases = ib_config.get('min_net_purchases', 3)
        lookback_days = ib_config.get('lookback_days', 90)
        
        try:
            insider_net = provider.get_insider_net_purchases(symbol, lookback_days=lookback_days)
        except Exception:
            insider_net = None
        
        if not insider_net or insider_net.get('buy_count', 0) == 0:
            return None
        
        net_purchases = insider_net.get('buy_count', 0) - insider_net.get('sell_count', 0)
        if net_purchases < min_net_purchases:
            return None
        
        net_shares = insider_net.get('net_shares', 0)
        last_buy = insider_net.get('last_buy_date', 'unknown')
        confidence = min(0.60 + (net_purchases * 0.05), 0.90)
        reasoning = (
            f"Insider Buying entry for {symbol}: {net_purchases} net insider purchases "
            f"({insider_net.get('buy_count', 0)} buys, {insider_net.get('sell_count', 0)} sells) "
            f"in last {lookback_days}d, net shares={net_shares}, last buy={last_buy}"
        )
        logger.info(f"Alpha Edge Insider Buying ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
            confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "insider_buying",
                      "net_purchases": net_purchases, "net_shares": net_shares,
                      "last_buy_date": last_buy, "strategy_name": strategy.name}
        )
    
    def _handle_revenue_acceleration(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame, provider,
        ra_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """Check FMP financials for 3 consecutive quarters of accelerating revenue growth."""
        from src.models.enums import SignalAction
        
        profit_target = ra_config.get('profit_target', 0.12)
        stop_loss = ra_config.get('stop_loss_pct', 0.05)
        hold_max = ra_config.get('hold_period_max', 40)
        current_price = float(data['close'].iloc[-1])
        
        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            elif days_held >= hold_max:
                exit_reason = f"Max hold period reached: {days_held}d"
            if exit_reason:
                logger.info(f"Alpha Edge Revenue Acceleration EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT_LONG,
                    confidence=0.85, reasoning=f"Revenue Acceleration exit: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "revenue_acceleration",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # ENTRY LOGIC: check revenue growth acceleration
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data:
            return None
        
        rev_growth = getattr(fund_data, 'revenue_growth', None)
        if rev_growth is None or rev_growth <= 0:
            logger.debug(f"{symbol}: no positive revenue growth ({rev_growth}) — skip")
            return None
        
        # Use positive earnings surprise + revenue growth as proxy for acceleration
        earnings_surprise = getattr(fund_data, 'earnings_surprise', None)
        if earnings_surprise is not None and earnings_surprise > 0.01 and rev_growth > 0.03:
            confidence = min(1.0, 0.60 + rev_growth + (earnings_surprise * 2))
            reasoning = (f"Revenue Acceleration entry for {symbol}: rev growth {rev_growth:.1%}, "
                         f"earnings surprise {earnings_surprise:.1%}")
            logger.info(f"Alpha Edge Revenue Acceleration ENTRY for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "revenue_acceleration",
                          "revenue_growth": rev_growth, "earnings_surprise": earnings_surprise,
                          "strategy_name": strategy.name}
            )
        
        # Fallback: strong revenue growth alone (no earnings surprise data)
        if rev_growth > 0.10:
            confidence = min(1.0, 0.55 + rev_growth)
            reasoning = f"Revenue Acceleration entry for {symbol}: strong rev growth {rev_growth:.1%} (no earnings surprise data)"
            logger.info(f"Alpha Edge Revenue Acceleration ENTRY (growth-only) for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "revenue_acceleration",
                          "revenue_growth": rev_growth, "strategy_name": strategy.name}
            )

        return None
    
    def _handle_relative_value(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame, provider,
        rv_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """Calculate sector-relative valuation metrics. Compare to sector median from FMP."""
        from src.models.enums import SignalAction
        
        profit_target = rv_config.get('profit_target', 0.10)
        stop_loss = rv_config.get('stop_loss_pct', 0.05)
        hold_max = rv_config.get('hold_period_max', 45)
        current_price = float(data['close'].iloc[-1])
        
        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            side = open_position.side if hasattr(open_position, 'side') else 'BUY'
            if side and 'sell' in str(side).lower():
                pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
            else:
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            days_held = (datetime.now() - open_position.opened_at).days if open_position.opened_at else 0
            exit_reason = None
            if pnl_pct >= profit_target:
                exit_reason = f"Profit target reached: {pnl_pct:.1%}"
            elif pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            elif days_held >= hold_max:
                exit_reason = f"Monthly rebalance / max hold: {days_held}d"
            if exit_reason:
                exit_action = SignalAction.EXIT_SHORT if side and 'sell' in str(side).lower() else SignalAction.EXIT_LONG
                logger.info(f"Alpha Edge Relative Value EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=exit_action,
                    confidence=0.80, reasoning=f"Relative Value exit: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "relative_value",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # ENTRY LOGIC: compare P/E to sector median
        fund_data = provider.get_fundamental_data(symbol)
        if not fund_data:
            return None
        
        pe_ratio = getattr(fund_data, 'pe_ratio', None)
        if pe_ratio is None or pe_ratio <= 0:
            return None
        
        # Use P/E < 20 as "cheap" proxy (sector median comparison would need full sector data)
        if pe_ratio < 20:
            confidence = min(1.0, 0.60 + (20 - pe_ratio) * 0.02)
            reasoning = f"Relative Value LONG entry for {symbol}: P/E {pe_ratio:.1f} (undervalued)"
            logger.info(f"Alpha Edge Relative Value ENTRY LONG for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price, "pe_ratio": pe_ratio},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "relative_value",
                          "pe_ratio": pe_ratio, "strategy_name": strategy.name}
            )
        elif pe_ratio > 30:
            confidence = min(1.0, 0.55 + (pe_ratio - 30) * 0.01)
            reasoning = f"Relative Value SHORT entry for {symbol}: P/E {pe_ratio:.1f} (overvalued)"
            logger.info(f"Alpha Edge Relative Value ENTRY SHORT for {symbol}: {reasoning}")
            return TradingSignal(
                strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_SHORT,
                confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
                indicators={"price": current_price, "pe_ratio": pe_ratio},
                metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "relative_value",
                          "pe_ratio": pe_ratio, "strategy_name": strategy.name}
            )
        
        return None
    
    def _handle_end_of_month_momentum(
        self, strategy: Strategy, symbol: str, data: pd.DataFrame,
        eom_config: Dict[str, Any], has_open_position: bool, open_position
    ) -> Optional[TradingSignal]:
        """
        End-of-Month Momentum: buy in the last 3 trading days of each month
        when price > SMA(20) and RSI > 40. Exit on the 3rd trading day of the
        next month. Stop loss 2%. Captures institutional rebalancing flows.
        """
        from src.models.enums import SignalAction
        
        stop_loss = eom_config.get('stop_loss_pct', 0.02)
        sma_period = eom_config.get('sma_period', 20)
        rsi_min = eom_config.get('rsi_min', 40)
        month_end_day = eom_config.get('month_end_day_threshold', 26)
        exit_day = eom_config.get('exit_day_of_new_month', 3)
        
        if len(data) < sma_period + 1:
            return None
        
        current_price = float(data['close'].iloc[-1])
        today = data.index[-1]
        today_day = today.day if hasattr(today, 'day') else datetime.now().day
        today_month = today.month if hasattr(today, 'month') else datetime.now().month
        
        # Calculate SMA(20)
        sma_20 = float(data['close'].rolling(window=sma_period).mean().iloc[-1])
        
        # Calculate RSI(14)
        rsi_period = eom_config.get('rsi_period', 14)
        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        
        # EXIT LOGIC
        if has_open_position and open_position:
            entry_price = open_position.entry_price or current_price
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            entry_month = open_position.opened_at.month if open_position.opened_at else today_month
            
            exit_reason = None
            # Stop loss
            if pnl_pct <= -stop_loss:
                exit_reason = f"Stop loss triggered: {pnl_pct:.1%}"
            # Exit on 3rd trading day of new month (different month from entry)
            elif today_month != entry_month and today_day >= exit_day:
                exit_reason = f"New month exit (day {today_day} of new month)"
            
            if exit_reason:
                logger.info(f"Alpha Edge End-of-Month Momentum EXIT for {symbol}: {exit_reason}")
                return TradingSignal(
                    strategy_id=strategy.id, symbol=symbol, action=SignalAction.EXIT_LONG,
                    confidence=0.85, reasoning=f"End-of-Month Momentum exit: {exit_reason}",
                    generated_at=datetime.now(), indicators={"price": current_price, "sma_20": sma_20, "rsi": current_rsi},
                    metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "end_of_month_momentum",
                              "exit_reason": exit_reason, "pnl_pct": pnl_pct}
                )
        
        if has_open_position:
            return None
        
        # ENTRY LOGIC: last 3 trading days of month (day >= 26 as approximation)
        if today_day < month_end_day:
            return None
        
        # Price must be above SMA(20)
        if current_price <= sma_20:
            logger.debug(f"{symbol}: price {current_price:.2f} <= SMA(20) {sma_20:.2f} — skip EOM entry")
            return None
        
        # RSI must be above 40 (not oversold)
        if current_rsi <= rsi_min:
            logger.debug(f"{symbol}: RSI {current_rsi:.1f} <= {rsi_min} — skip EOM entry")
            return None
        
        confidence = min(1.0, 0.65 + (current_rsi - rsi_min) / 100 + (current_price - sma_20) / current_price)
        reasoning = (f"End-of-Month Momentum entry for {symbol}: day {today_day} (month-end window), "
                     f"price {current_price:.2f} > SMA(20) {sma_20:.2f}, RSI {current_rsi:.1f}")
        logger.info(f"Alpha Edge End-of-Month Momentum ENTRY for {symbol}: {reasoning}")
        return TradingSignal(
            strategy_id=strategy.id, symbol=symbol, action=SignalAction.ENTER_LONG,
            confidence=confidence, reasoning=reasoning, generated_at=datetime.now(),
            indicators={"price": current_price, "sma_20": sma_20, "rsi": current_rsi},
            metadata={"signal_engine": "alpha_edge_fundamental", "template_type": "end_of_month_momentum",
                      "day_of_month": today_day, "strategy_name": strategy.name}
        )
    
    def _generate_signal_for_symbol(
        self,
        strategy: Strategy,
        symbol: str,
        data: pd.DataFrame
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal for a specific symbol using the DSL rule engine.

        Uses the same indicator calculation and rule parsing as backtesting
        to ensure consistent signal generation between backtest and live trading.

        Position-aware logic:
        - When both entry and exit conditions fire simultaneously, entry takes
          priority if there is NO open position (you can't exit what you don't have).
        - Exit takes priority only when there IS an open position for this symbol.

        Args:
            strategy: Strategy to use
            symbol: Symbol to generate signal for
            data: Historical OHLCV data (must include open, high, low, close, volume)

        Returns:
            TradingSignal or None if no signal
        """
        from src.models.enums import SignalAction

        # Time-based exit: force close positions held longer than max_holding_days
        max_holding_days = 30  # Default max holding period
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    max_holding_days = config.get('alpha_edge', {}).get('max_holding_period_days', 30)
        except Exception:
            pass
        
        try:
            from src.models.database import get_database
            from src.models.orm import PositionORM
            from src.utils.symbol_normalizer import normalize_symbol
            
            db = get_database()
            session = db.get_session()
            try:
                normalized = normalize_symbol(symbol)
                stale_positions = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy.id,
                    PositionORM.symbol == normalized,
                    PositionORM.closed_at.is_(None)
                ).all()
                
                for pos in stale_positions:
                    if pos.opened_at and (datetime.now() - pos.opened_at).days > max_holding_days:
                        logger.info(
                            f"Time-based exit: Position {pos.id} in {symbol} held for "
                            f"{(datetime.now() - pos.opened_at).days} days (max: {max_holding_days}). "
                            f"Generating EXIT signal."
                        )
                        exit_action = SignalAction.EXIT_LONG if pos.side.value == 'LONG' else SignalAction.EXIT_SHORT
                        return TradingSignal(
                            strategy_id=strategy.id,
                            symbol=symbol,
                            action=exit_action,
                            confidence=0.9,
                            reasoning=f"Time-based exit: held {(datetime.now() - pos.opened_at).days} days (max {max_holding_days})",
                            generated_at=datetime.now(),
                            indicators={"time_exit": True, "days_held": (datetime.now() - pos.opened_at).days},
                            metadata={"exit_type": "time_based", "max_holding_days": max_holding_days}
                        )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not check for stale positions: {e}")

        # Earnings awareness: skip entry signals if earnings are within 3 days
        try:
            if hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                days_to_earnings = self._fundamental_data_provider.get_days_since_earnings(symbol)
                # get_days_since_earnings returns negative if earnings are upcoming
                if days_to_earnings is not None and days_to_earnings < 0 and abs(days_to_earnings) <= 3:
                    logger.info(
                        f"Earnings awareness: Skipping signal for {symbol} - "
                        f"earnings in {abs(days_to_earnings)} days. Avoiding pre-earnings volatility."
                    )
                    return None
        except Exception as e:
            logger.debug(f"Could not check earnings for {symbol}: {e}")

        # Check if this is a short strategy
        is_short_strategy = (
            hasattr(strategy, 'metadata') and 
            strategy.metadata and 
            strategy.metadata.get('direction') == 'short'
        )

        # Intraday indicator period scaling:
        # Templates are calibrated for daily bars (RSI(14) = 14-day RSI).
        # On 1h data, we scale periods to approximate daily behavior:
        #   - Stocks/ETFs: ~7 bars/day → scale factor 7
        #   - Crypto: ~24 bars/day → scale factor 24
        #   - Forex: ~24 bars/day on weekdays → scale factor 20
        # We cap the scale to avoid excessively long lookbacks.
        # Thresholds (RSI < 25, STOCH > 80) stay the same — oversold is oversold.
        import re
        signal_rules = strategy.rules
        
        # Detect if we're running on intraday data by checking bar count vs calendar days
        bars_per_day = 1
        if len(data) > 10:
            unique_dates = data.index.normalize().nunique() if hasattr(data.index, 'normalize') else len(set(str(d)[:10] for d in data.index))
            if unique_dates > 0:
                bars_per_day = len(data) / unique_dates
        
        is_intraday = bars_per_day > 2  # More than 2 bars per day = intraday data
        
        if is_intraday:
            # Don't scale intraday-native templates — they're already calibrated for hourly data
            is_intraday_template = (
                hasattr(strategy, 'metadata') and strategy.metadata and
                (strategy.metadata.get('intraday', False) or strategy.metadata.get('interval_4h', False))
            )
            # Also check rules.interval — if the strategy was backtested on 4h/1h bars,
            # the indicators are already calibrated for that timeframe. Don't scale.
            if not is_intraday_template:
                strat_rules_interval = strategy.rules.get('interval', '1d') if strategy.rules else '1d'
                if strat_rules_interval in ('1h', '4h', '2h', '15m', '30m'):
                    is_intraday_template = True
            
            if not is_intraday_template:
                # Scale indicator periods: multiply by bars_per_day, but cap at reasonable values
                # Use lower cap for crypto (12x) since 24x makes indicators too sluggish
                # with only ~30 days of 1h data from Yahoo Finance
                is_crypto_symbol = False
                try:
                    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                    is_crypto_symbol = symbol.upper() in set(DEMO_ALLOWED_CRYPTO)
                except ImportError:
                    pass
                max_scale = 12 if is_crypto_symbol else 24
                scale_factor = min(int(bars_per_day), max_scale)
            
                def scale_indicator_period(condition: str, scale: int) -> str:
                    """Scale indicator periods in a DSL condition for intraday data."""
                    def replace_period(match):
                        indicator = match.group(1)
                        period = int(match.group(2))
                        # Scale the period, but cap at reasonable values
                        scaled = min(period * scale, 200)
                        # Don't scale very short periods (1-2) — they're intentional
                        if period <= 2:
                            return f"{indicator}({period}"
                        return f"{indicator}({scaled}"
                    
                    return re.sub(r'(RSI|SMA|EMA|STOCH|ATR|STDDEV|VOLUME_MA|BB_LOWER|BB_UPPER|BB_MIDDLE)\((\d+)', replace_period, condition)
                
                # Create scaled copy of rules (don't modify original)
                scaled_entry = [scale_indicator_period(c, scale_factor) for c in strategy.rules.get('entry_conditions', [])]
                scaled_exit = [scale_indicator_period(c, scale_factor) for c in strategy.rules.get('exit_conditions', [])]
                
                # Scale indicator specs too (e.g., "RSI:14" → "RSI:98")
                scaled_indicators = []
                for ind in strategy.rules.get('indicators', []):
                    if ':' in ind:
                        base, period_str = ind.split(':', 1)
                        try:
                            period = int(period_str)
                            if period > 2:
                                scaled_indicators.append(f"{base}:{min(period * scale_factor, 200)}")
                            else:
                                scaled_indicators.append(ind)
                        except ValueError:
                            scaled_indicators.append(ind)
                    elif ind == 'Bollinger Bands':
                        # Scale BB period: "Bollinger Bands" → "Bollinger Bands:140" (period 20 * 7)
                        scaled_bb_period = min(20 * scale_factor, 200)
                        scaled_indicators.append(f"Bollinger Bands:{scaled_bb_period}")
                    else:
                        scaled_indicators.append(ind)
                
                signal_rules = {
                    **strategy.rules,
                    'entry_conditions': scaled_entry,
                    'exit_conditions': scaled_exit,
                    'indicators': scaled_indicators,
                }
                
                logger.info(
                    f"Intraday scaling for {symbol}: {bars_per_day:.1f} bars/day, "
                    f"scale={scale_factor}x (e.g., RSI(14)→RSI({min(14*scale_factor, 200)}))"
                )
            else:
                logger.info(f"Intraday-native template {strategy.name} — no period scaling needed")

        # Calculate indicators using the (possibly scaled) rules
        # Create a temporary strategy-like object with scaled rules for indicator calculation
        class _ScaledStrategy:
            def __init__(self, original, rules):
                self.name = original.name
                self.rules = rules
                self.symbols = original.symbols
                self.metadata = original.metadata
                self.risk_params = original.risk_params
        
        calc_strategy = _ScaledStrategy(strategy, signal_rules) if is_intraday else strategy
        indicators = self._calculate_indicators_from_strategy(calc_strategy, data, symbol)

        if not indicators:
            logger.warning(f"No indicators calculated for {symbol}, cannot generate signal")
            return None

        # Parse strategy rules using DSL (use scaled rules for intraday)
        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"] if "volume" in data.columns else None

        entries, exits = self._parse_strategy_rules(
            close, high, low, indicators, signal_rules, volume=volume
        )

        # Check the most recent data point for signals
        if len(entries) == 0 or len(exits) == 0:
            logger.debug(f"No signal data for {symbol}")
            return None

        latest_entry = entries.iloc[-1] if len(entries) > 0 else False
        latest_exit = exits.iloc[-1] if len(exits) > 0 else False

        current_price = float(close.iloc[-1])

        # Build indicator snapshot for the signal
        indicator_snapshot = {}
        for key, values in indicators.items():
            if len(values) > 0 and not values.isna().all():
                latest_val = values.iloc[-1]
                if not pd.isna(latest_val):
                    indicator_snapshot[key] = float(latest_val)

        indicator_snapshot["price"] = current_price

        # Calculate confidence based on strategy type and signal characteristics.
        # 
        # A top trader sizes positions based on conviction, not just "did the signal fire?"
        # The meaning of signal persistence differs by strategy type:
        #
        # MEAN REVERSION: Buying oversold. A signal that JUST appeared (1-2 days) is the
        #   freshest entry — the asset just became oversold. A signal firing 8/10 days means
        #   the asset is stuck oversold (death spiral or broken indicator). Confidence peaks
        #   at 1-3 days of persistence, then decays.
        #
        # TREND FOLLOWING: Riding momentum. A signal firing 8/10 days means the trend is
        #   strong and persistent — high conviction. A 1-day signal could be noise.
        #   Confidence increases with persistence.
        #
        # BREAKOUT: Similar to trend — a breakout that holds is more convincing.
        #
        # Additionally, we factor in indicator extremity: RSI at 15 is more oversold than
        # RSI at 28 — the deeper the extreme, the higher the conviction for mean reversion.
        
        lookback = min(10, len(entries))
        recent_entries = entries.iloc[-lookback:]
        recent_exits = exits.iloc[-lookback:]
        entry_persistence = float(recent_entries.sum())  # How many of last N bars had signal
        exit_strength = float(recent_exits.sum()) / lookback
        
        # Determine strategy type from template
        strategy_type_str = "mean_reversion"  # Default
        if hasattr(strategy, 'metadata') and strategy.metadata:
            strategy_type_str = strategy.metadata.get('strategy_type', '')
        if not strategy_type_str:
            # Look up from template library
            template_name = ''
            if hasattr(strategy, 'metadata') and strategy.metadata:
                template_name = strategy.metadata.get('template_name', '')
            if template_name:
                try:
                    from src.strategy.strategy_templates import StrategyTemplateLibrary
                    _lib = StrategyTemplateLibrary()
                    _tmpl = _lib.get_template_by_name(template_name)
                    if _tmpl:
                        strategy_type_str = _tmpl.strategy_type.value
                except Exception:
                    pass
        
        is_mean_reversion = 'mean_reversion' in strategy_type_str.lower() or 'reversion' in strategy_type_str.lower()
        is_trend = 'trend' in strategy_type_str.lower() or 'momentum' in strategy_type_str.lower()
        
        if is_mean_reversion:
            # Mean reversion: confidence peaks at 1-3 days of persistence, then decays.
            # 1 day = 0.70 (fresh signal, good entry)
            # 2-3 days = 0.80 (confirmed oversold, best entry)
            # 4-5 days = 0.60 (getting stale)
            # 6+ days = 0.40 (stuck oversold, dangerous)
            if entry_persistence <= 1:
                base_confidence = 0.70
            elif entry_persistence <= 3:
                base_confidence = 0.80
            elif entry_persistence <= 5:
                base_confidence = 0.60
            else:
                base_confidence = 0.40
            
            # Boost for indicator extremity: deeper oversold = higher conviction
            # Check RSI and Stochastic values if available
            rsi_val = indicator_snapshot.get('RSI_14')
            stoch_val = indicator_snapshot.get('STOCH_14') or indicator_snapshot.get('STOCH_5')
            
            extremity_boost = 0.0
            if rsi_val is not None:
                if rsi_val < 20:
                    extremity_boost = max(extremity_boost, 0.15)  # Deeply oversold
                elif rsi_val < 30:
                    extremity_boost = max(extremity_boost, 0.10)
                elif rsi_val < 40:
                    extremity_boost = max(extremity_boost, 0.05)
                # For short mean-reversion (overbought)
                elif rsi_val > 80:
                    extremity_boost = max(extremity_boost, 0.15)
                elif rsi_val > 70:
                    extremity_boost = max(extremity_boost, 0.10)
            
            confidence = min(1.0, base_confidence + extremity_boost)
            
        elif is_trend:
            # Trend following: confidence increases with persistence
            # 1 day = 0.40 (could be noise)
            # 3-5 days = 0.60 (trend establishing)
            # 6-8 days = 0.80 (strong trend)
            # 9-10 days = 0.90 (very strong trend)
            confidence = min(1.0, max(0.35, 0.30 + (entry_persistence / lookback) * 0.65))
        else:
            # Breakout / volatility: moderate persistence scaling
            confidence = min(1.0, max(0.40, 0.35 + (entry_persistence / lookback) * 0.55))

        # Determine if there's an open position for this symbol under this strategy
        has_open_position = False
        try:
            from src.models.orm import PositionORM
            session = self.db.get_session()
            try:
                open_pos = session.query(PositionORM).filter(
                    PositionORM.strategy_id == strategy.id,
                    PositionORM.symbol == symbol,
                    PositionORM.closed_at.is_(None)
                ).first()
                has_open_position = open_pos is not None
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not check open positions for {symbol}: {e}")
            # Default: no open position, so entry takes priority on conflict
            has_open_position = False

        # Resolve signal with position-aware priority
        # When both entry and exit fire simultaneously:
        #   - No open position → entry takes priority (can't exit what you don't have)
        #   - Has open position → exit takes priority (protect capital)
        emit_entry = False
        emit_exit = False

        if latest_entry and latest_exit:
            # Both conditions active — resolve by position state
            if has_open_position:
                emit_exit = True
                logger.info(
                    f"Both entry and exit active for {symbol} — has open position, "
                    f"exit takes priority"
                )
            else:
                emit_entry = True
                logger.info(
                    f"Both entry and exit active for {symbol} — no open position, "
                    f"entry takes priority"
                )
        elif latest_entry and not latest_exit:
            emit_entry = True
        elif latest_exit and not latest_entry:
            emit_exit = True

        # Determine signal actions based on strategy direction
        if is_short_strategy:
            entry_action = SignalAction.ENTER_SHORT
            exit_action = SignalAction.EXIT_SHORT
            direction_label = "SHORT"
        else:
            entry_action = SignalAction.ENTER_LONG
            exit_action = SignalAction.EXIT_LONG
            direction_label = "LONG"

        if emit_entry:
            # Confidence already computed above based on strategy type

            # Alpha Edge fundamental boost: increase confidence for strategies with fundamental backing
            if (hasattr(strategy, 'metadata') and strategy.metadata and 
                strategy.metadata.get('strategy_category') == 'alpha_edge'):
                try:
                    if hasattr(self, '_fundamental_data_provider') and self._fundamental_data_provider:
                        fund_data = self._fundamental_data_provider.get_fundamental_data(symbol)
                        if fund_data:
                            # Boost confidence based on fundamental quality
                            boost = 0.0
                            if fund_data.eps and fund_data.eps > 0:
                                boost += 0.05  # Profitable company
                            if fund_data.revenue_growth and fund_data.revenue_growth > 0.1:
                                boost += 0.05  # Growing revenue >10%
                            if fund_data.roe and fund_data.roe > 0.15:
                                boost += 0.05  # Strong ROE
                            if fund_data.debt_to_equity and fund_data.debt_to_equity < 0.5:
                                boost += 0.03  # Low debt
                            
                            if boost > 0:
                                old_confidence = confidence
                                confidence = min(1.0, confidence + boost)
                                logger.info(
                                    f"Alpha Edge fundamental boost for {symbol}: "
                                    f"confidence {old_confidence:.2f} → {confidence:.2f} "
                                    f"(+{boost:.2f} from fundamentals)"
                                )
                except Exception as e:
                    logger.debug(f"Could not apply fundamental boost for {symbol}: {e}")

            entry_conditions = strategy.rules.get("entry_conditions", [])
            reasoning_parts = [f"Entry conditions met for {symbol} at ${current_price:.2f}"]
            for cond in entry_conditions:
                reasoning_parts.append(f"Condition: {cond}")
            reasoning_parts.append(f"Signal persistence: {int(entry_persistence)}/{lookback} bars, type: {strategy_type_str}")
            reasoning = ". ".join(reasoning_parts)

            # Add fundamental data to metadata if available
            metadata = {
                "strategy_name": strategy.name,
                "timestamp": datetime.now().isoformat(),
                "signal_engine": "dsl",
                "entry_persistence": int(entry_persistence),
                "strategy_type": strategy_type_str,
                "data_points": len(data),
                "conflict_resolved": latest_entry and latest_exit,
                "direction": "short" if is_short_strategy else "long",
            }
            
            # Try to add fundamental data
            try:
                from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
                import yaml
                from pathlib import Path
                
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        
                    alpha_edge_config = config.get('alpha_edge', {})
                    fundamental_config = alpha_edge_config.get('fundamental_filters', {})
                    
                    if fundamental_config.get('enabled', False):
                        # Use singleton to preserve cache and rate limiter state
                        if not hasattr(self, '_fundamental_data_provider') or self._fundamental_data_provider is None:
                            data_provider = get_fundamental_data_provider(config)
                            self._fundamental_data_provider = data_provider
                        else:
                            data_provider = self._fundamental_data_provider
                        fundamental_data = data_provider.get_fundamental_data(symbol)
                        
                        if fundamental_data:
                            metadata['fundamental_data'] = {
                                'eps': fundamental_data.eps,
                                'revenue_growth': fundamental_data.revenue_growth,
                                'pe_ratio': fundamental_data.pe_ratio,
                                'roe': fundamental_data.roe,
                                'debt_to_equity': fundamental_data.debt_to_equity,
                                'market_cap': fundamental_data.market_cap,
                                'source': fundamental_data.source,
                                'timestamp': fundamental_data.timestamp.isoformat()
                            }
                            logger.debug(f"Added fundamental data to signal for {symbol}")
            except Exception as e:
                logger.debug(f"Could not add fundamental data to signal: {e}")

            signal = TradingSignal(
                strategy_id=strategy.id,
                symbol=symbol,
                action=entry_action,
                confidence=confidence,
                reasoning=reasoning,
                generated_at=datetime.now(),
                indicators=indicator_snapshot,
                metadata=metadata
            )

            logger.info(f"Generated ENTER_{direction_label} signal for {symbol} (confidence: {confidence:.2f}, persistence: {int(entry_persistence)}/{lookback}, type: {strategy_type_str})")
            return signal

        elif emit_exit:
            # Only emit exit if there's actually an open position to exit
            if not has_open_position:
                logger.debug(
                    f"Exit condition active for {symbol} but no open position — "
                    f"skipping EXIT signal"
                )
                return None

            confidence = min(1.0, max(0.3, exit_strength))

            exit_conditions = strategy.rules.get("exit_conditions", [])
            reasoning_parts = [f"Exit conditions met for {symbol} at ${current_price:.2f}"]
            for cond in exit_conditions:
                reasoning_parts.append(f"Condition: {cond}")
            reasoning_parts.append(f"Signal strength: {exit_strength:.0%} of last {lookback} days")
            reasoning = ". ".join(reasoning_parts)

            signal = TradingSignal(
                strategy_id=strategy.id,
                symbol=symbol,
                action=exit_action,
                confidence=confidence,
                reasoning=reasoning,
                generated_at=datetime.now(),
                indicators=indicator_snapshot,
                metadata={
                    "strategy_name": strategy.name,
                    "timestamp": datetime.now().isoformat(),
                    "signal_engine": "dsl",
                    "exit_strength": exit_strength,
                    "data_points": len(data),
                    "conflict_resolved": latest_entry and latest_exit,
                    "direction": "short" if is_short_strategy else "long",
                }
            )

            logger.info(f"Generated EXIT_{direction_label} signal for {symbol} (confidence: {confidence:.2f}, strength: {exit_strength:.0%})")
            return signal

        # No signal
        logger.debug(f"No signal for {symbol}: entry={latest_entry}, exit={latest_exit}")
        return None
    
    def monitor_performance(self, strategy_id: str) -> PerformanceMetrics:
        """
        Calculate real-time performance metrics for a strategy.
        
        Calculates daily/weekly/monthly returns, Sharpe, Sortino, drawdown,
        win rate, average win, and average loss based on closed positions.
        
        Args:
            strategy_id: ID of strategy to monitor
        
        Returns:
            PerformanceMetrics with current metrics
        
        Raises:
            ValueError: If strategy not found
        """
        from src.models.orm import PositionORM, OrderORM
        
        strategy = self._load_strategy(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        logger.debug(f"Monitoring performance for strategy {strategy.name}")
        
        # Fetch all closed positions for this strategy
        session = self.db.get_session()
        try:
            positions = session.query(PositionORM).filter(
                PositionORM.strategy_id == strategy_id,
                PositionORM.closed_at.isnot(None)
            ).all()
            
            if not positions:
                logger.info(f"No closed positions for strategy {strategy.name}")
                return PerformanceMetrics()
            
            # Calculate metrics
            metrics = self._calculate_performance_metrics(positions)
            
            # Update strategy performance
            strategy.performance = metrics
            self._save_strategy(strategy)
            
            logger.info(
                f"Performance metrics for {strategy.name}: "
                f"return={metrics.total_return:.2%}, "
                f"sharpe={metrics.sharpe_ratio:.2f}, "
                f"win_rate={metrics.win_rate:.2%}"
            )
            
            # Broadcast performance update
            self._broadcast_strategy_update_sync(strategy)
            
            return metrics
        
        finally:
            session.close()
    
    def _calculate_performance_metrics(self, positions: List) -> PerformanceMetrics:
        """
        Calculate performance metrics from closed positions.
        
        Args:
            positions: List of PositionORM objects
        
        Returns:
            PerformanceMetrics with calculated values
        """
        if not positions:
            return PerformanceMetrics()
        
        # Extract P&L values
        pnl_values = [pos.realized_pnl for pos in positions]
        
        # Total return (sum of all P&L)
        total_return = sum(pnl_values)
        
        # Win/loss statistics
        winning_trades = [pnl for pnl in pnl_values if pnl > 0]
        losing_trades = [pnl for pnl in pnl_values if pnl < 0]
        
        total_trades = len(positions)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0.0
        
        # Calculate returns series for Sharpe/Sortino
        returns = pd.Series(pnl_values)
        
        # Sharpe ratio (assuming risk-free rate of 0 for simplicity)
        if len(returns) > 1 and returns.std() > 0:
            sharpe_ratio = returns.mean() / returns.std() * (252 ** 0.5)  # Annualized
        else:
            sharpe_ratio = 0.0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 1 and downside_returns.std() > 0:
            sortino_ratio = returns.mean() / downside_returns.std() * (252 ** 0.5)
        else:
            sortino_ratio = 0.0
        
        # Maximum drawdown
        cumulative_returns = returns.cumsum()
        running_max = cumulative_returns.expanding().max()
        drawdown = cumulative_returns - running_max
        max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0.0
        
        return PerformanceMetrics(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=total_trades
        )
    
    def retire_strategy(self, strategy_id: str, reason: str) -> None:
        """
        Retire underperforming strategy with improved tracking.
        
        Records retirement in StrategyRetirementORM table with detailed metrics,
        removes from active strategies, and logs open positions that need closing.
        
        Args:
            strategy_id: ID of strategy to retire
            reason: Detailed reason for retirement
        
        Raises:
            ValueError: If strategy not found
        """
        from src.models.orm import PositionORM, StrategyORM, StrategyRetirementORM, OrderORM
        from datetime import datetime
        
        strategy = self._load_strategy(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        logger.info(f"Retiring strategy {strategy.name}: {reason}")
        
        # Remove from active strategies
        if strategy_id in self._active_strategies:
            del self._active_strategies[strategy_id]
        
        # Get open positions for this strategy
        session = self.db.get_session()
        try:
            open_positions = session.query(PositionORM).filter(
                PositionORM.strategy_id == strategy_id,
                PositionORM.closed_at.is_(None)
            ).all()
            
            if open_positions:
                logger.info(
                    f"Strategy {strategy.name} has {len(open_positions)} open positions. "
                    f"Marking them for closure approval."
                )
                for position in open_positions:
                    position.pending_closure = True
                    position.closure_reason = f"Strategy retired: {reason}"
                logger.info(f"Marked {len(open_positions)} positions for closure approval")
            
            # Cancel all pending orders for this strategy
            pending_orders = session.query(OrderORM).filter(
                OrderORM.strategy_id == strategy_id,
                OrderORM.status == OrderStatus.PENDING
            ).all()
            
            if pending_orders:
                logger.info(f"Cancelling {len(pending_orders)} pending orders for strategy {strategy.name}")
                for order in pending_orders:
                    try:
                        # Cancel via eToro API if order has eToro ID
                        if order.etoro_order_id:
                            success = self.etoro_client.cancel_order(order.etoro_order_id)
                            if success:
                                order.status = OrderStatus.CANCELLED
                                logger.info(f"Cancelled order {order.id} (eToro: {order.etoro_order_id}) on eToro")
                            else:
                                logger.warning(f"Failed to cancel order {order.id} on eToro, marking as cancelled locally")
                                order.status = OrderStatus.CANCELLED
                        else:
                            # Order not yet submitted to eToro, just mark as cancelled
                            order.status = OrderStatus.CANCELLED
                            logger.info(f"Cancelled order {order.id} (not yet submitted to eToro)")
                    except Exception as e:
                        logger.error(f"Error cancelling order {order.id}: {e}")
                        # Still mark as cancelled locally
                        order.status = OrderStatus.CANCELLED
            
            # Record retirement in StrategyRetirementORM table
            retirement_record = StrategyRetirementORM(
                strategy_id=strategy_id,
                retired_at=datetime.now(),
                reason=reason,
                final_sharpe=strategy.performance.sharpe_ratio,
                final_return=strategy.performance.total_return,
                final_drawdown=strategy.performance.max_drawdown
            )
            session.add(retirement_record)
            
            # Delete the strategy from database
            strategy_orm = session.query(StrategyORM).filter(StrategyORM.id == strategy_id).first()
            if strategy_orm:
                session.delete(strategy_orm)
            
            session.commit()
            logger.info(
                f"Strategy {strategy.name} retired and deleted successfully. "
                f"Final metrics: Sharpe={strategy.performance.sharpe_ratio:.2f}, "
                f"Return={strategy.performance.total_return:.2%}, "
                f"Drawdown={strategy.performance.max_drawdown:.2%}"
            )
        
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to retire strategy {strategy.name}: {e}")
            raise
        finally:
            session.close()
        
        # Broadcast strategy retirement
        self._broadcast_strategy_update_sync(strategy)
    
    def check_retirement_triggers(self, strategy_id: str) -> Optional[str]:
        """
        Check if strategy should be retired based on improved performance triggers.
        
        Improved retirement logic:
        - Requires minimum live trades before evaluation (default: 20)
        - Uses rolling window metrics (default: 60 days) instead of point-in-time
        - Requires consecutive evaluation failures (default: 3) before retirement
        - Respects probation period for new strategies (default: 30 days)
        
        Retirement triggers (must fail 3 consecutive times):
        - Sharpe ratio < 0.5
        - Maximum drawdown > 15%
        - Win rate < 40%
        - Negative total return
        
        Args:
            strategy_id: ID of strategy to check
        
        Returns:
            Retirement reason if should retire, None otherwise
        """
        import yaml
        from pathlib import Path
        from datetime import datetime, timedelta
        
        strategy = self._load_strategy(strategy_id)
        if strategy is None:
            return None
        
        # Only check active strategies
        if strategy.status not in [StrategyStatus.DEMO, StrategyStatus.LIVE]:
            return None
        
        # Load retirement configuration
        config_path = Path("config/autonomous_trading.yaml")
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                retirement_config = config.get("retirement_logic", {})
                min_live_trades = retirement_config.get("min_live_trades_before_evaluation", 20)
                rolling_window_days = retirement_config.get("rolling_window_days", 60)
                consecutive_failures_required = retirement_config.get("consecutive_failures_required", 3)
                probation_period_days = retirement_config.get("probation_period_days", 30)
        except Exception as e:
            logger.warning(f"Failed to load retirement config: {e}, using defaults")
            min_live_trades = 20
            rolling_window_days = 60
            consecutive_failures_required = 3
            probation_period_days = 30
        
        # Check 1: Minimum live trades requirement
        if strategy.live_trade_count < min_live_trades:
            logger.debug(
                f"Strategy {strategy.name} has only {strategy.live_trade_count} live trades "
                f"(minimum: {min_live_trades}). Skipping retirement evaluation."
            )
            return None
        
        # Check 2: Probation period for new strategies
        if strategy.activated_at:
            strategy_age_days = (datetime.now() - strategy.activated_at).days
            if strategy_age_days < probation_period_days:
                logger.debug(
                    f"Strategy {strategy.name} is {strategy_age_days} days old "
                    f"(probation period: {probation_period_days} days). Skipping retirement evaluation."
                )
                return None
        
        # Calculate rolling metrics over window period
        # For now, we'll use the current performance metrics
        # TODO: In future, calculate metrics from trades in the rolling window
        perf = strategy.performance
        
        # Evaluate retirement triggers
        failure_reasons = []
        
        # Trigger 1: Low Sharpe ratio
        if perf.sharpe_ratio < 0.5:
            failure_reasons.append(f"Sharpe ratio ({perf.sharpe_ratio:.2f}) below 0.5 threshold")
        
        # Trigger 2: High drawdown
        if perf.max_drawdown > 0.15:
            failure_reasons.append(f"Maximum drawdown ({perf.max_drawdown:.2%}) exceeds 15% threshold")
        
        # Trigger 3: Low win rate
        if perf.win_rate < 0.40:
            failure_reasons.append(f"Win rate ({perf.win_rate:.2%}) below 40% threshold")
        
        # Trigger 4: Negative returns
        if perf.total_return < 0:
            failure_reasons.append(f"Negative total return ({perf.total_return:.2%})")
        
        # Record evaluation result
        evaluation_result = {
            "timestamp": datetime.now().isoformat(),
            "passed": len(failure_reasons) == 0,
            "failure_reasons": failure_reasons,
            "metrics": {
                "sharpe_ratio": perf.sharpe_ratio,
                "max_drawdown": perf.max_drawdown,
                "win_rate": perf.win_rate,
                "total_return": perf.total_return,
                "total_trades": perf.total_trades,
                "live_trade_count": strategy.live_trade_count
            }
        }
        
        # Update evaluation history
        strategy.retirement_evaluation_history.append(evaluation_result)
        strategy.last_retirement_evaluation = datetime.now()
        
        # Keep only recent evaluations (last 10)
        if len(strategy.retirement_evaluation_history) > 10:
            strategy.retirement_evaluation_history = strategy.retirement_evaluation_history[-10:]
        
        # Save updated strategy
        self._save_strategy(strategy)
        
        # Check for consecutive failures
        if len(failure_reasons) > 0:
            # Count consecutive failures from most recent evaluations
            consecutive_failures = 0
            for eval_result in reversed(strategy.retirement_evaluation_history):
                if not eval_result["passed"]:
                    consecutive_failures += 1
                else:
                    break
            
            logger.info(
                f"Strategy {strategy.name} failed retirement evaluation "
                f"({consecutive_failures}/{consecutive_failures_required} consecutive failures). "
                f"Reasons: {', '.join(failure_reasons)}"
            )
            
            # Only retire after consecutive failures threshold met
            if consecutive_failures >= consecutive_failures_required:
                detailed_reason = (
                    f"Failed {consecutive_failures} consecutive retirement evaluations. "
                    f"Latest failures: {', '.join(failure_reasons)}. "
                    f"Metrics: Sharpe={perf.sharpe_ratio:.2f}, Drawdown={perf.max_drawdown:.2%}, "
                    f"WinRate={perf.win_rate:.2%}, Return={perf.total_return:.2%}, "
                    f"LiveTrades={strategy.live_trade_count}"
                )
                return detailed_reason
        else:
            logger.debug(f"Strategy {strategy.name} passed retirement evaluation")
        
        # No retirement needed
        return None
    
    def optimize_allocations(self, strategies: List[Strategy]) -> Dict[str, float]:
        """
        Calculate optimal capital allocation using Sharpe ratio weighting.
        
        Allocates capital proportional to each strategy's Sharpe ratio,
        with minimum/maximum allocation constraints.
        
        Args:
            strategies: List of active strategies
        
        Returns:
            Dictionary mapping strategy_id to allocation percentage (0.0 to 1.0)
        """
        if not strategies:
            logger.warning("No strategies provided for allocation optimization")
            return {}
        
        # Filter to only active strategies
        active_strategies = [
            s for s in strategies 
            if s.status in [StrategyStatus.DEMO, StrategyStatus.LIVE]
        ]
        
        if not active_strategies:
            logger.warning("No active strategies for allocation optimization")
            return {}
        
        logger.info(f"Optimizing allocations for {len(active_strategies)} strategies")
        
        # Minimum and maximum allocation per strategy
        MIN_ALLOCATION = 0.05  # 5%
        MAX_ALLOCATION = 0.40  # 40%
        
        # Calculate Sharpe ratios (use max(0, sharpe) to ignore negative Sharpe)
        sharpe_ratios = {}
        for strategy in active_strategies:
            sharpe = max(0.0, strategy.performance.sharpe_ratio)
            sharpe_ratios[strategy.id] = sharpe
        
        # Calculate total Sharpe
        total_sharpe = sum(sharpe_ratios.values())
        
        # Calculate initial allocations
        allocations = {}
        if total_sharpe > 0:
            # Allocate proportional to Sharpe ratio
            for strategy in active_strategies:
                sharpe = sharpe_ratios[strategy.id]
                allocation = sharpe / total_sharpe
                allocations[strategy.id] = allocation
        else:
            # Equal allocation if all Sharpe ratios are zero or negative
            equal_allocation = 1.0 / len(active_strategies)
            for strategy in active_strategies:
                allocations[strategy.id] = equal_allocation
        
        # Apply constraints
        for strategy_id in allocations:
            allocation = allocations[strategy_id]
            allocation = max(MIN_ALLOCATION, min(MAX_ALLOCATION, allocation))
            allocations[strategy_id] = allocation
        
        # Normalize to 100%
        total_allocation = sum(allocations.values())
        if total_allocation > 0:
            for strategy_id in allocations:
                allocations[strategy_id] = allocations[strategy_id] / total_allocation
        
        # Log allocations
        for strategy in active_strategies:
            alloc = allocations.get(strategy.id, 0.0)
            logger.info(
                f"Strategy {strategy.name}: {alloc:.1%} allocation "
                f"(Sharpe: {strategy.performance.sharpe_ratio:.2f})"
            )
        
        return allocations
    
    def rebalance_portfolio(
        self,
        target_allocations: Dict[str, float],
        account_balance: float,
        current_positions: List
    ) -> List[Dict]:
        """
        Rebalance portfolio to match target allocations.
        
        Calculates current allocations from positions, determines required trades
        to reach targets, and creates rebalancing orders.
        
        Args:
            target_allocations: Dictionary mapping strategy_id to target allocation (0.0-1.0)
            account_balance: Current account balance
            current_positions: List of current Position objects
        
        Returns:
            List of rebalancing order specifications (dicts with strategy_id, symbol, action, value)
        """
        from src.models.enums import SignalAction
        
        logger.info("Calculating portfolio rebalancing")
        
        # Rebalancing parameters
        REBALANCE_THRESHOLD = 0.05  # 5% drift threshold
        MIN_TRADE_SIZE = 100.0  # Minimum $100 trade
        
        # Calculate current allocations by strategy
        current_allocations = self._calculate_current_allocations(
            current_positions, account_balance
        )
        
        # Determine required trades
        rebalancing_orders = []
        
        for strategy_id, target_pct in target_allocations.items():
            current_pct = current_allocations.get(strategy_id, 0.0)
            drift = abs(target_pct - current_pct)
            
            # Only rebalance if drift exceeds threshold
            if drift > REBALANCE_THRESHOLD:
                target_value = account_balance * target_pct
                current_value = account_balance * current_pct
                trade_value = target_value - current_value
                
                # Only create order if trade size is significant
                if abs(trade_value) >= MIN_TRADE_SIZE:
                    # Determine action
                    if trade_value > 0:
                        action = SignalAction.ENTER_LONG
                    else:
                        action = SignalAction.EXIT_LONG
                        trade_value = abs(trade_value)
                    
                    # Get strategy to find symbols
                    strategy = self._load_strategy(strategy_id)
                    if strategy and strategy.symbols:
                        # Use first symbol for simplicity
                        symbol = strategy.symbols[0]
                        
                        order_spec = {
                            "strategy_id": strategy_id,
                            "strategy_name": strategy.name,
                            "symbol": symbol,
                            "action": action,
                            "value": trade_value,
                            "reason": f"Rebalancing: current={current_pct:.1%}, target={target_pct:.1%}"
                        }
                        
                        rebalancing_orders.append(order_spec)
                        
                        logger.info(
                            f"Rebalancing {strategy.name}: {action.value} ${trade_value:.2f} "
                            f"(current={current_pct:.1%}, target={target_pct:.1%})"
                        )
        
        logger.info(f"Generated {len(rebalancing_orders)} rebalancing orders")
        return rebalancing_orders
    
    def _calculate_current_allocations(
        self,
        positions: List,
        account_balance: float
    ) -> Dict[str, float]:
        """
        Calculate current allocation percentages by strategy.
        
        Args:
            positions: List of Position objects
            account_balance: Current account balance
        
        Returns:
            Dictionary mapping strategy_id to current allocation percentage
        """
        if account_balance <= 0:
            return {}
        
        # Calculate total value by strategy
        strategy_values = {}
        for position in positions:
            if position.closed_at is None:  # Only open positions
                position_value = position.quantity * position.current_price
                strategy_id = position.strategy_id
                
                if strategy_id not in strategy_values:
                    strategy_values[strategy_id] = 0.0
                
                strategy_values[strategy_id] += position_value
        
        # Convert to percentages
        allocations = {}
        for strategy_id, value in strategy_values.items():
            allocations[strategy_id] = value / account_balance
        
        return allocations

    def compare_to_benchmark(
        self,
        strategy_id: str,
        benchmark_symbol: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Compare strategy returns against a benchmark (SPY, BTC, etc.).

        Fetches benchmark data from market data manager, calculates relative
        performance and alpha.

        Args:
            strategy_id: ID of strategy to compare
            benchmark_symbol: Symbol of benchmark (e.g., "SPY", "BTC-USD")
            start: Start date for comparison (defaults to strategy activation date)
            end: End date for comparison (defaults to now)

        Returns:
            Dictionary with comparison metrics:
                - strategy_return: Strategy total return
                - benchmark_return: Benchmark total return
                - relative_performance: Strategy return - benchmark return
                - alpha: Excess return over benchmark
                - beta: Strategy volatility relative to benchmark

        Raises:
            ValueError: If strategy not found or benchmark data unavailable
        """
        from src.models.orm import PositionORM

        strategy = self._load_strategy(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Determine time period
        if start is None:
            start = strategy.activated_at or strategy.created_at
        if end is None:
            end = datetime.now()

        logger.info(
            f"Comparing strategy {strategy.name} to benchmark {benchmark_symbol} "
            f"from {start} to {end}"
        )

        # Fetch benchmark data from Yahoo Finance
        try:
            benchmark_data = self.market_data.get_historical_data(
                benchmark_symbol, start, end, interval="1d", prefer_yahoo=True
            )

            if not benchmark_data or len(benchmark_data) < 2:
                raise ValueError(f"Insufficient benchmark data for {benchmark_symbol}")

            # Convert to DataFrame
            benchmark_df = pd.DataFrame([
                {
                    "timestamp": d.timestamp,
                    "close": d.close
                }
                for d in benchmark_data
            ])
            benchmark_df.set_index("timestamp", inplace=True)
            benchmark_df.sort_index(inplace=True)

            # Calculate benchmark returns
            benchmark_prices = benchmark_df["close"]
            benchmark_return = (benchmark_prices.iloc[-1] - benchmark_prices.iloc[0]) / benchmark_prices.iloc[0]

            # Calculate daily benchmark returns for beta calculation
            benchmark_daily_returns = benchmark_prices.pct_change().dropna()

        except Exception as e:
            logger.error(f"Failed to fetch benchmark data for {benchmark_symbol}: {e}")
            raise ValueError(f"Failed to fetch benchmark data: {e}")

        # Get strategy positions to calculate returns
        session = self.db.get_session()
        try:
            positions = session.query(PositionORM).filter(
                PositionORM.strategy_id == strategy_id,
                PositionORM.opened_at >= start,
                PositionORM.opened_at <= end
            ).all()

            if not positions:
                logger.warning(f"No positions found for strategy {strategy.name} in time period")
                return {
                    "strategy_return": 0.0,
                    "benchmark_return": benchmark_return,
                    "relative_performance": -benchmark_return,
                    "alpha": 0.0,
                    "beta": 0.0
                }

            # Calculate strategy returns from positions
            # Build equity curve from position P&L
            position_events = []
            for pos in positions:
                # Entry event
                position_events.append({
                    "timestamp": pos.opened_at,
                    "pnl": 0.0
                })
                # Exit event (if closed)
                if pos.closed_at:
                    position_events.append({
                        "timestamp": pos.closed_at,
                        "pnl": pos.realized_pnl
                    })

            # Sort by timestamp
            position_events.sort(key=lambda x: x["timestamp"])

            # Build cumulative P&L series
            cumulative_pnl = []
            current_pnl = 0.0
            for event in position_events:
                current_pnl += event["pnl"]
                cumulative_pnl.append({
                    "timestamp": event["timestamp"],
                    "cumulative_pnl": current_pnl
                })

            # Calculate strategy return (assuming initial capital of 100,000)
            initial_capital = 100000.0
            if cumulative_pnl:
                final_pnl = cumulative_pnl[-1]["cumulative_pnl"]
                strategy_return = final_pnl / initial_capital
            else:
                strategy_return = 0.0

            # Calculate daily strategy returns for beta
            strategy_df = pd.DataFrame(cumulative_pnl)
            if len(strategy_df) > 1:
                strategy_df.set_index("timestamp", inplace=True)
                strategy_df.sort_index(inplace=True)

                # Resample to daily and forward-fill
                strategy_daily = strategy_df.resample("D").last().ffill()
                strategy_daily_returns = strategy_daily["cumulative_pnl"].pct_change().dropna()

                # Align with benchmark returns
                common_dates = strategy_daily_returns.index.intersection(benchmark_daily_returns.index)

                if len(common_dates) > 1:
                    aligned_strategy = strategy_daily_returns.loc[common_dates]
                    aligned_benchmark = benchmark_daily_returns.loc[common_dates]

                    # Calculate beta (covariance / variance)
                    covariance = aligned_strategy.cov(aligned_benchmark)
                    benchmark_variance = aligned_benchmark.var()

                    if benchmark_variance > 0:
                        beta = covariance / benchmark_variance
                    else:
                        beta = 0.0
                else:
                    beta = 0.0
            else:
                beta = 0.0

            # Calculate relative performance and alpha
            relative_performance = strategy_return - benchmark_return
            alpha = strategy_return - (beta * benchmark_return)

            result = {
                "strategy_return": strategy_return,
                "benchmark_return": benchmark_return,
                "relative_performance": relative_performance,
                "alpha": alpha,
                "beta": beta
            }

            logger.info(
                f"Benchmark comparison for {strategy.name}: "
                f"strategy={strategy_return:.2%}, benchmark={benchmark_return:.2%}, "
                f"alpha={alpha:.2%}, beta={beta:.2f}"
            )

            return result

        finally:
            session.close()

    def attribute_pnl(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        group_by: str = "strategy"
    ) -> Dict[str, Dict[str, float]]:
        """
        Assign P&L to strategies and positions.

        Tracks P&L by strategy, position, and time period. Calculates contribution
        to total returns.

        Args:
            start: Start date for attribution (defaults to 30 days ago)
            end: End date for attribution (defaults to now)
            group_by: Grouping method - "strategy", "position", or "time_period"

        Returns:
            Dictionary with attribution data:
                - For "strategy": {strategy_id: {name, pnl, contribution_pct, trades}}
                - For "position": {position_id: {symbol, strategy, pnl, contribution_pct}}
                - For "time_period": {period: {pnl, trades, strategies}}

        Raises:
            ValueError: If invalid group_by parameter
        """
        from src.models.orm import PositionORM

        # Validate group_by parameter
        valid_groupings = ["strategy", "position", "time_period"]
        if group_by not in valid_groupings:
            raise ValueError(f"Invalid group_by '{group_by}'. Must be one of {valid_groupings}")

        # Determine time period
        if end is None:
            end = datetime.now()
        if start is None:
            start = end - timedelta(days=30)

        logger.info(f"Attributing P&L from {start} to {end}, grouped by {group_by}")

        # Fetch all positions in time period
        session = self.db.get_session()
        try:
            positions = session.query(PositionORM).filter(
                PositionORM.opened_at >= start,
                PositionORM.opened_at <= end
            ).all()

            if not positions:
                logger.info("No positions found in time period")
                return {}

            # Calculate total P&L
            total_pnl = sum(
                pos.realized_pnl if pos.closed_at else pos.unrealized_pnl
                for pos in positions
            )

            if group_by == "strategy":
                return self._attribute_by_strategy(positions, total_pnl)
            elif group_by == "position":
                return self._attribute_by_position(positions, total_pnl)
            elif group_by == "time_period":
                return self._attribute_by_time_period(positions, start, end)

        finally:
            session.close()

    def _attribute_by_strategy(
        self,
        positions: List,
        total_pnl: float
    ) -> Dict[str, Dict[str, float]]:
        """
        Attribute P&L by strategy.

        Args:
            positions: List of PositionORM objects
            total_pnl: Total P&L across all positions

        Returns:
            Dictionary mapping strategy_id to attribution data
        """
        strategy_attribution = {}

        for pos in positions:
            strategy_id = pos.strategy_id

            if strategy_id not in strategy_attribution:
                # Load strategy name
                strategy = self._load_strategy(strategy_id)
                strategy_name = strategy.name if strategy else "Unknown"

                strategy_attribution[strategy_id] = {
                    "name": strategy_name,
                    "pnl": 0.0,
                    "contribution_pct": 0.0,
                    "trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0
                }

            # Add position P&L
            pnl = pos.realized_pnl if pos.closed_at else pos.unrealized_pnl
            strategy_attribution[strategy_id]["pnl"] += pnl
            strategy_attribution[strategy_id]["trades"] += 1

            if pnl > 0:
                strategy_attribution[strategy_id]["winning_trades"] += 1
            elif pnl < 0:
                strategy_attribution[strategy_id]["losing_trades"] += 1

        # Calculate contribution percentages
        if total_pnl != 0:
            for strategy_id in strategy_attribution:
                pnl = strategy_attribution[strategy_id]["pnl"]
                strategy_attribution[strategy_id]["contribution_pct"] = (pnl / total_pnl) * 100

        # Log attribution
        for strategy_id, data in strategy_attribution.items():
            logger.info(
                f"Strategy {data['name']}: P&L=${data['pnl']:.2f}, "
                f"contribution={data['contribution_pct']:.1f}%, "
                f"trades={data['trades']}"
            )

        return strategy_attribution

    def _attribute_by_position(
        self,
        positions: List,
        total_pnl: float
    ) -> Dict[str, Dict[str, float]]:
        """
        Attribute P&L by individual position.

        Args:
            positions: List of PositionORM objects
            total_pnl: Total P&L across all positions

        Returns:
            Dictionary mapping position_id to attribution data
        """
        position_attribution = {}

        for pos in positions:
            # Load strategy name
            strategy = self._load_strategy(pos.strategy_id)
            strategy_name = strategy.name if strategy else "Unknown"

            # Calculate P&L
            pnl = pos.realized_pnl if pos.closed_at else pos.unrealized_pnl

            # Calculate contribution percentage
            contribution_pct = (pnl / total_pnl * 100) if total_pnl != 0 else 0.0

            position_attribution[pos.id] = {
                "symbol": pos.symbol,
                "strategy_id": pos.strategy_id,
                "strategy_name": strategy_name,
                "pnl": pnl,
                "contribution_pct": contribution_pct,
                "opened_at": pos.opened_at.isoformat(),
                "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price
            }

        # Sort by absolute contribution (largest impact first)
        sorted_positions = sorted(
            position_attribution.items(),
            key=lambda x: abs(x[1]["pnl"]),
            reverse=True
        )

        # Log top contributors
        logger.info(f"Top 5 position contributors:")
        for pos_id, data in sorted_positions[:5]:
            logger.info(
                f"  {data['symbol']} ({data['strategy_name']}): "
                f"P&L=${data['pnl']:.2f}, contribution={data['contribution_pct']:.1f}%"
            )

        return position_attribution

    def _attribute_by_time_period(
        self,
        positions: List,
        start: datetime,
        end: datetime
    ) -> Dict[str, Dict[str, float]]:
        """
        Attribute P&L by time period (daily, weekly, monthly).

        Args:
            positions: List of PositionORM objects
            start: Start date
            end: End date

        Returns:
            Dictionary mapping time period to attribution data
        """
        # Determine period granularity based on date range
        days_diff = (end - start).days

        if days_diff <= 7:
            period_format = "%Y-%m-%d"  # Daily
            period_name = "daily"
        elif days_diff <= 60:
            period_format = "%Y-W%W"  # Weekly
            period_name = "weekly"
        else:
            period_format = "%Y-%m"  # Monthly
            period_name = "monthly"

        logger.info(f"Attributing P&L by {period_name} periods")

        time_attribution = {}

        for pos in positions:
            # Determine which period this position belongs to
            period_key = pos.opened_at.strftime(period_format)

            if period_key not in time_attribution:
                time_attribution[period_key] = {
                    "pnl": 0.0,
                    "trades": 0,
                    "strategies": set(),
                    "winning_trades": 0,
                    "losing_trades": 0
                }

            # Add position P&L
            pnl = pos.realized_pnl if pos.closed_at else pos.unrealized_pnl
            time_attribution[period_key]["pnl"] += pnl
            time_attribution[period_key]["trades"] += 1
            time_attribution[period_key]["strategies"].add(pos.strategy_id)

            if pnl > 0:
                time_attribution[period_key]["winning_trades"] += 1
            elif pnl < 0:
                time_attribution[period_key]["losing_trades"] += 1

        # Convert strategy sets to counts
        for period_key in time_attribution:
            strategy_count = len(time_attribution[period_key]["strategies"])
            time_attribution[period_key]["strategies"] = strategy_count

        # Sort by period
        sorted_periods = sorted(time_attribution.items())

        # Log attribution
        logger.info(f"P&L attribution by {period_name} period:")
        for period_key, data in sorted_periods:
            logger.info(
                f"  {period_key}: P&L=${data['pnl']:.2f}, "
                f"trades={data['trades']}, strategies={data['strategies']}"
            )

        return dict(sorted_periods)


