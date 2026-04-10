"""Portfolio Risk Manager for portfolio-level risk management and allocation optimization."""

import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from src.models.dataclasses import Strategy

logger = logging.getLogger(__name__)


class PortfolioRiskManager:
    """Manages portfolio-level risk metrics and optimizes allocations."""

    def __init__(self, max_correlation: float = 0.7, min_trades: int = 20):
        """
        Initialize Portfolio Risk Manager.
        
        Args:
            max_correlation: Maximum allowed correlation between strategies (default 0.7)
            min_trades: Minimum trades required for strategy inclusion (default 20)
        """
        self.max_correlation = max_correlation
        self.min_trades = min_trades
        logger.info(f"PortfolioRiskManager initialized with max_correlation={max_correlation}, min_trades={min_trades}")

    def calculate_portfolio_metrics(
        self, strategies: List[Strategy], returns_data: Dict[str, pd.Series]
    ) -> Dict:
        """
        Calculate portfolio-level performance metrics.

        Args:
            strategies: List of active strategies
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Dict containing:
            - portfolio_sharpe: Portfolio Sharpe ratio (weighted average)
            - portfolio_max_drawdown: Portfolio max drawdown (combined equity curve)
            - correlation_matrix: Strategy correlation matrix (DataFrame)
            - diversification_score: Diversification score (1 - avg correlation)
        """
        if not strategies or not returns_data:
            logger.warning("No strategies or returns data provided")
            return {
                "portfolio_sharpe": 0.0,
                "portfolio_max_drawdown": 0.0,
                "correlation_matrix": pd.DataFrame(),
                "diversification_score": 0.0,
            }

        # Get allocations for each strategy
        allocations = {s.id: s.allocation_percent / 100.0 for s in strategies}

        # Calculate portfolio Sharpe ratio (weighted average)
        portfolio_sharpe = self._calculate_portfolio_sharpe(
            strategies, allocations, returns_data
        )

        # Calculate portfolio max drawdown (combined equity curve)
        portfolio_max_drawdown = self._calculate_portfolio_max_drawdown(
            allocations, returns_data
        )

        # Calculate correlation matrix
        correlation_matrix = self._calculate_correlation_matrix(returns_data)

        # Calculate diversification score (1 - avg correlation)
        diversification_score = self._calculate_diversification_score(correlation_matrix)

        logger.info(
            f"Portfolio metrics: Sharpe={portfolio_sharpe:.2f}, "
            f"MaxDD={portfolio_max_drawdown:.2%}, "
            f"Diversification={diversification_score:.2f}"
        )

        return {
            "portfolio_sharpe": portfolio_sharpe,
            "portfolio_max_drawdown": portfolio_max_drawdown,
            "correlation_matrix": correlation_matrix,
            "diversification_score": diversification_score,
        }

    def filter_by_correlation(
        self, strategies: List[Strategy], returns_data: Dict[str, pd.Series]
    ) -> tuple[List[Strategy], Dict[str, pd.Series]]:
        """
        Filter strategies to remove highly correlated pairs.
        
        Keeps the better performing strategy (higher Sharpe) when correlation exceeds threshold.
        
        Args:
            strategies: List of strategies to filter
            returns_data: Dict mapping strategy_id -> daily returns
            
        Returns:
            Tuple of (filtered_strategies, filtered_returns_data)
        """
        if len(strategies) < 2:
            return strategies, returns_data
        
        # Calculate correlation matrix
        correlation_matrix = self._calculate_correlation_matrix(returns_data)
        
        strategies_to_remove = set()
        logger.info(f"Filtering strategies with correlation > {self.max_correlation}")
        
        for i, s1 in enumerate(strategies):
            if s1.id in strategies_to_remove:
                continue
                
            for s2 in strategies[i+1:]:
                if s2.id in strategies_to_remove:
                    continue
                    
                if s1.id in correlation_matrix.index and s2.id in correlation_matrix.columns:
                    corr = abs(correlation_matrix.loc[s1.id, s2.id])
                    
                    if corr > self.max_correlation:
                        # Keep the better performing strategy
                        s1_sharpe = s1.performance.sharpe_ratio if s1.performance else 0
                        s2_sharpe = s2.performance.sharpe_ratio if s2.performance else 0
                        
                        if s1_sharpe < s2_sharpe:
                            strategies_to_remove.add(s1.id)
                            logger.info(
                                f"Removing {s1.name} (corr={corr:.3f} with {s2.name}, "
                                f"Sharpe {s1_sharpe:.2f} < {s2_sharpe:.2f})"
                            )
                        else:
                            strategies_to_remove.add(s2.id)
                            logger.info(
                                f"Removing {s2.name} (corr={corr:.3f} with {s1.name}, "
                                f"Sharpe {s2_sharpe:.2f} < {s1_sharpe:.2f})"
                            )
        
        # Filter strategies and returns
        filtered_strategies = [s for s in strategies if s.id not in strategies_to_remove]
        filtered_returns = {k: v for k, v in returns_data.items() if k not in strategies_to_remove}
        
        logger.info(f"Filtered {len(strategies_to_remove)} strategies, {len(filtered_strategies)} remaining")
        return filtered_strategies, filtered_returns

    def filter_by_min_trades(self, strategies: List[Strategy]) -> List[Strategy]:
        """
        Filter strategies that don't meet minimum trade requirement.
        
        Args:
            strategies: List of strategies to filter
            
        Returns:
            Filtered list of strategies
        """
        filtered = []
        for strategy in strategies:
            trades = strategy.performance.total_trades if strategy.performance else 0
            if trades >= self.min_trades:
                filtered.append(strategy)
            else:
                logger.info(
                    f"Filtering {strategy.name}: {trades} trades < {self.min_trades} minimum"
                )
        
        logger.info(f"Filtered by min trades: {len(filtered)}/{len(strategies)} strategies passed")
        return filtered

    def optimize_allocations(
        self, strategies: List[Strategy], returns_data: Dict[str, pd.Series]
    ) -> Dict[str, float]:
        """
        Optimize portfolio allocations for risk-adjusted returns.

        Algorithm:
        1. Start with equal weight allocation
        2. Adjust based on individual Sharpe ratios
        3. Reduce allocation to highly correlated strategies
        4. Ensure no strategy > 20% of portfolio
        5. Ensure total allocation = 100%

        Args:
            strategies: List of strategies to allocate
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Dict mapping strategy_id -> allocation percentage (0-100)
        """
        if not strategies:
            logger.warning("No strategies provided for allocation optimization")
            return {}

        if len(strategies) == 1:
            logger.info("Single strategy, allocating 100%")
            return {strategies[0].id: 100.0}

        # Step 1: Start with equal weight
        equal_weight = 100.0 / len(strategies)
        allocations = {s.id: equal_weight for s in strategies}

        logger.info(f"Starting with equal weight: {equal_weight:.1f}% per strategy")

        # Step 2: Adjust based on Sharpe ratios
        allocations = self._adjust_by_sharpe(strategies, allocations)

        # Step 3: Reduce allocation to highly correlated strategies
        if returns_data:
            allocations = self._adjust_by_correlation(strategies, allocations, returns_data)

        # Step 4: Ensure no strategy > 20% (only if we have 5+ strategies)
        # For fewer strategies, allow higher allocations
        if len(strategies) >= 5:
            allocations = self._cap_max_allocation(allocations, max_pct=20.0)

        # Step 5: Normalize to ensure total = 100%
        allocations = self._normalize_allocations(allocations)

        logger.info(
            f"Optimized allocations: "
            f"{', '.join([f'{sid[:8]}={pct:.1f}%' for sid, pct in allocations.items()])}"
        )

        return allocations

    def _calculate_portfolio_sharpe(
        self,
        strategies: List[Strategy],
        allocations: Dict[str, float],
        returns_data: Dict[str, pd.Series],
    ) -> float:
        """
        Calculate portfolio Sharpe ratio as weighted average.

        Args:
            strategies: List of strategies
            allocations: Dict mapping strategy_id -> allocation (0-1)
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Portfolio Sharpe ratio
        """
        if not returns_data:
            # Fallback to weighted average of individual Sharpe ratios
            total_weight = 0.0
            weighted_sharpe = 0.0

            for strategy in strategies:
                weight = allocations.get(strategy.id, 0.0)
                sharpe = strategy.performance.sharpe_ratio if strategy.performance else 0.0
                weighted_sharpe += weight * sharpe
                total_weight += weight

            if total_weight > 0:
                return weighted_sharpe / total_weight
            return 0.0

        # Calculate portfolio returns
        portfolio_returns = self._calculate_portfolio_returns(allocations, returns_data)

        if portfolio_returns.empty or len(portfolio_returns) < 2:
            return 0.0

        # Calculate Sharpe ratio
        mean_return = portfolio_returns.mean()
        std_return = portfolio_returns.std()

        if std_return == 0:
            return 0.0

        # Annualize (assuming daily returns)
        sharpe = (mean_return / std_return) * np.sqrt(252)

        return sharpe

    def _calculate_portfolio_max_drawdown(
        self, allocations: Dict[str, float], returns_data: Dict[str, pd.Series]
    ) -> float:
        """
        Calculate portfolio max drawdown from combined equity curve.

        Args:
            allocations: Dict mapping strategy_id -> allocation (0-1)
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Portfolio max drawdown (0-1)
        """
        if not returns_data:
            return 0.0

        # Calculate portfolio returns
        portfolio_returns = self._calculate_portfolio_returns(allocations, returns_data)

        if portfolio_returns.empty:
            return 0.0

        # Calculate cumulative returns (equity curve)
        cumulative_returns = (1 + portfolio_returns).cumprod()

        # Calculate running maximum
        running_max = cumulative_returns.expanding().max()

        # Calculate drawdown
        drawdown = (cumulative_returns - running_max) / running_max

        # Get max drawdown (most negative value)
        max_drawdown = abs(drawdown.min())

        return max_drawdown

    def _calculate_portfolio_returns(
        self, allocations: Dict[str, float], returns_data: Dict[str, pd.Series]
    ) -> pd.Series:
        """
        Calculate portfolio returns as weighted sum of strategy returns.

        Args:
            allocations: Dict mapping strategy_id -> allocation (0-1)
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Portfolio returns Series
        """
        # Align all returns to common dates
        returns_df = pd.DataFrame(returns_data)

        # Fill NaN with 0 (no return on days strategy wasn't active)
        returns_df = returns_df.fillna(0)

        # Calculate weighted returns
        portfolio_returns = pd.Series(0.0, index=returns_df.index)

        for strategy_id, allocation in allocations.items():
            if strategy_id in returns_df.columns:
                portfolio_returns += allocation * returns_df[strategy_id]

        return portfolio_returns

    def _calculate_correlation_matrix(
        self, returns_data: Dict[str, pd.Series]
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix between strategy returns.

        Args:
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Correlation matrix DataFrame
        """
        if not returns_data or len(returns_data) < 2:
            return pd.DataFrame()

        # Create DataFrame from returns
        returns_df = pd.DataFrame(returns_data)

        # Calculate correlation matrix
        correlation_matrix = returns_df.corr()

        return correlation_matrix

    def _calculate_diversification_score(self, correlation_matrix: pd.DataFrame) -> float:
        """
        Calculate diversification score as 1 - average correlation.

        Args:
            correlation_matrix: Correlation matrix DataFrame

        Returns:
            Diversification score (0-1, higher is better)
        """
        if correlation_matrix.empty or len(correlation_matrix) < 2:
            return 0.0

        # Get upper triangle of correlation matrix (excluding diagonal)
        mask = np.triu(np.ones_like(correlation_matrix, dtype=bool), k=1)
        correlations = correlation_matrix.where(mask)

        # Calculate average correlation
        avg_correlation = correlations.stack().mean()

        # Diversification score = 1 - avg correlation
        diversification_score = 1.0 - avg_correlation

        return max(0.0, min(1.0, diversification_score))

    def _adjust_by_sharpe(
        self, strategies: List[Strategy], allocations: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Adjust allocations based on individual Sharpe ratios.

        Higher Sharpe strategies get higher allocation.

        Args:
            strategies: List of strategies
            allocations: Current allocations

        Returns:
            Adjusted allocations
        """
        # Get Sharpe ratios
        sharpe_ratios = {}
        for strategy in strategies:
            sharpe = strategy.performance.sharpe_ratio if strategy.performance else 0.0
            # Use max(0, sharpe) to avoid negative weights
            sharpe_ratios[strategy.id] = max(0.0, sharpe)

        # If all Sharpe ratios are 0, return equal weight
        total_sharpe = sum(sharpe_ratios.values())
        if total_sharpe == 0:
            return allocations

        # Calculate Sharpe-weighted allocations
        sharpe_weighted = {}
        for strategy_id, sharpe in sharpe_ratios.items():
            sharpe_weighted[strategy_id] = (sharpe / total_sharpe) * 100.0

        # Blend with equal weight (50/50)
        adjusted = {}
        for strategy_id in allocations:
            equal_weight = allocations[strategy_id]
            sharpe_weight = sharpe_weighted.get(strategy_id, 0.0)
            adjusted[strategy_id] = 0.5 * equal_weight + 0.5 * sharpe_weight

        return adjusted

    def _adjust_by_correlation(
        self,
        strategies: List[Strategy],
        allocations: Dict[str, float],
        returns_data: Dict[str, pd.Series],
    ) -> Dict[str, float]:
        """
        Reduce allocation to highly correlated strategies.

        Args:
            strategies: List of strategies
            allocations: Current allocations
            returns_data: Dict mapping strategy_id -> daily returns Series

        Returns:
            Adjusted allocations
        """
        if len(strategies) < 2:
            return allocations

        # Calculate correlation matrix
        correlation_matrix = self._calculate_correlation_matrix(returns_data)

        if correlation_matrix.empty:
            return allocations

        # For each strategy, calculate average correlation with others
        avg_correlations = {}
        for strategy_id in allocations:
            if strategy_id in correlation_matrix.index:
                # Get correlations with other strategies (excluding self)
                correlations = correlation_matrix[strategy_id].drop(strategy_id, errors="ignore")
                avg_correlations[strategy_id] = correlations.mean() if not correlations.empty else 0.0
            else:
                avg_correlations[strategy_id] = 0.0

        # Penalize highly correlated strategies
        # Penalty factor: 1.0 - (avg_correlation * 0.5)
        # If avg_correlation = 0.8, penalty = 0.6 (reduce allocation by 40%)
        adjusted = {}
        for strategy_id, allocation in allocations.items():
            avg_corr = avg_correlations.get(strategy_id, 0.0)
            penalty = 1.0 - (avg_corr * 0.5)
            adjusted[strategy_id] = allocation * penalty

        return adjusted

    def _cap_max_allocation(
        self, allocations: Dict[str, float], max_pct: float = 20.0
    ) -> Dict[str, float]:
        """
        Ensure no strategy exceeds max allocation percentage.

        Args:
            allocations: Current allocations
            max_pct: Maximum allocation percentage per strategy

        Returns:
            Capped allocations
        """
        capped = {}
        excess = 0.0

        # Cap allocations and track excess
        for strategy_id, allocation in allocations.items():
            if allocation > max_pct:
                capped[strategy_id] = max_pct
                excess += allocation - max_pct
            else:
                capped[strategy_id] = allocation

        # Redistribute excess to strategies below cap
        if excess > 0:
            below_cap = {sid: alloc for sid, alloc in capped.items() if alloc < max_pct}

            if below_cap:
                # Distribute excess proportionally
                total_below_cap = sum(below_cap.values())
                for strategy_id in below_cap:
                    if total_below_cap > 0:
                        proportion = below_cap[strategy_id] / total_below_cap
                        additional = excess * proportion
                        # Ensure we don't exceed cap (with small tolerance for floating point)
                        capped[strategy_id] = min(max_pct - 0.01, capped[strategy_id] + additional)

        return capped

    def _normalize_allocations(self, allocations: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize allocations to sum to 100%.

        Args:
            allocations: Current allocations

        Returns:
            Normalized allocations
        """
        total = sum(allocations.values())

        if total == 0:
            # Equal weight if all are 0
            equal_weight = 100.0 / len(allocations)
            return {sid: equal_weight for sid in allocations}

        # Normalize to 100%
        normalized = {sid: (alloc / total) * 100.0 for sid, alloc in allocations.items()}

        return normalized
