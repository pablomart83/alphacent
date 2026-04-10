"""
Performance Degradation Monitoring System.

Detects when strategy performance degrades before major losses occur.
Implements early warning system with graduated response based on severity.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from src.models.database import Base
from src.models.dataclasses import Strategy, BacktestResults

logger = logging.getLogger(__name__)


@dataclass
class RollingMetrics:
    """Rolling performance metrics for a strategy."""
    sharpe_7d: float
    sharpe_14d: float
    sharpe_30d: float
    win_rate_7d: float
    win_rate_14d: float
    win_rate_30d: float
    max_drawdown_7d: float
    max_drawdown_14d: float
    max_drawdown_30d: float
    trade_count_7d: int
    trade_count_14d: int
    trade_count_30d: int
    calculated_at: datetime


@dataclass
class DegradationAlert:
    """Performance degradation alert."""
    strategy_id: str
    strategy_name: str
    severity: float  # 0.0 to 1.0
    degradation_type: str  # "sharpe", "win_rate", "drawdown", "combined"
    current_value: float
    baseline_value: float
    degradation_pct: float
    days_degraded: int
    recommended_action: str  # "reduce_size", "pause", "retire"
    details: str
    detected_at: datetime


class PerformanceDegradationHistoryORM(Base):
    """ORM model for storing performance degradation history."""
    __tablename__ = "performance_degradation_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False, index=True)
    strategy_name = Column(String, nullable=False)
    detected_at = Column(DateTime, nullable=False, index=True)
    
    # Degradation metrics
    severity = Column(Float, nullable=False)
    degradation_type = Column(String, nullable=False)
    current_value = Column(Float, nullable=False)
    baseline_value = Column(Float, nullable=False)
    degradation_pct = Column(Float, nullable=False)
    days_degraded = Column(Integer, nullable=False)
    
    # Rolling metrics
    sharpe_7d = Column(Float)
    sharpe_14d = Column(Float)
    sharpe_30d = Column(Float)
    win_rate_7d = Column(Float)
    win_rate_14d = Column(Float)
    win_rate_30d = Column(Float)
    max_drawdown_7d = Column(Float)
    max_drawdown_14d = Column(Float)
    max_drawdown_30d = Column(Float)
    
    # Response
    recommended_action = Column(String, nullable=False)
    action_taken = Column(String)
    details = Column(Text)


class PerformanceDegradationMonitor:
    """
    Monitors strategy performance for degradation and triggers graduated responses.
    
    Tracks rolling metrics and compares to backtest baseline to detect early
    warning signs of strategy failure.
    """
    
    def __init__(self, db):
        """
        Initialize performance degradation monitor.
        
        Args:
            db: Database instance for storing degradation history
        """
        self.db = db
        self.degradation_thresholds = {
            'sharpe_drop_pct': 0.50,  # 50% drop from baseline
            'sharpe_days': 14,  # Must persist for 14+ days
            'win_rate_drop_pct': 0.30,  # 30% drop from baseline
            'win_rate_min_trades': 20,  # Minimum trades for win rate check
            'drawdown_multiplier': 1.50,  # 50% worse than backtest max drawdown
        }
        
        # Severity thresholds for graduated response
        self.severity_thresholds = {
            'reduce_size': (0.3, 0.5),  # Severity 0.3-0.5
            'pause': (0.5, 0.7),  # Severity 0.5-0.7
            'retire': (0.7, 1.0),  # Severity 0.7+
        }
        
        logger.info("Performance degradation monitor initialized")
    
    def calculate_rolling_metrics(
        self,
        strategy: Strategy,
        trades_df: pd.DataFrame,
        equity_curve: pd.Series
    ) -> RollingMetrics:
        """
        Calculate rolling performance metrics for a strategy.
        
        Args:
            strategy: Strategy to analyze
            trades_df: DataFrame with trade history (columns: entry_date, exit_date, pnl, etc.)
            equity_curve: Series with daily equity values
            
        Returns:
            RollingMetrics with 7-day, 14-day, and 30-day metrics
        """
        now = datetime.now()
        
        # Calculate metrics for each window
        metrics_7d = self._calculate_window_metrics(trades_df, equity_curve, now, days=7)
        metrics_14d = self._calculate_window_metrics(trades_df, equity_curve, now, days=14)
        metrics_30d = self._calculate_window_metrics(trades_df, equity_curve, now, days=30)
        
        return RollingMetrics(
            sharpe_7d=metrics_7d['sharpe'],
            sharpe_14d=metrics_14d['sharpe'],
            sharpe_30d=metrics_30d['sharpe'],
            win_rate_7d=metrics_7d['win_rate'],
            win_rate_14d=metrics_14d['win_rate'],
            win_rate_30d=metrics_30d['win_rate'],
            max_drawdown_7d=metrics_7d['max_drawdown'],
            max_drawdown_14d=metrics_14d['max_drawdown'],
            max_drawdown_30d=metrics_30d['max_drawdown'],
            trade_count_7d=metrics_7d['trade_count'],
            trade_count_14d=metrics_14d['trade_count'],
            trade_count_30d=metrics_30d['trade_count'],
            calculated_at=now
        )
    
    def _calculate_window_metrics(
        self,
        trades_df: pd.DataFrame,
        equity_curve: pd.Series,
        end_date: datetime,
        days: int
    ) -> Dict:
        """Calculate metrics for a specific time window."""
        start_date = end_date - timedelta(days=days)
        
        # Filter trades in window
        if 'exit_date' in trades_df.columns:
            window_trades = trades_df[
                (trades_df['exit_date'] >= start_date) &
                (trades_df['exit_date'] <= end_date)
            ]
        else:
            # If no exit_date, use entry_date
            window_trades = trades_df[
                (trades_df['entry_date'] >= start_date) &
                (trades_df['entry_date'] <= end_date)
            ]
        
        trade_count = len(window_trades)
        
        if trade_count == 0:
            return {
                'sharpe': 0.0,
                'win_rate': 0.0,
                'max_drawdown': 0.0,
                'trade_count': 0
            }
        
        # Calculate win rate
        if 'pnl' in window_trades.columns:
            winning_trades = (window_trades['pnl'] > 0).sum()
            win_rate = winning_trades / trade_count if trade_count > 0 else 0.0
        else:
            win_rate = 0.0
        
        # Calculate Sharpe ratio from equity curve
        if equity_curve is not None and len(equity_curve) > 0:
            # Filter equity curve to window
            window_equity = equity_curve[
                (equity_curve.index >= start_date) &
                (equity_curve.index <= end_date)
            ]
            
            if len(window_equity) > 1:
                returns = window_equity.pct_change().dropna()
                if len(returns) > 0 and returns.std() > 0:
                    sharpe = (returns.mean() / returns.std()) * (252 ** 0.5)  # Annualized
                else:
                    sharpe = 0.0
                
                # Calculate max drawdown
                cumulative = (1 + returns).cumprod()
                running_max = cumulative.expanding().max()
                drawdown = (cumulative - running_max) / running_max
                max_drawdown = drawdown.min()
            else:
                sharpe = 0.0
                max_drawdown = 0.0
        else:
            sharpe = 0.0
            max_drawdown = 0.0
        
        return {
            'sharpe': sharpe,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'trade_count': trade_count
        }
    
    def detect_degradation(
        self,
        strategy: Strategy,
        rolling_metrics: RollingMetrics,
        baseline_results: BacktestResults
    ) -> Optional[DegradationAlert]:
        """
        Detect performance degradation by comparing rolling metrics to baseline.
        
        Args:
            strategy: Strategy to check
            rolling_metrics: Current rolling performance metrics
            baseline_results: Backtest results to use as baseline
            
        Returns:
            DegradationAlert if degradation detected, None otherwise
        """
        degradations = []
        
        # Check Sharpe ratio degradation (14-day window)
        if baseline_results.sharpe_ratio > 0:
            sharpe_drop_pct = (baseline_results.sharpe_ratio - rolling_metrics.sharpe_14d) / baseline_results.sharpe_ratio
            
            if sharpe_drop_pct > self.degradation_thresholds['sharpe_drop_pct']:
                degradations.append({
                    'type': 'sharpe',
                    'current': rolling_metrics.sharpe_14d,
                    'baseline': baseline_results.sharpe_ratio,
                    'drop_pct': sharpe_drop_pct,
                    'severity': min(sharpe_drop_pct, 1.0),
                    'days': 14
                })
        
        # Check win rate degradation (14-day window, minimum 20 trades)
        if rolling_metrics.trade_count_14d >= self.degradation_thresholds['win_rate_min_trades']:
            if baseline_results.win_rate > 0:
                win_rate_drop_pct = (baseline_results.win_rate - rolling_metrics.win_rate_14d) / baseline_results.win_rate
                
                if win_rate_drop_pct > self.degradation_thresholds['win_rate_drop_pct']:
                    degradations.append({
                        'type': 'win_rate',
                        'current': rolling_metrics.win_rate_14d,
                        'baseline': baseline_results.win_rate,
                        'drop_pct': win_rate_drop_pct,
                        'severity': min(win_rate_drop_pct * 1.5, 1.0),  # Scale up severity
                        'days': 14
                    })
        
        # Check drawdown degradation (30-day window)
        if baseline_results.max_drawdown < 0:  # Drawdown is negative
            drawdown_ratio = rolling_metrics.max_drawdown_30d / baseline_results.max_drawdown
            
            if drawdown_ratio > self.degradation_thresholds['drawdown_multiplier']:
                degradations.append({
                    'type': 'drawdown',
                    'current': rolling_metrics.max_drawdown_30d,
                    'baseline': baseline_results.max_drawdown,
                    'drop_pct': (drawdown_ratio - 1.0),
                    'severity': min((drawdown_ratio - 1.0), 1.0),
                    'days': 30
                })
        
        if not degradations:
            return None
        
        # Find most severe degradation
        worst_degradation = max(degradations, key=lambda x: x['severity'])
        
        # Calculate combined severity (average of all degradations)
        combined_severity = sum(d['severity'] for d in degradations) / len(degradations)
        
        # Determine recommended action based on severity
        recommended_action = self._get_recommended_action(combined_severity)
        
        # Build details string
        details_parts = []
        for deg in degradations:
            details_parts.append(
                f"{deg['type'].upper()}: {deg['current']:.3f} vs baseline {deg['baseline']:.3f} "
                f"({deg['drop_pct']*100:.1f}% drop over {deg['days']} days)"
            )
        details = " | ".join(details_parts)
        
        alert = DegradationAlert(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            severity=combined_severity,
            degradation_type=worst_degradation['type'],
            current_value=worst_degradation['current'],
            baseline_value=worst_degradation['baseline'],
            degradation_pct=worst_degradation['drop_pct'] * 100,
            days_degraded=worst_degradation['days'],
            recommended_action=recommended_action,
            details=details,
            detected_at=datetime.now()
        )
        
        logger.warning(
            f"Performance degradation detected for {strategy.name}: "
            f"severity={combined_severity:.2f}, action={recommended_action}"
        )
        logger.warning(f"  Details: {details}")
        
        return alert
    
    def _get_recommended_action(self, severity: float) -> str:
        """Determine recommended action based on severity score."""
        if severity >= self.severity_thresholds['retire'][0]:
            return 'retire'
        elif severity >= self.severity_thresholds['pause'][0]:
            return 'pause'
        elif severity >= self.severity_thresholds['reduce_size'][0]:
            return 'reduce_size'
        else:
            return 'monitor'
    
    def store_degradation_event(
        self,
        alert: DegradationAlert,
        rolling_metrics: RollingMetrics,
        action_taken: Optional[str] = None
    ) -> None:
        """
        Store degradation event in database for historical tracking.
        
        Args:
            alert: Degradation alert to store
            rolling_metrics: Rolling metrics at time of detection
            action_taken: Action that was taken in response (if any)
        """
        try:
            with self.db.get_session() as session:
                event = PerformanceDegradationHistoryORM(
                    strategy_id=alert.strategy_id,
                    strategy_name=alert.strategy_name,
                    detected_at=alert.detected_at,
                    severity=alert.severity,
                    degradation_type=alert.degradation_type,
                    current_value=alert.current_value,
                    baseline_value=alert.baseline_value,
                    degradation_pct=alert.degradation_pct,
                    days_degraded=alert.days_degraded,
                    sharpe_7d=rolling_metrics.sharpe_7d,
                    sharpe_14d=rolling_metrics.sharpe_14d,
                    sharpe_30d=rolling_metrics.sharpe_30d,
                    win_rate_7d=rolling_metrics.win_rate_7d,
                    win_rate_14d=rolling_metrics.win_rate_14d,
                    win_rate_30d=rolling_metrics.win_rate_30d,
                    max_drawdown_7d=rolling_metrics.max_drawdown_7d,
                    max_drawdown_14d=rolling_metrics.max_drawdown_14d,
                    max_drawdown_30d=rolling_metrics.max_drawdown_30d,
                    recommended_action=alert.recommended_action,
                    action_taken=action_taken,
                    details=alert.details
                )
                session.add(event)
                session.commit()
                
                logger.info(f"Stored degradation event for {alert.strategy_name}")
        except Exception as e:
            logger.error(f"Failed to store degradation event: {e}")
    
    def get_degradation_history(
        self,
        strategy_id: str,
        days: int = 90
    ) -> List[Dict]:
        """
        Get degradation history for a strategy.
        
        Args:
            strategy_id: Strategy ID
            days: Number of days of history to retrieve
            
        Returns:
            List of degradation events
        """
        try:
            with self.db.get_session() as session:
                cutoff_date = datetime.now() - timedelta(days=days)
                
                events = session.query(PerformanceDegradationHistoryORM).filter(
                    PerformanceDegradationHistoryORM.strategy_id == strategy_id,
                    PerformanceDegradationHistoryORM.detected_at >= cutoff_date
                ).order_by(PerformanceDegradationHistoryORM.detected_at.desc()).all()
                
                return [
                    {
                        'detected_at': event.detected_at,
                        'severity': event.severity,
                        'degradation_type': event.degradation_type,
                        'current_value': event.current_value,
                        'baseline_value': event.baseline_value,
                        'degradation_pct': event.degradation_pct,
                        'recommended_action': event.recommended_action,
                        'action_taken': event.action_taken,
                        'details': event.details
                    }
                    for event in events
                ]
        except Exception as e:
            logger.error(f"Failed to get degradation history: {e}")
            return []
