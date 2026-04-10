"""Strategy performance tracking for learning from historical results."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from src.models.database import get_database
from src.models.orm import Base
from sqlalchemy import Column, Integer, String, Float, DateTime

logger = logging.getLogger(__name__)


class StrategyPerformanceHistoryORM(Base):
    """Strategy performance history ORM model."""
    __tablename__ = "strategy_performance_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_type = Column(String, nullable=False, index=True)  # mean_reversion, momentum, breakout
    market_regime = Column(String, nullable=False, index=True)  # trending_up, trending_down, ranging
    sharpe_ratio = Column(Float, nullable=False)
    total_return = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    backtest_date = Column(DateTime, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    
    def to_dict(self) -> Dict:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_type": self.strategy_type,
            "market_regime": self.market_regime,
            "sharpe_ratio": self.sharpe_ratio,
            "total_return": self.total_return,
            "win_rate": self.win_rate,
            "backtest_date": self.backtest_date.isoformat() if self.backtest_date else None,
            "symbol": self.symbol
        }


class StrategyPerformanceTracker:
    """Tracks strategy performance history to learn what works."""
    
    def __init__(self, db_path: str = "alphacent.db"):
        """Initialize performance tracker.
        
        Args:
            db_path: Path to database file
        """
        # Create database instance directly (don't use singleton get_database)
        from src.models.database import Database
        self.db = Database(db_path)
        self.db.initialize()
        self._ensure_table_exists()
        logger.info(f"StrategyPerformanceTracker initialized with database: {db_path}")
    
    def _ensure_table_exists(self) -> None:
        """Ensure the performance history table exists."""
        try:
            # Create table if it doesn't exist
            Base.metadata.create_all(bind=self.db.engine, tables=[StrategyPerformanceHistoryORM.__table__])
            logger.info("Strategy performance history table ready")
        except Exception as e:
            logger.error(f"Error ensuring table exists: {e}")
    
    def track_performance(
        self,
        strategy_type: str,
        market_regime: str,
        sharpe_ratio: float,
        total_return: float,
        win_rate: float,
        symbol: str,
        backtest_date: Optional[datetime] = None
    ) -> None:
        """Track a strategy backtest result.
        
        Args:
            strategy_type: Type of strategy (mean_reversion, momentum, breakout, etc.)
            market_regime: Market regime at backtest time (trending_up, trending_down, ranging)
            sharpe_ratio: Sharpe ratio from backtest
            total_return: Total return from backtest
            win_rate: Win rate from backtest
            symbol: Symbol backtested
            backtest_date: Date of backtest (defaults to now)
        """
        session = self.db.get_session()
        try:
            if backtest_date is None:
                backtest_date = datetime.now()
            
            record = StrategyPerformanceHistoryORM(
                strategy_type=strategy_type,
                market_regime=market_regime,
                sharpe_ratio=sharpe_ratio,
                total_return=total_return,
                win_rate=win_rate,
                backtest_date=backtest_date,
                symbol=symbol
            )
            
            session.add(record)
            session.commit()
            
            logger.info(
                f"Tracked performance: {strategy_type} in {market_regime} regime - "
                f"Sharpe: {sharpe_ratio:.2f}, Return: {total_return:.2%}, Win Rate: {win_rate:.2%}"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Error tracking performance: {e}")
        finally:
            session.close()
    
    def get_recent_performance(
        self,
        days: int = 30,
        market_regime: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """Get recent strategy performance statistics.
        
        Args:
            days: Number of days to look back (default 30)
            market_regime: Optional filter by market regime
            
        Returns:
            Dictionary mapping strategy_type to performance metrics:
            {
                "mean_reversion": {
                    "avg_sharpe": 1.2,
                    "success_rate": 0.6,
                    "count": 10
                },
                "momentum": {...},
                ...
            }
        """
        session = self.db.get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Build query
            query = session.query(
                StrategyPerformanceHistoryORM.strategy_type,
                func.avg(StrategyPerformanceHistoryORM.sharpe_ratio).label('avg_sharpe'),
                func.count(StrategyPerformanceHistoryORM.id).label('count'),
                func.sum(
                    case(
                        (StrategyPerformanceHistoryORM.sharpe_ratio > 0, 1),
                        else_=0
                    )
                ).label('success_count')
            ).filter(
                StrategyPerformanceHistoryORM.backtest_date >= cutoff_date
            )
            
            # Add regime filter if specified
            if market_regime:
                query = query.filter(
                    StrategyPerformanceHistoryORM.market_regime == market_regime
                )
            
            # Group by strategy type
            query = query.group_by(StrategyPerformanceHistoryORM.strategy_type)
            
            results = query.all()
            
            # Format results
            performance = {}
            for row in results:
                strategy_type = row.strategy_type
                avg_sharpe = float(row.avg_sharpe) if row.avg_sharpe else 0.0
                count = int(row.count)
                success_count = int(row.success_count) if row.success_count else 0
                success_rate = success_count / count if count > 0 else 0.0
                
                performance[strategy_type] = {
                    "avg_sharpe": avg_sharpe,
                    "success_rate": success_rate,
                    "count": count
                }
            
            logger.info(
                f"Retrieved recent performance for {len(performance)} strategy types "
                f"(last {days} days{f', regime={market_regime}' if market_regime else ''})"
            )
            
            return performance
            
        except Exception as e:
            logger.error(f"Error getting recent performance: {e}")
            return {}
        finally:
            session.close()
    
    def get_performance_by_regime(
        self,
        days: int = 30
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Get performance statistics grouped by market regime.
        
        Args:
            days: Number of days to look back (default 30)
            
        Returns:
            Dictionary mapping regime -> strategy_type -> metrics:
            {
                "trending_up": {
                    "momentum": {"avg_sharpe": 1.5, "success_rate": 0.7, "count": 5},
                    ...
                },
                "ranging": {...},
                ...
            }
        """
        session = self.db.get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            query = session.query(
                StrategyPerformanceHistoryORM.market_regime,
                StrategyPerformanceHistoryORM.strategy_type,
                func.avg(StrategyPerformanceHistoryORM.sharpe_ratio).label('avg_sharpe'),
                func.count(StrategyPerformanceHistoryORM.id).label('count'),
                func.sum(
                    case(
                        (StrategyPerformanceHistoryORM.sharpe_ratio > 0, 1),
                        else_=0
                    )
                ).label('success_count')
            ).filter(
                StrategyPerformanceHistoryORM.backtest_date >= cutoff_date
            ).group_by(
                StrategyPerformanceHistoryORM.market_regime,
                StrategyPerformanceHistoryORM.strategy_type
            )
            
            results = query.all()
            
            # Format results
            performance_by_regime = {}
            for row in results:
                regime = row.market_regime
                strategy_type = row.strategy_type
                avg_sharpe = float(row.avg_sharpe) if row.avg_sharpe else 0.0
                count = int(row.count)
                success_count = int(row.success_count) if row.success_count else 0
                success_rate = success_count / count if count > 0 else 0.0
                
                if regime not in performance_by_regime:
                    performance_by_regime[regime] = {}
                
                performance_by_regime[regime][strategy_type] = {
                    "avg_sharpe": avg_sharpe,
                    "success_rate": success_rate,
                    "count": count
                }
            
            logger.info(
                f"Retrieved performance by regime for last {days} days: "
                f"{len(performance_by_regime)} regimes"
            )
            
            return performance_by_regime
            
        except Exception as e:
            logger.error(f"Error getting performance by regime: {e}")
            return {}
        finally:
            session.close()
    
    def clear_old_records(self, days: int = 90) -> int:
        """Clear performance records older than specified days.
        
        Args:
            days: Keep records from last N days
            
        Returns:
            Number of records deleted
        """
        session = self.db.get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            deleted = session.query(StrategyPerformanceHistoryORM).filter(
                StrategyPerformanceHistoryORM.backtest_date < cutoff_date
            ).delete()
            
            session.commit()
            logger.info(f"Cleared {deleted} old performance records (older than {days} days)")
            return deleted
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error clearing old records: {e}")
            return 0
        finally:
            session.close()
