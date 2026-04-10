"""
Backtesting support for meta-strategies.

Extends the standard backtesting framework to support meta-strategies with
dynamic allocation and signal aggregation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from src.strategy.meta_strategy import MetaStrategy, SignalAggregationMethod
from src.models.dataclasses import Strategy, BacktestResults

logger = logging.getLogger(__name__)


class MetaStrategyBacktester:
    """
    Backtester for meta-strategies with dynamic allocation.
    
    Simulates:
    - Dynamic rebalancing over time
    - Signal aggregation from multiple base strategies
    - Portfolio-level performance metrics
    - Comparison to equal-weight portfolio
    """
    
    def __init__(self, meta_strategy: MetaStrategy):
        """
        Initialize backtester for a meta-strategy.
        
        Args:
            meta_strategy: MetaStrategy to backtest
        """
        self.meta_strategy = meta_strategy
    
    def backtest(
        self,
        base_strategy_results: Dict[str, BacktestResults],
        start: datetime,
        end: datetime,
        initial_capital: float = 100000.0
    ) -> BacktestResults:
        """
        Backtest meta-strategy with dynamic allocation.
        
        Args:
            base_strategy_results: Dict mapping strategy_id to BacktestResults
            start: Start date for backtest
            end: End date for backtest
            initial_capital: Initial capital in dollars
        
        Returns:
            BacktestResults for the meta-strategy
        """
        logger.info(
            f"Backtesting meta-strategy '{self.meta_strategy.name}' "
            f"from {start.date()} to {end.date()}"
        )
        
        # Validate we have results for all base strategies
        missing_strategies = set(self.meta_strategy.base_strategies.keys()) - set(base_strategy_results.keys())
        if missing_strategies:
            raise ValueError(
                f"Missing backtest results for strategies: {missing_strategies}"
            )
        
        # Extract equity curves from base strategies
        equity_curves = {}
        for sid, results in base_strategy_results.items():
            if results.equity_curve is None or len(results.equity_curve) == 0:
                raise ValueError(f"Strategy {sid} has no equity curve data")
            equity_curves[sid] = results.equity_curve
        
        # Align all equity curves to common date range
        aligned_curves = self._align_equity_curves(equity_curves, start, end)
        
        # Calculate daily returns for each strategy
        returns_data = {}
        for sid, equity in aligned_curves.items():
            returns = equity.pct_change().fillna(0.0)
            returns_data[sid] = returns
        
        # Simulate dynamic allocation over time
        meta_equity_curve = self._simulate_dynamic_allocation(
            aligned_curves,
            returns_data,
            initial_capital
        )
        
        # Calculate performance metrics
        meta_returns = meta_equity_curve.pct_change().fillna(0.0)
        
        total_return = (meta_equity_curve.iloc[-1] / meta_equity_curve.iloc[0]) - 1.0
        
        # Sharpe ratio (annualized)
        mean_return = meta_returns.mean()
        std_return = meta_returns.std()
        sharpe_ratio = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
        
        # Sortino ratio (annualized, using downside deviation)
        downside_returns = meta_returns[meta_returns < 0]
        downside_std = downside_returns.std()
        sortino_ratio = (mean_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
        
        # Maximum drawdown
        cumulative = (1 + meta_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Trade statistics (aggregate from base strategies)
        total_trades = sum(r.total_trades for r in base_strategy_results.values())
        
        # Win rate (weighted average by number of trades)
        total_wins = sum(r.total_trades * r.win_rate for r in base_strategy_results.values())
        win_rate = total_wins / total_trades if total_trades > 0 else 0.0
        
        # Average win/loss (weighted average)
        avg_win = np.mean([r.avg_win for r in base_strategy_results.values() if r.avg_win > 0])
        avg_loss = np.mean([r.avg_loss for r in base_strategy_results.values() if r.avg_loss < 0])
        
        # Calculate diversification benefit
        avg_base_sharpe = np.mean([r.sharpe_ratio for r in base_strategy_results.values()])
        diversification_benefit = sharpe_ratio - avg_base_sharpe
        
        logger.info(f"Meta-strategy backtest complete:")
        logger.info(f"  Total return: {total_return:.2%}")
        logger.info(f"  Sharpe ratio: {sharpe_ratio:.2f}")
        logger.info(f"  Max drawdown: {max_drawdown:.2%}")
        logger.info(f"  Avg base strategy Sharpe: {avg_base_sharpe:.2f}")
        logger.info(f"  Diversification benefit: {diversification_benefit:+.2f}")
        
        # Update meta-strategy performance
        self.meta_strategy.performance.total_return = total_return
        self.meta_strategy.performance.sharpe_ratio = sharpe_ratio
        self.meta_strategy.performance.max_drawdown = max_drawdown
        self.meta_strategy.performance.win_rate = win_rate
        self.meta_strategy.performance.total_trades = total_trades
        self.meta_strategy.performance.avg_base_strategy_sharpe = avg_base_sharpe
        self.meta_strategy.performance.diversification_benefit = diversification_benefit
        
        return BacktestResults(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=total_trades,
            equity_curve=meta_equity_curve,
            trades=None,  # Meta-strategy doesn't have individual trades
            backtest_period=(start, end)
        )
    
    def _align_equity_curves(
        self,
        equity_curves: Dict[str, pd.Series],
        start: datetime,
        end: datetime
    ) -> Dict[str, pd.Series]:
        """
        Align equity curves to common date range.
        
        Args:
            equity_curves: Dict mapping strategy_id to equity curve Series
            start: Start date
            end: End date
        
        Returns:
            Dict of aligned equity curves
        """
        # Find common date range
        all_dates = set()
        for curve in equity_curves.values():
            all_dates.update(curve.index)
        
        common_dates = sorted([d for d in all_dates if start <= d <= end])
        
        if not common_dates:
            raise ValueError("No common dates found in equity curves")
        
        # Align all curves to common dates
        aligned = {}
        for sid, curve in equity_curves.items():
            # Reindex to common dates, forward fill missing values
            aligned_curve = curve.reindex(common_dates, method='ffill')
            
            # If still have NaN at start, backfill
            aligned_curve = aligned_curve.fillna(method='bfill')
            
            aligned[sid] = aligned_curve
        
        logger.info(f"Aligned {len(equity_curves)} equity curves to {len(common_dates)} common dates")
        
        return aligned
    
    def _simulate_dynamic_allocation(
        self,
        equity_curves: Dict[str, pd.Series],
        returns_data: Dict[str, pd.Series],
        initial_capital: float
    ) -> pd.Series:
        """
        Simulate meta-strategy with dynamic allocation over time.
        
        Args:
            equity_curves: Dict mapping strategy_id to equity curve
            returns_data: Dict mapping strategy_id to daily returns
            initial_capital: Initial capital
        
        Returns:
            Meta-strategy equity curve
        """
        # Get common dates
        dates = equity_curves[list(equity_curves.keys())[0]].index
        
        # Initialize meta-strategy equity curve
        meta_equity = pd.Series(index=dates, dtype=float)
        meta_equity.iloc[0] = initial_capital
        
        # Track current allocations (start with initial allocations)
        current_allocations = {
            sid: alloc.allocation_pct / 100.0
            for sid, alloc in self.meta_strategy.allocations.items()
        }
        
        # Track last rebalance date
        last_rebalance_date = dates[0]
        rebalance_count = 0
        
        # Simulate day by day
        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i-1]
            
            # Check if we should rebalance
            days_since_rebalance = (current_date - last_rebalance_date).days
            should_rebalance = days_since_rebalance >= self.meta_strategy.config.rebalance_frequency_days
            
            if should_rebalance and i > self.meta_strategy.config.performance_lookback_days:
                # Rebalance based on recent performance
                lookback_start = max(0, i - self.meta_strategy.config.performance_lookback_days)
                recent_returns = {
                    sid: returns_data[sid].iloc[lookback_start:i]
                    for sid in returns_data.keys()
                }
                
                # Calculate new allocations
                new_allocations = self.meta_strategy.rebalance_allocations(recent_returns)
                current_allocations = {sid: alloc / 100.0 for sid, alloc in new_allocations.items()}
                
                last_rebalance_date = current_date
                rebalance_count += 1
                
                logger.debug(f"Rebalanced on {current_date.date()} (rebalance #{rebalance_count})")
            
            # Calculate portfolio return for this day
            portfolio_return = 0.0
            for sid, allocation in current_allocations.items():
                strategy_return = returns_data[sid].iloc[i]
                portfolio_return += allocation * strategy_return
            
            # Update equity
            meta_equity.iloc[i] = meta_equity.iloc[i-1] * (1 + portfolio_return)
        
        logger.info(f"Simulated {len(dates)} days with {rebalance_count} rebalances")
        
        return meta_equity
    
    def compare_to_equal_weight(
        self,
        base_strategy_results: Dict[str, BacktestResults],
        start: datetime,
        end: datetime,
        initial_capital: float = 100000.0
    ) -> Dict:
        """
        Compare meta-strategy performance to equal-weight portfolio.
        
        Args:
            base_strategy_results: Dict mapping strategy_id to BacktestResults
            start: Start date
            end: End date
            initial_capital: Initial capital
        
        Returns:
            Dict with comparison metrics
        """
        logger.info("Comparing meta-strategy to equal-weight portfolio...")
        
        # Backtest meta-strategy
        meta_results = self.backtest(base_strategy_results, start, end, initial_capital)
        
        # Calculate equal-weight portfolio performance
        equity_curves = {
            sid: results.equity_curve
            for sid, results in base_strategy_results.items()
        }
        
        aligned_curves = self._align_equity_curves(equity_curves, start, end)
        
        # Equal weight allocation
        num_strategies = len(aligned_curves)
        equal_weight = 1.0 / num_strategies
        
        # Calculate equal-weight equity curve
        equal_weight_equity = pd.Series(index=aligned_curves[list(aligned_curves.keys())[0]].index, dtype=float)
        equal_weight_equity.iloc[0] = initial_capital
        
        for i in range(1, len(equal_weight_equity)):
            portfolio_return = 0.0
            for sid, curve in aligned_curves.items():
                strategy_return = curve.pct_change().iloc[i]
                portfolio_return += equal_weight * strategy_return
            
            equal_weight_equity.iloc[i] = equal_weight_equity.iloc[i-1] * (1 + portfolio_return)
        
        # Calculate equal-weight metrics
        ew_returns = equal_weight_equity.pct_change().fillna(0.0)
        ew_total_return = (equal_weight_equity.iloc[-1] / equal_weight_equity.iloc[0]) - 1.0
        ew_sharpe = (ew_returns.mean() / ew_returns.std() * np.sqrt(252)) if ew_returns.std() > 0 else 0.0
        
        ew_cumulative = (1 + ew_returns).cumprod()
        ew_running_max = ew_cumulative.expanding().max()
        ew_drawdown = (ew_cumulative - ew_running_max) / ew_running_max
        ew_max_drawdown = ew_drawdown.min()
        
        # Calculate improvement
        return_improvement = meta_results.total_return - ew_total_return
        sharpe_improvement = meta_results.sharpe_ratio - ew_sharpe
        drawdown_improvement = ew_max_drawdown - meta_results.max_drawdown  # Positive = better (less drawdown)
        
        comparison = {
            "meta_strategy": {
                "total_return": meta_results.total_return,
                "sharpe_ratio": meta_results.sharpe_ratio,
                "max_drawdown": meta_results.max_drawdown,
            },
            "equal_weight": {
                "total_return": ew_total_return,
                "sharpe_ratio": ew_sharpe,
                "max_drawdown": ew_max_drawdown,
            },
            "improvement": {
                "return_improvement": return_improvement,
                "sharpe_improvement": sharpe_improvement,
                "drawdown_improvement": drawdown_improvement,
            },
            "meta_is_better": (
                meta_results.sharpe_ratio > ew_sharpe and
                meta_results.max_drawdown > ew_max_drawdown  # Less negative = better
            )
        }
        
        logger.info("Comparison results:")
        logger.info(f"  Meta-strategy Sharpe: {meta_results.sharpe_ratio:.2f}")
        logger.info(f"  Equal-weight Sharpe: {ew_sharpe:.2f}")
        logger.info(f"  Sharpe improvement: {sharpe_improvement:+.2f}")
        logger.info(f"  Meta-strategy return: {meta_results.total_return:.2%}")
        logger.info(f"  Equal-weight return: {ew_total_return:.2%}")
        logger.info(f"  Return improvement: {return_improvement:+.2%}")
        logger.info(f"  Meta is better: {comparison['meta_is_better']}")
        
        return comparison
