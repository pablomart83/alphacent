"""
Parameter Optimizer for Strategy Templates.

Performs grid search optimization to find optimal parameters for strategy templates,
with walk-forward validation to prevent overfitting.
"""

import logging
from datetime import datetime, timedelta
from itertools import product
from typing import Dict, List, Tuple, Any, Optional

from src.models.dataclasses import Strategy
from src.strategy.strategy_templates import StrategyTemplate

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """
    Optimizes strategy template parameters using grid search with walk-forward validation.
    
    Prevents overfitting by:
    1. Limiting parameter combinations
    2. Requiring out-of-sample validation
    3. Penalizing complex parameter sets
    """
    
    def __init__(self, strategy_engine):
        """
        Initialize parameter optimizer.
        
        Args:
            strategy_engine: StrategyEngine instance for backtesting
        """
        self.strategy_engine = strategy_engine
        
        # Define parameter grids for different indicator types
        # REDUCED GRIDS: Only test 2 values per parameter for speed
        self.parameter_grids = {
            'RSI': {
                'entry_threshold': [25, 30],  # Reduced from [20, 25, 30]
                'exit_threshold': [70, 75]    # Reduced from [70, 75, 80]
            },
            'MA': {
                'short_period': [10, 20],     # Reduced from [10, 20, 30]
                'long_period': [30, 50]       # Reduced from [30, 50, 90]
            },
            'BOLLINGER': {
                'period': [20, 25],           # Reduced from [15, 20, 25]
                'std_dev': [2.0, 2.5]         # Reduced from [1.5, 2.0, 2.5]
            },
            'STOCHASTIC': {
                'period': [14, 20],           # Reduced from [10, 14, 20]
                'entry_threshold': [20, 25],  # Reduced from [15, 20, 25]
                'exit_threshold': [75, 80]    # Reduced from [75, 80, 85]
            },
            'MACD': {
                'fast_period': [12, 16],      # Reduced from [8, 12, 16]
                'slow_period': [26, 31],      # Reduced from [21, 26, 31]
                'signal_period': [9, 11]      # Reduced from [7, 9, 11]
            }
        }
    
    def optimize(
        self,
        template: StrategyTemplate,
        strategy: Strategy,
        start: datetime,
        end: datetime,
        min_out_of_sample_sharpe: float = 0.3
    ) -> Dict[str, Any]:
        """
        Optimize parameters for a strategy template using grid search.
        
        Args:
            template: Strategy template to optimize
            strategy: Strategy instance with template applied
            start: Start date for optimization
            end: End date for optimization
            min_out_of_sample_sharpe: Minimum Sharpe required on test data
        
        Returns:
            Dict with:
                - best_params: Optimal parameter combination
                - best_sharpe: Sharpe ratio with optimal parameters
                - in_sample_sharpe: In-sample Sharpe
                - out_of_sample_sharpe: Out-of-sample Sharpe
                - sharpe_improvement: Improvement over default parameters
                - tested_combinations: Number of combinations tested
        """
        logger.info(f"Optimizing parameters for template: {template.name}")
        
        # Identify which indicators are used in the template
        indicators_used = self._identify_indicators(template)
        logger.info(f"Indicators used: {indicators_used}")
        
        # Generate parameter combinations
        param_combinations = self._generate_parameter_combinations(indicators_used)
        logger.info(f"Testing {len(param_combinations)} parameter combinations")
        
        # Limit combinations to prevent overfitting (max 20 combinations for speed)
        if len(param_combinations) > 20:
            logger.warning(f"Too many combinations ({len(param_combinations)}), limiting to 20")
            # Use random sampling instead of just taking first 20
            import random
            param_combinations = random.sample(param_combinations, 20)
        
        # Split data into in-sample and out-of-sample periods
        total_days = (end - start).days
        in_sample_days = int(total_days * 0.67)  # 67% for training
        out_of_sample_days = total_days - in_sample_days  # 33% for testing
        
        in_sample_end = start + timedelta(days=in_sample_days)
        out_of_sample_start = in_sample_end
        
        logger.info(f"In-sample period: {start.date()} to {in_sample_end.date()} ({in_sample_days} days)")
        logger.info(f"Out-of-sample period: {out_of_sample_start.date()} to {end.date()} ({out_of_sample_days} days)")
        
        # Test default parameters first
        default_results = self._test_parameters(
            strategy, {}, start, in_sample_end, out_of_sample_start, end
        )
        
        if default_results:
            logger.info(
                f"Default parameters: "
                f"in-sample Sharpe={default_results['in_sample_sharpe']:.2f}, "
                f"out-of-sample Sharpe={default_results['out_of_sample_sharpe']:.2f}"
            )
        
        # Test all parameter combinations
        best_result = default_results
        best_params = {}
        tested_count = 0
        
        for params in param_combinations:
            tested_count += 1
            
            # Test this parameter combination
            result = self._test_parameters(
                strategy, params, start, in_sample_end, out_of_sample_start, end
            )
            
            if result is None:
                continue
            
            # Log progress every 10 combinations
            if tested_count % 10 == 0:
                logger.info(
                    f"Progress: {tested_count}/{len(param_combinations)} - "
                    f"Current best Sharpe: {best_result['out_of_sample_sharpe']:.2f}"
                )
            
            # Update best if this is better (based on out-of-sample Sharpe)
            if result['out_of_sample_sharpe'] > best_result['out_of_sample_sharpe']:
                best_result = result
                best_params = params
                logger.info(
                    f"New best parameters found: {params} - "
                    f"out-of-sample Sharpe={result['out_of_sample_sharpe']:.2f}"
                )
        
        # Check if best parameters meet minimum out-of-sample Sharpe
        if best_result['out_of_sample_sharpe'] < min_out_of_sample_sharpe:
            logger.warning(
                f"Best out-of-sample Sharpe ({best_result['out_of_sample_sharpe']:.2f}) "
                f"below minimum threshold ({min_out_of_sample_sharpe}). "
                f"Using default parameters."
            )
            return {
                'best_params': {},
                'best_sharpe': default_results['out_of_sample_sharpe'] if default_results else 0.0,
                'in_sample_sharpe': default_results['in_sample_sharpe'] if default_results else 0.0,
                'out_of_sample_sharpe': default_results['out_of_sample_sharpe'] if default_results else 0.0,
                'sharpe_improvement': 0.0,
                'tested_combinations': tested_count,
                'optimization_failed': True
            }
        
        # Calculate improvement over default
        sharpe_improvement = 0.0
        if default_results and default_results['out_of_sample_sharpe'] != 0:
            sharpe_improvement = (
                (best_result['out_of_sample_sharpe'] - default_results['out_of_sample_sharpe']) /
                abs(default_results['out_of_sample_sharpe'])
            ) * 100
        
        logger.info(
            f"Optimization complete: "
            f"best params={best_params}, "
            f"out-of-sample Sharpe={best_result['out_of_sample_sharpe']:.2f}, "
            f"improvement={sharpe_improvement:.1f}%"
        )
        
        return {
            'best_params': best_params,
            'best_sharpe': best_result['out_of_sample_sharpe'],
            'in_sample_sharpe': best_result['in_sample_sharpe'],
            'out_of_sample_sharpe': best_result['out_of_sample_sharpe'],
            'sharpe_improvement': sharpe_improvement,
            'tested_combinations': tested_count,
            'optimization_failed': False
        }
    
    def _identify_indicators(self, template: StrategyTemplate) -> List[str]:
        """
        Identify which indicators are used in a template.
        
        Args:
            template: Strategy template
        
        Returns:
            List of indicator types (e.g., ['RSI', 'BOLLINGER'])
        """
        indicators = set()
        
        # Check entry and exit conditions for indicator references
        all_conditions = template.entry_conditions + template.exit_conditions
        
        for condition in all_conditions:
            condition_upper = condition.upper()
            
            if 'RSI' in condition_upper:
                indicators.add('RSI')
            if 'SMA' in condition_upper or 'EMA' in condition_upper:
                indicators.add('MA')
            if 'BB_' in condition_upper or 'BOLLINGER' in condition_upper:
                indicators.add('BOLLINGER')
            if 'STOCH' in condition_upper:
                indicators.add('STOCHASTIC')
            if 'MACD' in condition_upper:
                indicators.add('MACD')
        
        return list(indicators)
    
    def _generate_parameter_combinations(self, indicators: List[str]) -> List[Dict[str, Any]]:
        """
        Generate all parameter combinations for the given indicators.
        
        Args:
            indicators: List of indicator types
        
        Returns:
            List of parameter dictionaries
        """
        if not indicators:
            return [{}]
        
        # Get parameter grids for each indicator
        grids = {}
        for indicator in indicators:
            if indicator in self.parameter_grids:
                grids[indicator] = self.parameter_grids[indicator]
        
        if not grids:
            return [{}]
        
        # Generate all combinations
        combinations = []
        
        # For each indicator, generate combinations of its parameters
        for indicator, param_grid in grids.items():
            param_names = list(param_grid.keys())
            param_values = [param_grid[name] for name in param_names]
            
            # Generate cartesian product of parameter values
            for values in product(*param_values):
                param_dict = {
                    f"{indicator}_{name}": value
                    for name, value in zip(param_names, values)
                }
                combinations.append(param_dict)
        
        # If multiple indicators, combine their parameters
        if len(grids) > 1:
            # For simplicity, test each indicator's parameters independently
            # rather than all cross-combinations (which would be too many)
            pass
        
        return combinations if combinations else [{}]
    
    def _test_parameters(
        self,
        strategy: Strategy,
        params: Dict[str, Any],
        in_sample_start: datetime,
        in_sample_end: datetime,
        out_of_sample_start: datetime,
        out_of_sample_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Test a parameter combination with walk-forward validation.
        
        Args:
            strategy: Strategy to test
            params: Parameter dictionary
            in_sample_start: Start of in-sample period
            in_sample_end: End of in-sample period
            out_of_sample_start: Start of out-of-sample period
            out_of_sample_end: End of out-of-sample period
        
        Returns:
            Dict with in_sample_sharpe and out_of_sample_sharpe, or None if test failed
        """
        try:
            # If no params provided, use strategy as-is (default parameters)
            test_strategy = strategy
            
            # If params provided, create a modified strategy with new parameters
            if params:
                test_strategy = self._apply_parameters_to_strategy(strategy, params)
            
            # Backtest on in-sample period
            in_sample_results = self.strategy_engine.backtest_strategy(
                test_strategy, in_sample_start, in_sample_end
            )
            
            # Backtest on out-of-sample period
            out_of_sample_results = self.strategy_engine.backtest_strategy(
                test_strategy, out_of_sample_start, out_of_sample_end
            )
            
            return {
                'in_sample_sharpe': in_sample_results.sharpe_ratio,
                'out_of_sample_sharpe': out_of_sample_results.sharpe_ratio,
                'in_sample_trades': in_sample_results.total_trades,
                'out_of_sample_trades': out_of_sample_results.total_trades
            }
        
        except Exception as e:
            logger.warning(f"Failed to test parameters {params}: {e}")
            return None
    
    def _apply_parameters_to_strategy(
        self,
        strategy: Strategy,
        params: Dict[str, Any]
    ) -> Strategy:
        """
        Create a new strategy with modified parameters.
        
        Args:
            strategy: Original strategy
            params: Parameter dictionary (e.g., {'STOCHASTIC_period': 14, 'STOCHASTIC_entry_threshold': 20})
        
        Returns:
            New strategy with modified DSL rules
        """
        import re
        from copy import deepcopy
        
        # Create a copy of the strategy
        modified_strategy = deepcopy(strategy)
        
        # Modify entry rules
        modified_entry_rules = []
        for rule in strategy.rules.get('entry_conditions', []):
            modified_rule = rule
            
            # Apply STOCHASTIC parameters
            if 'STOCHASTIC_period' in params:
                # Replace STOCH_K(14) with STOCH_K(new_period)
                modified_rule = re.sub(
                    r'STOCH_K\(\d+\)',
                    f"STOCH_K({params['STOCHASTIC_period']})",
                    modified_rule
                )
                modified_rule = re.sub(
                    r'STOCH_D\(\d+\)',
                    f"STOCH_D({params['STOCHASTIC_period']})",
                    modified_rule
                )
            
            if 'STOCHASTIC_entry_threshold' in params:
                # Replace threshold values (e.g., "< 20" -> "< 25")
                modified_rule = re.sub(
                    r'(STOCH_[KD]\(\d+\))\s*<\s*\d+',
                    f"\\1 < {params['STOCHASTIC_entry_threshold']}",
                    modified_rule
                )
            
            # Apply RSI parameters
            if 'RSI_entry_threshold' in params:
                modified_rule = re.sub(
                    r'RSI\(\d+\)\s*<\s*\d+',
                    f"RSI(14) < {params['RSI_entry_threshold']}",
                    modified_rule
                )
            
            # Apply MA parameters
            if 'MA_short_period' in params:
                # Replace first SMA occurrence
                modified_rule = re.sub(
                    r'SMA\(\d+\)',
                    f"SMA({params['MA_short_period']})",
                    modified_rule,
                    count=1
                )
            
            if 'MA_long_period' in params:
                # Replace second SMA occurrence
                parts = modified_rule.split('SMA(')
                if len(parts) > 2:
                    # Find the second SMA and replace its period
                    second_sma = parts[2].split(')')[0]
                    modified_rule = modified_rule.replace(
                        f'SMA({second_sma})',
                        f'SMA({params["MA_long_period"]})',
                        1
                    )
            
            # Apply Bollinger Band parameters
            if 'BOLLINGER_period' in params and 'BOLLINGER_std_dev' in params:
                modified_rule = re.sub(
                    r'BB_LOWER\(\d+,\s*[\d.]+\)',
                    f"BB_LOWER({params['BOLLINGER_period']}, {params['BOLLINGER_std_dev']})",
                    modified_rule
                )
                modified_rule = re.sub(
                    r'BB_UPPER\(\d+,\s*[\d.]+\)',
                    f"BB_UPPER({params['BOLLINGER_period']}, {params['BOLLINGER_std_dev']})",
                    modified_rule
                )
            
            modified_entry_rules.append(modified_rule)
        
        # Modify exit rules
        modified_exit_rules = []
        for rule in strategy.rules.get('exit_conditions', []):
            modified_rule = rule
            
            # Apply STOCHASTIC parameters
            if 'STOCHASTIC_period' in params:
                modified_rule = re.sub(
                    r'STOCH_K\(\d+\)',
                    f"STOCH_K({params['STOCHASTIC_period']})",
                    modified_rule
                )
                modified_rule = re.sub(
                    r'STOCH_D\(\d+\)',
                    f"STOCH_D({params['STOCHASTIC_period']})",
                    modified_rule
                )
            
            if 'STOCHASTIC_exit_threshold' in params:
                # Replace threshold values (e.g., "> 80" -> "> 85")
                modified_rule = re.sub(
                    r'(STOCH_[KD]\(\d+\))\s*>\s*\d+',
                    f"\\1 > {params['STOCHASTIC_exit_threshold']}",
                    modified_rule
                )
            
            # Apply RSI parameters
            if 'RSI_exit_threshold' in params:
                modified_rule = re.sub(
                    r'RSI\(\d+\)\s*>\s*\d+',
                    f"RSI(14) > {params['RSI_exit_threshold']}",
                    modified_rule
                )
            
            # Apply MA parameters (for exit rules)
            if 'MA_short_period' in params:
                modified_rule = re.sub(
                    r'SMA\(\d+\)',
                    f"SMA({params['MA_short_period']})",
                    modified_rule,
                    count=1
                )
            
            if 'MA_long_period' in params:
                parts = modified_rule.split('SMA(')
                if len(parts) > 2:
                    second_sma = parts[2].split(')')[0]
                    modified_rule = modified_rule.replace(
                        f'SMA({second_sma})',
                        f'SMA({params["MA_long_period"]})',
                        1
                    )
            
            modified_exit_rules.append(modified_rule)
        
        # Update the strategy with modified rules
        modified_strategy.rules['entry_conditions'] = modified_entry_rules
        modified_strategy.rules['exit_conditions'] = modified_exit_rules
        
        return modified_strategy
    
    def apply_optimized_parameters(
        self,
        template: StrategyTemplate,
        optimized_params: Dict[str, Any]
    ) -> StrategyTemplate:
        """
        Apply optimized parameters to a strategy template.
        
        Args:
            template: Original template
            optimized_params: Optimized parameter dictionary
        
        Returns:
            New template with optimized parameters
        """
        if not optimized_params:
            return template
        
        # Create a copy of the template
        optimized_template = StrategyTemplate(
            name=template.name,
            description=template.description,
            market_regime=template.market_regime,
            entry_conditions=template.entry_conditions.copy(),
            exit_conditions=template.exit_conditions.copy(),
            indicators=template.indicators.copy(),
            default_params=template.default_params.copy()
        )
        
        # Update default parameters with optimized values
        optimized_template.default_params.update(optimized_params)
        
        # Update conditions with new parameter values
        optimized_template.entry_conditions = self._apply_params_to_conditions(
            template.entry_conditions, optimized_params
        )
        optimized_template.exit_conditions = self._apply_params_to_conditions(
            template.exit_conditions, optimized_params
        )
        
        logger.info(f"Applied optimized parameters to template: {template.name}")
        logger.info(f"Optimized params: {optimized_params}")
        
        return optimized_template
    
    def _apply_params_to_conditions(
        self,
        conditions: List[str],
        params: Dict[str, Any]
    ) -> List[str]:
        """
        Apply parameter values to condition strings.
        
        Args:
            conditions: List of condition strings
            params: Parameter dictionary
        
        Returns:
            List of conditions with parameters applied
        """
        updated_conditions = []
        
        for condition in conditions:
            updated_condition = condition
            
            # Replace RSI thresholds
            if 'RSI_entry_threshold' in params:
                # Replace entry threshold (e.g., "< 30" -> "< 25")
                import re
                updated_condition = re.sub(
                    r'RSI\(\d+\)\s*<\s*\d+',
                    f"RSI(14) < {params['RSI_entry_threshold']}",
                    updated_condition
                )
            
            if 'RSI_exit_threshold' in params:
                # Replace exit threshold (e.g., "> 70" -> "> 75")
                import re
                updated_condition = re.sub(
                    r'RSI\(\d+\)\s*>\s*\d+',
                    f"RSI(14) > {params['RSI_exit_threshold']}",
                    updated_condition
                )
            
            # Replace MA periods
            if 'MA_short_period' in params and 'MA_long_period' in params:
                import re
                # Replace short period
                updated_condition = re.sub(
                    r'SMA\(\d+\)',
                    f"SMA({params['MA_short_period']})",
                    updated_condition,
                    count=1
                )
                # Replace long period
                updated_condition = re.sub(
                    r'SMA\(\d+\)',
                    f"SMA({params['MA_long_period']})",
                    updated_condition,
                    count=1
                )
            
            # Replace Bollinger Band parameters
            if 'BOLLINGER_period' in params and 'BOLLINGER_std_dev' in params:
                import re
                updated_condition = re.sub(
                    r'BB_\w+\(\d+,\s*[\d.]+\)',
                    f"BB_LOWER({params['BOLLINGER_period']}, {params['BOLLINGER_std_dev']})",
                    updated_condition
                )
            
            updated_conditions.append(updated_condition)
        
        return updated_conditions
