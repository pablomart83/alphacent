"""
Meta-Strategy Framework for Ensemble Trading.

This module implements meta-strategies that dynamically allocate capital between
multiple base strategies, combining their signals intelligently for improved
risk-adjusted returns.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

import pandas as pd
import numpy as np

from src.models.dataclasses import Strategy, StrategyStatus, PerformanceMetrics

logger = logging.getLogger(__name__)


class SignalAggregationMethod(Enum):
    """Methods for aggregating signals from multiple strategies."""
    VOTING = "voting"  # Enter if N of M strategies signal entry
    WEIGHTED = "weighted"  # Weight signals by strategy Sharpe ratio
    CONFIDENCE = "confidence"  # Only enter if aggregate confidence > threshold


@dataclass
class MetaStrategyConfig:
    """Configuration for meta-strategy behavior."""
    aggregation_method: SignalAggregationMethod = SignalAggregationMethod.WEIGHTED
    rebalance_frequency_days: int = 7  # Rebalance weekly
    min_strategies: int = 2  # Minimum number of base strategies
    max_strategies: int = 5  # Maximum number of base strategies
    
    # Voting method parameters
    voting_threshold: float = 0.5  # Enter if >50% of strategies signal entry
    
    # Weighted method parameters
    min_sharpe_for_weight: float = 0.3  # Minimum Sharpe to get non-zero weight
    
    # Confidence method parameters
    confidence_threshold: float = 0.6  # Minimum aggregate confidence to enter
    
    # Dynamic allocation parameters
    performance_lookback_days: int = 30  # Rolling window for performance evaluation
    min_allocation_pct: float = 5.0  # Minimum allocation per strategy
    max_allocation_pct: float = 40.0  # Maximum allocation per strategy


@dataclass
class BaseStrategyAllocation:
    """Allocation for a single base strategy within meta-strategy."""
    strategy_id: str
    strategy_name: str
    allocation_pct: float
    recent_sharpe: float
    recent_return: float
    weight: float  # Weight for signal aggregation (0.0 to 1.0)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class MetaStrategyPerformance:
    """Performance metrics specific to meta-strategies."""
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    
    # Meta-strategy specific metrics
    avg_base_strategy_sharpe: float = 0.0
    diversification_benefit: float = 0.0  # Portfolio Sharpe - Avg Strategy Sharpe
    rebalance_count: int = 0
    last_rebalance: Optional[datetime] = None


class MetaStrategy:
    """
    Meta-strategy that dynamically allocates between multiple base strategies.
    
    Features:
    - Dynamic allocation based on recent performance
    - Signal aggregation using voting, weighted, or confidence methods
    - Weekly rebalancing to adapt to changing market conditions
    - Performance tracking and comparison to equal-weight portfolio
    """
    
    def __init__(
        self,
        meta_strategy_id: str,
        name: str,
        base_strategies: List[Strategy],
        config: Optional[MetaStrategyConfig] = None
    ):
        """
        Initialize meta-strategy.
        
        Args:
            meta_strategy_id: Unique identifier for meta-strategy
            name: Human-readable name
            base_strategies: List of base strategies to combine
            config: Configuration for meta-strategy behavior
        """
        self.id = meta_strategy_id
        self.name = name
        self.base_strategies = {s.id: s for s in base_strategies}
        self.config = config or MetaStrategyConfig()
        
        # Validate minimum strategies
        if len(base_strategies) < self.config.min_strategies:
            raise ValueError(
                f"Meta-strategy requires at least {self.config.min_strategies} base strategies, "
                f"got {len(base_strategies)}"
            )
        
        # Initialize allocations (equal weight initially)
        self.allocations: Dict[str, BaseStrategyAllocation] = {}
        self._initialize_allocations()
        
        # Performance tracking
        self.performance = MetaStrategyPerformance()
        self.created_at = datetime.now()
        self.last_rebalance = None
        
        logger.info(
            f"Created meta-strategy '{name}' with {len(base_strategies)} base strategies "
            f"using {self.config.aggregation_method.value} aggregation"
        )
    
    def _initialize_allocations(self) -> None:
        """Initialize equal-weight allocations for all base strategies."""
        num_strategies = len(self.base_strategies)
        equal_weight = 100.0 / num_strategies
        
        for strategy_id, strategy in self.base_strategies.items():
            # Get recent performance if available
            recent_sharpe = strategy.performance.sharpe_ratio if strategy.performance else 0.0
            recent_return = strategy.performance.total_return if strategy.performance else 0.0
            
            self.allocations[strategy_id] = BaseStrategyAllocation(
                strategy_id=strategy_id,
                strategy_name=strategy.name,
                allocation_pct=equal_weight,
                recent_sharpe=recent_sharpe,
                recent_return=recent_return,
                weight=1.0 / num_strategies  # Equal weight for signal aggregation
            )
        
        logger.info(f"Initialized equal-weight allocations: {equal_weight:.1f}% per strategy")
    
    def should_rebalance(self) -> bool:
        """
        Check if meta-strategy should rebalance allocations.
        
        Returns:
            True if rebalance is needed (based on frequency)
        """
        if self.last_rebalance is None:
            return True
        
        days_since_rebalance = (datetime.now() - self.last_rebalance).days
        return days_since_rebalance >= self.config.rebalance_frequency_days
    
    def rebalance_allocations(
        self,
        returns_data: Dict[str, pd.Series]
    ) -> Dict[str, float]:
        """
        Rebalance allocations based on recent performance.
        
        Allocates more capital to strategies with strong recent performance,
        reduces allocation to strategies showing degradation.
        
        Args:
            returns_data: Dict mapping strategy_id to Series of daily returns
        
        Returns:
            Dict mapping strategy_id to new allocation percentage
        """
        logger.info("Rebalancing meta-strategy allocations...")
        
        # Calculate rolling performance metrics for each strategy
        performance_scores = {}
        
        for strategy_id, returns in returns_data.items():
            if strategy_id not in self.base_strategies:
                continue
            
            # Calculate rolling Sharpe ratio (last N days)
            lookback = min(self.config.performance_lookback_days, len(returns))
            recent_returns = returns.tail(lookback)
            
            if len(recent_returns) < 10:  # Need minimum data
                logger.warning(f"Insufficient data for {strategy_id}, using default score")
                performance_scores[strategy_id] = 0.5
                continue
            
            # Calculate Sharpe ratio
            mean_return = recent_returns.mean()
            std_return = recent_returns.std()
            sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
            
            # Calculate cumulative return
            cumulative_return = (1 + recent_returns).prod() - 1
            
            # Performance score combines Sharpe and return
            # Score = 0.7 * normalized_sharpe + 0.3 * normalized_return
            # Normalize Sharpe: 0 -> 0.5, 1.0 -> 0.75, 2.0 -> 1.0
            normalized_sharpe = min(1.0, max(0.0, (sharpe + 1.0) / 3.0))
            # Normalize return: -10% -> 0.0, 0% -> 0.5, +10% -> 1.0
            normalized_return = min(1.0, max(0.0, (cumulative_return + 0.1) / 0.2))
            
            score = 0.7 * normalized_sharpe + 0.3 * normalized_return
            performance_scores[strategy_id] = score
            
            # Update allocation record
            if strategy_id in self.allocations:
                self.allocations[strategy_id].recent_sharpe = sharpe
                self.allocations[strategy_id].recent_return = cumulative_return
            
            logger.info(
                f"  {self.base_strategies[strategy_id].name}: "
                f"Sharpe={sharpe:.2f}, Return={cumulative_return:.2%}, Score={score:.2f}"
            )
        
        # Calculate new allocations based on performance scores
        total_score = sum(performance_scores.values())
        
        if total_score == 0:
            # Fallback to equal weight if all scores are zero
            logger.warning("All performance scores are zero, using equal weight")
            new_allocations = {
                sid: 100.0 / len(performance_scores)
                for sid in performance_scores.keys()
            }
        else:
            # Allocate proportionally to performance scores
            raw_allocations = {
                sid: (score / total_score) * 100.0
                for sid, score in performance_scores.items()
            }
            
            # Apply min/max constraints
            new_allocations = {}
            for sid, allocation in raw_allocations.items():
                constrained = max(
                    self.config.min_allocation_pct,
                    min(self.config.max_allocation_pct, allocation)
                )
                new_allocations[sid] = constrained
            
            # Renormalize to ensure total = 100%
            total_allocation = sum(new_allocations.values())
            new_allocations = {
                sid: (alloc / total_allocation) * 100.0
                for sid, alloc in new_allocations.items()
            }
        
        # Update allocations
        for strategy_id, allocation_pct in new_allocations.items():
            if strategy_id in self.allocations:
                old_allocation = self.allocations[strategy_id].allocation_pct
                self.allocations[strategy_id].allocation_pct = allocation_pct
                self.allocations[strategy_id].last_updated = datetime.now()
                
                logger.info(
                    f"  {self.allocations[strategy_id].strategy_name}: "
                    f"{old_allocation:.1f}% -> {allocation_pct:.1f}%"
                )
        
        # Update rebalance tracking
        self.last_rebalance = datetime.now()
        self.performance.rebalance_count += 1
        self.performance.last_rebalance = self.last_rebalance
        
        logger.info(f"Rebalance complete (total: {self.performance.rebalance_count})")
        
        return new_allocations
    
    def calculate_signal_weights(self) -> Dict[str, float]:
        """
        Calculate weights for signal aggregation based on recent performance.
        
        Returns:
            Dict mapping strategy_id to weight (0.0 to 1.0, sum = 1.0)
        """
        if self.config.aggregation_method == SignalAggregationMethod.VOTING:
            # Equal weight for voting
            num_strategies = len(self.base_strategies)
            return {sid: 1.0 / num_strategies for sid in self.base_strategies.keys()}
        
        elif self.config.aggregation_method == SignalAggregationMethod.WEIGHTED:
            # Weight by Sharpe ratio
            sharpe_values = {}
            for sid, allocation in self.allocations.items():
                # Use max(0, sharpe) to avoid negative weights
                sharpe = max(0.0, allocation.recent_sharpe)
                # Apply minimum threshold
                if sharpe < self.config.min_sharpe_for_weight:
                    sharpe = 0.0
                sharpe_values[sid] = sharpe
            
            total_sharpe = sum(sharpe_values.values())
            
            if total_sharpe == 0:
                # Fallback to equal weight
                num_strategies = len(self.base_strategies)
                return {sid: 1.0 / num_strategies for sid in self.base_strategies.keys()}
            
            # Normalize to sum to 1.0
            weights = {sid: sharpe / total_sharpe for sid, sharpe in sharpe_values.items()}
            
            # Update allocation weights
            for sid, weight in weights.items():
                if sid in self.allocations:
                    self.allocations[sid].weight = weight
            
            return weights
        
        elif self.config.aggregation_method == SignalAggregationMethod.CONFIDENCE:
            # Weight by allocation percentage (recent performance)
            weights = {
                sid: allocation.allocation_pct / 100.0
                for sid, allocation in self.allocations.items()
            }
            return weights
        
        else:
            raise ValueError(f"Unknown aggregation method: {self.config.aggregation_method}")
    
    def aggregate_signals(
        self,
        strategy_signals: Dict[str, bool],
        strategy_confidences: Optional[Dict[str, float]] = None
    ) -> Tuple[bool, float]:
        """
        Aggregate entry signals from multiple base strategies.
        
        Args:
            strategy_signals: Dict mapping strategy_id to entry signal (True/False)
            strategy_confidences: Optional dict mapping strategy_id to confidence (0.0 to 1.0)
        
        Returns:
            Tuple of (should_enter: bool, aggregate_confidence: float)
        """
        if not strategy_signals:
            return False, 0.0
        
        # Calculate signal weights
        weights = self.calculate_signal_weights()
        
        if self.config.aggregation_method == SignalAggregationMethod.VOTING:
            # Voting: Enter if N of M strategies signal entry
            num_signals = sum(1 for signal in strategy_signals.values() if signal)
            total_strategies = len(strategy_signals)
            vote_ratio = num_signals / total_strategies if total_strategies > 0 else 0.0
            
            should_enter = vote_ratio >= self.config.voting_threshold
            confidence = vote_ratio
            
            logger.debug(
                f"Voting aggregation: {num_signals}/{total_strategies} strategies signal entry "
                f"(threshold: {self.config.voting_threshold:.0%}, result: {should_enter})"
            )
            
            return should_enter, confidence
        
        elif self.config.aggregation_method == SignalAggregationMethod.WEIGHTED:
            # Weighted: Weight signals by strategy Sharpe ratio
            weighted_signal = 0.0
            total_weight = 0.0
            
            for sid, signal in strategy_signals.items():
                if sid in weights:
                    weight = weights[sid]
                    weighted_signal += weight * (1.0 if signal else 0.0)
                    total_weight += weight
            
            aggregate_confidence = weighted_signal / total_weight if total_weight > 0 else 0.0
            should_enter = aggregate_confidence >= 0.5  # Enter if weighted average > 50%
            
            logger.debug(
                f"Weighted aggregation: aggregate_confidence={aggregate_confidence:.2f}, "
                f"result: {should_enter}"
            )
            
            return should_enter, aggregate_confidence
        
        elif self.config.aggregation_method == SignalAggregationMethod.CONFIDENCE:
            # Confidence: Only enter if aggregate confidence > threshold
            if strategy_confidences is None:
                # Fallback to simple voting if no confidences provided
                strategy_confidences = {sid: 1.0 if signal else 0.0 
                                       for sid, signal in strategy_signals.items()}
            
            weighted_confidence = 0.0
            total_weight = 0.0
            
            for sid, confidence in strategy_confidences.items():
                if sid in weights and sid in strategy_signals:
                    weight = weights[sid]
                    # Only count confidence if strategy signals entry
                    if strategy_signals[sid]:
                        weighted_confidence += weight * confidence
                    total_weight += weight
            
            aggregate_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0
            should_enter = aggregate_confidence >= self.config.confidence_threshold
            
            logger.debug(
                f"Confidence aggregation: aggregate_confidence={aggregate_confidence:.2f}, "
                f"threshold={self.config.confidence_threshold:.2f}, result: {should_enter}"
            )
            
            return should_enter, aggregate_confidence
        
        else:
            raise ValueError(f"Unknown aggregation method: {self.config.aggregation_method}")
    
    def get_allocation_summary(self) -> Dict:
        """
        Get summary of current allocations.
        
        Returns:
            Dict with allocation details for each base strategy
        """
        summary = {
            "meta_strategy_id": self.id,
            "meta_strategy_name": self.name,
            "aggregation_method": self.config.aggregation_method.value,
            "last_rebalance": self.last_rebalance.isoformat() if self.last_rebalance else None,
            "rebalance_count": self.performance.rebalance_count,
            "base_strategies": []
        }
        
        for sid, allocation in self.allocations.items():
            strategy = self.base_strategies.get(sid)
            if strategy:
                summary["base_strategies"].append({
                    "strategy_id": sid,
                    "strategy_name": allocation.strategy_name,
                    "allocation_pct": allocation.allocation_pct,
                    "weight": allocation.weight,
                    "recent_sharpe": allocation.recent_sharpe,
                    "recent_return": allocation.recent_return,
                    "status": strategy.status.value if strategy.status else "unknown"
                })
        
        return summary
    
    def to_dict(self) -> Dict:
        """Convert meta-strategy to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "type": "meta_strategy",
            "base_strategy_ids": list(self.base_strategies.keys()),
            "config": {
                "aggregation_method": self.config.aggregation_method.value,
                "rebalance_frequency_days": self.config.rebalance_frequency_days,
                "min_strategies": self.config.min_strategies,
                "max_strategies": self.config.max_strategies,
            },
            "allocations": {
                sid: {
                    "allocation_pct": alloc.allocation_pct,
                    "weight": alloc.weight,
                    "recent_sharpe": alloc.recent_sharpe,
                    "recent_return": alloc.recent_return,
                }
                for sid, alloc in self.allocations.items()
            },
            "performance": {
                "total_return": self.performance.total_return,
                "sharpe_ratio": self.performance.sharpe_ratio,
                "max_drawdown": self.performance.max_drawdown,
                "win_rate": self.performance.win_rate,
                "total_trades": self.performance.total_trades,
                "avg_base_strategy_sharpe": self.performance.avg_base_strategy_sharpe,
                "diversification_benefit": self.performance.diversification_benefit,
                "rebalance_count": self.performance.rebalance_count,
            },
            "created_at": self.created_at.isoformat(),
            "last_rebalance": self.last_rebalance.isoformat() if self.last_rebalance else None,
        }
