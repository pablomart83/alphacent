"""
Adaptive Walk-Forward Analysis with Parameter Optimization.

Implements rolling window validation where parameters are re-optimized on each
training window and tested on the corresponding test window. Includes parameter
stability analysis and performance degradation detection.
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass

from src.models.dataclasses import Strategy
from src.strategy.strategy_templates import StrategyTemplate, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Results from a single walk-forward window."""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_sharpe: float
    test_sharpe: float
    train_return: float
    test_return: float
    train_trades: int
    test_trades: int
    optimized_params: Dict[str, Any]
    train_regime: MarketRegime
    test_regime: MarketRegime
    performance_degradation: float


@dataclass
class AdaptiveWalkForwardResults:
    """Complete results from adaptive walk-forward analysis."""
    strategy_name: str
    total_windows: int
    window_results: List[WindowResult]
    
    # Aggregated metrics
    avg_train_sharpe: float
    avg_test_sharpe: float
    avg_degradation: float
    
    # Parameter stability
    parameter_stability_score: float  # 0-1, higher is more stable
    parameter_variance: Dict[str, float]  # Variance for each parameter
    
    # Performance trend
    performance_trend: str  # "improving", "stable", "degrading"
    trend_slope: float  # Slope of test Sharpe over time
    
    # Regime adaptation
    regime_consistency: float  # 0-1, how often train/test regimes match
    regime_specific_performance: Dict[MarketRegime, float]  # Avg Sharpe by regime
    
    # Overall assessment
    is_stable: bool  # Parameters are stable across windows
    is_degrading: bool  # Performance is consistently declining
    is_regime_adaptive: bool  # Works well across different regimes
    passes_validation: bool  # Overall pass/fail


