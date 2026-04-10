"""
Deep Correlation Analysis for Strategy Portfolio.

Implements multi-dimensional correlation analysis to identify hidden relationships
between strategies beyond simple returns correlation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base
from src.models.dataclasses import Strategy

logger = logging.getLogger(__name__)


class StrategyCorrelationHistoryORM(Base):
    """ORM model for storing strategy correlation history."""
    
    __tablename__ = "strategy_correlation_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id_1 = Column(String, nullable=False, index=True)
    strategy_id_2 = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    
    # Multi-dimensional correlations
    returns_correlation = Column(Float, nullable=False)
    signal_correlation = Column(Float, nullable=False)
    drawdown_correlation = Column(Float, nullable=False)
    volatility_correlation = Column(Float, nullable=False)
    
    # Composite score
    composite_correlation = Column(Float, nullable=False)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "strategy_id_1": self.strategy_id_1,
            "strategy_id_2": self.strategy_id_2,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "returns_correlation": self.returns_correlation,
            "signal_correlation": self.signal_correlation,
            "drawdown_correlation": self.drawdown_correlation,
            "volatility_correlation": self.volatility_correlation,
            "composite_correlation": self.composite_correlation,
        }


class CorrelationAnalyzer:
    """
    Analyzes multi-dimensional correlations between strategies.
    
    Tracks:
    - Returns correlation: Do strategies make/lose money together?
    - Signal correlation: Do strategies enter/exit at same times?
    - Drawdown correlation: Do strategies lose money together?
    - Volatility correlation: Do strategies have similar volatility patterns?
    """
    
    def __init__(self, db_path: str = "alphacent.db"):
        """
        Initialize Correlation Analyzer.
        
        Args:
            db_path: Path to SQLite database (ignored if DATABASE_URL is set)
        """
        self.db_path = db_path
        from src.models.database import _get_database_url
        self.engine = create_engine(_get_database_url(db_path))
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table_exists()
        logger.info(f"CorrelationAnalyzer initialized")
    
    def _ensure_table_exists(self) -> None:
        """Create correlation history table if it doesn't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Correlation history table ensured")
    
    def calculate_multi_dimensional_correlation(
        self,
        strategy1: Strategy,
        strategy2: Strategy,
        returns_data: Dict[str, pd.Series],
        signals_data: Dict[str, pd.Series],
    ) -> Dict[str, float]:
        """
        Calculate multi-dimensional correlation between two strategies.
        
        Args:
            strategy1: First strategy
            strategy2: Second strategy
            returns_data: Dict mapping strategy_id -> daily returns Series
            signals_data: Dict mapping strategy_id -> daily signals Series (1=long, 0=flat, -1=short)
            
        Returns:
            Dict containing:
            - returns_correlation: Correlation of daily returns
            - signal_correlation: Correlation of entry/exit signals
            - drawdown_correlation: Correlation during drawdown periods
            - volatility_correlation: Correlation of volatility patterns
            - composite_correlation: Weighted average of all correlations
        """
        s1_id = strategy1.id
        s2_id = strategy2.id
        
        # 1. Returns Correlation
        returns_corr = self._calculate_returns_correlation(
            returns_data.get(s1_id),
            returns_data.get(s2_id)
        )
        
        # 2. Signal Correlation
        signal_corr = self._calculate_signal_correlation(
            signals_data.get(s1_id),
            signals_data.get(s2_id)
        )
        
        # 3. Drawdown Correlation
        drawdown_corr = self._calculate_drawdown_correlation(
            returns_data.get(s1_id),
            returns_data.get(s2_id)
        )
        
        # 4. Volatility Correlation
        volatility_corr = self._calculate_volatility_correlation(
            returns_data.get(s1_id),
            returns_data.get(s2_id)
        )
        
        # 5. Composite Correlation (weighted average)
        # Returns correlation is most important (40%), others 20% each
        composite_corr = (
            0.4 * returns_corr +
            0.2 * signal_corr +
            0.2 * drawdown_corr +
            0.2 * volatility_corr
        )
        
        result = {
            "returns_correlation": returns_corr,
            "signal_correlation": signal_corr,
            "drawdown_correlation": drawdown_corr,
            "volatility_correlation": volatility_corr,
            "composite_correlation": composite_corr,
        }
        
        logger.info(
            f"Correlation between {strategy1.name} and {strategy2.name}: "
            f"Returns={returns_corr:.3f}, Signal={signal_corr:.3f}, "
            f"Drawdown={drawdown_corr:.3f}, Volatility={volatility_corr:.3f}, "
            f"Composite={composite_corr:.3f}"
        )
        
        return result
    
    def _calculate_returns_correlation(
        self,
        returns1: pd.Series,
        returns2: pd.Series
    ) -> float:
        """Calculate correlation of daily returns."""
        if returns1 is None or returns2 is None:
            return 0.0
        
        if len(returns1) < 2 or len(returns2) < 2:
            return 0.0
        
        # Align series by index
        aligned = pd.DataFrame({"r1": returns1, "r2": returns2}).dropna()
        
        if len(aligned) < 2:
            return 0.0
        
        corr = aligned["r1"].corr(aligned["r2"])
        return corr if not np.isnan(corr) else 0.0
    
    def _calculate_signal_correlation(
        self,
        signals1: pd.Series,
        signals2: pd.Series
    ) -> float:
        """
        Calculate correlation of entry/exit signals.
        
        Measures if strategies enter/exit at the same times.
        """
        if signals1 is None or signals2 is None:
            return 0.0
        
        if len(signals1) < 2 or len(signals2) < 2:
            return 0.0
        
        # Align series by index
        aligned = pd.DataFrame({"s1": signals1, "s2": signals2}).dropna()
        
        if len(aligned) < 2:
            return 0.0
        
        # Calculate correlation of signal values
        corr = aligned["s1"].corr(aligned["s2"])
        return corr if not np.isnan(corr) else 0.0
    
    def _calculate_drawdown_correlation(
        self,
        returns1: pd.Series,
        returns2: pd.Series
    ) -> float:
        """
        Calculate correlation during drawdown periods.
        
        Measures if strategies lose money together.
        """
        if returns1 is None or returns2 is None:
            return 0.0
        
        if len(returns1) < 2 or len(returns2) < 2:
            return 0.0
        
        # Align series by index
        aligned = pd.DataFrame({"r1": returns1, "r2": returns2}).dropna()
        
        if len(aligned) < 2:
            return 0.0
        
        # Calculate cumulative returns
        cum_returns1 = (1 + aligned["r1"]).cumprod()
        cum_returns2 = (1 + aligned["r2"]).cumprod()
        
        # Calculate drawdowns
        running_max1 = cum_returns1.expanding().max()
        running_max2 = cum_returns2.expanding().max()
        
        drawdown1 = (cum_returns1 - running_max1) / running_max1
        drawdown2 = (cum_returns2 - running_max2) / running_max2
        
        # Only consider periods where at least one strategy is in drawdown
        in_drawdown = (drawdown1 < 0) | (drawdown2 < 0)
        
        if in_drawdown.sum() < 2:
            return 0.0
        
        # Calculate correlation during drawdown periods
        dd_aligned = pd.DataFrame({
            "dd1": drawdown1[in_drawdown],
            "dd2": drawdown2[in_drawdown]
        }).dropna()
        
        if len(dd_aligned) < 2:
            return 0.0
        
        corr = dd_aligned["dd1"].corr(dd_aligned["dd2"])
        return corr if not np.isnan(corr) else 0.0
    
    def _calculate_volatility_correlation(
        self,
        returns1: pd.Series,
        returns2: pd.Series
    ) -> float:
        """
        Calculate correlation of volatility patterns.
        
        Measures if strategies have similar volatility over time.
        """
        if returns1 is None or returns2 is None:
            return 0.0
        
        if len(returns1) < 10 or len(returns2) < 10:
            return 0.0
        
        # Align series by index
        aligned = pd.DataFrame({"r1": returns1, "r2": returns2}).dropna()
        
        if len(aligned) < 10:
            return 0.0
        
        # Calculate rolling volatility (5-day window)
        vol1 = aligned["r1"].rolling(window=5, min_periods=3).std()
        vol2 = aligned["r2"].rolling(window=5, min_periods=3).std()
        
        # Drop NaN values
        vol_aligned = pd.DataFrame({"v1": vol1, "v2": vol2}).dropna()
        
        if len(vol_aligned) < 2:
            return 0.0
        
        corr = vol_aligned["v1"].corr(vol_aligned["v2"])
        return corr if not np.isnan(corr) else 0.0
    
    def store_correlation(
        self,
        strategy1: Strategy,
        strategy2: Strategy,
        correlations: Dict[str, float]
    ) -> None:
        """
        Store correlation data in database.
        
        Args:
            strategy1: First strategy
            strategy2: Second strategy
            correlations: Dict with correlation values
        """
        session = self.Session()
        try:
            record = StrategyCorrelationHistoryORM(
                strategy_id_1=strategy1.id,
                strategy_id_2=strategy2.id,
                timestamp=datetime.now(),
                returns_correlation=correlations["returns_correlation"],
                signal_correlation=correlations["signal_correlation"],
                drawdown_correlation=correlations["drawdown_correlation"],
                volatility_correlation=correlations["volatility_correlation"],
                composite_correlation=correlations["composite_correlation"],
            )
            session.add(record)
            session.commit()
            logger.info(
                f"Stored correlation between {strategy1.name} and {strategy2.name}"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store correlation: {e}")
        finally:
            session.close()
    
    def get_correlation_history(
        self,
        strategy1_id: str,
        strategy2_id: str,
        days: int = 30
    ) -> List[Dict]:
        """
        Get correlation history between two strategies.
        
        Args:
            strategy1_id: First strategy ID
            strategy2_id: Second strategy ID
            days: Number of days to look back
            
        Returns:
            List of correlation records
        """
        session = self.Session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Query both directions (s1-s2 and s2-s1)
            records = session.query(StrategyCorrelationHistoryORM).filter(
                (
                    (StrategyCorrelationHistoryORM.strategy_id_1 == strategy1_id) &
                    (StrategyCorrelationHistoryORM.strategy_id_2 == strategy2_id)
                ) | (
                    (StrategyCorrelationHistoryORM.strategy_id_1 == strategy2_id) &
                    (StrategyCorrelationHistoryORM.strategy_id_2 == strategy1_id)
                ),
                StrategyCorrelationHistoryORM.timestamp >= cutoff_date
            ).order_by(StrategyCorrelationHistoryORM.timestamp.desc()).all()
            
            return [r.to_dict() for r in records]
        finally:
            session.close()
    
    def detect_correlation_regime_change(
        self,
        strategy1_id: str,
        strategy2_id: str,
        threshold: float = 0.4
    ) -> Tuple[bool, Dict]:
        """
        Detect if correlation has changed significantly.
        
        Args:
            strategy1_id: First strategy ID
            strategy2_id: Second strategy ID
            threshold: Minimum change to trigger alert (default 0.4)
            
        Returns:
            Tuple of (changed, details_dict)
        """
        history = self.get_correlation_history(strategy1_id, strategy2_id, days=30)
        
        if len(history) < 2:
            return False, {}
        
        # Get most recent and oldest correlation
        recent = history[0]
        old = history[-1]
        
        # Calculate change in composite correlation
        change = abs(recent["composite_correlation"] - old["composite_correlation"])
        
        if change >= threshold:
            details = {
                "old_correlation": old["composite_correlation"],
                "new_correlation": recent["composite_correlation"],
                "change": change,
                "old_timestamp": old["timestamp"],
                "new_timestamp": recent["timestamp"],
                "alert": True,
            }
            logger.warning(
                f"Correlation regime change detected: "
                f"{old['composite_correlation']:.3f} -> {recent['composite_correlation']:.3f} "
                f"(change: {change:.3f})"
            )
            return True, details
        
        return False, {}
    
    def calculate_portfolio_diversification_score(
        self,
        strategies: List[Strategy],
        returns_data: Dict[str, pd.Series],
        signals_data: Dict[str, pd.Series]
    ) -> Dict:
        """
        Calculate portfolio diversification score based on multi-dimensional correlations.
        
        Args:
            strategies: List of strategies in portfolio
            returns_data: Dict mapping strategy_id -> daily returns
            signals_data: Dict mapping strategy_id -> daily signals
            
        Returns:
            Dict containing:
            - diversification_score: Overall score (0-1, higher is better)
            - avg_returns_correlation: Average returns correlation
            - avg_signal_correlation: Average signal correlation
            - avg_drawdown_correlation: Average drawdown correlation
            - avg_volatility_correlation: Average volatility correlation
            - max_correlation: Maximum pairwise correlation
            - correlation_matrix: Full correlation matrix
        """
        if len(strategies) < 2:
            return {
                "diversification_score": 1.0,
                "avg_returns_correlation": 0.0,
                "avg_signal_correlation": 0.0,
                "avg_drawdown_correlation": 0.0,
                "avg_volatility_correlation": 0.0,
                "max_correlation": 0.0,
                "correlation_matrix": {},
            }
        
        # Calculate all pairwise correlations
        correlations = []
        correlation_matrix = {}
        
        for i, s1 in enumerate(strategies):
            correlation_matrix[s1.id] = {}
            for j, s2 in enumerate(strategies):
                if i < j:
                    corr = self.calculate_multi_dimensional_correlation(
                        s1, s2, returns_data, signals_data
                    )
                    correlations.append(corr)
                    correlation_matrix[s1.id][s2.id] = corr["composite_correlation"]
                    
                    # Store in database
                    self.store_correlation(s1, s2, corr)
                elif i == j:
                    correlation_matrix[s1.id][s2.id] = 1.0
                else:
                    # Use symmetric value
                    correlation_matrix[s1.id][s2.id] = correlation_matrix[s2.id][s1.id]
        
        if not correlations:
            return {
                "diversification_score": 1.0,
                "avg_returns_correlation": 0.0,
                "avg_signal_correlation": 0.0,
                "avg_drawdown_correlation": 0.0,
                "avg_volatility_correlation": 0.0,
                "max_correlation": 0.0,
                "correlation_matrix": correlation_matrix,
            }
        
        # Calculate averages
        avg_returns_corr = np.mean([c["returns_correlation"] for c in correlations])
        avg_signal_corr = np.mean([c["signal_correlation"] for c in correlations])
        avg_drawdown_corr = np.mean([c["drawdown_correlation"] for c in correlations])
        avg_volatility_corr = np.mean([c["volatility_correlation"] for c in correlations])
        avg_composite_corr = np.mean([c["composite_correlation"] for c in correlations])
        
        # Find maximum correlation
        max_corr = max([c["composite_correlation"] for c in correlations])
        
        # Diversification score = 1 - average composite correlation
        diversification_score = 1.0 - avg_composite_corr
        diversification_score = max(0.0, min(1.0, diversification_score))
        
        result = {
            "diversification_score": diversification_score,
            "avg_returns_correlation": avg_returns_corr,
            "avg_signal_correlation": avg_signal_corr,
            "avg_drawdown_correlation": avg_drawdown_corr,
            "avg_volatility_correlation": avg_volatility_corr,
            "max_correlation": max_corr,
            "correlation_matrix": correlation_matrix,
        }
        
        logger.info(
            f"Portfolio diversification score: {diversification_score:.3f} "
            f"(avg_corr={avg_composite_corr:.3f}, max_corr={max_corr:.3f})"
        )
        
        return result