class AdaptiveWalkForwardAnalyzer:
    """
    Performs adaptive walk-forward analysis with parameter optimization.
    
    Key features:
    1. Re-optimizes parameters on each training window
    2. Tests optimized parameters on corresponding test window
    3. Tracks parameter stability across windows
    4. Detects performance degradation over time
    5. Analyzes regime-specific performance
    """
    
    def __init__(
        self,
        strategy_engine,
        parameter_optimizer,
        market_analyzer
    ):
        """
        Initialize adaptive walk-forward analyzer.
        
        Args:
            strategy_engine: StrategyEngine for backtesting
            parameter_optimizer: ParameterOptimizer for parameter optimization
            market_analyzer: MarketStatisticsAnalyzer for regime detection
        """
        self.strategy_engine = strategy_engine
        self.parameter_optimizer = parameter_optimizer
        self.market_analyzer = market_analyzer
    
    def analyze(
        self,
        template: StrategyTemplate,
        strategy: Strategy,
        start: datetime,
        end: datetime,
        window_size_days: int = 240,  # 8 months per window
        step_size_days: int = 60,  # 2 months step (rolling)
        min_test_sharpe: float = 0.3,
        max_param_variance: float = 0.5,
        max_degradation_slope: float = -0.1,
        skip_optimization: bool = False,  # Skip parameter optimization to speed up
        optimize_once: bool = True  # NEW: Only optimize on first window, reuse for others
    ) -> AdaptiveWalkForwardResults:
        """
        Perform adaptive walk-forward analysis.
        
        Args:
            template: Strategy template being tested
            strategy: Strategy instance
            start: Start date for analysis
            end: End date for analysis
            window_size_days: Size of each train+test window (default 240 days = 8 months)
            step_size_days: Step size for rolling windows (default 60 days = 2 months)
            min_test_sharpe: Minimum acceptable test Sharpe (default 0.3)
            max_param_variance: Maximum acceptable parameter variance (default 0.5)
            max_degradation_slope: Maximum acceptable degradation slope (default -0.1)
            skip_optimization: Skip all optimization (fastest, but less accurate)
            optimize_once: Optimize only on first window, reuse parameters (good balance)
        
        Returns:
            AdaptiveWalkForwardResults with comprehensive analysis
        """
        logger.info(f"Starting adaptive walk-forward analysis for {strategy.name}")
        logger.info(f"Period: {start.date()} to {end.date()}")
        logger.info(f"Window size: {window_size_days} days, Step size: {step_size_days} days")
        logger.info(f"Optimization mode: {'skip' if skip_optimization else ('once' if optimize_once else 'every window')}")
        
        # Split each window into train (67%) and test (33%)
        train_days = int(window_size_days * 0.67)
        test_days = window_size_days - train_days
        
        # Generate rolling windows
        windows = self._generate_windows(
            start, end, train_days, test_days, step_size_days
        )
        
        logger.info(f"Generated {len(windows)} rolling windows")
        
        # Optimize once on first window if optimize_once=True
        shared_params = {}
        if optimize_once and not skip_optimization and len(windows) > 0:
            logger.info("\n=== OPTIMIZING PARAMETERS ON FIRST WINDOW (will reuse for all windows) ===")
            train_start, train_end, _, _ = windows[0]
            optimization_result = self.parameter_optimizer.optimize(
                template=template,
                strategy=strategy,
                start=train_start,
                end=train_end,
                min_out_of_sample_sharpe=0.0
            )
            shared_params = optimization_result['best_params']
            logger.info(f"Optimized parameters (will use for all windows): {shared_params}")
        
        # Process each window
        window_results = []
        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            logger.info(f"\n--- Window {i+1}/{len(windows)} ---")
            logger.info(f"Train: {train_start.date()} to {train_end.date()}")
            logger.info(f"Test: {test_start.date()} to {test_end.date()}")
            
            try:
                window_result = self._process_window(
                    template, strategy, i+1,
                    train_start, train_end, test_start, test_end,
                    skip_optimization,
                    shared_params if optimize_once else None
                )
                window_results.append(window_result)
                
                logger.info(f"Train Sharpe: {window_result.train_sharpe:.2f}")
                logger.info(f"Test Sharpe: {window_result.test_sharpe:.2f}")
                logger.info(f"Degradation: {window_result.performance_degradation:.1f}%")
                logger.info(f"Optimized params: {window_result.optimized_params}")
                
            except Exception as e:
                logger.error(f"Window {i+1} failed: {e}")
                continue
        
        if not window_results:
            raise ValueError("No windows completed successfully")
        
        # Analyze results
        results = self._analyze_results(
            strategy.name, window_results,
            min_test_sharpe, max_param_variance, max_degradation_slope
        )
        
        # Log summary
        self._log_summary(results)
        
        return results
    
    def _generate_windows(
        self,
        start: datetime,
        end: datetime,
        train_days: int,
        test_days: int,
        step_size_days: int
    ) -> List[Tuple[datetime, datetime, datetime, datetime]]:
        """
        Generate rolling windows for walk-forward analysis.
        
        Returns:
            List of (train_start, train_end, test_start, test_end) tuples
        """
        windows = []
        window_size = train_days + test_days
        
        current_start = start
        while True:
            train_start = current_start
            train_end = train_start + timedelta(days=train_days)
            test_start = train_end
            test_end = test_start + timedelta(days=test_days)
            
            # Check if we have enough data
            if test_end > end:
                break
            
            windows.append((train_start, train_end, test_start, test_end))
            
            # Move to next window
            current_start += timedelta(days=step_size_days)
        
        return windows
    
    def _process_window(
        self,
        template: StrategyTemplate,
        strategy: Strategy,
        window_id: int,
        train_start: datetime,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime,
        skip_optimization: bool = False,
        shared_params: Dict[str, Any] = None  # NEW: Pre-optimized params to reuse
    ) -> WindowResult:
        """
        Process a single walk-forward window.
        
        Steps:
        1. Detect regime in training window
        2. Optimize parameters on training data (or use shared_params)
        3. Backtest with optimized parameters on training data
        4. Test with same parameters on test data
        5. Detect regime in test window
        6. Calculate metrics
        """
        # Detect regime in training window
        train_regime = self._detect_regime(strategy.symbols[0], train_start, train_end)
        logger.info(f"Train regime: {train_regime}")
        
        # Determine which parameters to use
        if shared_params is not None:
            # Use pre-optimized parameters from first window
            optimized_params = shared_params
            logger.info(f"Using shared parameters: {optimized_params}")
        elif skip_optimization:
            # Use default parameters (no optimization)
            optimized_params = {}
            logger.info("Using default parameters (no optimization)")
        else:
            # Optimize parameters on this training window
            logger.info("Optimizing parameters on training data...")
            optimization_result = self.parameter_optimizer.optimize(
                template=template,
                strategy=strategy,
                start=train_start,
                end=train_end,
                min_out_of_sample_sharpe=0.0  # Don't filter during window optimization
            )
            optimized_params = optimization_result['best_params']
            logger.info(f"Optimized parameters: {optimized_params}")
        
        # Apply optimized parameters to strategy
        if optimized_params:
            optimized_template = self.parameter_optimizer.apply_optimized_parameters(
                template, optimized_params
            )
            # Update strategy with optimized template
            strategy.rules = {
                'entry_conditions': optimized_template.entry_conditions,
                'exit_conditions': optimized_template.exit_conditions,
                'indicators': optimized_template.indicators
            }
        
        # Backtest on training data
        train_results = self.strategy_engine.backtest_strategy(
            strategy, train_start, train_end
        )
        
        # Backtest on test data (out-of-sample)
        test_results = self.strategy_engine.backtest_strategy(
            strategy, test_start, test_end
        )
        
        # Detect regime in test window
        test_regime = self._detect_regime(strategy.symbols[0], test_start, test_end)
        logger.info(f"Test regime: {test_regime}")
        
        # Calculate performance degradation
        if train_results.sharpe_ratio != 0:
            degradation = (
                (train_results.sharpe_ratio - test_results.sharpe_ratio) /
                abs(train_results.sharpe_ratio)
            ) * 100
        else:
            degradation = 0.0
        
        return WindowResult(
            window_id=window_id,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_sharpe=train_results.sharpe_ratio,
            test_sharpe=test_results.sharpe_ratio,
            train_return=train_results.total_return,
            test_return=test_results.total_return,
            train_trades=train_results.total_trades,
            test_trades=test_results.total_trades,
            optimized_params=optimized_params,
            train_regime=train_regime,
            test_regime=test_regime,
            performance_degradation=degradation
        )
    
    def _detect_regime(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> MarketRegime:
        """Detect market regime for a time period."""
        try:
            regime, confidence, data_quality, metrics = self.market_analyzer.detect_sub_regime([symbol])
            return regime
        except Exception as e:
            logger.warning(f"Could not detect regime: {e}, defaulting to RANGING")
            return MarketRegime.RANGING
    
    def _analyze_results(
        self,
        strategy_name: str,
        window_results: List[WindowResult],
        min_test_sharpe: float,
        max_param_variance: float,
        max_degradation_slope: float
    ) -> AdaptiveWalkForwardResults:
        """
        Analyze window results and compute aggregate metrics.
        """
        # Calculate average metrics
        avg_train_sharpe = np.mean([w.train_sharpe for w in window_results])
        avg_test_sharpe = np.mean([w.test_sharpe for w in window_results])
        avg_degradation = np.mean([w.performance_degradation for w in window_results])
        
        # Analyze parameter stability
        param_stability, param_variance = self._analyze_parameter_stability(window_results)
        
        # Analyze performance trend
        trend, trend_slope = self._analyze_performance_trend(window_results)
        
        # Analyze regime consistency
        regime_consistency, regime_performance = self._analyze_regime_performance(window_results)
        
        # Determine pass/fail criteria
        is_stable = param_stability >= (1 - max_param_variance)
        is_degrading = trend_slope < max_degradation_slope
        is_regime_adaptive = regime_consistency >= 0.5  # At least 50% regime match
        
        # Overall pass: good test Sharpe, stable params, not degrading
        passes_validation = (
            avg_test_sharpe >= min_test_sharpe and
            is_stable and
            not is_degrading
        )
        
        return AdaptiveWalkForwardResults(
            strategy_name=strategy_name,
            total_windows=len(window_results),
            window_results=window_results,
            avg_train_sharpe=avg_train_sharpe,
            avg_test_sharpe=avg_test_sharpe,
            avg_degradation=avg_degradation,
            parameter_stability_score=param_stability,
            parameter_variance=param_variance,
            performance_trend=trend,
            trend_slope=trend_slope,
            regime_consistency=regime_consistency,
            regime_specific_performance=regime_performance,
            is_stable=is_stable,
            is_degrading=is_degrading,
            is_regime_adaptive=is_regime_adaptive,
            passes_validation=passes_validation
        )
    
    def _analyze_parameter_stability(
        self,
        window_results: List[WindowResult]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Analyze parameter stability across windows.
        
        Returns:
            (stability_score, parameter_variance_dict)
            stability_score: 0-1, higher is more stable
            parameter_variance_dict: variance for each parameter
        """
        # Collect all parameter values across windows
        param_values = {}
        for window in window_results:
            for param_name, param_value in window.optimized_params.items():
                if param_name not in param_values:
                    param_values[param_name] = []
                param_values[param_name].append(param_value)
        
        # Calculate variance for each parameter
        param_variance = {}
        for param_name, values in param_values.items():
            if len(values) > 1:
                # Normalize variance by mean to get coefficient of variation
                mean_val = np.mean(values)
                if mean_val != 0:
                    variance = np.var(values)
                    cv = np.sqrt(variance) / abs(mean_val)  # Coefficient of variation
                    param_variance[param_name] = cv
                else:
                    param_variance[param_name] = 0.0
            else:
                param_variance[param_name] = 0.0
        
        # Calculate overall stability score (inverse of average variance)
        if param_variance:
            avg_variance = np.mean(list(param_variance.values()))
            stability_score = 1.0 / (1.0 + avg_variance)  # Maps [0, inf] to [0, 1]
        else:
            stability_score = 1.0  # No parameters = perfectly stable
        
        return stability_score, param_variance
    
    def _analyze_performance_trend(
        self,
        window_results: List[WindowResult]
    ) -> Tuple[str, float]:
        """
        Analyze performance trend over time.
        
        Returns:
            (trend_description, trend_slope)
            trend_description: "improving", "stable", or "degrading"
            trend_slope: slope of test Sharpe over time
        """
        # Extract test Sharpe values
        test_sharpes = [w.test_sharpe for w in window_results]
        
        if len(test_sharpes) < 2:
            return "stable", 0.0
        
        # Fit linear regression to test Sharpe over time
        x = np.arange(len(test_sharpes))
        y = np.array(test_sharpes)
        
        # Calculate slope using least squares
        slope = np.polyfit(x, y, 1)[0]
        
        # Classify trend
        if slope > 0.05:
            trend = "improving"
        elif slope < -0.05:
            trend = "degrading"
        else:
            trend = "stable"
        
        return trend, slope
    
    def _analyze_regime_performance(
        self,
        window_results: List[WindowResult]
    ) -> Tuple[float, Dict[MarketRegime, float]]:
        """
        Analyze regime consistency and regime-specific performance.
        
        Returns:
            (regime_consistency, regime_specific_performance)
            regime_consistency: 0-1, how often train/test regimes match
            regime_specific_performance: avg test Sharpe by regime
        """
        # Calculate regime consistency
        matching_regimes = sum(
            1 for w in window_results
            if w.train_regime == w.test_regime
        )
        regime_consistency = matching_regimes / len(window_results)
        
        # Calculate average performance by test regime
        regime_performance = {}
        for regime in MarketRegime:
            regime_sharpes = [
                w.test_sharpe for w in window_results
                if w.test_regime == regime
            ]
            if regime_sharpes:
                regime_performance[regime] = np.mean(regime_sharpes)
        
        return regime_consistency, regime_performance
    
    def _log_summary(self, results: AdaptiveWalkForwardResults):
        """Log summary of adaptive walk-forward analysis."""
        logger.info("\n" + "=" * 80)
        logger.info("ADAPTIVE WALK-FORWARD ANALYSIS SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Strategy: {results.strategy_name}")
        logger.info(f"Total Windows: {results.total_windows}")
        logger.info("")
        logger.info("Performance Metrics:")
        logger.info(f"  Avg Train Sharpe: {results.avg_train_sharpe:.2f}")
        logger.info(f"  Avg Test Sharpe: {results.avg_test_sharpe:.2f}")
        logger.info(f"  Avg Degradation: {results.avg_degradation:.1f}%")
        logger.info("")
        logger.info("Parameter Stability:")
        logger.info(f"  Stability Score: {results.parameter_stability_score:.2f}")
        logger.info(f"  Parameter Variance: {results.parameter_variance}")
        logger.info(f"  Is Stable: {results.is_stable}")
        logger.info("")
        logger.info("Performance Trend:")
        logger.info(f"  Trend: {results.performance_trend}")
        logger.info(f"  Trend Slope: {results.trend_slope:.3f}")
        logger.info(f"  Is Degrading: {results.is_degrading}")
        logger.info("")
        logger.info("Regime Analysis:")
        logger.info(f"  Regime Consistency: {results.regime_consistency:.1%}")
        logger.info(f"  Regime-Specific Performance:")
        for regime, sharpe in results.regime_specific_performance.items():
            logger.info(f"    {regime.value}: {sharpe:.2f}")
        logger.info(f"  Is Regime Adaptive: {results.is_regime_adaptive}")
        logger.info("")
        logger.info(f"OVERALL VALIDATION: {'PASS' if results.passes_validation else 'FAIL'}")
        logger.info("=" * 80)
